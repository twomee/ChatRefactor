package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- Admin handler tests ----

func TestListOnlineUsersSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{
			{ID: 1, Name: "general", IsActive: true},
			{ID: 2, Name: "random", IsActive: true},
		},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/users", h.ListOnlineUsers)

	req := httptest.NewRequest(http.MethodGet, "/admin/users", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	if body["all_online"] == nil {
		t.Error("expected all_online field")
	}
	if body["per_room"] == nil {
		t.Error("expected per_room field")
	}
}

func TestListOnlineUsersNonAdminRejected(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: false}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/users", h.ListOnlineUsers)

	req := httptest.NewRequest(http.MethodGet, "/admin/users", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(2, "bob"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestCloseRoomSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{{ID: 1, Name: "general", IsActive: true}},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/rooms/:id/close", h.CloseRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/1/close", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestCloseRoomInvalidID(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/rooms/:id/close", h.CloseRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/abc/close", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestOpenRoomSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{{ID: 1, Name: "general", IsActive: false}},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/rooms/:id/open", h.OpenRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/1/open", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestListAllRoomsSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{
			{ID: 1, Name: "general", IsActive: true},
			{ID: 2, Name: "closed", IsActive: false},
		},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/rooms", h.ListAllRooms)

	req := httptest.NewRequest(http.MethodGet, "/admin/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	var rooms []model.Room
	json.Unmarshal(w.Body.Bytes(), &rooms)
	if len(rooms) != 2 {
		t.Errorf("expected 2 rooms, got %d", len(rooms))
	}
}

func TestListAllRoomsDBError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/rooms", h.ListAllRooms)

	req := httptest.NewRequest(http.MethodGet, "/admin/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

func TestCloseAllRoomsSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{{ID: 1, Name: "general", IsActive: true}},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/chat/close", h.CloseAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/chat/close", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestCloseAllRoomsDBError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/chat/close", h.CloseAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/chat/close", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

func TestOpenAllRoomsSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{{ID: 1, Name: "general", IsActive: false}},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/chat/open", h.OpenAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/chat/open", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestResetDatabaseSuccessDev(t *testing.T) {
	t.Setenv("APP_ENV", "dev")
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/admin/db", h.ResetDatabase)

	req := httptest.NewRequest(http.MethodDelete, "/admin/db", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestResetDatabaseForbiddenProd(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/admin/db", h.ResetDatabase)

	req := httptest.NewRequest(http.MethodDelete, "/admin/db", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestResetDatabaseDBError(t *testing.T) {
	t.Setenv("APP_ENV", "dev")
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/admin/db", h.ResetDatabase)

	req := httptest.NewRequest(http.MethodDelete, "/admin/db", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

func TestPromoteUserInAllRoomsSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{{ID: 1, Name: "general", IsActive: true}},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/promote", h.PromoteUserInAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/promote?username=bob", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestPromoteUserMissingUsername(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/promote", h.PromoteUserInAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/promote", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestPromoteUserNotFound(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: nil} // nil = not found
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/promote", h.PromoteUserInAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/promote?username=nobody", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// requireGlobalAdmin calls GetUserByID with caller's ID.
	// If authClient returns nil, it returns 403.
	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 (nil user from auth check), got %d", w.Code)
	}
}

// ---- requireGlobalAdmin edge cases ----

func TestRequireGlobalAdminAuthError(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{err: fmt.Errorf("auth service down")}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/rooms", h.ListAllRooms)

	req := httptest.NewRequest(http.MethodGet, "/admin/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadGateway {
		t.Errorf("expected 502 when auth service is down, got %d", w.Code)
	}
}

func TestRequireGlobalAdminNotAdmin(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: false}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/rooms", h.ListAllRooms)

	req := httptest.NewRequest(http.MethodGet, "/admin/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(2, "bob"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for non-admin user, got %d", w.Code)
	}
}

func TestRequireGlobalAdminNilUser(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: nil}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/rooms", h.ListAllRooms)

	req := httptest.NewRequest(http.MethodGet, "/admin/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for nil user, got %d", w.Code)
	}
}

// ---- ListAllRooms edge cases ----

func TestListAllRoomsNilRoomsReturnsEmptyArray(t *testing.T) {
	store := &mockRoomStore{rooms: nil}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/rooms", h.ListAllRooms)

	req := httptest.NewRequest(http.MethodGet, "/admin/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	// Should return empty JSON array, not null.
	body := strings.TrimSpace(w.Body.String())
	if body != "[]" {
		t.Errorf("expected empty JSON array '[]', got %q", body)
	}
}

func TestListAllRoomsNonAdminRejected(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: false}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/rooms", h.ListAllRooms)

	req := httptest.NewRequest(http.MethodGet, "/admin/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(2, "bob"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

// ---- OpenAllRooms edge cases ----

func TestOpenAllRoomsDBError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/chat/open", h.OpenAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/chat/open", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

func TestOpenAllRoomsNonAdminRejected(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: false}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/chat/open", h.OpenAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/chat/open", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(2, "bob"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

// ---- CloseRoom edge cases ----

func TestCloseRoomNonAdminRejected(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: false}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/rooms/:id/close", h.CloseRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/1/close", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(2, "bob"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestCloseRoomStoreError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/rooms/:id/close", h.CloseRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/1/close", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

// ---- OpenRoom edge cases ----

func TestOpenRoomInvalidID(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/rooms/:id/open", h.OpenRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/abc/open", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestOpenRoomNonAdminRejected(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: false}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/rooms/:id/open", h.OpenRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/1/open", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(2, "bob"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestOpenRoomStoreError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/rooms/:id/open", h.OpenRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/1/open", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

// ---- PromoteUserInAllRooms edge cases ----

func TestPromoteUserAuthServiceError(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{err: fmt.Errorf("auth service down")}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/promote", h.PromoteUserInAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/promote?username=bob", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// requireGlobalAdmin calls GetUserByID first. If that errors, we get 502.
	if w.Code != http.StatusBadGateway {
		t.Errorf("expected 502, got %d", w.Code)
	}
}

func TestPromoteUserLookupNotFound(t *testing.T) {
	// Use a two-phase auth client: returns admin for GetUserByID (caller check),
	// but returns nil for GetUserByUsername (target lookup).
	store := &mockRoomStore{
		rooms: []model.Room{{ID: 1, Name: "general", IsActive: true}},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockTwoPhaseAuthClient{
		byIDUser:       &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true},
		byUsernameUser: nil, // target not found
	}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/promote", h.PromoteUserInAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/promote?username=nobody", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", w.Code)
	}
}

func TestPromoteUserLookupError(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{{ID: 1, Name: "general", IsActive: true}},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockTwoPhaseAuthClient{
		byIDUser:          &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true},
		byUsernameUser:    nil,
		byUsernameErr:     fmt.Errorf("auth service lookup failed"),
	}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/promote", h.PromoteUserInAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/promote?username=bob", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadGateway {
		t.Errorf("expected 502, got %d", w.Code)
	}
}

func TestPromoteUserAlreadyAdminInRoom(t *testing.T) {
	store := &mockRoomStore{
		rooms:    []model.Room{{ID: 1, Name: "general", IsActive: true}},
		isAdmin:  true, // target is already admin in the room
		adminSet: nil,  // use legacy isAdmin field
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)

	// We need user 2 to be connected in room 1 for the promote logic.
	// Use createWSPair from ws_commands_test (but that's a WS concern).
	// Instead, directly register in the manager.
	bobConn := createDummyConn(t)
	mgr.ConnectRoom(1, bobConn, ws.UserInfo{UserID: 2, Username: "bob"})

	authClient := &mockTwoPhaseAuthClient{
		byIDUser:       &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true},
		byUsernameUser: &client.UserResponse{ID: 2, Username: "bob"},
	}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/promote", h.PromoteUserInAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/promote?username=bob", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}

	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	promoted := body["rooms_promoted"].(float64)
	if promoted != 0 {
		t.Errorf("expected 0 rooms promoted (already admin), got %v", promoted)
	}
}

func TestPromoteUserInRoomSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms:    []model.Room{{ID: 1, Name: "general", IsActive: true}},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)

	// Connect bob in room 1.
	bobConn := createDummyConn(t)
	mgr.ConnectRoom(1, bobConn, ws.UserInfo{UserID: 2, Username: "bob"})

	authClient := &mockTwoPhaseAuthClient{
		byIDUser:       &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true},
		byUsernameUser: &client.UserResponse{ID: 2, Username: "bob"},
	}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/promote", h.PromoteUserInAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/promote?username=bob", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}

	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	promoted := body["rooms_promoted"].(float64)
	if promoted != 1 {
		t.Errorf("expected 1 room promoted, got %v", promoted)
	}
}

func TestPromoteUserNotConnectedInAnyRoom(t *testing.T) {
	store := &mockRoomStore{
		rooms:    []model.Room{{ID: 1, Name: "general", IsActive: true}},
		adminSet: make(map[string]bool),
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	// Bob is NOT connected in any room.

	authClient := &mockTwoPhaseAuthClient{
		byIDUser:       &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true},
		byUsernameUser: &client.UserResponse{ID: 2, Username: "bob"},
	}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/promote", h.PromoteUserInAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/promote?username=bob", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}

	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	promoted := body["rooms_promoted"].(float64)
	if promoted != 0 {
		t.Errorf("expected 0 rooms promoted (not connected), got %v", promoted)
	}
}

// ---- CloseAllRooms edge cases ----

func TestCloseAllRoomsNonAdminRejected(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: false}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/admin/chat/close", h.CloseAllRooms)

	req := httptest.NewRequest(http.MethodPost, "/admin/chat/close", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(2, "bob"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

// ---- ListOnlineUsers edge cases ----

func TestListOnlineUsersDBError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/admin/users", h.ListOnlineUsers)

	req := httptest.NewRequest(http.MethodGet, "/admin/users", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

