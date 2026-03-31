package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/delivery"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

const errMsgIDRequired = "msg_id is required"

// PMActionsHandler handles REST endpoints for PM edit, delete, and reaction.
type PMActionsHandler struct {
	manager  *ws.Manager
	delivery delivery.Strategy
	logger   *zap.Logger
}

// NewPMActionsHandler creates a PMActionsHandler.
func NewPMActionsHandler(
	manager *ws.Manager,
	delivery delivery.Strategy,
	logger *zap.Logger,
) *PMActionsHandler {
	return &PMActionsHandler{
		manager:  manager,
		delivery: delivery,
		logger:   logger,
	}
}

// parsePMMsgID extracts sender and recipient user IDs from a PM message ID.
// Format: "pm-{senderID}-{recipientID}-{timestamp}"
func parsePMMsgID(msgID string) (senderID int, recipientID int, err error) {
	parts := strings.SplitN(msgID, "-", 4)
	if len(parts) != 4 || parts[0] != "pm" {
		return 0, 0, fmt.Errorf("invalid PM message ID format")
	}
	senderID, err = strconv.Atoi(parts[1])
	if err != nil {
		return 0, 0, fmt.Errorf("invalid sender ID in message ID")
	}
	recipientID, err = strconv.Atoi(parts[2])
	if err != nil {
		return 0, 0, fmt.Errorf("invalid recipient ID in message ID")
	}
	return senderID, recipientID, nil
}

// EditPM handles PATCH /pm/edit/:msg_id
// Verifies the requester is the original sender, produces a Kafka event for
// persistence, and pushes a real-time WS event to both sender and recipient.
func (h *PMActionsHandler) EditPM(c *gin.Context) {
	msgID := c.Param("msg_id")
	if strings.TrimSpace(msgID) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": errMsgIDRequired})
		return
	}

	var req struct {
		Text string `json:"text" binding:"required,min=1,max=4096"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	userID, _ := c.Get(middleware.CtxUserID)
	username, _ := c.Get(middleware.CtxUsername)

	origSenderID, recipientID, err := parsePMMsgID(msgID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	// Only the original sender can edit the message.
	if userID.(int) != origSenderID {
		c.JSON(http.StatusForbidden, gin.H{"detail": "you can only edit your own messages"})
		return
	}

	now := time.Now().UTC()

	// Produce Kafka event for persistence.
	kafkaMsg := map[string]interface{}{
		"type":      "edit_pm",
		"msg_id":    msgID,
		"sender_id": userID.(int),
		"username":  username.(string),
		"text":      req.Text,
		"timestamp": now.Format(time.RFC3339),
	}
	payload, _ := json.Marshal(kafkaMsg)
	if err := h.delivery.DeliverPM(c.Request.Context(), userID.(int), payload); err != nil {
		h.logger.Warn("pm_edit_kafka_failed", zap.Error(err))
	}

	// Push real-time WS event to both sender and recipient.
	wsMsg := map[string]interface{}{
		"type":      "pm_message_edited",
		"msg_id":    msgID,
		"text":      req.Text,
		"from":      username.(string),
		"to":        "", // filled below if known
		"edited_at": now.Format(time.RFC3339),
	}

	// Deliver to recipient via lobby.
	h.manager.SendPersonal(recipientID, wsMsg)
	// Also deliver to sender (other tabs).
	h.manager.SendPersonal(userID.(int), wsMsg)

	c.JSON(http.StatusOK, gin.H{"detail": "PM edited"})
}

// DeletePM handles DELETE /pm/delete/:msg_id
func (h *PMActionsHandler) DeletePM(c *gin.Context) {
	msgID := c.Param("msg_id")
	if strings.TrimSpace(msgID) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": errMsgIDRequired})
		return
	}

	userID, _ := c.Get(middleware.CtxUserID)
	username, _ := c.Get(middleware.CtxUsername)

	origSenderID, recipientID, err := parsePMMsgID(msgID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	if userID.(int) != origSenderID {
		c.JSON(http.StatusForbidden, gin.H{"detail": "you can only delete your own messages"})
		return
	}

	now := time.Now().UTC()

	kafkaMsg := map[string]interface{}{
		"type":      "delete_pm",
		"msg_id":    msgID,
		"sender_id": userID.(int),
		"username":  username.(string),
		"timestamp": now.Format(time.RFC3339),
	}
	payload, _ := json.Marshal(kafkaMsg)
	if err := h.delivery.DeliverPM(c.Request.Context(), userID.(int), payload); err != nil {
		h.logger.Warn("pm_delete_kafka_failed", zap.Error(err))
	}

	wsMsg := map[string]interface{}{
		"type":   "pm_message_deleted",
		"msg_id": msgID,
		"from":   username.(string),
	}
	h.manager.SendPersonal(recipientID, wsMsg)
	h.manager.SendPersonal(userID.(int), wsMsg)

	c.JSON(http.StatusOK, gin.H{"detail": "PM deleted"})
}

// AddPMReaction handles POST /pm/reaction/:msg_id
func (h *PMActionsHandler) AddPMReaction(c *gin.Context) {
	msgID := c.Param("msg_id")
	if strings.TrimSpace(msgID) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": errMsgIDRequired})
		return
	}

	var req struct {
		Emoji string `json:"emoji" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	if len(req.Emoji) > 32 {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "emoji too long"})
		return
	}

	userID, _ := c.Get(middleware.CtxUserID)
	username, _ := c.Get(middleware.CtxUsername)

	origSenderID, recipientID, err := parsePMMsgID(msgID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	// Both sender and recipient can react.
	kafkaMsg := map[string]interface{}{
		"type":       "add_pm_reaction",
		"msg_id":     msgID,
		"emoji":      req.Emoji,
		"reactor_id": userID.(int),
		"reactor":    username.(string),
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	}
	payload, _ := json.Marshal(kafkaMsg)
	if err := h.delivery.DeliverPM(c.Request.Context(), userID.(int), payload); err != nil {
		h.logger.Warn("pm_reaction_kafka_failed", zap.Error(err))
	}

	wsMsg := map[string]interface{}{
		"type":       "pm_reaction_added",
		"msg_id":     msgID,
		"emoji":      req.Emoji,
		"reactor":    username.(string),
		"reactor_id": userID.(int),
		"from":       "", // determined by the msg_id participants
	}

	// Deliver to both participants.
	h.manager.SendPersonal(origSenderID, wsMsg)
	if recipientID != origSenderID {
		h.manager.SendPersonal(recipientID, wsMsg)
	}

	c.JSON(http.StatusOK, gin.H{"detail": "reaction added"})
}

// RemovePMReaction handles DELETE /pm/reaction/:msg_id/:emoji
func (h *PMActionsHandler) RemovePMReaction(c *gin.Context) {
	msgID := c.Param("msg_id")
	emoji := c.Param("emoji")

	if strings.TrimSpace(msgID) == "" || strings.TrimSpace(emoji) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "msg_id and emoji are required"})
		return
	}

	userID, _ := c.Get(middleware.CtxUserID)
	username, _ := c.Get(middleware.CtxUsername)

	origSenderID, recipientID, err := parsePMMsgID(msgID)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	kafkaMsg := map[string]interface{}{
		"type":       "remove_pm_reaction",
		"msg_id":     msgID,
		"emoji":      emoji,
		"reactor_id": userID.(int),
		"reactor":    username.(string),
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	}
	payload, _ := json.Marshal(kafkaMsg)
	if err := h.delivery.DeliverPM(c.Request.Context(), userID.(int), payload); err != nil {
		h.logger.Warn("pm_reaction_remove_kafka_failed", zap.Error(err))
	}

	wsMsg := map[string]interface{}{
		"type":    "pm_reaction_removed",
		"msg_id":  msgID,
		"emoji":   emoji,
		"reactor": username.(string),
	}
	h.manager.SendPersonal(origSenderID, wsMsg)
	if recipientID != origSenderID {
		h.manager.SendPersonal(recipientID, wsMsg)
	}

	c.JSON(http.StatusOK, gin.H{"detail": "reaction removed"})
}
