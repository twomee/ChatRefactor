package handler

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/client"
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

	// maxConnectionsPerUser limits the total number of WebSocket connections
	// a single user can have open simultaneously (across all rooms + lobby).
	// Prevents resource exhaustion from a single authenticated user.
	maxConnectionsPerUser = 5

	// pingInterval is how often the server sends a WebSocket ping frame.
	// If the client doesn't respond with a pong within pongWait, the
	// connection is considered dead and closed.
	pingInterval = 30 * time.Second

	// pongWait is how long to wait for a pong response before closing.
	pongWait = 10 * time.Second
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
	authClient    *client.AuthClient
	secretKey     string
	logger        *zap.Logger
	limiter       *rateLimiter
	messageSvcURL string

	// kickedUsers tracks users that were kicked (by "room:user" key).
	// When a kicked user's readLoop exits, handleDisconnect checks this
	// set and skips the "user_left" broadcast to avoid duplicates.
	kickedMu    sync.Mutex
	kickedUsers map[string]bool

	// pendingLeaves tracks delayed leave broadcasts for reconnect grace period.
	// Key: "room:user" → cancel function. If the user reconnects within the
	// grace period, the pending leave is cancelled silently.
	pendingLeaveMu sync.Mutex
	pendingLeaves  map[string]context.CancelFunc
}

// NewWSHandler creates a WebSocket handler.
func NewWSHandler(
	manager *ws.Manager,
	store store.RoomRepository,
	delivery delivery.Strategy,
	authClient *client.AuthClient,
	secretKey string,
	messageServiceURL string,
	logger *zap.Logger,
) *WSHandler {
	return &WSHandler{
		manager:       manager,
		store:         store,
		delivery:      delivery,
		authClient:    authClient,
		secretKey:     secretKey,
		logger:        logger,
		limiter:       newRateLimiter(),
		messageSvcURL: messageServiceURL,
		kickedUsers:   make(map[string]bool),
		pendingLeaves: make(map[string]context.CancelFunc),
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

	// Verify user still exists in auth database. JWTs are stateless, so a
	// valid token might belong to a deleted/re-registered user. Without this
	// check, stale tokens create ghost connections that cause duplicate
	// messages and phantom presence.
	if h.authClient != nil {
		authUser, authErr := h.authClient.GetUserByID(c.Request.Context(), userID)
		if authErr != nil {
			h.logger.Warn("auth_user_lookup_failed", zap.Error(authErr))
			c.JSON(http.StatusServiceUnavailable, gin.H{"detail": "auth service unavailable"})
			return
		}
		if authUser == nil || authUser.Username != username {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "user no longer exists"})
			return
		}
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

	// If the user already has a connection in this room (e.g., a stale connection
	// left over from a page refresh or a previous session that has not yet timed
	// out), evict it so the incoming connection can join cleanly.  This is
	// preferable to returning 409 (which the browser maps to WS close code 1006
	// and the front-end does not retry), because the old connection is almost
	// certainly dead — the client would not be trying to reconnect otherwise.
	h.manager.CloseUserConnsInRoom(roomID, userID)

	// Enforce per-user connection limit to prevent resource exhaustion.
	if h.manager.UserConnectionCount(userID) >= maxConnectionsPerUser {
		c.JSON(http.StatusTooManyRequests, gin.H{"detail": "too many connections"})
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

	// Start ping/pong heartbeat to detect dead connections.
	cancelPing := configurePingPong(conn, h.manager)
	defer cancelPing()

	user := ws.UserInfo{UserID: userID, Username: username}
	h.manager.ConnectRoom(roomID, conn, user)

	// Auto-promote to admin if no admin is currently connected to this room.
	// Stale admin records (from users who left) are cleared so the first
	// user to join an empty room always becomes admin.
	ctx := context.Background()
	admins, _ := h.store.GetAdmins(ctx, roomID)
	hasConnectedAdmin := false
	for _, a := range admins {
		if h.manager.IsUserInRoom(roomID, a.UserID) {
			hasConnectedAdmin = true
			break
		}
	}
	if !hasConnectedAdmin {
		// Clear stale admin records from previous sessions.
		for _, a := range admins {
			_ = h.store.RemoveAdmin(ctx, roomID, a.UserID)
		}
		_, _ = h.store.AddAdmin(ctx, roomID, userID)
	}

	// Handle join: broadcast user_join and update room state.
	h.handleJoin(ctx, conn, roomID, userID, username, token)

	// Send message history asynchronously so readLoop can start immediately.
	// Starting readLoop first closes the eviction window: when a new connection
	// arrives and calls CloseUserConnsInRoom, the old connection's readLoop is
	// already running and will detect the close naturally (via a read error),
	// triggering a clean handleDisconnect rather than a silent eviction that
	// re-triggers the reconnect loop. The 3-second HTTP timeout in sendHistory
	// was the root cause of the K8s reconnect storm — it kept connections
	// registered in the manager maps long enough for the client's 1-second
	// retry to arrive and self-sustain the eviction cycle.
	go h.sendHistory(conn, roomID, token)

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

// configurePingPong sets up ping/pong heartbeat on a WebSocket connection.
// It sets a read deadline that gets extended every time a pong is received,
// and starts a goroutine that sends pings at a regular interval.
// The returned cancel function stops the ping goroutine.
func configurePingPong(conn *websocket.Conn, mgr *ws.Manager) func() {
	// Set initial read deadline — extended on each pong.
	_ = conn.SetReadDeadline(time.Now().Add(pingInterval + pongWait))

	conn.SetPongHandler(func(string) error {
		// Client responded — reset the read deadline.
		return conn.SetReadDeadline(time.Now().Add(pingInterval + pongWait))
	})

	// Start a goroutine that sends pings at the configured interval.
	done := make(chan struct{})
	go func() {
		ticker := time.NewTicker(pingInterval)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				deadline := time.Now().Add(pongWait)
				if err := conn.WriteControl(websocket.PingMessage, nil, deadline); err != nil {
					return
				}
			case <-done:
				return
			}
		}
	}()

	return func() { close(done) }
}

// sendError sends an error message to a single connection.
func (h *WSHandler) sendError(conn *websocket.Conn, detail string) {
	msg := map[string]interface{}{
		"type":   "error",
		"detail": detail,
	}
	_ = h.manager.SendToConn(conn, msg)
}
