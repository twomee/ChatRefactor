package handler

import (
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

// ---- CloseRoom tests ----

func TestCloseRoomSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{{ID: 1, Name: "general", IsActive: true}},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/admin/rooms/:id/close", h.CloseRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/abc/close", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestCloseRoomNonAdminRejected(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: false}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/admin/rooms/:id/close", h.CloseRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/1/close", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}

// ---- OpenRoom tests ----

func TestOpenRoomSuccess(t *testing.T) {
	store := &mockRoomStore{
		rooms: []model.Room{{ID: 1, Name: "general", IsActive: false}},
	}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/admin/rooms/:id/open", h.OpenRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/1/open", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

func TestOpenRoomInvalidID(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	mgr := ws.NewManager(logger)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}
	h := NewAdminHandler(store, mgr, authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
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
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/admin/rooms/:id/open", h.OpenRoom)

	req := httptest.NewRequest(http.MethodPost, "/admin/rooms/1/open", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusInternalServerError {
		t.Errorf("expected 500, got %d", w.Code)
	}
}
