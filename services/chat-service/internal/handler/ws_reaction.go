package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// handleAddReaction validates the reaction payload, broadcasts a reaction_added
// event to the room, and publishes to Kafka for persistence.
func (h *WSHandler) handleAddReaction(ctx context.Context, conn *websocket.Conn, roomID, userID int, username string, msg IncomingMessage) {
	msgID := strings.TrimSpace(msg.MsgID)
	emoji := strings.TrimSpace(msg.Emoji)

	if msgID == "" {
		h.sendError(conn, "msg_id is required for reactions")
		return
	}
	if emoji == "" {
		h.sendError(conn, "emoji is required for reactions")
		return
	}
	if len(emoji) > 32 {
		h.sendError(conn, "emoji too long")
		return
	}

	// Check if user is muted.
	muted, _ := h.store.IsMuted(ctx, roomID, userID)
	if muted {
		h.sendError(conn, "You are muted in this room")
		return
	}

	// Rate limiting.
	key := fmt.Sprintf("reaction:%d:user:%d", roomID, userID)
	if !h.limiter.allow(key) {
		return
	}

	// Broadcast reaction_added to all clients in the room.
	broadcast := map[string]interface{}{
		"type":     "reaction_added",
		"msg_id":   msgID,
		"emoji":    emoji,
		"user_id":  userID,
		"username": username,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, broadcast)

	// Publish to Kafka for persistence.
	kafkaMsg := map[string]interface{}{
		"type":     "add_reaction",
		"msg_id":   msgID,
		"emoji":    emoji,
		"user_id":  userID,
		"username": username,
		"room_id":  roomID,
	}
	payload, _ := json.Marshal(kafkaMsg)
	if err := h.delivery.DeliverChat(ctx, roomID, payload); err != nil {
		h.logger.Warn("kafka_reaction_deliver_failed", zap.Error(err))
	}
}

// handleRemoveReaction validates the reaction payload, broadcasts a reaction_removed
// event to the room, and publishes to Kafka for persistence.
func (h *WSHandler) handleRemoveReaction(ctx context.Context, conn *websocket.Conn, roomID, userID int, username string, msg IncomingMessage) {
	msgID := strings.TrimSpace(msg.MsgID)
	emoji := strings.TrimSpace(msg.Emoji)

	if msgID == "" {
		h.sendError(conn, "msg_id is required for reactions")
		return
	}
	if emoji == "" {
		h.sendError(conn, "emoji is required for reactions")
		return
	}
	if len(emoji) > 32 {
		h.sendError(conn, "emoji too long")
		return
	}

	// Rate limiting.
	key := fmt.Sprintf("reaction:%d:user:%d", roomID, userID)
	if !h.limiter.allow(key) {
		return
	}

	// Broadcast reaction_removed to all clients in the room.
	broadcast := map[string]interface{}{
		"type":     "reaction_removed",
		"msg_id":   msgID,
		"emoji":    emoji,
		"user_id":  userID,
		"username": username,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, broadcast)

	// Publish to Kafka for persistence.
	kafkaMsg := map[string]interface{}{
		"type":       "remove_reaction",
		"msg_id":     msgID,
		"emoji":      emoji,
		"user_id":    userID,
		"username":   username,
		"room_id":    roomID,
	}
	payload, _ := json.Marshal(kafkaMsg)
	if err := h.delivery.DeliverChat(ctx, roomID, payload); err != nil {
		h.logger.Warn("kafka_reaction_deliver_failed", zap.Error(err))
	}
}
