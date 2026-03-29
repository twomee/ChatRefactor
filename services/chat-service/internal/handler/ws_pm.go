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

// handlePrivateMessage processes a private message sent via WebSocket.
func (h *WSHandler) handlePrivateMessage(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, to, text string) {
	if to == "" {
		h.sendError(conn, "Recipient username required")
		return
	}
	if strings.TrimSpace(text) == "" {
		h.sendError(conn, "Message text cannot be empty")
		return
	}
	if len(text) > maxContentLength {
		h.sendError(conn, "Message too long")
		return
	}

	// Cannot PM yourself.
	if to == username {
		h.sendError(conn, "Cannot send PM to yourself")
		return
	}

	// Rate limiting (same window as chat messages).
	key := fmt.Sprintf("pm:%d:user:%d", roomID, userID)
	if !h.limiter.allow(key) {
		h.sendError(conn, "Rate limit exceeded")
		return
	}

	// Find target in room.
	targetID, found := h.manager.FindUserIDByUsername(roomID, to)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	now := time.Now().UTC().Format(time.RFC3339)

	// WebSocket payload uses "from"/"to" for frontend rendering.
	wsPM := map[string]interface{}{
		"type":      "private_message",
		"from":      username,
		"to":        to,
		"text":      text,
		"room_id":   roomID,
		"timestamp": now,
	}

	// Send to target.
	h.manager.SendToUserInRoom(roomID, targetID, wsPM)

	// Echo back to sender with "self": true so frontend can distinguish.
	selfPM := map[string]interface{}{
		"type":      "private_message",
		"from":      username,
		"to":        to,
		"text":      text,
		"room_id":   roomID,
		"timestamp": now,
		"self":      true,
	}
	h.manager.SendToUserInRoom(roomID, userID, selfPM)

	// Kafka payload uses "sender"/"recipient" to match what the
	// message-service persistence consumer expects.
	kafkaPayload := map[string]interface{}{
		"type":      "private_message",
		"msg_id":    fmt.Sprintf("pm-%d-%d-%d", roomID, userID, time.Now().UnixNano()),
		"sender":    username,
		"sender_id": userID,
		"recipient": to,
		"text":      text,
		"room_id":   roomID,
		"timestamp": now,
	}
	payload, _ := json.Marshal(kafkaPayload)
	if err := h.delivery.DeliverPM(ctx, userID, payload); err != nil {
		h.logger.Warn("kafka_pm_deliver_failed", zap.Error(err))
	}
}
