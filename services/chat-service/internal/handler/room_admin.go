package handler

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/model"
)

// isCallerRoomOrGlobalAdmin checks if the caller is a room admin or a global admin.
// Returns true if authorized, false otherwise (and writes the HTTP error response).
func (h *RoomHandler) isCallerRoomOrGlobalAdmin(c *gin.Context, roomID int) bool {
	callerID, _ := c.Get(middleware.CtxUserID)

	// Check room admin first (fast, local DB query).
	isAdmin, _ := h.store.IsAdmin(c.Request.Context(), roomID, callerID.(int))
	if isAdmin {
		return true
	}

	// Fall back to global admin check via auth service.
	caller, err := h.authClient.GetUserByID(c.Request.Context(), callerID.(int))
	if err != nil {
		h.logger.Error("admin_check_failed", zap.Error(err))
		c.JSON(http.StatusBadGateway, gin.H{"detail": "failed to verify admin status"})
		return false
	}
	if caller != nil && caller.IsGlobalAdmin {
		return true
	}

	c.JSON(http.StatusForbidden, gin.H{"detail": "admin access required"})
	return false
}

// AddAdmin appoints a user as room admin. Requires room admin or global admin.
// POST /rooms/:id/admins
func (h *RoomHandler) AddAdmin(c *gin.Context) {
	roomID, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid room id"})
		return
	}

	if !h.isCallerRoomOrGlobalAdmin(c, roomID) {
		return
	}

	var req model.AddAdminRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	admin, err := h.store.AddAdmin(c.Request.Context(), roomID, req.UserID)
	if err != nil {
		h.logger.Warn("add_admin_error", zap.Error(err))
		c.JSON(http.StatusConflict, gin.H{"detail": "failed to add admin"})
		return
	}
	c.JSON(http.StatusCreated, admin)
}

// RemoveAdmin removes a user's admin role. Requires room admin or global admin.
// DELETE /rooms/:id/admins/:userId
func (h *RoomHandler) RemoveAdmin(c *gin.Context) {
	roomID, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid room id"})
		return
	}

	if !h.isCallerRoomOrGlobalAdmin(c, roomID) {
		return
	}

	userID, err := strconv.Atoi(c.Param("userId"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid user id"})
		return
	}

	if err := h.store.RemoveAdmin(c.Request.Context(), roomID, userID); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			c.JSON(http.StatusNotFound, gin.H{"detail": "admin not found"})
			return
		}
		h.logger.Error("remove_admin_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to remove admin"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"detail": "admin removed"})
}

// MuteUser mutes a user in a room.
// POST /rooms/:id/mutes
func (h *RoomHandler) MuteUser(c *gin.Context) {
	roomID, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid room id"})
		return
	}

	// Only room admins or the user themselves can mute.
	callerID, _ := c.Get(middleware.CtxUserID)
	isAdmin, _ := h.store.IsAdmin(c.Request.Context(), roomID, callerID.(int))
	if !isAdmin {
		c.JSON(http.StatusForbidden, gin.H{"detail": "admin access required"})
		return
	}

	var req model.MuteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	muted, err := h.store.MuteUser(c.Request.Context(), roomID, req.UserID)
	if err != nil {
		h.logger.Warn("mute_user_error", zap.Error(err))
		c.JSON(http.StatusConflict, gin.H{"detail": "failed to mute user"})
		return
	}
	c.JSON(http.StatusCreated, muted)
}

// UnmuteUser removes a mute.
// DELETE /rooms/:id/mutes/:userId
func (h *RoomHandler) UnmuteUser(c *gin.Context) {
	roomID, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid room id"})
		return
	}
	userID, err := strconv.Atoi(c.Param("userId"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid user id"})
		return
	}

	// Only room admins can unmute.
	callerID, _ := c.Get(middleware.CtxUserID)
	isAdmin, _ := h.store.IsAdmin(c.Request.Context(), roomID, callerID.(int))
	if !isAdmin {
		c.JSON(http.StatusForbidden, gin.H{"detail": "admin access required"})
		return
	}

	if err := h.store.UnmuteUser(c.Request.Context(), roomID, userID); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			c.JSON(http.StatusNotFound, gin.H{"detail": "mute not found"})
			return
		}
		h.logger.Error("unmute_user_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to unmute user"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"detail": "user unmuted"})
}
