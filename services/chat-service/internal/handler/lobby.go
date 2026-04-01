package handler

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// lobbyOfflineGrace is how long to wait before broadcasting user_offline after
// a lobby disconnect. During this window the old (dead) connection is still
// present in the manager's lobbyConns map, so HasLobbyConnection returns true
// and room handlers schedule their normal 10-second grace period rather than
// broadcasting user_left immediately. If the user reconnects within this window
// (e.g. page refresh) their new lobby connection is already registered by the
// time DisconnectLobby fires, so no user_offline is ever broadcast and the
// PM status indicator never flickers.
const lobbyOfflineGrace = 5 * time.Second

// LobbyHandler manages the lobby WebSocket endpoint used for PM delivery
// and real-time room list updates.
type LobbyHandler struct {
	manager   *ws.Manager
	secretKey string
	logger    *zap.Logger
}

// NewLobbyHandler creates a LobbyHandler.
func NewLobbyHandler(manager *ws.Manager, secretKey string, logger *zap.Logger) *LobbyHandler {
	return &LobbyHandler{
		manager:   manager,
		secretKey: secretKey,
		logger:    logger,
	}
}

// HandleLobbyWS upgrades to WebSocket and holds the connection for PM delivery.
// WS /ws/lobby?token=<jwt>
func (h *LobbyHandler) HandleLobbyWS(c *gin.Context) {
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

	// Enforce per-user connection limit to prevent resource exhaustion.
	if h.manager.UserConnectionCount(userID) >= maxConnectionsPerUser {
		c.JSON(http.StatusTooManyRequests, gin.H{"detail": "too many connections"})
		return
	}

	up := newUpgrader()
	conn, err := up.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		h.logger.Error("lobby_ws_upgrade_failed", zap.Error(err))
		return
	}

	// Set read size limit to prevent memory exhaustion.
	conn.SetReadLimit(maxMessageSize)

	// Start ping/pong heartbeat to detect dead connections.
	cancelPing := configurePingPong(conn, h.manager)
	defer cancelPing()

	user := ws.UserInfo{UserID: userID, Username: username}
	h.manager.ConnectLobby(conn, user)

	// Hold connection open — the lobby is primarily for server -> client push.
	// Read loop keeps the connection alive, detects disconnection, and handles
	// an explicit {"type":"logout"} message for immediate graceful logout.
	intentionalLogout := false
	for {
		_, msg, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure, websocket.CloseAbnormalClosure, websocket.CloseNoStatusReceived) {
				h.logger.Warn("lobby_ws_read_error", zap.Error(err))
			}
			break
		}
		var payload struct {
			Type string `json:"type"`
			To   string `json:"to"`
		}
		if json.Unmarshal(msg, &payload) == nil {
			switch payload.Type {
			case "logout":
				intentionalLogout = true
			case "typing_pm":
				if payload.To != "" {
					if recipientID, ok := h.manager.GetUserIDByUsername(payload.To); ok {
						h.manager.SendPersonal(recipientID, map[string]interface{}{
							"type": "typing_pm",
							"from": username,
						})
					}
				}
			}
		}
		if intentionalLogout {
			break
		}
	}

	// For intentional logouts skip the grace period — the user is gone now.
	// For unexpected closes (page refresh, network drop) keep the grace period
	// so the user's presence doesn't flicker while the browser reconnects.
	if !intentionalLogout {
		time.Sleep(lobbyOfflineGrace)
	}

	cleanup := h.manager.DisconnectLobby(conn)
	_ = conn.Close()

	// If the user fully logged out (no remaining lobby connections), the
	// manager evicted their zombie room connections. The closed connections
	// will trigger handleDisconnect in each room handler, which detects
	// the missing lobby and broadcasts user_left immediately (no grace period).
	if cleanup != nil {
		h.logger.Info("zombie_room_conns_evicted",
			zap.Int("user_id", cleanup.UserID),
			zap.String("username", cleanup.Username),
			zap.Int("rooms_cleaned", len(cleanup.RoomIDs)),
		)
	}
}
