package handler

import (
	"github.com/jackc/pgx/v5"
	"github.com/gin-gonic/gin"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- Room handler tests ----

func TestListRoomsSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{
			{ID: 1, Name: "general", IsActive: true},
			{ID: 2, Name: "random", IsActive: true},
		},
	}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/rooms", h.ListRooms)

	req := httptest.NewRequest(http.MethodGet, "/rooms", nil)
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

func TestListRoomsEmpty(t *testing.T) {
	store := &mockRoomStore{rooms: nil}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/rooms", h.ListRooms)

	req := httptest.NewRequest(http.MethodGet, "/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	// Should return empty array, not null.
	if strings.TrimSpace(w.Body.String()) != "[]" {
		t.Errorf("expected empty JSON array, got %q", w.Body.String())
	}
}

func TestListRoomsError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/rooms", h.ListRooms)

	req := httptest.NewRequest(http.MethodGet, "/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

func TestCreateRoomSuccess(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms", h.CreateRoom)

	body := `{"name":"test-room"}`
	req := httptest.NewRequest(http.MethodPost, "/rooms", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("expected 201, got %d", w.Code)
	}
}

func TestCreateRoomBadBody(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms", h.CreateRoom)

	body := `{"invalid": true}`
	req := httptest.NewRequest(http.MethodPost, "/rooms", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestCreateRoomConflict(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("unique violation")}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms", h.CreateRoom)

	body := `{"name":"duplicate"}`
	req := httptest.NewRequest(http.MethodPost, "/rooms", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusConflict {
		t.Errorf("expected 409, got %d", w.Code)
	}
}

func TestGetRoomUsersSuccess(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	store := &mockRoomStore{}
	h := NewRoomHandler(store, manager, &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/rooms/:id/users", h.GetRoomUsers)

	req := httptest.NewRequest(http.MethodGet, "/rooms/1/users", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestGetRoomUsersInvalidID(t *testing.T) {
	logger := newLogger()
	store := &mockRoomStore{}
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.GET("/rooms/:id/users", h.GetRoomUsers)

	req := httptest.NewRequest(http.MethodGet, "/rooms/abc/users", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestSetActiveSuccess(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.PUT("/rooms/:id/active", h.SetActive)

	body := `{"is_active": false}`
	req := httptest.NewRequest(http.MethodPut, "/rooms/1/active", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestSetActiveInvalidID(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.PUT("/rooms/:id/active", h.SetActive)

	body := `{"is_active": false}`
	req := httptest.NewRequest(http.MethodPut, "/rooms/abc/active", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestSetActiveBadBody(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.PUT("/rooms/:id/active", h.SetActive)

	req := httptest.NewRequest(http.MethodPut, "/rooms/1/active", strings.NewReader("not json"))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestSetActiveNotFound(t *testing.T) {
	store := &mockRoomStore{err: pgx.ErrNoRows}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.PUT("/rooms/:id/active", h.SetActive)

	body := `{"is_active": false}`
	req := httptest.NewRequest(http.MethodPut, "/rooms/999/active", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", w.Code)
	}
}

func TestSetActiveDBError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.PUT("/rooms/:id/active", h.SetActive)

	body := `{"is_active": false}`
	req := httptest.NewRequest(http.MethodPut, "/rooms/1/active", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

func TestAddAdminSuccess(t *testing.T) {
	store := &mockRoomStore{
		admin: &model.RoomAdmin{ID: 1, UserID: 2, RoomID: 1, AppointedAt: time.Now()},
	}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms/:id/admins", h.AddAdmin)

	body := `{"user_id": 2}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/1/admins", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("expected 201, got %d", w.Code)
	}
}

func TestAddAdminInvalidRoomID(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms/:id/admins", h.AddAdmin)

	body := `{"user_id": 2}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/abc/admins", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestAddAdminBadBody(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms/:id/admins", h.AddAdmin)

	req := httptest.NewRequest(http.MethodPost, "/rooms/1/admins", strings.NewReader("bad"))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestAddAdminConflict(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("duplicate")}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms/:id/admins", h.AddAdmin)

	body := `{"user_id": 2}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/1/admins", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusConflict {
		t.Errorf("expected 409, got %d", w.Code)
	}
}

func TestRemoveAdminSuccess(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/admins/:userId", h.RemoveAdmin)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/admins/2", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestRemoveAdminInvalidRoomID(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/admins/:userId", h.RemoveAdmin)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/abc/admins/2", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestRemoveAdminInvalidUserID(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/admins/:userId", h.RemoveAdmin)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/admins/abc", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestRemoveAdminNotFound(t *testing.T) {
	store := &mockRoomStore{err: pgx.ErrNoRows}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/admins/:userId", h.RemoveAdmin)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/admins/999", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", w.Code)
	}
}

func TestRemoveAdminDBError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/admins/:userId", h.RemoveAdmin)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/admins/2", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

func TestMuteUserSuccess(t *testing.T) {
	store := &mockRoomStore{
		isAdmin:   true,
		mutedUser: &model.MutedUser{ID: 1, UserID: 5, RoomID: 1, MutedAt: time.Now()},
	}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms/:id/mutes", h.MuteUser)

	body := `{"user_id": 5}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/1/mutes", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("expected 201, got %d", w.Code)
	}
}

func TestMuteUserForbidden(t *testing.T) {
	store := &mockRoomStore{isAdmin: false}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms/:id/mutes", h.MuteUser)

	body := `{"user_id": 5}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/1/mutes", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestMuteUserInvalidRoomID(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms/:id/mutes", h.MuteUser)

	body := `{"user_id": 5}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/abc/mutes", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestMuteUserBadBody(t *testing.T) {
	store := &mockRoomStore{isAdmin: true}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms/:id/mutes", h.MuteUser)

	req := httptest.NewRequest(http.MethodPost, "/rooms/1/mutes", strings.NewReader("bad"))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestMuteUserConflict(t *testing.T) {
	store := &mockRoomStore{isAdmin: true, err: fmt.Errorf("already muted")}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/rooms/:id/mutes", h.MuteUser)

	body := `{"user_id": 5}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/1/mutes", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusConflict {
		t.Errorf("expected 409, got %d", w.Code)
	}
}

func TestUnmuteUserSuccess(t *testing.T) {
	store := &mockRoomStore{isAdmin: true}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/mutes/:userId", h.UnmuteUser)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/mutes/5", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestUnmuteUserForbidden(t *testing.T) {
	store := &mockRoomStore{isAdmin: false}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/mutes/:userId", h.UnmuteUser)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/mutes/5", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestUnmuteUserInvalidRoomID(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/mutes/:userId", h.UnmuteUser)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/abc/mutes/5", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestUnmuteUserInvalidUserID(t *testing.T) {
	store := &mockRoomStore{isAdmin: true}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/mutes/:userId", h.UnmuteUser)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/mutes/abc", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestUnmuteUserNotFound(t *testing.T) {
	store := &mockRoomStore{isAdmin: true, err: pgx.ErrNoRows}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/mutes/:userId", h.UnmuteUser)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/mutes/999", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", w.Code)
	}
}

func TestUnmuteUserDBError(t *testing.T) {
	store := &mockRoomStore{isAdmin: true, err: fmt.Errorf("db error")}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.DELETE("/rooms/:id/mutes/:userId", h.UnmuteUser)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/mutes/5", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

