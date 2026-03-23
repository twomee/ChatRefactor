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
