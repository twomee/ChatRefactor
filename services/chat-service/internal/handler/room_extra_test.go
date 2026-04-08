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

// TestCreateRoomInvalidName verifies that a room name with invalid characters
// (e.g. special chars) returns a 400 Bad Request.
func TestCreateRoomInvalidName(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/rooms", h.CreateRoom)

	body := `{"name":"bad@name!"}`
	req := httptest.NewRequest(http.MethodPost, "/rooms", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 for invalid room name, got %d", w.Code)
	}
}

// TestCreateRoomNonAdminForbidden verifies that a non-global-admin cannot create rooms.
func TestCreateRoomNonAdminForbidden(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	// Not a global admin.
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 2, Username: "bob", IsGlobalAdmin: false}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/rooms", h.CreateRoom)

	body := `{"name":"test-room"}`
	req := httptest.NewRequest(http.MethodPost, "/rooms", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(2, "bob"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403 for non-admin, got %d", w.Code)
	}
}

// TestCreateRoomAuthClientError verifies that when auth client fails, a 502 is returned.
func TestCreateRoomAuthClientError(t *testing.T) {
	store := &mockRoomStore{}
	logger := newLogger()
	// Auth client returns error.
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{err: fmt.Errorf("auth unavailable")}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.POST("/rooms", h.CreateRoom)

	body := `{"name":"test-room"}`
	req := httptest.NewRequest(http.MethodPost, "/rooms", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadGateway {
		t.Errorf("expected 502 when auth fails, got %d", w.Code)
	}
}

// TestBroadcastRoomListUpdatedGetAllError verifies that broadcastRoomListUpdated
// does NOT panic when GetAll returns an error (error is just logged).
func TestBroadcastRoomListUpdatedGetAllError(t *testing.T) {
	store := &mockRoomStore{err: fmt.Errorf("db error")}
	logger := newLogger()
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: false}}, logger)

	// Call broadcastRoomListUpdated directly — it should log and return without panic.
	// We need to trigger it through SetActive (which calls broadcastRoomListUpdated on success).
	// But store.SetActive will also fail with the same error before reaching broadcastRoomListUpdated.
	// So let's use a store where SetActive succeeds but GetAll fails.
	// We can't easily do that with the current mockRoomStore (single err field).
	// Instead, let's call broadcastRoomListUpdated via SetActive with a store
	// that succeeds on SetActive but fails on GetAll.
	// The simplest approach: call broadcastRoomListUpdated directly.
	// It's not exported, so we call it through a route that invokes it.

	// Use store where SetActive returns no error (success), but GetAll fails.
	// mockRoomStore.SetActive always returns m.err.
	// So if m.err is set, SetActive also fails. We cannot easily decouple them.
	// Instead, use the no-error path through CreateRoom but with GetAll failing.

	// Actually, broadcastRoomListUpdated is called after successful Create.
	// If we make Create succeed but GetAll fail, we trigger the error branch.
	// The mockRoomStore.Create ignores m.err (it creates a hardcoded room).
	// But GetAll returns m.rooms and m.err. So set m.err on a mock that also
	// has create work... let's use a different approach:

	// Make Create succeed by having a clean store for the Create call,
	// then switch the GetAll to fail. Not possible with the single-mock design.
	// However, broadcastRoomListUpdated internally calls GetAll. With the current
	// mock, GetAll also returns m.err. So if we set m.err, Create will NOT return
	// an error (its branch checks m.err but Create has: if m.err != nil { return nil, m.err }).
	// Oh wait, Create does check m.err. So to get past Create but fail on GetAll
	// is impossible with a single err field.

	// Simplest alternative: just verify broadcastRoomListUpdated is callable
	// without panic by checking the SetActive → broadcastRoomListUpdated path
	// where GetAll succeeds (the normal test TestSetActiveSuccess already covers this).
	// For the error branch, we invoke it directly through the test by
	// calling the unexported function via a helper (not possible since we're in
	// the same package - we can access it directly).

	// Since we're in the same handler package, we can call it directly.
	h.broadcastRoomListUpdated(nil) // pass nil context — store.GetAll will fail (nil ctx)
}

// TestGetRoomUsersETagNotModified verifies that the ETag caching works —
// sending If-None-Match with the correct etag returns 304.
func TestGetRoomUsersETagNotModified(t *testing.T) {
	logger := newLogger()
	store := &mockRoomStore{}
	h := NewRoomHandler(store, ws.NewManager(logger), &mockAuthClient{user: &client.UserResponse{ID: 1, Username: "alice", IsGlobalAdmin: true}}, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret, nil, false))
	r.GET("/rooms/:id/users", h.GetRoomUsers)

	// First request to get the ETag.
	req := httptest.NewRequest(http.MethodGet, "/rooms/1/users", nil)
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	etag := w.Header().Get("ETag")
	if etag == "" {
		t.Fatal("expected ETag header in response")
	}

	// Second request with If-None-Match — should return 304.
	req2 := httptest.NewRequest(http.MethodGet, "/rooms/1/users", nil)
	req2.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req2.Header.Set("If-None-Match", etag)
	w2 := httptest.NewRecorder()
	r.ServeHTTP(w2, req2)

	if w2.Code != http.StatusNotModified {
		t.Errorf("expected 304 with matching ETag, got %d", w2.Code)
	}
}
