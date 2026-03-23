package ws

import (
	"encoding/json"
	"sync"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

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
