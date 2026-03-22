package handler

import (
	"encoding/json"
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

	pm := model.PrivateMessage{
		Type:       "private_message",
		FromUserID: senderID.(int),
		FromUser:   senderName.(string),
		ToUserID:   recipient.ID,
		ToUser:     recipient.Username,
		Content:    req.Content,
		Timestamp:  time.Now().UTC(),
	}

	// Try live delivery via lobby WebSocket.
	delivered := h.manager.SendPersonal(recipient.ID, pm)

	// Always produce to Kafka for persistence regardless of live delivery.
	payload, _ := json.Marshal(pm)
	if err := h.delivery.DeliverPM(c.Request.Context(), senderID.(int), payload); err != nil {
		h.logger.Warn("pm_kafka_deliver_failed", zap.Error(err))
	}

	c.JSON(http.StatusOK, gin.H{
		"detail":         "PM sent",
		"live_delivered": delivered,
	})
}
