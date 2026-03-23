package handler

import (
	"context"
	"encoding/json"
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

	// Find target in room.
	targetID, found := h.manager.FindUserIDByUsername(roomID, to)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	pm := map[string]interface{}{
		"type":      "private_message",
		"from":      username,
		"to":        to,
		"text":      text,
		"room_id":   roomID,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}

	// Send to target.
	h.manager.SendToUserInRoom(roomID, targetID, pm)
	// Also echo back to sender.
	h.manager.SendToUserInRoom(roomID, userID, pm)

	// Produce to Kafka for persistence.
	payload, _ := json.Marshal(pm)
	if err := h.delivery.DeliverPM(ctx, userID, payload); err != nil {
		h.logger.Warn("kafka_pm_deliver_failed", zap.Error(err))
	}
}
