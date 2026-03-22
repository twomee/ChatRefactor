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

	logger *zap.Logger
}

// NewManager creates an initialised connection manager.
func NewManager(logger *zap.Logger) *Manager {
	return &Manager{
		rooms:      make(map[int]map[*websocket.Conn]bool),
		connUser:   make(map[*websocket.Conn]UserInfo),
		userConns:  make(map[int]map[*websocket.Conn]bool),
		lobbyConns: make(map[*websocket.Conn]UserInfo),
		logger:     logger,
	}
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

	if m.userConns[user.UserID] == nil {
		m.userConns[user.UserID] = make(map[*websocket.Conn]bool)
	}
	m.userConns[user.UserID][conn] = true

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
	if len(m.rooms[roomID]) == 0 {
		delete(m.rooms, roomID)
	}

	delete(m.connUser, conn)

	delete(m.userConns[user.UserID], conn)
	if len(m.userConns[user.UserID]) == 0 {
		delete(m.userConns, user.UserID)
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
		if err := c.WriteMessage(websocket.TextMessage, data); err != nil {
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

// ---------- Lobby connections ----------

// ConnectLobby registers a lobby WebSocket connection.
func (m *Manager) ConnectLobby(conn *websocket.Conn, user UserInfo) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.lobbyConns[conn] = user

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
		if err := c.WriteMessage(websocket.TextMessage, data); err == nil {
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
