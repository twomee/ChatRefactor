package handler

import (
	"context"
	"encoding/json"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// handleEditMessage validates the edit request, broadcasts the edit to the room,
// and publishes to Kafka for persistence.
func (h *WSHandler) handleEditMessage(conn *websocket.Conn, roomID, userID int, username string, msg IncomingMessage) {
	if strings.TrimSpace(msg.MessageID) == "" {
		h.sendError(conn, "Message ID is required for editing")
		return
	}

	if strings.TrimSpace(msg.Text) == "" {
		h.sendError(conn, "Edited message text cannot be empty")
		return
	}

	if len(msg.Text) > maxContentLength {
		h.sendError(conn, "Message too long")
		return
	}

	now := time.Now().UTC()

	// Broadcast the edit to all room members.
	broadcast := map[string]interface{}{
		"type":      "message_edited",
		"msg_id":    msg.MessageID,
		"text":      msg.Text,
		"from":      username,
		"room_id":   roomID,
		"edited_at": now.Format(time.RFC3339),
	}
	h.manager.BroadcastRoom(roomID, broadcast)

	// Produce to Kafka for persistence.
	kafkaMsg := map[string]interface{}{
		"type":      "edit_message",
		"msg_id":    msg.MessageID,
		"sender_id": userID,
		"username":  username,
		"text":      msg.Text,
		"room_id":   roomID,
		"timestamp": now.Format(time.RFC3339),
	}
	payload, _ := json.Marshal(kafkaMsg)
	ctx := context.Background()
	if err := h.delivery.DeliverChat(ctx, roomID, payload); err != nil {
		h.logger.Warn("kafka_edit_deliver_failed", zap.Error(err))
	}
}

// handleDeleteMessage validates the delete request, broadcasts the deletion to the room,
// and publishes to Kafka for persistence.
func (h *WSHandler) handleDeleteMessage(conn *websocket.Conn, roomID, userID int, username string, msg IncomingMessage) {
	if strings.TrimSpace(msg.MessageID) == "" {
		h.sendError(conn, "Message ID is required for deletion")
		return
	}

	now := time.Now().UTC()

	// Broadcast the deletion to all room members.
	broadcast := map[string]interface{}{
		"type":    "message_deleted",
		"msg_id":  msg.MessageID,
		"from":    username,
		"room_id": roomID,
	}
	h.manager.BroadcastRoom(roomID, broadcast)

	// Produce to Kafka for persistence.
	kafkaMsg := map[string]interface{}{
		"type":      "delete_message",
		"msg_id":    msg.MessageID,
		"sender_id": userID,
		"username":  username,
		"room_id":   roomID,
		"timestamp": now.Format(time.RFC3339),
	}
	payload, _ := json.Marshal(kafkaMsg)
	ctx := context.Background()
	if err := h.delivery.DeliverChat(ctx, roomID, payload); err != nil {
		h.logger.Warn("kafka_delete_deliver_failed", zap.Error(err))
	}
}
