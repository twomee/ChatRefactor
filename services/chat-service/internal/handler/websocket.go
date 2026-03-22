package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/delivery"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/store"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	// In production, restrict origins. For dev, allow all.
	CheckOrigin: func(r *http.Request) bool { return true },
}

// WSHandler handles WebSocket upgrades for room chat.
type WSHandler struct {
	manager   *ws.Manager
	store     *store.RoomStore
	delivery  delivery.Strategy
	secretKey string
	logger    *zap.Logger
}

// NewWSHandler creates a WebSocket handler.
func NewWSHandler(
	manager *ws.Manager,
	store *store.RoomStore,
	delivery delivery.Strategy,
	secretKey string,
	logger *zap.Logger,
) *WSHandler {
	return &WSHandler{
		manager:   manager,
		store:     store,
		delivery:  delivery,
		secretKey: secretKey,
		logger:    logger,
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

	// Check if user is muted.
	muted, _ := h.store.IsMuted(c.Request.Context(), roomID, userID)

	// Upgrade to WebSocket.
	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		h.logger.Error("ws_upgrade_failed", zap.Error(err))
		return
	}

	user := ws.UserInfo{UserID: userID, Username: username}
	h.manager.ConnectRoom(roomID, conn, user)

	// Broadcast join event.
	joinMsg := model.ChatMessage{
		Type:      "join",
		RoomID:    roomID,
		UserID:    userID,
		Username:  username,
		Content:   username + " joined the room",
		Timestamp: time.Now().UTC(),
	}
	h.manager.BroadcastRoom(roomID, joinMsg)

	// Blocking read loop — runs until the client disconnects.
	h.readLoop(conn, roomID, userID, username, muted)

	// Cleanup on disconnect.
	h.manager.DisconnectRoom(roomID, conn)
	_ = conn.Close()

	leaveMsg := model.ChatMessage{
		Type:      "leave",
		RoomID:    roomID,
		UserID:    userID,
		Username:  username,
		Content:   username + " left the room",
		Timestamp: time.Now().UTC(),
	}
	h.manager.BroadcastRoom(roomID, leaveMsg)
}

// readLoop reads messages from the client and broadcasts them.
func (h *WSHandler) readLoop(conn *websocket.Conn, roomID, userID int, username string, muted bool) {
	for {
		_, raw, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				h.logger.Warn("ws_read_error", zap.Error(err))
			}
			return
		}

		// Parse the incoming message.
		var incoming struct {
			Content string `json:"content"`
		}
		if err := json.Unmarshal(raw, &incoming); err != nil || incoming.Content == "" {
			continue // skip malformed messages
		}

		if muted {
			// Muted users cannot broadcast — send an error back to them only.
			errMsg := gin.H{"type": "error", "content": "You are muted in this room"}
			_ = conn.WriteJSON(errMsg)
			continue
		}

		msg := model.ChatMessage{
			Type:      "message",
			RoomID:    roomID,
			UserID:    userID,
			Username:  username,
			Content:   incoming.Content,
			Timestamp: time.Now().UTC(),
		}

		// Broadcast to all connections in the room.
		h.manager.BroadcastRoom(roomID, msg)

		// Produce to Kafka for persistence.
		payload, _ := json.Marshal(msg)
		if err := h.delivery.DeliverChat(context.Background(), roomID, payload); err != nil {
			h.logger.Warn("kafka_chat_deliver_failed", zap.Error(err))
		}
	}
}
