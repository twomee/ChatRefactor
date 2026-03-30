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
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure, websocket.CloseAbnormalClosure, websocket.CloseNoStatusReceived) {
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
		case "typing":
			h.handleTyping(conn, roomID, username)
		case "edit_message":
			h.handleEditMessage(conn, roomID, userID, username, incoming)
		case "delete_message":
			h.handleDeleteMessage(conn, roomID, userID, username, incoming)
		case "add_reaction":
			h.handleAddReaction(ctx, conn, roomID, userID, username, incoming)
		case "remove_reaction":
			h.handleRemoveReaction(ctx, conn, roomID, userID, username, incoming)
		case "mark_read":
			h.handleMarkRead(ctx, conn, roomID, userID, incoming.MessageID)
		case "leave":
			h.handleLeave(ctx, conn, roomID, userID, username)
			return // exit readLoop — connection is being closed
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
		"type":         "message",
		"from":         username,
		"text":         text,
		"room_id":      roomID,
		"msg_id":       msgID,
		"timestamp":    now.Format(time.RFC3339),
		"mentions":     parseMentions(text),
		"mention_room": isRoomMention(text),
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

// handleTyping broadcasts a typing indicator to all other connections in the
// room. Typing events are ephemeral — they are NOT persisted to Kafka or the
// database. The frontend auto-clears stale indicators after a short timeout.
func (h *WSHandler) handleTyping(conn *websocket.Conn, roomID int, username string) {
	typingPayload := map[string]interface{}{
		"type":     "typing",
		"room_id":  roomID,
		"username": username,
	}
	h.manager.BroadcastRoomExcept(roomID, conn, typingPayload)
}

// handleMarkRead persists the user's last-read message position in a room.
// Read positions are per-user and are NOT broadcast to other users.
func (h *WSHandler) handleMarkRead(ctx context.Context, conn *websocket.Conn, roomID, userID int, messageID string) {
	messageID = strings.TrimSpace(messageID)
	if messageID == "" {
		h.sendError(conn, "msg_id is required for mark_read")
		return
	}

	if _, err := uuid.Parse(messageID); err != nil {
		h.sendError(conn, "msg_id must be a valid UUID")
		return
	}

	if h.readPositionStore == nil {
		// Gracefully degrade if read-position store is not configured (e.g. no DB).
		return
	}

	if err := h.readPositionStore.Upsert(ctx, userID, roomID, messageID); err != nil {
		h.logger.Warn("mark_read_failed", zap.Int("user_id", userID), zap.Int("room_id", roomID), zap.Error(err))
		// Don't send error to client — mark_read is best-effort.
	}
}
