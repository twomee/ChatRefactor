package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/delivery"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// PMHandler handles private message REST endpoints.
type PMHandler struct {
	manager    *ws.Manager
	authClient client.UserLookup
	delivery   delivery.Strategy
	logger     *zap.Logger
}

// NewPMHandler creates a PMHandler.
func NewPMHandler(
	manager *ws.Manager,
	authClient client.UserLookup,
	delivery delivery.Strategy,
	logger *zap.Logger,
) *PMHandler {
	return &PMHandler{
		manager:    manager,
		authClient: authClient,
		delivery:   delivery,
		logger:     logger,
	}
}

// SendPM handles POST /pm/send. It looks up the recipient via the Auth
// Service, delivers the PM over the lobby WebSocket if the recipient is
// online, and produces to Kafka for persistence.
func (h *PMHandler) SendPM(c *gin.Context) {
	var req model.SendPMRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	senderID, _ := c.Get(middleware.CtxUserID)
	senderName, _ := c.Get(middleware.CtxUsername)

	// Cannot PM yourself.
	if req.ToUsername == senderName.(string) {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "cannot send PM to yourself"})
		return
	}

	// Look up recipient.
	recipient, err := h.authClient.GetUserByUsername(c.Request.Context(), req.ToUsername)
	if err != nil {
		h.logger.Error("pm_recipient_lookup_failed", zap.Error(err))
		c.JSON(http.StatusBadGateway, gin.H{"detail": "failed to look up recipient"})
		return
	}
	if recipient == nil {
		c.JSON(http.StatusNotFound, gin.H{"detail": "recipient not found"})
		return
	}

	now := time.Now().UTC()

	// Build WebSocket message matching the format the frontend expects.
	wsMsg := map[string]interface{}{
		"type":      "private_message",
		"from":      senderName.(string),
		"to":        recipient.Username,
		"text":      req.Content,
		"timestamp": now.Format(time.RFC3339),
	}

	// Try live delivery via lobby WebSocket.
	// No self-echo needed — the frontend adds the message to local state
	// immediately after the REST call succeeds (ChatPage.jsx).
	delivered := h.manager.SendPersonal(recipient.ID, wsMsg)

	// Kafka payload uses "sender"/"recipient" field names to match what the
	// message-service persistence consumer expects.
	kafkaPayload := map[string]interface{}{
		"type":      "private_message",
		"msg_id":    fmt.Sprintf("pm-%d-%d-%d", senderID.(int), recipient.ID, now.UnixNano()),
		"sender":    senderName.(string),
		"sender_id": senderID.(int),
		"recipient": recipient.Username,
		"text":      req.Content,
		"timestamp": now.Format(time.RFC3339),
	}
	payload, _ := json.Marshal(kafkaPayload)
	if err := h.delivery.DeliverPM(c.Request.Context(), senderID.(int), payload); err != nil {
		h.logger.Warn("pm_kafka_deliver_failed", zap.Error(err))
	}

	c.JSON(http.StatusOK, gin.H{
		"detail":         "PM sent",
		"live_delivered": delivered,
	})
}
