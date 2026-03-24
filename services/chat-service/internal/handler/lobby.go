package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

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
	// Read loop just keeps the connection alive and detects disconnection.
	for {
		if _, _, err := conn.ReadMessage(); err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				h.logger.Warn("lobby_ws_read_error", zap.Error(err))
			}
			break
		}
	}

	h.manager.DisconnectLobby(conn)
	_ = conn.Close()
}
