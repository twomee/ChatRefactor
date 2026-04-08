package handler

import (
	"fmt"
	"github.com/gin-gonic/gin"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
	"github.com/gorilla/websocket"

	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- WebSocket handler tests ----

func TestWSHandlerRejectsWithoutToken(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	wsH := NewWSHandler(manager, nil, nil, nil, nil, testSecret, nil, logger, nil, false)

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
	wsH := NewWSHandler(manager, nil, nil, nil, nil, testSecret, nil, logger, nil, false)

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
	wsH := NewWSHandler(manager, nil, nil, nil, nil, testSecret, nil, logger, nil, false)

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
	wsH := NewWSHandler(manager, store, nil, nil, nil, testSecret, nil, logger, nil, false)

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
	wsH := NewWSHandler(manager, store, nil, nil, nil, testSecret, nil, logger, nil, false)

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
	wsH := NewWSHandler(manager, store, nil, del, nil, testSecret, nil, logger, nil, false)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)

	srv := httptest.NewServer(r)
	defer srv.Close()

	// Register lobby so HandleRoomWS doesn't reject with "no lobby connection".
	cleanupLobby := registerTestLobby(t, manager, 1, "alice")
	defer cleanupLobby()

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

	// Verify delivery was called: 1 for the join system message
	// ("alice joined the room") + 1 for the chat message = 2 total.
	if del.chatCalls != 2 {
		t.Errorf("expected 2 chat deliveries (join + message), got %d", del.chatCalls)
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
	wsH := NewWSHandler(manager, store, nil, del, nil, testSecret, nil, logger, nil, false)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)

	srv := httptest.NewServer(r)
	defer srv.Close()

	cleanupLobby := registerTestLobby(t, manager, 1, "alice")
	defer cleanupLobby()

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

	// Only the join system message should have been delivered (1 call).
	// The muted user's chat message should NOT have triggered a delivery.
	if del.chatCalls != 1 {
		t.Errorf("expected 1 chat delivery (join only), got %d", del.chatCalls)
	}
}

