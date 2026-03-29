// Package ws provides the WebSocket connection manager that tracks all active
// connections across rooms and the lobby. It is the central coordination point
// for broadcasting messages and delivering private messages.
//
// Design decision: a single in-process manager with sync.RWMutex is the right
// choice while the service runs as a single instance. When we horizontally
// scale, Redis Pub/Sub will sit in front of this manager so that a broadcast
// on one instance fans out to connections on all instances.
//
// Files:
//   - manager.go       — struct, constructor, core utils
//   - manager_room.go  — room connect/disconnect/broadcast, user queries
//   - manager_lobby.go — lobby connect/disconnect, personal delivery
package ws

import (
	"encoding/json"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/metrics"
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

	// onFullLogout callbacks fire when a user's last lobby connection closes
	// (full logout). Called OUTSIDE the manager lock so callbacks can safely
	// call Manager methods. Used by WSHandler to cancel pending grace timers.
	onFullLogout []func(userID int, username string)

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

// RoomCleanup holds the result of evicting a user's room connections.
// The caller must broadcast user_left for each affected room.
type RoomCleanup struct {
	UserID   int
	Username string
	RoomIDs  []int              // rooms the user was removed from
	Conns    []*websocket.Conn  // connections that were closed
}

// evictUserRoomConnsLocked removes ALL room connections for a user from
// internal tracking maps. Must be called while m.mu is write-locked.
// Connections are returned for closing outside the lock.
func (m *Manager) evictUserRoomConnsLocked(userID int, username string) *RoomCleanup {
	toClose, affectedRooms := m.removeUserFromAllRooms(userID)

	m.cleanupUserConns(userID, toClose)

	if len(toClose) == 0 {
		return nil
	}

	metrics.WSConnectionsActive.WithLabelValues("room").Sub(float64(len(toClose)))
	metrics.WSActiveRooms.Set(float64(len(m.rooms)))

	roomIDs := make([]int, 0, len(affectedRooms))
	for id := range affectedRooms {
		roomIDs = append(roomIDs, id)
	}

	return &RoomCleanup{
		UserID:   userID,
		Username: username,
		RoomIDs:  roomIDs,
		Conns:    toClose,
	}
}

// removeUserFromAllRooms finds and removes all room connections for a user.
// Must be called while m.mu is write-locked.
func (m *Manager) removeUserFromAllRooms(userID int) ([]*websocket.Conn, map[int]bool) {
	var toClose []*websocket.Conn
	affectedRooms := make(map[int]bool)

	for roomID, conns := range m.rooms {
		toClose = m.evictUserFromRoom(roomID, conns, userID, toClose, affectedRooms)
		m.cleanupEmptyRoom(roomID, conns, userID)
	}

	return toClose, affectedRooms
}

// evictUserFromRoom removes a user's connections from a single room's conn set.
// Must be called while m.mu is write-locked.
func (m *Manager) evictUserFromRoom(roomID int, conns map[*websocket.Conn]bool, userID int, toClose []*websocket.Conn, affected map[int]bool) []*websocket.Conn {
	for c := range conns {
		u, ok := m.connUser[c]
		if !ok || u.UserID != userID {
			continue
		}
		toClose = append(toClose, c)
		affected[roomID] = true
		delete(conns, c)
		delete(m.connUser, c)
		delete(m.connMu, c)
	}
	return toClose
}

// cleanupEmptyRoom removes a room if empty, or removes the user from join order.
// Must be called while m.mu is write-locked.
func (m *Manager) cleanupEmptyRoom(roomID int, conns map[*websocket.Conn]bool, userID int) {
	if len(conns) == 0 {
		delete(m.rooms, roomID)
		delete(m.roomJoinOrder, roomID)
		return
	}
	order := m.roomJoinOrder[roomID]
	for i, uid := range order {
		if uid == userID {
			m.roomJoinOrder[roomID] = append(order[:i], order[i+1:]...)
			return
		}
	}
}

// cleanupUserConns removes evicted connections from the user's connection set.
// Must be called while m.mu is write-locked.
func (m *Manager) cleanupUserConns(userID int, evicted []*websocket.Conn) {
	for _, c := range evicted {
		delete(m.userConns[userID], c)
	}
	if len(m.userConns[userID]) == 0 {
		delete(m.userConns, userID)
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
		return websocket.ErrCloseSent
	}
	mu.Lock()
	defer mu.Unlock()
	return conn.WriteMessage(websocket.TextMessage, data)
}

// SendToConn sends a raw JSON-encodable message to a single connection.
func (m *Manager) SendToConn(conn *websocket.Conn, msg interface{}) error {
	data, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	return m.safeWrite(conn, data)
}

// UserConnectionCount returns the total number of active connections for a user
// across all rooms and lobby. Used to enforce per-user connection limits.
//
// Both ConnectRoom and ConnectLobby register connections in m.userConns, so
// len(m.userConns[userID]) already reflects the complete count across all
// connection types. No additional iteration over lobbyConns is needed.
func (m *Manager) UserConnectionCount(userID int) int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.userConns[userID])
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

// OnFullLogout registers a callback that fires when a user fully logs out
// (last lobby connection closes). Called outside the manager lock.
func (m *Manager) OnFullLogout(fn func(userID int, username string)) {
	m.onFullLogout = append(m.onFullLogout, fn)
}

// HasLobbyConnection returns true if the user has at least one active lobby
// connection. A user without a lobby connection is considered logged out —
// they should not be allowed to hold room connections.
func (m *Manager) HasLobbyConnection(userID int) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, info := range m.lobbyConns {
		if info.UserID == userID {
			return true
		}
	}
	return false
}

// CloseAll gracefully closes every tracked connection with WebSocket close code 1001
// (GoingAway). Called during server shutdown to ensure clean disconnect.
func (m *Manager) CloseAll() {
	m.mu.Lock()

	roomConnCount := len(m.connUser)
	lobbyConnCount := len(m.lobbyConns)

	var allConns []*websocket.Conn
	for conn := range m.connUser {
		allConns = append(allConns, conn)
	}
	for conn := range m.lobbyConns {
		allConns = append(allConns, conn)
	}

	// Clear all tracking maps.
	m.rooms = make(map[int]map[*websocket.Conn]bool)
	m.connUser = make(map[*websocket.Conn]UserInfo)
	m.userConns = make(map[int]map[*websocket.Conn]bool)
	m.lobbyConns = make(map[*websocket.Conn]UserInfo)
	m.connMu = make(map[*websocket.Conn]*sync.Mutex)
	m.roomJoinOrder = make(map[int][]int)

	// Reset metrics gauges to reflect cleared state.
	metrics.WSConnectionsActive.WithLabelValues("room").Sub(float64(roomConnCount))
	metrics.WSConnectionsActive.WithLabelValues("lobby").Sub(float64(lobbyConnCount))
	metrics.WSActiveRooms.Set(0)

	m.mu.Unlock()

	// Close connections outside the lock to avoid deadlock.
	closeMsg := websocket.FormatCloseMessage(websocket.CloseGoingAway, "server shutting down")
	for _, conn := range allConns {
		_ = conn.WriteControl(websocket.CloseMessage, closeMsg, time.Now().Add(time.Second))
		_ = conn.Close()
	}

	m.logger.Info("all_connections_closed", zap.Int("count", len(allConns)))
}
