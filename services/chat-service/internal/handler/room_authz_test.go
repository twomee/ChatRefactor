package handler

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- isCallerRoomOrGlobalAdmin authorization tests ----
// These tests verify that AddAdmin, RemoveAdmin, and SetActive
// require room admin or global admin authorization.

// TestAddAdminNonAdminReturns403 verifies that a non-admin user
// cannot add a room admin via the REST API.
func TestAddAdminNonAdminReturns403(t *testing.T) {
	store := &mockRoomStore{isAdmin: false}
	logger := newLogger()
	// Auth client returns a non-admin user
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "regular", IsGlobalAdmin: false}}
	h := NewRoomHandler(store, ws.NewManager(logger), authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/rooms/:id/admins", h.AddAdmin)

	body := `{"user_id": 2}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/1/admins", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "regular"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

// TestAddAdminRoomAdminSucceeds verifies that a room admin
// can add another room admin via the REST API.
func TestAddAdminRoomAdminSucceeds(t *testing.T) {
	store := &mockRoomStore{isAdmin: true}
	logger := newLogger()
	// Auth client returns a non-global-admin (but store says room admin)
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "roomadmin", IsGlobalAdmin: false}}
	h := NewRoomHandler(store, ws.NewManager(logger), authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/rooms/:id/admins", h.AddAdmin)

	body := `{"user_id": 2}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/1/admins", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "roomadmin"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("expected 201, got %d", w.Code)
	}
}

// TestAddAdminGlobalAdminSucceeds verifies that a global admin
// can add a room admin even if they are not a room admin.
func TestAddAdminGlobalAdminSucceeds(t *testing.T) {
	store := &mockRoomStore{isAdmin: false}
	logger := newLogger()
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "globaladmin", IsGlobalAdmin: true}}
	h := NewRoomHandler(store, ws.NewManager(logger), authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/rooms/:id/admins", h.AddAdmin)

	body := `{"user_id": 2}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/1/admins", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "globaladmin"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("expected 201, got %d", w.Code)
	}
}

// TestAddAdminAuthServiceFailureReturns502 verifies that when the auth
// service is unreachable and the user is not a room admin, 502 is returned.
func TestAddAdminAuthServiceFailureReturns502(t *testing.T) {
	store := &mockRoomStore{isAdmin: false}
	logger := newLogger()
	authClient := &mockAuthClient{err: fmt.Errorf("auth service down")}
	h := NewRoomHandler(store, ws.NewManager(logger), authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/rooms/:id/admins", h.AddAdmin)

	body := `{"user_id": 2}`
	req := httptest.NewRequest(http.MethodPost, "/rooms/1/admins", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadGateway {
		t.Errorf("expected 502, got %d", w.Code)
	}
}

// TestRemoveAdminNonAdminReturns403 verifies that a non-admin user
// cannot remove a room admin.
func TestRemoveAdminNonAdminReturns403(t *testing.T) {
	store := &mockRoomStore{isAdmin: false}
	logger := newLogger()
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "regular", IsGlobalAdmin: false}}
	h := NewRoomHandler(store, ws.NewManager(logger), authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.DELETE("/rooms/:id/admins/:userId", h.RemoveAdmin)

	req := httptest.NewRequest(http.MethodDelete, "/rooms/1/admins/2", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "regular"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

// TestSetActiveNonAdminReturns403 verifies that a non-admin user
// cannot toggle a room's active state.
func TestSetActiveNonAdminReturns403(t *testing.T) {
	store := &mockRoomStore{isAdmin: false}
	logger := newLogger()
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "regular", IsGlobalAdmin: false}}
	h := NewRoomHandler(store, ws.NewManager(logger), authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.PUT("/rooms/:id/active", h.SetActive)

	body := `{"is_active": false}`
	req := httptest.NewRequest(http.MethodPut, "/rooms/1/active", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "regular"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

// TestSetActiveGlobalAdminSucceeds verifies that a global admin
// can toggle a room's active state even without being a room admin.
func TestSetActiveGlobalAdminSucceeds(t *testing.T) {
	store := &mockRoomStore{isAdmin: false}
	logger := newLogger()
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "globaladmin", IsGlobalAdmin: true}}
	h := NewRoomHandler(store, ws.NewManager(logger), authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.PUT("/rooms/:id/active", h.SetActive)

	body := `{"is_active": false}`
	req := httptest.NewRequest(http.MethodPut, "/rooms/1/active", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "globaladmin"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

// TestSetActiveRoomAdminSucceeds verifies that a room admin
// can toggle the room's active state.
func TestSetActiveRoomAdminSucceeds(t *testing.T) {
	store := &mockRoomStore{isAdmin: true}
	logger := newLogger()
	authClient := &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "roomadmin", IsGlobalAdmin: false}}
	h := NewRoomHandler(store, ws.NewManager(logger), authClient, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.PUT("/rooms/:id/active", h.SetActive)

	body := `{"is_active": true}`
	req := httptest.NewRequest(http.MethodPut, "/rooms/1/active", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "roomadmin"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}
