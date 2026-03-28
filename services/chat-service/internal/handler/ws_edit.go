package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// handleEditMessage validates the edit request, broadcasts the edit to the room,
// and publishes to Kafka for persistence.
func (h *WSHandler) handleEditMessage(ctx context.Context, conn *websocket.Conn, roomID, userID int, username string, msg IncomingMessage) {
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

	// Check if user is muted.
	muted, _ := h.store.IsMuted(ctx, roomID, userID)
	if muted {
		h.sendError(conn, "You are muted in this room")
		return
	}

	// Rate limiting.
	key := fmt.Sprintf("room:%d:user:%d", roomID, userID)
	if !h.limiter.allow(key) {
		h.sendError(conn, "Rate limit exceeded")
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
	if err := h.delivery.DeliverChat(ctx, roomID, payload); err != nil {
		h.logger.Warn("kafka_edit_deliver_failed", zap.Error(err))
	}
}

// handleDeleteMessage validates the delete request, broadcasts the deletion to the room,
// and publishes to Kafka for persistence.
func (h *WSHandler) handleDeleteMessage(ctx context.Context, conn *websocket.Conn, roomID, userID int, username string, msg IncomingMessage) {
	if strings.TrimSpace(msg.MessageID) == "" {
		h.sendError(conn, "Message ID is required for deletion")
		return
	}

	// Check if user is muted.
	muted, _ := h.store.IsMuted(ctx, roomID, userID)
	if muted {
		h.sendError(conn, "You are muted in this room")
		return
	}

	// Rate limiting.
	key := fmt.Sprintf("room:%d:user:%d", roomID, userID)
	if !h.limiter.allow(key) {
		h.sendError(conn, "Rate limit exceeded")
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
	if err := h.delivery.DeliverChat(ctx, roomID, payload); err != nil {
		h.logger.Warn("kafka_delete_deliver_failed", zap.Error(err))
	}
}
