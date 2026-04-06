package handler

import (
	"context"
	"encoding/json"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

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

// sendHistory fetches recent messages from the Message Service and sends them
// to the newly connected client.
func (h *WSHandler) sendHistory(conn *websocket.Conn, roomID int, token string) {
	if h.messageClient == nil {
		h.sendEmptyHistory(conn, roomID)
		return
	}
	rawMessages := h.messageClient.GetRoomHistory(context.Background(), roomID, token, 50)
	if rawMessages == nil {
		h.sendEmptyHistory(conn, roomID)
		return
	}

	historyMsg := map[string]interface{}{
		"type":     "history",
		"messages": transformHistoryMessages(rawMessages),
		"room_id":  roomID,
	}
	_ = h.manager.SendToConn(conn, historyMsg)
}

// sendReadPosition sends the user's last-read message position for the room.
// Called after sendHistory so the frontend can render the "New messages" divider.
func (h *WSHandler) sendReadPosition(ctx context.Context, conn *websocket.Conn, roomID, userID int) {
	if h.readPositionStore == nil {
		return
	}

	rp, err := h.readPositionStore.Get(ctx, userID, roomID)
	if err != nil {
		// No read position yet (first visit) — nothing to send.
		return
	}

	readPosMsg := map[string]interface{}{
		"type":                 "read_position",
		"room_id":              roomID,
		"last_read_message_id": rp.LastReadMessageID,
	}
	_ = h.manager.SendToConn(conn, readPosMsg)
}

// sendEmptyHistory sends an empty history payload to the client.
// Used when the message service is unavailable or returns a non-OK status.
func (h *WSHandler) sendEmptyHistory(conn *websocket.Conn, roomID int) {
	historyMsg := map[string]interface{}{
		"type":     "history",
		"messages": []interface{}{},
		"room_id":  roomID,
	}
	_ = h.manager.SendToConn(conn, historyMsg)
}

// transformHistoryMessages converts raw message-service records (sender_id,
// content) into the frontend wire format (from, text) expected by MessageList.
func transformHistoryMessages(rawMessages []map[string]interface{}) []map[string]interface{} {
	transformed := make([]map[string]interface{}, 0, len(rawMessages))
	for _, m := range rawMessages {
		transformed = append(transformed, transformOneMessage(m))
	}
	return transformed
}

// transformOneMessage converts a single message-service record into the
// frontend wire format.
func transformOneMessage(m map[string]interface{}) map[string]interface{} {
	isFile, _ := m["is_file"].(bool)
	msgType := "message"
	if isFile {
		msgType = "file_shared"
	}
	msg := map[string]interface{}{
		"type": msgType,
		"from": m["sender_name"],
		"text": m["content"],
	}
	copyIfPresent(msg, m, "sent_at", "timestamp")
	copyIfPresent(msg, m, "message_id", "msg_id")
	copyIfPresentNonNil(msg, m, "edited_at", "edited_at")
	copyIfPresent(msg, m, "is_deleted", "is_deleted")
	copyIfPresent(msg, m, "reactions", "reactions")
	if isFile {
		msg["isFile"] = true
		copyIfPresentNonNil(msg, m, "file_id", "fileId")
	}
	return msg
}

// copyIfPresent copies a value from src to dst under a new key if it exists.
func copyIfPresent(dst, src map[string]interface{}, srcKey, dstKey string) {
	if v, ok := src[srcKey]; ok {
		dst[dstKey] = v
	}
}

// copyIfPresentNonNil copies a value from src to dst only if it exists and is not nil.
func copyIfPresentNonNil(dst, src map[string]interface{}, srcKey, dstKey string) {
	if v, ok := src[srcKey]; ok && v != nil {
		dst[dstKey] = v
	}
}
