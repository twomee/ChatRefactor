package ws

import (
	"encoding/json"
	"sync"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/metrics"
)

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

	metrics.WSConnectionsActive.WithLabelValues("room").Inc()
	metrics.WSConnectionsTotal.WithLabelValues("room").Inc()
	metrics.WSActiveRooms.Set(float64(len(m.rooms)))

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

	metrics.WSConnectionsActive.WithLabelValues("room").Dec()
	metrics.WSActiveRooms.Set(float64(len(m.rooms)))

	m.logger.Info("ws_room_disconnect",
		zap.Int("room_id", roomID),
		zap.Int("user_id", user.UserID),
	)
}

// BroadcastRoom sends a JSON message to every connection in a room.
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
				metrics.WSConnectionsActive.WithLabelValues("room").Dec()
			}
			_ = c.Close()
		}
		metrics.WSActiveRooms.Set(float64(len(m.rooms)))
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

// CloseUserConnsInRoom closes all connections for a specific user in a room.
// Used for kick operations.
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

	// Update metrics for removed connections.
	metrics.WSConnectionsActive.WithLabelValues("room").Sub(float64(len(toClose)))
	metrics.WSActiveRooms.Set(float64(len(m.rooms)))

	m.mu.Unlock()

	for _, conn := range toClose {
		_ = conn.Close()
	}
}

// SendToUserInRoom sends a message to all of a user's connections in a room.
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

// GetNextUserInRoom returns the next user in join order, excluding the given user.
// Used for admin succession.
func (m *Manager) GetNextUserInRoom(roomID, excludeUserID int) (int, string, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	for _, uid := range m.roomJoinOrder[roomID] {
		if uid == excludeUserID {
			continue
		}
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

	// Update metrics for removed connections.
	metrics.WSConnectionsActive.WithLabelValues("room").Sub(float64(len(toClose)))
	metrics.WSActiveRooms.Set(float64(len(m.rooms)))

	m.mu.Unlock()

	for _, conn := range toClose {
		_ = conn.Close()
	}
}
