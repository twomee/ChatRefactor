// Package ws provides the WebSocket connection manager that tracks all active
// connections across rooms and the lobby. It is the central coordination point
// for broadcasting messages and delivering private messages.
//
// Design decision: a single in-process manager with sync.RWMutex is the right
// choice while the service runs as a single instance. When we horizontally
// scale, Redis Pub/Sub will sit in front of this manager so that a broadcast
// on one instance fans out to connections on all instances.
package ws

import (
	"encoding/json"
	"sync"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// UserInfo holds identity data attached to a WebSocket connection.
type UserInfo struct {
	UserID   int
	Username string
}

// Manager tracks all WebSocket connections, maps them to users and rooms,
// and provides thread-safe broadcast and personal delivery methods.
type Manager struct {
	mu sync.RWMutex
	// rooms maps room ID -> set of connections in that room.
	rooms map[int]map[*websocket.Conn]bool
	// connUser maps a connection to its user info.
	connUser map[*websocket.Conn]UserInfo
	// userConns maps user ID -> set of connections (a user can have multiple tabs).
	userConns map[int]map[*websocket.Conn]bool
	// lobbyConns maps lobby connections to their user info.
	lobbyConns map[*websocket.Conn]UserInfo
	// connMu maps each connection to a write mutex. gorilla/websocket does not
	// support concurrent writes, so every write to a connection must be
	// serialized through its mutex.
	connMu map[*websocket.Conn]*sync.Mutex
	// roomJoinOrder tracks the order in which users joined a room (by userID).
	// Used for admin succession — when an admin leaves, the next user in join
	// order is promoted.
	roomJoinOrder map[int][]int

	logger *zap.Logger
}

// NewManager creates an initialised connection manager.
func NewManager(logger *zap.Logger) *Manager {
	return &Manager{
		rooms:         make(map[int]map[*websocket.Conn]bool),
		connUser:      make(map[*websocket.Conn]UserInfo),
		userConns:     make(map[int]map[*websocket.Conn]bool),
		lobbyConns:    make(map[*websocket.Conn]UserInfo),
		connMu:        make(map[*websocket.Conn]*sync.Mutex),
		roomJoinOrder: make(map[int][]int),
		logger:        logger,
	}
}

// safeWrite sends data to a connection while holding its per-connection write
// mutex. This prevents concurrent writes which would violate gorilla/websocket
// thread safety requirements.
func (m *Manager) safeWrite(conn *websocket.Conn, data []byte) error {
	m.mu.RLock()
	mu, ok := m.connMu[conn]
	m.mu.RUnlock()
	if !ok {
		// Connection already removed; treat as write failure.
		return websocket.ErrCloseSent
	}
	mu.Lock()
	defer mu.Unlock()
	return conn.WriteMessage(websocket.TextMessage, data)
}

// ---------- Room connections ----------

// ConnectRoom registers a connection in a room.
func (m *Manager) ConnectRoom(roomID int, conn *websocket.Conn, user UserInfo) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.rooms[roomID] == nil {
		m.rooms[roomID] = make(map[*websocket.Conn]bool)
	}
	m.rooms[roomID][conn] = true
	m.connUser[conn] = user
	m.connMu[conn] = &sync.Mutex{}

	if m.userConns[user.UserID] == nil {
		m.userConns[user.UserID] = make(map[*websocket.Conn]bool)
	}
	m.userConns[user.UserID][conn] = true

	// Track join order for admin succession. Only add if user not already
	// in the join order list (avoids duplicates from multiple tabs).
	found := false
	for _, uid := range m.roomJoinOrder[roomID] {
		if uid == user.UserID {
			found = true
			break
		}
	}
	if !found {
		m.roomJoinOrder[roomID] = append(m.roomJoinOrder[roomID], user.UserID)
	}

	m.logger.Info("ws_room_connect",
		zap.Int("room_id", roomID),
		zap.Int("user_id", user.UserID),
		zap.String("username", user.Username),
	)
}

// DisconnectRoom removes a connection from its room and cleans up maps.
func (m *Manager) DisconnectRoom(roomID int, conn *websocket.Conn) {
	m.mu.Lock()
	defer m.mu.Unlock()

	user, ok := m.connUser[conn]
	if !ok {
		return
	}

	delete(m.rooms[roomID], conn)

	delete(m.connUser, conn)
	delete(m.connMu, conn)

	delete(m.userConns[user.UserID], conn)
	if len(m.userConns[user.UserID]) == 0 {
		delete(m.userConns, user.UserID)
	}

	// Check if the user has any remaining connections in this room.
	hasOtherConns := false
	for c := range m.rooms[roomID] {
		if u, ok2 := m.connUser[c]; ok2 && u.UserID == user.UserID {
			hasOtherConns = true
			break
		}
	}

	// Remove from join order if no more connections in this room.
	if !hasOtherConns {
		order := m.roomJoinOrder[roomID]
		for i, uid := range order {
			if uid == user.UserID {
				m.roomJoinOrder[roomID] = append(order[:i], order[i+1:]...)
				break
			}
		}
	}

	if len(m.rooms[roomID]) == 0 {
		delete(m.rooms, roomID)
		delete(m.roomJoinOrder, roomID)
	}

	m.logger.Info("ws_room_disconnect",
		zap.Int("room_id", roomID),
		zap.Int("user_id", user.UserID),
	)
}

// BroadcastRoom sends a JSON message to every connection in a room.
// Connections that fail to write are silently removed.
func (m *Manager) BroadcastRoom(roomID int, msg interface{}) {
	data, err := json.Marshal(msg)
	if err != nil {
		m.logger.Error("broadcast_marshal_error", zap.Error(err))
		return
	}

	m.mu.RLock()
	conns := make([]*websocket.Conn, 0, len(m.rooms[roomID]))
	for c := range m.rooms[roomID] {
		conns = append(conns, c)
	}
	m.mu.RUnlock()

	var failed []*websocket.Conn
	for _, c := range conns {
		if err := m.safeWrite(c, data); err != nil {
			failed = append(failed, c)
		}
	}

	// Clean up failed connections outside the read lock.
	if len(failed) > 0 {
		m.mu.Lock()
		for _, c := range failed {
			user, ok := m.connUser[c]
			if ok {
				delete(m.rooms[roomID], c)
				delete(m.connUser, c)
				delete(m.connMu, c)
				delete(m.userConns[user.UserID], c)
				if len(m.userConns[user.UserID]) == 0 {
					delete(m.userConns, user.UserID)
				}
			}
			_ = c.Close()
		}
		m.mu.Unlock()
	}
}

// SendToConn sends a raw JSON-encodable message to a single connection.
func (m *Manager) SendToConn(conn *websocket.Conn, msg interface{}) error {
	data, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	return m.safeWrite(conn, data)
}

// GetUsersInRoom returns the set of user IDs currently connected to a room.
func (m *Manager) GetUsersInRoom(roomID int) []int {
	m.mu.RLock()
	defer m.mu.RUnlock()

	seen := make(map[int]bool)
	for conn := range m.rooms[roomID] {
		if u, ok := m.connUser[conn]; ok {
			seen[u.UserID] = true
		}
	}
	ids := make([]int, 0, len(seen))
	for id := range seen {
		ids = append(ids, id)
	}
	return ids
}

// GetUsernamesInRoom returns the set of unique usernames in a room.
func (m *Manager) GetUsernamesInRoom(roomID int) []string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	seen := make(map[string]bool)
	for conn := range m.rooms[roomID] {
		if u, ok := m.connUser[conn]; ok {
			seen[u.Username] = true
		}
	}
	names := make([]string, 0, len(seen))
	for name := range seen {
		names = append(names, name)
	}
	return names
}

// FindUserIDByUsername looks up a user ID by username among connections in a room.
// Returns (userID, true) if found, (0, false) otherwise.
func (m *Manager) FindUserIDByUsername(roomID int, username string) (int, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	for conn := range m.rooms[roomID] {
		if u, ok := m.connUser[conn]; ok && u.Username == username {
			return u.UserID, true
		}
	}
	return 0, false
}

// IsUserInRoom checks whether a user (by ID) has any connections in the room.
func (m *Manager) IsUserInRoom(roomID, userID int) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()

	for conn := range m.rooms[roomID] {
		if u, ok := m.connUser[conn]; ok && u.UserID == userID {
			return true
		}
	}
	return false
}

// CloseUserConnsInRoom closes all connections for a specific user in a room
// and removes them from tracking. Used for kick operations. Returns the
// connections that were closed so the caller can handle any post-close logic.
func (m *Manager) CloseUserConnsInRoom(roomID, userID int) {
	m.mu.Lock()

	var toClose []*websocket.Conn
	for conn := range m.rooms[roomID] {
		if u, ok := m.connUser[conn]; ok && u.UserID == userID {
			toClose = append(toClose, conn)
		}
	}

	for _, conn := range toClose {
		delete(m.rooms[roomID], conn)
		delete(m.connUser, conn)
		delete(m.connMu, conn)
		delete(m.userConns[userID], conn)
	}
	if len(m.userConns[userID]) == 0 {
		delete(m.userConns, userID)
	}

	// Remove from join order.
	order := m.roomJoinOrder[roomID]
	for i, uid := range order {
		if uid == userID {
			m.roomJoinOrder[roomID] = append(order[:i], order[i+1:]...)
			break
		}
	}

	if len(m.rooms[roomID]) == 0 {
		delete(m.rooms, roomID)
		delete(m.roomJoinOrder, roomID)
	}

	m.mu.Unlock()

	// Close connections outside the lock to avoid deadlocks.
	for _, conn := range toClose {
		_ = conn.Close()
	}
}

// SendToUserInRoom sends a message to all of a user's connections in a specific room.
func (m *Manager) SendToUserInRoom(roomID, userID int, msg interface{}) {
	data, err := json.Marshal(msg)
	if err != nil {
		m.logger.Error("send_to_user_marshal_error", zap.Error(err))
		return
	}

	m.mu.RLock()
	var targets []*websocket.Conn
	for conn := range m.rooms[roomID] {
		if u, ok := m.connUser[conn]; ok && u.UserID == userID {
			targets = append(targets, conn)
		}
	}
	m.mu.RUnlock()

	for _, c := range targets {
		_ = m.safeWrite(c, data)
	}
}

// GetNextUserInRoom returns the next user in join order for a room,
// excluding a given user ID (typically the departing admin).
// Returns (userID, username, true) if found, (0, "", false) otherwise.
func (m *Manager) GetNextUserInRoom(roomID, excludeUserID int) (int, string, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	for _, uid := range m.roomJoinOrder[roomID] {
		if uid == excludeUserID {
			continue
		}
		// Find the username for this user from their connections.
		for conn := range m.rooms[roomID] {
			if u, ok := m.connUser[conn]; ok && u.UserID == uid {
				return uid, u.Username, true
			}
		}
	}
	return 0, "", false
}

// CloseAllInRoom closes all connections in a room. Used when a room is deactivated.
func (m *Manager) CloseAllInRoom(roomID int) {
	m.mu.Lock()

	var toClose []*websocket.Conn
	for conn := range m.rooms[roomID] {
		toClose = append(toClose, conn)
		user, ok := m.connUser[conn]
		if ok {
			delete(m.connUser, conn)
			delete(m.connMu, conn)
			delete(m.userConns[user.UserID], conn)
			if len(m.userConns[user.UserID]) == 0 {
				delete(m.userConns, user.UserID)
			}
		}
	}

	delete(m.rooms, roomID)
	delete(m.roomJoinOrder, roomID)

	m.mu.Unlock()

	for _, conn := range toClose {
		_ = conn.Close()
	}
}

// ---------- Lobby connections ----------

// ConnectLobby registers a lobby WebSocket connection.
func (m *Manager) ConnectLobby(conn *websocket.Conn, user UserInfo) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.lobbyConns[conn] = user
	m.connMu[conn] = &sync.Mutex{}

	if m.userConns[user.UserID] == nil {
		m.userConns[user.UserID] = make(map[*websocket.Conn]bool)
	}
	m.userConns[user.UserID][conn] = true

	m.logger.Info("ws_lobby_connect",
		zap.Int("user_id", user.UserID),
		zap.String("username", user.Username),
	)
}

// DisconnectLobby removes a lobby connection.
func (m *Manager) DisconnectLobby(conn *websocket.Conn) {
	m.mu.Lock()
	defer m.mu.Unlock()

	user, ok := m.lobbyConns[conn]
	if !ok {
		return
	}

	delete(m.lobbyConns, conn)
	delete(m.connMu, conn)

	delete(m.userConns[user.UserID], conn)
	if len(m.userConns[user.UserID]) == 0 {
		delete(m.userConns, user.UserID)
	}

	m.logger.Info("ws_lobby_disconnect", zap.Int("user_id", user.UserID))
}

// SendPersonal delivers a JSON message to all connections belonging to a user
// (lobby connections only). Returns true if at least one delivery succeeded.
func (m *Manager) SendPersonal(userID int, msg interface{}) bool {
	data, err := json.Marshal(msg)
	if err != nil {
		m.logger.Error("personal_marshal_error", zap.Error(err))
		return false
	}

	m.mu.RLock()
	// Collect lobby connections for this user.
	var targets []*websocket.Conn
	for conn, info := range m.lobbyConns {
		if info.UserID == userID {
			targets = append(targets, conn)
		}
	}
	m.mu.RUnlock()

	if len(targets) == 0 {
		return false
	}

	sent := false
	for _, c := range targets {
		if err := m.safeWrite(c, data); err == nil {
			sent = true
		}
	}
	return sent
}

// RoomCount returns the number of active rooms with connections.
func (m *Manager) RoomCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.rooms)
}

// TotalConnections returns the total number of tracked connections.
func (m *Manager) TotalConnections() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.connUser) + len(m.lobbyConns)
}
