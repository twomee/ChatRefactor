package handler

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/gorilla/websocket"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/client"
	"github.com/twomee/chatbox/chat-service/internal/model"
)

const testSecret = "test-secret-key-for-ci"

func init() {
	gin.SetMode(gin.TestMode)
}

// ---- Mock store ----

// mockRoomStore tracks admin/mute state dynamically using maps, simulating
// a real database. Legacy fields (isAdmin, isMuted) are used as defaults
// when the maps are nil, keeping older tests working.
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

	// Dynamic state (used by WS integration tests).
	adminSet map[string]bool // "roomID:userID" -> true
	muteSet  map[string]bool // "roomID:userID" -> true
}

func adminKey(roomID, userID int) string {
	return fmt.Sprintf("%d:%d", roomID, userID)
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
	if m.adminSet != nil {
		var result []model.RoomAdmin
		for k := range m.adminSet {
			var rid, uid int
			fmt.Sscanf(k, "%d:%d", &rid, &uid)
			if rid == roomID {
				result = append(result, model.RoomAdmin{UserID: uid, RoomID: rid})
			}
		}
		return result, nil
	}
	return m.admins, m.err
}

func (m *mockRoomStore) AddAdmin(ctx context.Context, roomID, userID int) (*model.RoomAdmin, error) {
	if m.err != nil {
		return nil, m.err
	}
	if m.adminSet != nil {
		m.adminSet[adminKey(roomID, userID)] = true
	}
	return &model.RoomAdmin{ID: 1, UserID: userID, RoomID: roomID, AppointedAt: time.Now()}, nil
}

func (m *mockRoomStore) RemoveAdmin(ctx context.Context, roomID, userID int) error {
	if m.adminSet != nil {
		delete(m.adminSet, adminKey(roomID, userID))
	}
	return m.err
}

func (m *mockRoomStore) IsAdmin(ctx context.Context, roomID, userID int) (bool, error) {
	if m.adminSet != nil {
		return m.adminSet[adminKey(roomID, userID)], nil
	}
	return m.isAdmin, m.err
}

func (m *mockRoomStore) GetMutedUsers(ctx context.Context, roomID int) ([]model.MutedUser, error) {
	if m.muteSet != nil {
		var result []model.MutedUser
		for k := range m.muteSet {
			var rid, uid int
			fmt.Sscanf(k, "%d:%d", &rid, &uid)
			if rid == roomID {
				result = append(result, model.MutedUser{UserID: uid, RoomID: rid})
			}
		}
		return result, nil
	}
	return m.mutedUsers, m.err
}

func (m *mockRoomStore) MuteUser(ctx context.Context, roomID, userID int) (*model.MutedUser, error) {
	if m.err != nil {
		return nil, m.err
	}
	if m.muteSet != nil {
		m.muteSet[adminKey(roomID, userID)] = true
	}
	return &model.MutedUser{ID: 1, UserID: userID, RoomID: roomID, MutedAt: time.Now()}, nil
}

func (m *mockRoomStore) UnmuteUser(ctx context.Context, roomID, userID int) error {
	if m.muteSet != nil {
		delete(m.muteSet, adminKey(roomID, userID))
	}
	return m.err
}

func (m *mockRoomStore) IsMuted(ctx context.Context, roomID, userID int) (bool, error) {
	if m.muteSet != nil {
		return m.muteSet[adminKey(roomID, userID)], nil
	}
	return m.isMuted, m.err
}

func (m *mockRoomStore) GetAllIncludingInactive(ctx context.Context) ([]model.Room, error) {
	return m.rooms, m.err
}

func (m *mockRoomStore) SetAllActive(ctx context.Context, active bool) (int, error) {
	return len(m.rooms), m.err
}

func (m *mockRoomStore) DeleteAllData(ctx context.Context) error {
	return m.err
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

// ---- Two-phase auth client ----
// Returns different results for GetUserByID (caller admin check) vs
// GetUserByUsername (target user lookup). Used to test PromoteUserInAllRooms
// where the caller must be a global admin but the target lookup can fail.

type mockTwoPhaseAuthClient struct {
	byIDUser       *client.UserResponse
	byIDErr        error
	byUsernameUser *client.UserResponse
	byUsernameErr  error
}

func (m *mockTwoPhaseAuthClient) GetUserByID(ctx context.Context, userID int) (*client.UserResponse, error) {
	return m.byIDUser, m.byIDErr
}

func (m *mockTwoPhaseAuthClient) GetUserByUsername(ctx context.Context, username string) (*client.UserResponse, error) {
	return m.byUsernameUser, m.byUsernameErr
}

func (m *mockTwoPhaseAuthClient) Ping(ctx context.Context) error {
	return nil
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

// createDummyConn creates a WebSocket connection that can be registered with
// the ws.Manager. Uses an in-memory httptest server with a simple upgrader.
// The returned connection is the server-side connection.
func createDummyConn(t *testing.T) *websocket.Conn {
	t.Helper()
	var serverConn *websocket.Conn
	upgrader := websocket.Upgrader{}

	mux := http.NewServeMux()
	mux.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Fatalf("upgrade: %v", err)
		}
		serverConn = conn
	})

	srv := httptest.NewServer(mux)
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws"
	clientConn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer clientConn.Close()

	// Wait for upgrade to complete.
	time.Sleep(50 * time.Millisecond)

	if serverConn == nil {
		t.Fatal("server-side WebSocket connection was not established")
	}

	return serverConn
}

