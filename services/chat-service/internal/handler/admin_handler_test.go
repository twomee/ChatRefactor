package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.GET("/admin/users", h.ListOnlineUsers)

	req := httptest.NewRequest(http.MethodGet, "/admin/users", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(2, "bob"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestListOnlineUsersDBError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.GET("/admin/users", h.ListOnlineUsers)

	req := httptest.NewRequest(http.MethodGet, "/admin/users", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.DELETE("/admin/db", h.ResetDatabase)

	req := httptest.NewRequest(http.MethodDelete, "/admin/db", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.GET("/admin/rooms", h.ListAllRooms)

	req := httptest.NewRequest(http.MethodGet, "/admin/rooms", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for nil user, got %d", w.Code)
	}
}
