package ws

import (
	"encoding/json"
	"sync"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/metrics"
)

// ConnectLobby registers a lobby WebSocket connection.
func (m *Manager) ConnectLobby(conn *websocket.Conn, user UserInfo) {
	m.mu.Lock()

	m.lobbyConns[conn] = user
	m.connMu[conn] = &sync.Mutex{}

	if m.userConns[user.UserID] == nil {
		m.userConns[user.UserID] = make(map[*websocket.Conn]bool)
	}
	m.userConns[user.UserID][conn] = true

	metrics.WSConnectionsActive.WithLabelValues("lobby").Inc()
	metrics.WSConnectionsTotal.WithLabelValues("lobby").Inc()

	// Check if this is the user's first lobby connection (they just logged in).
	firstLobby := true
	for c, info := range m.lobbyConns {
		if c != conn && info.UserID == user.UserID {
			firstLobby = false
			break
		}
	}

	m.logger.Info("ws_lobby_connect",
		zap.Int("user_id", user.UserID),
		zap.String("username", user.Username),
	)

	m.mu.Unlock()

	// Broadcast user_online outside the lock (BroadcastLobby takes RLock).
	if firstLobby {
		m.BroadcastLobby(map[string]interface{}{
			"type":     "user_online",
			"username": user.Username,
		})
	}
}

// DisconnectLobby removes a lobby connection. If the user has no remaining
// lobby connections (i.e. they fully logged out), all their room connections
// are also closed to prevent zombie presence. The returned RoomCleanup, if
// non-nil, contains room IDs that need user_left broadcasts — the caller
// must handle those outside the manager.
func (m *Manager) DisconnectLobby(conn *websocket.Conn) *RoomCleanup {
	m.mu.Lock()

	user, ok := m.lobbyConns[conn]
	if !ok {
		m.mu.Unlock()
		return nil
	}

	delete(m.lobbyConns, conn)
	delete(m.connMu, conn)

	delete(m.userConns[user.UserID], conn)
	if len(m.userConns[user.UserID]) == 0 {
		delete(m.userConns, user.UserID)
	}

	metrics.WSConnectionsActive.WithLabelValues("lobby").Dec()

	// Check if the user has any remaining lobby connections.
	// If not, they fully logged out — close zombie room connections.
	hasLobby := false
	for _, info := range m.lobbyConns {
		if info.UserID == user.UserID {
			hasLobby = true
			break
		}
	}

	var cleanup *RoomCleanup
	if !hasLobby {
		cleanup = m.evictUserRoomConnsLocked(user.UserID, user.Username)
	}

	m.mu.Unlock()

	// Close evicted connections outside the lock.
	if cleanup != nil {
		for _, c := range cleanup.Conns {
			_ = c.Close()
		}
	}

	m.logger.Info("ws_lobby_disconnect",
		zap.Int("user_id", user.UserID),
		zap.Bool("full_logout", !hasLobby),
	)

	if !hasLobby {
		// Broadcast user_offline to all remaining lobby connections.
		m.BroadcastLobby(map[string]interface{}{
			"type":     "user_offline",
			"username": user.Username,
		})
		// Fire full-logout callbacks (e.g. cancel pending grace timers).
		for _, fn := range m.onFullLogout {
			fn(user.UserID, user.Username)
		}
	}

	return cleanup
}

// BroadcastLobby sends a JSON message to ALL lobby connections.
// Used for room_list_updated and file_shared notifications.
func (m *Manager) BroadcastLobby(msg interface{}) {
	data, err := json.Marshal(msg)
	if err != nil {
		m.logger.Error("lobby_broadcast_marshal_error", zap.Error(err))
		return
	}

	m.mu.RLock()
	conns := make([]*websocket.Conn, 0, len(m.lobbyConns))
	for c := range m.lobbyConns {
		conns = append(conns, c)
	}
	m.mu.RUnlock()

	for _, c := range conns {
		_ = m.safeWrite(c, data)
	}
}

// GetLobbyUsernames returns a deduplicated list of all users connected to the lobby.
// This represents all logged-in users (regardless of room membership).
func (m *Manager) GetLobbyUsernames() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	seen := make(map[string]bool)
	for _, info := range m.lobbyConns {
		seen[info.Username] = true
	}
	names := make([]string, 0, len(seen))
	for name := range seen {
		names = append(names, name)
	}
	return names
}

// SendPersonal delivers a JSON message to all lobby connections belonging to a user.
// Returns true if at least one delivery succeeded.
func (m *Manager) SendPersonal(userID int, msg interface{}) bool {
	data, err := json.Marshal(msg)
	if err != nil {
		m.logger.Error("personal_marshal_error", zap.Error(err))
		return false
	}

	m.mu.RLock()
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
