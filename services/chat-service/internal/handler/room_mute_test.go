package handler

import (
	"github.com/jackc/pgx/v5"
	"github.com/gin-gonic/gin"
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

// ---- Room mute tests ----

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

