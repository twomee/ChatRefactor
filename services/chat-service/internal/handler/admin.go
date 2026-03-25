package handler

import (
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/store"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// parseIntParam extracts an integer path parameter.
func parseIntParam(c *gin.Context, name string) (int, error) {
	v, err := strconv.Atoi(c.Param(name))
	if err != nil {
		return 0, fmt.Errorf("invalid %s: %w", name, err)
	}
	return v, nil
}

// AdminHandler provides global admin dashboard endpoints.
type AdminHandler struct {
	store      store.RoomRepository
	manager    *ws.Manager
	authClient client.UserLookup
	logger     *zap.Logger
}

// NewAdminHandler creates an AdminHandler.
func NewAdminHandler(s store.RoomRepository, m *ws.Manager, authClient client.UserLookup, logger *zap.Logger) *AdminHandler {
	return &AdminHandler{store: s, manager: m, authClient: authClient, logger: logger}
}

// requireGlobalAdmin verifies the caller is a global admin via the auth service.
// Returns the caller user info or writes an HTTP error and returns nil.
func (h *AdminHandler) requireGlobalAdmin(c *gin.Context) *client.UserResponse {
	callerID, _ := c.Get(middleware.CtxUserID)
	caller, err := h.authClient.GetUserByID(c.Request.Context(), callerID.(int))
	if err != nil {
		h.logger.Error("admin_check_failed", zap.Error(err))
		c.JSON(http.StatusBadGateway, gin.H{"detail": "failed to verify admin status"})
		return nil
	}
	if caller == nil || !caller.IsGlobalAdmin {
		c.JSON(http.StatusForbidden, gin.H{"detail": "global admin access required"})
		return nil
	}
	return caller
}

// ListAllRooms returns all rooms including inactive ones.
// GET /admin/rooms
func (h *AdminHandler) ListAllRooms(c *gin.Context) {
	if h.requireGlobalAdmin(c) == nil {
		return
	}

	rooms, err := h.store.GetAllIncludingInactive(c.Request.Context())
	if err != nil {
		h.logger.Error("admin_list_rooms_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to list rooms"})
		return
	}
	if rooms == nil {
		rooms = []model.Room{}
	}
	c.JSON(http.StatusOK, rooms)
}

// CloseAllRooms deactivates all rooms and disconnects everyone.
// POST /admin/chat/close
func (h *AdminHandler) CloseAllRooms(c *gin.Context) {
	if h.requireGlobalAdmin(c) == nil {
		return
	}

	affected, err := h.store.SetAllActive(c.Request.Context(), false)
	if err != nil {
		h.logger.Error("admin_close_all_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to close rooms"})
		return
	}

	// Broadcast chat_closed to all rooms and close connections.
	rooms, _ := h.store.GetAllIncludingInactive(c.Request.Context())
	for _, room := range rooms {
		closedMsg := map[string]interface{}{
			"type":   "chat_closed",
			"detail": "All rooms closed by admin",
		}
		h.manager.BroadcastRoom(room.ID, closedMsg)
		h.manager.CloseAllInRoom(room.ID)
	}

	// Notify lobby connections with active rooms only (matching what ListRooms returns).
	activeRooms, _ := h.store.GetAll(c.Request.Context())
	if activeRooms == nil {
		activeRooms = []model.Room{}
	}
	h.manager.BroadcastLobby(map[string]interface{}{
		"type":  "room_list_updated",
		"rooms": activeRooms,
	})

	c.JSON(http.StatusOK, gin.H{"detail": "all rooms closed", "affected": affected})
}

// OpenAllRooms reactivates all rooms.
// POST /admin/chat/open
func (h *AdminHandler) OpenAllRooms(c *gin.Context) {
	if h.requireGlobalAdmin(c) == nil {
		return
	}

	affected, err := h.store.SetAllActive(c.Request.Context(), true)
	if err != nil {
		h.logger.Error("admin_open_all_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to open rooms"})
		return
	}

	// Notify lobby connections with active rooms only (matching what ListRooms returns).
	activeRooms, _ := h.store.GetAll(c.Request.Context())
	if activeRooms == nil {
		activeRooms = []model.Room{}
	}
	h.manager.BroadcastLobby(map[string]interface{}{
		"type":  "room_list_updated",
		"rooms": activeRooms,
	})

	c.JSON(http.StatusOK, gin.H{"detail": "all rooms opened", "affected": affected})
}

// ResetDatabase truncates all chat tables. Only allowed in dev/staging.
// DELETE /admin/db
func (h *AdminHandler) ResetDatabase(c *gin.Context) {
	if h.requireGlobalAdmin(c) == nil {
		return
	}

	env := strings.ToLower(os.Getenv("APP_ENV"))
	if env == "prod" || env == "production" {
		c.JSON(http.StatusForbidden, gin.H{"detail": "database reset is not allowed in production"})
		return
	}

	if err := h.store.DeleteAllData(c.Request.Context()); err != nil {
		h.logger.Error("admin_db_reset_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to reset database"})
		return
	}

	h.logger.Warn("database_reset_by_admin")
	c.JSON(http.StatusOK, gin.H{"detail": "database reset complete"})
}

// ListOnlineUsers returns all logged-in users (lobby connections) and users per room.
// GET /admin/users
func (h *AdminHandler) ListOnlineUsers(c *gin.Context) {
	if h.requireGlobalAdmin(c) == nil {
		return
	}

	rooms, err := h.store.GetAllIncludingInactive(c.Request.Context())
	if err != nil {
		h.logger.Error("admin_list_users_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to list rooms"})
		return
	}

	perRoom := make(map[int][]string)
	for _, room := range rooms {
		usernames := h.manager.GetUsernamesInRoom(room.ID)
		if len(usernames) > 0 {
			perRoom[room.ID] = usernames
		}
	}

	// All online = all lobby-connected users (logged in, regardless of room membership).
	allOnline := h.manager.GetLobbyUsernames()

	c.JSON(http.StatusOK, gin.H{
		"all_online": allOnline,
		"per_room":   perRoom,
	})
}

// CloseRoom deactivates a specific room and disconnects its users.
// POST /admin/rooms/:id/close
func (h *AdminHandler) CloseRoom(c *gin.Context) {
	if h.requireGlobalAdmin(c) == nil {
		return
	}

	roomID, err := parseIntParam(c, "id")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid room id"})
		return
	}

	if err := h.store.SetActive(c.Request.Context(), roomID, false); err != nil {
		h.logger.Error("admin_close_room_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to close room"})
		return
	}

	closedMsg := map[string]interface{}{
		"type":   "chat_closed",
		"detail": "Room closed by admin",
	}
	h.manager.BroadcastRoom(roomID, closedMsg)
	h.manager.CloseAllInRoom(roomID)

	// Notify lobby connections with active rooms only.
	activeRooms, _ := h.store.GetAll(c.Request.Context())
	if activeRooms == nil {
		activeRooms = []model.Room{}
	}
	h.manager.BroadcastLobby(map[string]interface{}{
		"type":  "room_list_updated",
		"rooms": activeRooms,
	})

	c.JSON(http.StatusOK, gin.H{"detail": "room closed", "room_id": roomID})
}

// OpenRoom reactivates a specific room.
// POST /admin/rooms/:id/open
func (h *AdminHandler) OpenRoom(c *gin.Context) {
	if h.requireGlobalAdmin(c) == nil {
		return
	}

	roomID, err := parseIntParam(c, "id")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "invalid room id"})
		return
	}

	if err := h.store.SetActive(c.Request.Context(), roomID, true); err != nil {
		h.logger.Error("admin_open_room_error", zap.Error(err))
		c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to open room"})
		return
	}

	// Notify lobby connections with active rooms only.
	activeRooms, _ := h.store.GetAll(c.Request.Context())
	if activeRooms == nil {
		activeRooms = []model.Room{}
	}
	h.manager.BroadcastLobby(map[string]interface{}{
		"type":  "room_list_updated",
		"rooms": activeRooms,
	})

	c.JSON(http.StatusOK, gin.H{"detail": "room opened", "room_id": roomID})
}

// PromoteUserInAllRooms promotes a user to admin in all rooms where they are connected.
// POST /admin/promote?username=X
func (h *AdminHandler) PromoteUserInAllRooms(c *gin.Context) {
	if h.requireGlobalAdmin(c) == nil {
		return
	}

	username := c.Query("username")
	if username == "" {
		c.JSON(http.StatusBadRequest, gin.H{"detail": "username query parameter required"})
		return
	}

	// Look up user via auth service.
	user, err := h.authClient.GetUserByUsername(c.Request.Context(), username)
	if err != nil {
		h.logger.Error("admin_promote_lookup_failed", zap.Error(err))
		c.JSON(http.StatusBadGateway, gin.H{"detail": "failed to look up user"})
		return
	}
	if user == nil {
		c.JSON(http.StatusNotFound, gin.H{"detail": "user not found"})
		return
	}

	// Get all active rooms and promote in each where user is connected.
	rooms, _ := h.store.GetAll(c.Request.Context())
	promoted := 0
	for _, room := range rooms {
		if !h.manager.IsUserInRoom(room.ID, user.ID) {
			continue
		}
		isAlready, _ := h.store.IsAdmin(c.Request.Context(), room.ID, user.ID)
		if isAlready {
			continue
		}
		_, err := h.store.AddAdmin(c.Request.Context(), room.ID, user.ID)
		if err != nil {
			h.logger.Warn("admin_promote_failed", zap.Int("room_id", room.ID), zap.Error(err))
			continue
		}
		promoted++

		// Broadcast new admin to the room.
		promoteMsg := map[string]interface{}{
			"type":     "new_admin",
			"username": username,
			"room_id":  room.ID,
		}
		h.manager.BroadcastRoom(room.ID, promoteMsg)
	}

	c.JSON(http.StatusOK, gin.H{
		"detail":         "user promoted",
		"username":       username,
		"rooms_promoted": promoted,
	})
}
