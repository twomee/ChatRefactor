package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
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
		h.sendEmptyHistory(conn, roomID)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		h.sendEmptyHistory(conn, roomID)
		return
	}

	var rawMessages []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&rawMessages); err != nil {
		rawMessages = []map[string]interface{}{}
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
		if ts, ok := m["sent_at"]; ok {
			msg["timestamp"] = ts
		}
		if mid, ok := m["message_id"]; ok {
			msg["msg_id"] = mid
		}
		if editedAt, ok := m["edited_at"]; ok && editedAt != nil {
			msg["edited_at"] = editedAt
		}
		if isDeleted, ok := m["is_deleted"]; ok {
			msg["is_deleted"] = isDeleted
		}
		if reactions, ok := m["reactions"]; ok {
			msg["reactions"] = reactions
		}
		if isFile {
			msg["isFile"] = true
			if fileID, ok := m["file_id"]; ok && fileID != nil {
				msg["fileId"] = fileID
			}
		}
		transformed = append(transformed, msg)
	}
	return transformed
}
