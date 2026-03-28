package handler

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/store"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// roomNamePattern matches alphanumeric characters, spaces, underscores, and hyphens.
var roomNamePattern = regexp.MustCompile(`^[a-zA-Z0-9 _-]+$`)

// RoomHandler groups all room-related HTTP handlers.
type RoomHandler struct {
	store      store.RoomRepository
	manager    *ws.Manager
	authClient client.UserLookup
	logger     *zap.Logger
}

// NewRoomHandler creates a RoomHandler.
func NewRoomHandler(s store.RoomRepository, m *ws.Manager, authClient client.UserLookup, logger *zap.Logger) *RoomHandler {
	return &RoomHandler{store: s, manager: m, authClient: authClient, logger: logger}
}

// ListRooms returns all rooms.
// GET /rooms
func (h *RoomHandler) ListRooms(c *gin.Context) {
	rooms, err := h.store.GetAll(c.Request.Context())
	if err != nil {
		h.logger.Error("list_rooms_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to list rooms"})
		return
	}
	if rooms == nil {
		rooms = []model.Room{}
	}
	c.JSON(http.StatusOK, rooms)
}

// CreateRoom creates a new room. Only global admins may create rooms.
// POST /rooms
func (h *RoomHandler) CreateRoom(c *gin.Context) {
	// Verify the caller is a global admin via the auth service.
	callerID, _ := c.Get(middleware.CtxUserID)
	caller, err := h.authClient.GetUserByID(c.Request.Context(), callerID.(int))
	if err != nil {
		h.logger.Error("create_room_admin_check_failed", zap.Error(err))
		c.JSON(http.StatusBadGateway, gin.H{"detail": "failed to verify admin status"})
		return
	}
	if caller == nil || !caller.IsGlobalAdmin {
		c.JSON(http.StatusForbidden, gin.H{"detail": "admin access required"})
		return
	}

	var req model.CreateRoomRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	// Validate room name: alphanumeric, spaces, underscores, hyphens only.
	name := strings.TrimSpace(req.Name)
	if !roomNamePattern.MatchString(name) {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "room name must contain only alphanumeric characters, spaces, underscores, or hyphens"})
		return
	}

	room, err := h.store.Create(c.Request.Context(), name)
	if err != nil {
		// Duplicate name results in a PG unique violation.
		h.logger.Warn("create_room_error", zap.Error(err))
		c.JSON(http.StatusConflict, gin.H{"detail": "room name already exists"})
		return
	}

	// Broadcast room_list_updated to all lobby connections.
	h.broadcastRoomListUpdated(c.Request.Context())

	c.JSON(http.StatusCreated, room)
}

// GetRoomUsers returns the user IDs currently connected via WebSocket.
// Supports ETag caching: returns 304 when If-None-Match matches the SHA256 of the user list.
// GET /rooms/:id/users
func (h *RoomHandler) GetRoomUsers(c *gin.Context) {
	roomID, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid room id"})
		return
	}

	users := h.manager.GetUsersInRoom(roomID)

	// Compute ETag from sorted user IDs for deterministic hashing.
	sort.Ints(users)
	parts := make([]string, len(users))
	for i, id := range users {
		parts[i] = strconv.Itoa(id)
	}
	hash := sha256.Sum256([]byte(strings.Join(parts, ",")))
	etag := fmt.Sprintf(`"%x"`, hash)

	// Check If-None-Match header.
	if c.GetHeader("If-None-Match") == etag {
		c.Status(http.StatusNotModified)
		return
	}

	c.Header("ETag", etag)
	c.JSON(http.StatusOK, gin.H{"room_id": roomID, "user_ids": users})
}

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

// SetActive toggles a room's active flag. Requires room admin or global admin.
// PUT /rooms/:id/active
func (h *RoomHandler) SetActive(c *gin.Context) {
	roomID, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid room id"})
		return
	}

	if !h.isCallerRoomOrGlobalAdmin(c, roomID) {
		return
	}

	var req model.SetActiveRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": err.Error()})
		return
	}

	if err := h.store.SetActive(c.Request.Context(), roomID, req.IsActive); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			c.JSON(http.StatusNotFound, gin.H{"detail": "room not found"})
			return
		}
		h.logger.Error("set_active_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to update room"})
		return
	}

	// Broadcast room_list_updated to all lobby connections.
	h.broadcastRoomListUpdated(c.Request.Context())

	c.JSON(http.StatusOK, gin.H{"room_id": roomID, "is_active": req.IsActive})
}

// ---------- Admin operations ----------

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

// ---------- Mute operations ----------

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

// broadcastRoomListUpdated fetches the current room list and pushes it to all lobby connections.
func (h *RoomHandler) broadcastRoomListUpdated(ctx context.Context) {
	rooms, err := h.store.GetAll(ctx)
	if err != nil {
		h.logger.Warn("broadcast_room_list_fetch_failed", zap.Error(err))
		return
	}
	if rooms == nil {
		rooms = []model.Room{}
	}
	msg := map[string]interface{}{
		"type":  "room_list_updated",
		"rooms": rooms,
	}
	h.manager.BroadcastLobby(msg)
}
