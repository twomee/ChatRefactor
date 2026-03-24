package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

const (
	// rateLimitWindow is the sliding window for rate limiting.
	rateLimitWindow = 10 * time.Second

	// rateLimitMax is the maximum messages per window per user.
	rateLimitMax = 30
)

// rateLimiter provides a per-user sliding window rate limiter.
type rateLimiter struct {
	mu      sync.Mutex
	windows map[string][]time.Time
}

func newRateLimiter() *rateLimiter {
	return &rateLimiter{
		windows: make(map[string][]time.Time),
	}
}

// allow checks whether a user (identified by key) is within the rate limit.
// Returns true if the message is allowed.
func (rl *rateLimiter) allow(key string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	cutoff := now.Add(-rateLimitWindow)

	// Prune expired timestamps.
	timestamps := rl.windows[key]
	start := 0
	for start < len(timestamps) && timestamps[start].Before(cutoff) {
		start++
	}
	timestamps = timestamps[start:]

	if len(timestamps) >= rateLimitMax {
		rl.windows[key] = timestamps
		return false
	}

	rl.windows[key] = append(timestamps, now)
	return true
}

// readLoop reads messages from the client and dispatches based on type.
func (h *WSHandler) readLoop(conn *websocket.Conn, roomID, userID int, username string) {
	for {
		_, raw, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				h.logger.Warn("ws_read_error", zap.Error(err))
			}
			return
		}

		var incoming IncomingMessage
		if err := json.Unmarshal(raw, &incoming); err != nil {
			h.sendError(conn, "Invalid message format")
			continue
		}

		ctx := context.Background()

		switch incoming.Type {
		case "message":
			h.handleMessage(ctx, conn, roomID, userID, username, incoming.Text)
		case "kick":
			h.handleKick(ctx, conn, roomID, userID, username, incoming.Target)
		case "mute":
			h.handleMute(ctx, conn, roomID, userID, username, incoming.Target)
		case "unmute":
			h.handleUnmute(ctx, conn, roomID, userID, username, incoming.Target)
		case "promote":
			h.handlePromote(ctx, conn, roomID, userID, username, incoming.Target)
		case "private_message":
			h.handlePrivateMessage(ctx, conn, roomID, userID, username, incoming.To, incoming.Text)
		default:
			h.sendError(conn, "Unknown message type")
		}
	}
}

// handleMessage processes a chat message broadcast.
func (h *WSHandler) handleMessage(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, text string) {
	if strings.TrimSpace(text) == "" {
		h.sendError(conn, "Message text cannot be empty")
		return
	}

	if len(text) > maxContentLength {
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

	msgID := uuid.New().String()
	now := time.Now().UTC()

	broadcast := map[string]interface{}{
		"type":      "message",
		"from":      username,
		"text":      text,
		"room_id":   roomID,
		"msg_id":    msgID,
		"timestamp": now.Format(time.RFC3339),
	}
	h.manager.BroadcastRoom(roomID, broadcast)

	// Produce to Kafka for persistence.
	// Field names must match what message-service consumer expects:
	// sender_id (not user_id), text (not content).
	kafkaMsg := map[string]interface{}{
		"type":      "message",
		"room_id":   roomID,
		"sender_id": userID,
		"username":  username,
		"text":      text,
		"msg_id":    msgID,
		"timestamp": now.Format(time.RFC3339),
	}
	payload, _ := json.Marshal(kafkaMsg)
	if err := h.delivery.DeliverChat(ctx, roomID, payload); err != nil {
		h.logger.Warn("kafka_chat_deliver_failed", zap.Error(err))
	}
}
