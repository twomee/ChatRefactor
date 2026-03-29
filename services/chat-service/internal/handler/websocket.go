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
//   - "edit_message":    uses MessageID and Text
//   - "delete_message":  uses MessageID
//   - "add_reaction","remove_reaction": uses MsgID and Emoji
type IncomingMessage struct {
	Type      string `json:"type"`
	Text      string `json:"text"`
	Target    string `json:"target"`
	To        string `json:"to"`
	MessageID string `json:"msg_id"`
	Emoji     string `json:"emoji"`
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
// In dev mode, all origins are allowed. In production, ALLOWED_ORIGINS must
// be configured — if missing, all origins are denied (fail-closed).
func checkOrigin(r *http.Request) bool {
	env := os.Getenv("APP_ENV")
	if env == "" || strings.EqualFold(env, "dev") || strings.EqualFold(env, "test") {
		return true
	}

	allowed := os.Getenv("ALLOWED_ORIGINS")
	if allowed == "" {
		return false // fail-closed: deny all origins when not configured in production
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
	manager           *ws.Manager
	store             store.RoomRepository
	readPositionStore store.ReadPositionRepository
	delivery          delivery.Strategy
	authClient        *client.AuthClient
	secretKey         string
	logger            *zap.Logger
	limiter           *rateLimiter
	messageSvcURL     string

	// kickedUsers tracks users that were kicked (by "room:user" key).
	// When a kicked user's readLoop exits, handleDisconnect checks this
	// set and skips the "user_left" broadcast to avoid duplicates.
	kickedMu    sync.Mutex
	kickedUsers map[string]bool

	// leftUsers tracks users that sent an intentional "leave" command.
	// When readLoop exits after handleLeave, handleDisconnect checks this
	// and skips the grace period (leave was already broadcast).
	leftMu    sync.Mutex
	leftUsers map[string]bool

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
	readPositionStore store.ReadPositionRepository,
	delivery delivery.Strategy,
	authClient *client.AuthClient,
	secretKey string,
	messageServiceURL string,
	logger *zap.Logger,
) *WSHandler {
	h := &WSHandler{
		manager:           manager,
		store:             store,
		readPositionStore: readPositionStore,
		delivery:          delivery,
		authClient:        authClient,
		secretKey:         secretKey,
		logger:            logger,
		limiter:           newRateLimiter(),
		messageSvcURL:     messageServiceURL,
		kickedUsers:       make(map[string]bool),
		leftUsers:         make(map[string]bool),
		pendingLeaves:     make(map[string]context.CancelFunc),
	}

	// When a user fully logs out (last lobby closes), cancel any pending
	// grace-period leave timers and broadcast user_left immediately.
	// This handles the case where room sockets close before the lobby.
	manager.OnFullLogout(h.flushPendingLeaves)

	return h
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

	// Reject room connections from users without a lobby connection.
	// A user without a lobby is logged out — any room connection attempt is a
	// zombie reconnect from a stale timer and must be refused so it can't
	// cancel a pending user_left broadcast or create ghost presence.
	if !h.manager.HasLobbyConnection(userID) {
		h.logger.Info("room_ws_rejected_no_lobby",
			zap.Int("room_id", roomID),
			zap.Int("user_id", userID),
		)
		c.JSON(http.StatusForbidden, gin.H{"detail": "no lobby connection"})
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

	// Auto-promote to admin if no admin is currently connected to this room.
	// Done BEFORE ConnectRoom so these DB calls do not delay readLoop startup.
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

	// Register conn — readLoop must start with zero additional delay from
	// this point. All remaining setup (join broadcast, Kafka writes, history)
	// runs in a single goroutine so readLoop is never blocked by DB queries
	// or Kafka backpressure.
	//
	// Why this matters: during a reconnect storm each new connection evicts
	// the previous one via CloseUserConnsInRoom. If readLoop has not started
	// yet, the eviction is silent (no ws_room_disconnect log), the goroutine
	// stays blocked on Kafka, and the storm sustains. With readLoop running
	// immediately, evictions are detected cleanly: readLoop exits → clean
	// handleDisconnect → client's onclose fires, but the new connection is
	// already in socketsRef, so the retry guard prevents a new connection
	// from being created and the storm dies in one cycle.
	silent := c.Query("silent") == "1"
	user := ws.UserInfo{UserID: userID, Username: username}
	h.manager.ConnectRoom(roomID, conn, user)
	go func() {
		h.handleJoin(ctx, conn, roomID, userID, username, token, silent)
		h.sendHistory(conn, roomID, token)
		h.sendReadPosition(ctx, conn, roomID, userID)
	}()

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
