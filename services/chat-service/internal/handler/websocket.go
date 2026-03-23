package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/delivery"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/store"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

const (
	// maxMessageSize is the maximum WebSocket message size in bytes (64 KB).
	// This prevents malicious clients from sending enormous payloads to
	// exhaust server memory.
	maxMessageSize = 64 * 1024

	// maxContentLength is the maximum chat message content length in characters.
	maxContentLength = 4096

	// rateLimitWindow is the sliding window for rate limiting.
	rateLimitWindow = 10 * time.Second

	// rateLimitMax is the maximum messages per window per user.
	rateLimitMax = 30
)

// IncomingMessage is the generic envelope parsed from the WebSocket client.
// The "type" field determines which fields are relevant:
//
//   - "message":         uses Text
//   - "kick","mute","unmute","promote": uses Target (username)
//   - "private_message": uses To and Text
type IncomingMessage struct {
	Type   string `json:"type"`
	Text   string `json:"text"`
	Target string `json:"target"`
	To     string `json:"to"`
}

// newUpgrader creates a WebSocket upgrader with origin checking.
// In production, only the configured allowed origins are accepted.
// In dev mode, all origins are allowed for convenience.
func newUpgrader() websocket.Upgrader {
	return websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin:     checkOrigin,
	}
}

// checkOrigin validates the request origin against allowed origins.
// In dev mode or when ALLOWED_ORIGINS is not set, all origins are allowed.
func checkOrigin(r *http.Request) bool {
	env := os.Getenv("APP_ENV")
	if env == "" || strings.EqualFold(env, "dev") || strings.EqualFold(env, "test") {
		return true
	}

	allowed := os.Getenv("ALLOWED_ORIGINS")
	if allowed == "" {
		return true // no restriction configured
	}

	origin := r.Header.Get("Origin")
	if origin == "" {
		return false // production requires an origin header
	}

	for _, o := range strings.Split(allowed, ",") {
		if strings.TrimSpace(o) == origin {
			return true
		}
	}
	return false
}

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

// WSHandler handles WebSocket upgrades for room chat.
type WSHandler struct {
	manager         *ws.Manager
	store           store.RoomRepository
	delivery        delivery.Strategy
	secretKey       string
	logger          *zap.Logger
	limiter         *rateLimiter
	messageSvcURL   string
}

// NewWSHandler creates a WebSocket handler.
func NewWSHandler(
	manager *ws.Manager,
	store store.RoomRepository,
	delivery delivery.Strategy,
	secretKey string,
	logger *zap.Logger,
) *WSHandler {
	msgURL := os.Getenv("MESSAGE_SERVICE_URL")
	if msgURL == "" {
		msgURL = "http://message-service:8004"
	}
	return &WSHandler{
		manager:       manager,
		store:         store,
		delivery:      delivery,
		secretKey:     secretKey,
		logger:        logger,
		limiter:       newRateLimiter(),
		messageSvcURL: msgURL,
	}
}

// HandleRoomWS upgrades the connection and enters the read/write loop.
// Authentication is via ?token= query parameter (WebSocket clients can't
// set Authorization headers reliably).
//
// WS /ws/:roomId?token=<jwt>
func (h *WSHandler) HandleRoomWS(c *gin.Context) {
	roomIDStr := c.Param("roomId")
	roomID, err := strconv.Atoi(roomIDStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid room id"})
		return
	}

	// Authenticate via query param token.
	token := c.Query("token")
	if token == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"detail": "missing token"})
		return
	}

	userID, username, err := middleware.ParseTokenFromString(token, h.secretKey)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"detail": "invalid token"})
		return
	}

	// Verify room exists and is active.
	room, err := h.store.GetByID(c.Request.Context(), roomID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"detail": "room not found"})
		return
	}
	if !room.IsActive {
		c.JSON(http.StatusForbidden, gin.H{"detail": "room is inactive"})
		return
	}

	// Upgrade to WebSocket.
	up := newUpgrader()
	conn, err := up.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		h.logger.Error("ws_upgrade_failed", zap.Error(err))
		return
	}

	// Set read size limit to prevent memory exhaustion from oversized frames.
	conn.SetReadLimit(maxMessageSize)

	user := ws.UserInfo{UserID: userID, Username: username}
	h.manager.ConnectRoom(roomID, conn, user)

	// If this is the first user in the room, make them admin.
	ctx := context.Background()
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		users := h.manager.GetUsersInRoom(roomID)
		if len(users) == 1 {
			_, _ = h.store.AddAdmin(ctx, roomID, userID)
		}
	}

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

	// Send message history to the newly joined connection.
	h.sendHistory(conn, roomID, token)

	// Blocking read loop — runs until the client disconnects.
	h.readLoop(conn, roomID, userID, username)

	// Cleanup on disconnect.
	h.manager.DisconnectRoom(roomID, conn)
	_ = conn.Close()

	// Handle admin succession before broadcasting leave.
	h.handleAdminSuccession(ctx, roomID, userID, username)

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

// ---------- Message type handlers ----------

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
	kafkaMsg := map[string]interface{}{
		"type":      "message",
		"room_id":   roomID,
		"user_id":   userID,
		"username":  username,
		"content":   text,
		"msg_id":    msgID,
		"timestamp": now.Format(time.RFC3339),
	}
	payload, _ := json.Marshal(kafkaMsg)
	if err := h.delivery.DeliverChat(ctx, roomID, payload); err != nil {
		h.logger.Warn("kafka_chat_deliver_failed", zap.Error(err))
	}
}

// handleKick processes an admin kick command.
func (h *WSHandler) handleKick(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, target string) {
	if target == "" {
		h.sendError(conn, "Target username required")
		return
	}

	// Check caller is admin.
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		h.sendError(conn, "Admin access required")
		return
	}

	// Cannot kick yourself.
	if target == username {
		h.sendError(conn, "Cannot kick yourself")
		return
	}

	// Find target user in room.
	targetID, found := h.manager.FindUserIDByUsername(roomID, target)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	// Cannot kick another admin.
	targetIsAdmin, _ := h.store.IsAdmin(ctx, roomID, targetID)
	if targetIsAdmin {
		h.sendError(conn, "Cannot kick an admin")
		return
	}

	// Send kicked message to target before closing their connections.
	kickedMsg := map[string]interface{}{
		"type":    "kicked",
		"room_id": roomID,
	}
	h.manager.SendToUserInRoom(roomID, targetID, kickedMsg)

	// Small delay so the kicked message is delivered before close.
	time.Sleep(50 * time.Millisecond)

	// Close target's connections.
	h.manager.CloseUserConnsInRoom(roomID, targetID)

	// Broadcast system message about the kick.
	systemMsg := map[string]interface{}{
		"type":    "message",
		"from":    "system",
		"text":    fmt.Sprintf("%s was kicked by %s", target, username),
		"room_id": roomID,
		"msg_id":  uuid.New().String(),
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	h.manager.BroadcastRoom(roomID, systemMsg)

	// Broadcast updated user list.
	updatedUsers := h.manager.GetUsernamesInRoom(roomID)
	adminNames := h.getAdminUsernames(ctx, roomID)
	mutedNames := h.getMutedUsernames(ctx, roomID)
	updateMsg := map[string]interface{}{
		"type":     "user_left",
		"username": target,
		"users":    updatedUsers,
		"admins":   adminNames,
		"muted":    mutedNames,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, updateMsg)
}

// handleMute processes an admin mute command.
func (h *WSHandler) handleMute(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, target string) {
	if target == "" {
		h.sendError(conn, "Target username required")
		return
	}

	// Check caller is admin.
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		h.sendError(conn, "Admin access required")
		return
	}

	// Cannot mute yourself.
	if target == username {
		h.sendError(conn, "Cannot mute yourself")
		return
	}

	// Find target user.
	targetID, found := h.manager.FindUserIDByUsername(roomID, target)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	// Cannot mute another admin.
	targetIsAdmin, _ := h.store.IsAdmin(ctx, roomID, targetID)
	if targetIsAdmin {
		h.sendError(conn, "Cannot mute an admin")
		return
	}

	// Check not already muted.
	alreadyMuted, _ := h.store.IsMuted(ctx, roomID, targetID)
	if alreadyMuted {
		h.sendError(conn, "User is already muted")
		return
	}

	// Mute in database.
	_, err := h.store.MuteUser(ctx, roomID, targetID)
	if err != nil {
		h.logger.Error("mute_user_failed", zap.Error(err))
		h.sendError(conn, "Failed to mute user")
		return
	}

	// Broadcast muted event.
	mutedMsg := map[string]interface{}{
		"type":     "muted",
		"username": target,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, mutedMsg)
}

// handleUnmute processes an admin unmute command.
func (h *WSHandler) handleUnmute(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, target string) {
	if target == "" {
		h.sendError(conn, "Target username required")
		return
	}

	// Check caller is admin.
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		h.sendError(conn, "Admin access required")
		return
	}

	// Find target user.
	targetID, found := h.manager.FindUserIDByUsername(roomID, target)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	// Check currently muted.
	isMuted, _ := h.store.IsMuted(ctx, roomID, targetID)
	if !isMuted {
		h.sendError(conn, "User is not muted")
		return
	}

	// Unmute in database.
	if err := h.store.UnmuteUser(ctx, roomID, targetID); err != nil {
		h.logger.Error("unmute_user_failed", zap.Error(err))
		h.sendError(conn, "Failed to unmute user")
		return
	}

	// Broadcast unmuted event.
	unmutedMsg := map[string]interface{}{
		"type":     "unmuted",
		"username": target,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, unmutedMsg)
}

// handlePromote processes an admin promote command.
func (h *WSHandler) handlePromote(ctx context.Context, conn *websocket.Conn, roomID, userID int, username, target string) {
	if target == "" {
		h.sendError(conn, "Target username required")
		return
	}

	// Check caller is admin.
	isAdmin, _ := h.store.IsAdmin(ctx, roomID, userID)
	if !isAdmin {
		h.sendError(conn, "Admin access required")
		return
	}

	// Cannot promote yourself.
	if target == username {
		h.sendError(conn, "Cannot promote yourself")
		return
	}

	// Find target user.
	targetID, found := h.manager.FindUserIDByUsername(roomID, target)
	if !found {
		h.sendError(conn, "User not in room")
		return
	}

	// Cannot promote already-admin.
	targetIsAdmin, _ := h.store.IsAdmin(ctx, roomID, targetID)
	if targetIsAdmin {
		h.sendError(conn, "User is already an admin")
		return
	}

	// Cannot promote muted user.
	isMuted, _ := h.store.IsMuted(ctx, roomID, targetID)
	if isMuted {
		h.sendError(conn, "Cannot promote a muted user")
		return
	}

	// Add admin in database.
	_, err := h.store.AddAdmin(ctx, roomID, targetID)
	if err != nil {
		h.logger.Error("promote_user_failed", zap.Error(err))
		h.sendError(conn, "Failed to promote user")
		return
	}

	// Broadcast new_admin event.
	promoteMsg := map[string]interface{}{
		"type":     "new_admin",
		"username": target,
		"room_id":  roomID,
	}
	h.manager.BroadcastRoom(roomID, promoteMsg)
}

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

// ---------- Helper methods ----------

// sendError sends an error message to a single connection.
func (h *WSHandler) sendError(conn *websocket.Conn, detail string) {
	msg := map[string]interface{}{
		"type":   "error",
		"detail": detail,
	}
	_ = h.manager.SendToConn(conn, msg)
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

	var messages []interface{}
	if err := json.NewDecoder(resp.Body).Decode(&messages); err != nil {
		// Try decoding as an object with a "messages" key.
		messages = []interface{}{}
	}

	historyMsg := map[string]interface{}{
		"type":     "history",
		"messages": messages,
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
