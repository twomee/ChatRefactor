package handler

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"

	"github.com/gin-gonic/gin"
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

// WSHandler handles WebSocket upgrades for room chat.
type WSHandler struct {
	manager       *ws.Manager
	store         store.RoomRepository
	delivery      delivery.Strategy
	secretKey     string
	logger        *zap.Logger
	limiter       *rateLimiter
	messageSvcURL string

	// kickedUsers tracks users that were kicked (by "room:user" key).
	// When a kicked user's readLoop exits, handleDisconnect checks this
	// set and skips the "user_left" broadcast to avoid duplicates.
	kickedMu    sync.Mutex
	kickedUsers map[string]bool
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
		kickedUsers:   make(map[string]bool),
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

	// Check for duplicate user in room before upgrading.
	if h.manager.IsUserInRoom(roomID, userID) {
		c.JSON(http.StatusConflict, gin.H{"detail": "user already in room"})
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

	// Handle join: broadcast, send history.
	h.handleJoin(ctx, conn, roomID, userID, username, token)

	// Blocking read loop -- runs until the client disconnects.
	h.readLoop(conn, roomID, userID, username)

	// Cleanup on disconnect.
	h.handleDisconnect(ctx, conn, roomID, userID, username)
}

// markKicked records that a user was kicked from a room.
func (h *WSHandler) markKicked(roomID, userID int) {
	h.kickedMu.Lock()
	h.kickedUsers[fmt.Sprintf("%d:%d", roomID, userID)] = true
	h.kickedMu.Unlock()
}

// wasKicked checks and clears the kicked flag for a user.
func (h *WSHandler) wasKicked(roomID, userID int) bool {
	key := fmt.Sprintf("%d:%d", roomID, userID)
	h.kickedMu.Lock()
	defer h.kickedMu.Unlock()
	if h.kickedUsers[key] {
		delete(h.kickedUsers, key)
		return true
	}
	return false
}

// sendError sends an error message to a single connection.
func (h *WSHandler) sendError(conn *websocket.Conn, detail string) {
	msg := map[string]interface{}{
		"type":   "error",
		"detail": detail,
	}
	_ = h.manager.SendToConn(conn, msg)
}
