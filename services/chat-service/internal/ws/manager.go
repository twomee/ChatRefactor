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
func (m *Manager) UserConnectionCount(userID int) int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	count := len(m.userConns[userID])
	// Also count lobby connections for this user
	for _, info := range m.lobbyConns {
		if info.UserID == userID {
			count++
		}
	}
	return count
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

// CloseAll gracefully closes every tracked connection with WebSocket close code 1001
// (GoingAway). Called during server shutdown to ensure clean disconnect.
func (m *Manager) CloseAll() {
	m.mu.Lock()

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

	m.mu.Unlock()

	// Close connections outside the lock to avoid deadlock.
	closeMsg := websocket.FormatCloseMessage(websocket.CloseGoingAway, "server shutting down")
	for _, conn := range allConns {
		_ = conn.WriteControl(websocket.CloseMessage, closeMsg, time.Now().Add(time.Second))
		_ = conn.Close()
	}

	m.logger.Info("all_connections_closed", zap.Int("count", len(allConns)))
}
