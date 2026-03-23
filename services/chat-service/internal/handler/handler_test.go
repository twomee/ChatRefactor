package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/gorilla/websocket"
	"github.com/jackc/pgx/v5"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/middleware"
	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

const testSecret = "test-secret-key-for-ci"

func init() {
	gin.SetMode(gin.TestMode)
}

// ---- Mock store ----

type mockRoomStore struct {
	rooms      []model.Room
	room       *model.Room
	admins     []model.RoomAdmin
	admin      *model.RoomAdmin
	mutedUsers []model.MutedUser
	mutedUser  *model.MutedUser
	isAdmin    bool
	isMuted    bool
	err        error
}

func (m *mockRoomStore) GetAll(ctx context.Context) ([]model.Room, error) {
	return m.rooms, m.err
}

func (m *mockRoomStore) GetByID(ctx context.Context, id int) (*model.Room, error) {
	if m.err != nil {
		return nil, m.err
	}
	return m.room, nil
}

func (m *mockRoomStore) Create(ctx context.Context, name string) (*model.Room, error) {
	if m.err != nil {
		return nil, m.err
	}
	return &model.Room{ID: 1, Name: name, IsActive: true, CreatedAt: time.Now()}, nil
}

func (m *mockRoomStore) SetActive(ctx context.Context, id int, active bool) error {
	return m.err
}

func (m *mockRoomStore) GetAdmins(ctx context.Context, roomID int) ([]model.RoomAdmin, error) {
	return m.admins, m.err
}

func (m *mockRoomStore) AddAdmin(ctx context.Context, roomID, userID int) (*model.RoomAdmin, error) {
	if m.err != nil {
		return nil, m.err
	}
	return m.admin, nil
}

func (m *mockRoomStore) RemoveAdmin(ctx context.Context, roomID, userID int) error {
	return m.err
}

func (m *mockRoomStore) IsAdmin(ctx context.Context, roomID, userID int) (bool, error) {
	return m.isAdmin, m.err
}

func (m *mockRoomStore) GetMutedUsers(ctx context.Context, roomID int) ([]model.MutedUser, error) {
	return m.mutedUsers, m.err
}

func (m *mockRoomStore) MuteUser(ctx context.Context, roomID, userID int) (*model.MutedUser, error) {
	if m.err != nil {
		return nil, m.err
	}
	return m.mutedUser, nil
}

func (m *mockRoomStore) UnmuteUser(ctx context.Context, roomID, userID int) error {
	return m.err
}

func (m *mockRoomStore) IsMuted(ctx context.Context, roomID, userID int) (bool, error) {
	return m.isMuted, m.err
}

// ---- Mock auth client ----

type mockAuthClient struct {
	user *client.UserResponse
	err  error
}

func (m *mockAuthClient) GetUserByUsername(ctx context.Context, username string) (*client.UserResponse, error) {
	return m.user, m.err
}

func (m *mockAuthClient) GetUserByID(ctx context.Context, userID int) (*client.UserResponse, error) {
	return m.user, m.err
}

func (m *mockAuthClient) Ping(ctx context.Context) error {
	return m.err
}

// ---- Mock delivery ----

type mockDelivery struct {
	chatCalls  int
	pmCalls    int
	eventCalls int
	err        error
}

func (m *mockDelivery) DeliverChat(ctx context.Context, roomID int, payload []byte) error {
	m.chatCalls++
	return m.err
}

func (m *mockDelivery) DeliverPM(ctx context.Context, fromUserID int, payload []byte) error {
	m.pmCalls++
	return m.err
}

func (m *mockDelivery) DeliverEvent(ctx context.Context, eventType string, payload []byte) error {
	m.eventCalls++
	return m.err
}

// ---- Helpers ----

func makeToken(userID int, username string) string {
	claims := jwt.MapClaims{
		"sub":      fmt.Sprintf("%d", userID),
		"username": username,
		"exp":      time.Now().Add(time.Hour).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, _ := token.SignedString([]byte(testSecret))
	return signed
}

func newLogger() *zap.Logger {
	l, _ := zap.NewDevelopment()
	return l
}

// ---- Health handler tests ----

func TestHealthEndpoint(t *testing.T) {
	h := NewHealthHandler(nil, nil, nil, nil)
	r := gin.New()
	r.GET("/health", h.Health)

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	var body map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &body)
	if body["status"] != "ok" {
		t.Errorf("expected 'ok', got %v", body["status"])
	}
}

func TestReadyEndpointNoInfra(t *testing.T) {
	h := NewHealthHandler(nil, nil, nil, nil)
	r := gin.New()
	r.GET("/ready", h.Ready)

	req := httptest.NewRequest(http.MethodGet, "/ready", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
}

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

// ---- WebSocket handler tests ----

func TestWSHandlerRejectsWithoutToken(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	wsH := NewWSHandler(manager, nil, nil, testSecret, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)

	req := httptest.NewRequest(http.MethodGet, "/ws/1", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestWSHandlerRejectsInvalidToken(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	wsH := NewWSHandler(manager, nil, nil, testSecret, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)

	req := httptest.NewRequest(http.MethodGet, "/ws/1?token=bad-token", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestWSHandlerRejectsInvalidRoomID(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	wsH := NewWSHandler(manager, nil, nil, testSecret, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)

	token := makeToken(1, "alice")
	req := httptest.NewRequest(http.MethodGet, "/ws/abc?token="+token, nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestWSHandlerRoomNotFound(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	store := &mockRoomStore{err: fmt.Errorf("not found")}
	wsH := NewWSHandler(manager, store, nil, testSecret, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)

	token := makeToken(1, "alice")
	req := httptest.NewRequest(http.MethodGet, "/ws/99?token="+token, nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", w.Code)
	}
}

func TestWSHandlerInactiveRoom(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	store := &mockRoomStore{
		room: &model.Room{ID: 1, Name: "test", IsActive: false},
	}
	wsH := NewWSHandler(manager, store, nil, testSecret, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)

	token := makeToken(1, "alice")
	req := httptest.NewRequest(http.MethodGet, "/ws/1?token="+token, nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Errorf("expected 403, got %d", w.Code)
	}
}

func TestWSHandlerRoomWSUpgradeAndMessage(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		room: &model.Room{ID: 1, Name: "test", IsActive: true},
	}
	wsH := NewWSHandler(manager, store, del, testSecret, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)

	srv := httptest.NewServer(r)
	defer srv.Close()

	token := makeToken(1, "alice")
	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws/1?token=" + token

	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial error: %v", err)
	}
	defer conn.Close()

	// Read user_join broadcast.
	var joinMsg map[string]interface{}
	if err := conn.ReadJSON(&joinMsg); err != nil {
		t.Fatalf("read join: %v", err)
	}
	if joinMsg["type"] != "user_join" {
		t.Errorf("expected user_join message, got %v", joinMsg["type"])
	}

	// Read history message (may be empty).
	var historyMsg map[string]interface{}
	if err := conn.ReadJSON(&historyMsg); err != nil {
		t.Fatalf("read history: %v", err)
	}
	if historyMsg["type"] != "history" {
		t.Errorf("expected history type, got %v", historyMsg["type"])
	}

	// Send a chat message using the new format.
	msg := map[string]string{"type": "message", "text": "hello world"}
	if err := conn.WriteJSON(msg); err != nil {
		t.Fatalf("write: %v", err)
	}

	// Read the broadcast back.
	var chatMsg map[string]interface{}
	if err := conn.ReadJSON(&chatMsg); err != nil {
		t.Fatalf("read chat: %v", err)
	}
	if chatMsg["type"] != "message" {
		t.Errorf("expected message type, got %v", chatMsg["type"])
	}
	if chatMsg["text"] != "hello world" {
		t.Errorf("expected 'hello world', got %v", chatMsg["text"])
	}
	if chatMsg["from"] != "alice" {
		t.Errorf("expected from 'alice', got %v", chatMsg["from"])
	}

	// Give the server-side goroutine time to complete the delivery call
	// after broadcasting. The broadcast happens before the Kafka delivery
	// in the readLoop, so we need to wait briefly.
	time.Sleep(50 * time.Millisecond)

	// Verify delivery was called.
	if del.chatCalls != 1 {
		t.Errorf("expected 1 chat delivery, got %d", del.chatCalls)
	}
}

func TestWSHandlerMutedUserCannotSend(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		room:    &model.Room{ID: 1, Name: "test", IsActive: true},
		isMuted: true,
	}
	wsH := NewWSHandler(manager, store, del, testSecret, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)

	srv := httptest.NewServer(r)
	defer srv.Close()

	token := makeToken(1, "alice")
	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws/1?token=" + token

	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial error: %v", err)
	}
	defer conn.Close()

	// Read user_join broadcast.
	var joinMsg map[string]interface{}
	conn.ReadJSON(&joinMsg)

	// Read history message.
	var historyMsg map[string]interface{}
	conn.ReadJSON(&historyMsg)

	// Send a message from muted user using new format.
	conn.WriteJSON(map[string]string{"type": "message", "text": "hello"})

	// Read the error response.
	var errMsg map[string]interface{}
	if err := conn.ReadJSON(&errMsg); err != nil {
		t.Fatalf("read error: %v", err)
	}
	if errMsg["type"] != "error" {
		t.Errorf("expected error type, got %v", errMsg["type"])
	}
	if errMsg["detail"] != "You are muted in this room" {
		t.Errorf("expected mute error detail, got %v", errMsg["detail"])
	}

	// Delivery should NOT have been called.
	if del.chatCalls != 0 {
		t.Errorf("expected 0 chat deliveries for muted user, got %d", del.chatCalls)
	}
}

// ---- Lobby handler tests ----

func TestLobbyHandlerRejectsWithoutToken(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger)

	r := gin.New()
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	req := httptest.NewRequest(http.MethodGet, "/ws/lobby", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestLobbyHandlerRejectsInvalidToken(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger)

	r := gin.New()
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	req := httptest.NewRequest(http.MethodGet, "/ws/lobby?token=bad", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestLobbyWSUpgrade(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	lobbyH := NewLobbyHandler(manager, testSecret, logger)

	r := gin.New()
	r.GET("/ws/lobby", lobbyH.HandleLobbyWS)

	srv := httptest.NewServer(r)
	defer srv.Close()

	token := makeToken(1, "alice")
	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws/lobby?token=" + token

	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer conn.Close()

	if resp.StatusCode != http.StatusSwitchingProtocols {
		t.Errorf("expected 101, got %d", resp.StatusCode)
	}

	if manager.TotalConnections() != 1 {
		t.Errorf("expected 1 connection, got %d", manager.TotalConnections())
	}
}

// ---- PM handler tests ----

func TestSendPMSuccess(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	authClient := &mockAuthClient{
		user: &client.UserResponse{ID: 2, Username: "bob"},
	}
	del := &mockDelivery{}
	pmH := NewPMHandler(manager, authClient, del, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/send", pmH.SendPM)

	body := `{"to": "bob", "text": "hello bob"}`
	req := httptest.NewRequest(http.MethodPost, "/pm/send", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}
	if del.pmCalls != 1 {
		t.Errorf("expected 1 PM delivery, got %d", del.pmCalls)
	}
}

func TestSendPMBadBody(t *testing.T) {
	logger := newLogger()
	pmH := NewPMHandler(ws.NewManager(logger), nil, nil, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/send", pmH.SendPM)

	req := httptest.NewRequest(http.MethodPost, "/pm/send", strings.NewReader("bad"))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestSendPMRecipientNotFound(t *testing.T) {
	logger := newLogger()
	authClient := &mockAuthClient{user: nil, err: nil}
	pmH := NewPMHandler(ws.NewManager(logger), authClient, nil, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/send", pmH.SendPM)

	body := `{"to": "unknown", "text": "hello"}`
	req := httptest.NewRequest(http.MethodPost, "/pm/send", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", w.Code)
	}
}

func TestSendPMAuthServiceError(t *testing.T) {
	logger := newLogger()
	authClient := &mockAuthClient{err: fmt.Errorf("auth service down")}
	pmH := NewPMHandler(ws.NewManager(logger), authClient, nil, logger)

	r := gin.New()
	r.Use(middleware.JWTAuth(testSecret))
	r.POST("/pm/send", pmH.SendPM)

	body := `{"to": "bob", "text": "hello"}`
	req := httptest.NewRequest(http.MethodPost, "/pm/send", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+makeToken(1, "alice"))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusBadGateway {
		t.Errorf("expected 502, got %d", w.Code)
	}
}
