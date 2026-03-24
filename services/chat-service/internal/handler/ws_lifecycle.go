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

// handleJoin broadcasts the user_join event and sends message history to
// the newly connected client.
func (h *WSHandler) handleJoin(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, token string) {
	// Fetch room state for the join broadcast.
	usernames := h.manager.GetUsernamesInRoom(roomID)
	adminNames := h.getAdminUsernames(ctx, roomID)
	mutedNames := h.getMutedUsernames(ctx, roomID)

	// Broadcast join event with full room state.
	joinBroadcast := map[string]interface{}{
		"type":     "user_join",
		"username": username,
		"users":    usernames,
		"admins":   adminNames,
		"muted":    mutedNames,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, joinBroadcast)

	// Produce join event to Kafka for downstream consumers (analytics, audit).
	h.produceEvent(ctx, "user_joined", roomID, userID, username)

	// Send message history to the newly joined connection.
	h.sendHistory(conn, roomID, token)
}

// handleDisconnect cleans up the connection, handles admin succession,
// clears the user's mute status, and broadcasts the user_left event.
// For kicked users, the user_left broadcast is skipped (handleKick already sent it).
func (h *WSHandler) handleDisconnect(ctx context.Context, conn *websocket.Conn, roomID, userID int, username string) {
	h.manager.DisconnectRoom(roomID, conn)
	_ = conn.Close()

	// If this user was kicked, skip the user_left broadcast — it was already
	// sent by handleKick. Also skip admin succession (kicked users aren't admins).
	if h.wasKicked(roomID, userID) {
		return
	}

	// NOTE: Admin status and mutes are NOT cleared on disconnect.
	// This preserves admin status across refreshes and reconnections.
	// Admin succession only happens on explicit kick (see handleKick).

	// Get updated room state for leave broadcast.
	remainingUsers := h.manager.GetUsernamesInRoom(roomID)
	updatedAdmins := h.getAdminUsernames(ctx, roomID)
	updatedMuted := h.getMutedUsernames(ctx, roomID)

	leaveBroadcast := map[string]interface{}{
		"type":     "user_left",
		"username": username,
		"users":    remainingUsers,
		"admins":   updatedAdmins,
		"muted":    updatedMuted,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, leaveBroadcast)

	// Produce leave event to Kafka for downstream consumers.
	h.produceEvent(ctx, "user_left", roomID, userID, username)
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
