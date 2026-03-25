package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// reconnectGrace is the time to wait before broadcasting a user_left event.
// If the user reconnects within this window (e.g. page refresh), the leave
// is cancelled silently — no leave/join messages, no state changes.
const reconnectGrace = 3 * time.Second

// handleJoin broadcasts the user_join event and sends message history to
// the newly connected client.
func (h *WSHandler) handleJoin(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, token string) {
	// Check if this is a reconnect (pending leave exists).
	leaveKey := fmt.Sprintf("%d:%d", roomID, userID)
	h.pendingLeaveMu.Lock()
	cancel, isReconnect := h.pendingLeaves[leaveKey]
	if isReconnect {
		cancel() // cancel the pending leave — user came back
		delete(h.pendingLeaves, leaveKey)
	}
	h.pendingLeaveMu.Unlock()

	// Fetch room state for the join broadcast.
	usernames := h.manager.GetUsernamesInRoom(roomID)
	adminNames := h.getAdminUsernames(ctx, roomID)
	mutedNames := h.getMutedUsernames(ctx, roomID)

	// Always broadcast updated user list (so other clients refresh their view).
	joinBroadcast := map[string]interface{}{
		"type":     "user_join",
		"username": username,
		"users":    usernames,
		"admins":   adminNames,
		"muted":    mutedNames,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, joinBroadcast)

	if !isReconnect {
		// First-time join: persist system message and produce event.
		joinMsgID := uuid.New().String()
		joinNow := time.Now().UTC().Format(time.RFC3339)
		joinKafka := map[string]interface{}{
			"type":      "message",
			"room_id":   roomID,
			"sender_id": 0,
			"username":  "system",
			"text":      fmt.Sprintf("%s joined the room", username),
			"msg_id":    joinMsgID,
			"timestamp": joinNow,
		}
		joinPayload, _ := json.Marshal(joinKafka)
		_ = h.delivery.DeliverChat(ctx, roomID, joinPayload)

		h.produceEvent(ctx, "user_joined", roomID, userID, username)
	}

	// Send message history to the newly joined connection.
	h.sendHistory(conn, roomID, token)
}

// handleDisconnect cleans up the connection and schedules a delayed leave
// broadcast. If the user reconnects within the grace period (e.g. page
// refresh), the leave is cancelled silently.
// For kicked users, the leave is immediate (no grace period).
func (h *WSHandler) handleDisconnect(ctx context.Context, conn *websocket.Conn, roomID, userID int, username string) {
	h.manager.DisconnectRoom(roomID, conn)
	_ = conn.Close()

	// Kicked users: immediate leave (already broadcast by handleKick).
	if h.wasKicked(roomID, userID) {
		return
	}

	// Check if user still has other connections in this room (multi-tab).
	if h.manager.IsUserInRoom(roomID, userID) {
		return
	}

	// Schedule a delayed leave. If the user reconnects within the grace
	// period, handleJoin cancels this and no leave/join is broadcast.
	leaveCtx, cancel := context.WithCancel(context.Background())
	leaveKey := fmt.Sprintf("%d:%d", roomID, userID)

	h.pendingLeaveMu.Lock()
	h.pendingLeaves[leaveKey] = cancel
	h.pendingLeaveMu.Unlock()

	go func() {
		select {
		case <-leaveCtx.Done():
			// Cancelled — user reconnected. Do nothing.
			return
		case <-time.After(reconnectGrace):
			// Grace period expired — user truly left.
		}

		h.pendingLeaveMu.Lock()
		delete(h.pendingLeaves, leaveKey)
		h.pendingLeaveMu.Unlock()

		// Broadcast leave with updated room state.
		bgCtx := context.Background()
		remainingUsers := h.manager.GetUsernamesInRoom(roomID)
		updatedAdmins := h.getAdminUsernames(bgCtx, roomID)
		updatedMuted := h.getMutedUsernames(bgCtx, roomID)

		leaveBroadcast := map[string]interface{}{
			"type":     "user_left",
			"username": username,
			"users":    remainingUsers,
			"admins":   updatedAdmins,
			"muted":    updatedMuted,
			"room_id":  roomID,
		}
		h.manager.BroadcastRoom(roomID, leaveBroadcast)

		// Persist leave system message.
		leaveMsgID := uuid.New().String()
		leaveNow := time.Now().UTC().Format(time.RFC3339)
		leaveKafka := map[string]interface{}{
			"type":      "message",
			"room_id":   roomID,
			"sender_id": 0,
			"username":  "system",
			"text":      fmt.Sprintf("%s left the room", username),
			"msg_id":    leaveMsgID,
			"timestamp": leaveNow,
		}
		leavePayload, _ := json.Marshal(leaveKafka)
		_ = h.delivery.DeliverChat(bgCtx, roomID, leavePayload)

		h.produceEvent(bgCtx, "user_left", roomID, userID, username)
	}()
}

// handleAdminSuccession handles admin departure and succession logic.
// When an admin leaves: remove their admin status, clear all mutes (amnesty),
// and promote the next user in join order.
func (h *WSHandler) handleAdminSuccession(ctx context.Context, roomID, userID int, username string) {
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		return
	}

	// Remove departing admin.
	_ = h.store.RemoveAdmin(ctx, roomID, userID)

	// Amnesty: clear all mutes in the room.
	mutedUsers, _ := h.store.GetMutedUsers(ctx, roomID)
	for _, mu := range mutedUsers {
		_ = h.store.UnmuteUser(ctx, roomID, mu.UserID)
	}

	// Find next user in join order to promote.
	nextUserID, nextUsername, found := h.manager.GetNextUserInRoom(roomID, userID)
	if !found {
		return // room is empty
	}

	// Promote next user.
	_, err := h.store.AddAdmin(ctx, roomID, nextUserID)
	if err != nil {
		h.logger.Error("admin_succession_failed", zap.Error(err))
		return
	}

	// Broadcast new admin.
	promoteMsg := map[string]interface{}{
		"type":     "new_admin",
		"username": nextUsername,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, promoteMsg)

	// Broadcast system message about succession.
	systemMsg := map[string]interface{}{
		"type":      "message",
		"from":      "system",
		"text":      fmt.Sprintf("%s left. %s is now admin", username, nextUsername),
		"room_id":   roomID,
		"msg_id":    uuid.New().String(),
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	h.manager.BroadcastRoom(roomID, systemMsg)
}

// sendHistory fetches recent messages from the Message Service and sends them
// to the newly connected client.
func (h *WSHandler) sendHistory(conn *websocket.Conn, roomID int, token string) {
	url := fmt.Sprintf("%s/messages/rooms/%d/history?limit=50", h.messageSvcURL, roomID)

	client := &http.Client{Timeout: 3 * time.Second}
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		h.logger.Warn("history_request_build_failed", zap.Error(err))
		return
	}
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := client.Do(req)
	if err != nil {
		h.logger.Warn("history_fetch_failed", zap.Error(err))
		// Send empty history instead of failing silently.
		historyMsg := map[string]interface{}{
			"type":     "history",
			"messages": []interface{}{},
			"room_id":  roomID,
		}
		_ = h.manager.SendToConn(conn, historyMsg)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		historyMsg := map[string]interface{}{
			"type":     "history",
			"messages": []interface{}{},
			"room_id":  roomID,
		}
		_ = h.manager.SendToConn(conn, historyMsg)
		return
	}

	var rawMessages []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&rawMessages); err != nil {
		rawMessages = []map[string]interface{}{}
	}

	// Transform field names from message-service format (sender_id, content)
	// to frontend format (from, text) so MessageList can render them.
	transformed := make([]map[string]interface{}, 0, len(rawMessages))
	for _, m := range rawMessages {
		msg := map[string]interface{}{
			"type": "message",
			"from": m["sender_name"],
			"text": m["content"],
		}
		if ts, ok := m["sent_at"]; ok {
			msg["timestamp"] = ts
		}
		if mid, ok := m["message_id"]; ok {
			msg["msg_id"] = mid
		}
		transformed = append(transformed, msg)
	}

	historyMsg := map[string]interface{}{
		"type":     "history",
		"messages": transformed,
		"room_id":  roomID,
	}
	_ = h.manager.SendToConn(conn, historyMsg)
}

// getAdminUsernames returns a list of admin usernames for a room by cross-referencing
// the admin records with currently connected users.
func (h *WSHandler) getAdminUsernames(ctx context.Context, roomID int) []string {
	admins, err := h.store.GetAdmins(ctx, roomID)
	if err != nil {
		return []string{}
	}

	// Build a map of userID -> username from connected users.
	usernames := h.manager.GetUsernamesInRoom(roomID)
	userIDToName := make(map[int]string)
	for _, name := range usernames {
		uid, found := h.manager.FindUserIDByUsername(roomID, name)
		if found {
			userIDToName[uid] = name
		}
	}

	names := make([]string, 0)
	for _, a := range admins {
		if name, ok := userIDToName[a.UserID]; ok {
			names = append(names, name)
		}
	}
	return names
}

// produceEvent fires an event to the chat.events Kafka topic (fire-and-forget).
func (h *WSHandler) produceEvent(ctx context.Context, eventType string, roomID, userID int, username string) {
	event := map[string]interface{}{
		"event_type": eventType,
		"room_id":    roomID,
		"user_id":    userID,
		"username":   username,
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	}
	payload, _ := json.Marshal(event)
	if err := h.delivery.DeliverEvent(ctx, eventType, payload); err != nil {
		h.logger.Debug("event_deliver_failed", zap.String("event", eventType), zap.Error(err))
	}
}

// getMutedUsernames returns a list of muted usernames for a room.
func (h *WSHandler) getMutedUsernames(ctx context.Context, roomID int) []string {
	mutedUsers, err := h.store.GetMutedUsers(ctx, roomID)
	if err != nil {
		return []string{}
	}

	usernames := h.manager.GetUsernamesInRoom(roomID)
	userIDToName := make(map[int]string)
	for _, name := range usernames {
		uid, found := h.manager.FindUserIDByUsername(roomID, name)
		if found {
			userIDToName[uid] = name
		}
	}

	names := make([]string, 0)
	for _, m := range mutedUsers {
		if name, ok := userIDToName[m.UserID]; ok {
			names = append(names, name)
		}
	}
	return names
}
