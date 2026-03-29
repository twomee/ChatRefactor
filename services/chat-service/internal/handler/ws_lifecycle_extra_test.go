package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/jackc/pgx/v5"

	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/store"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- sendHistory tests ----

// TestSendHistoryWithRealMessageService verifies that when the message service
// returns valid history, it is forwarded to the client with transformed field names.
func TestSendHistoryWithRealMessageService(t *testing.T) {
	// Create a fake message service that returns one message.
	msgSvc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify the Authorization header is forwarded.
		if r.Header.Get("Authorization") == "" {
			t.Error("expected Authorization header to be forwarded to message service")
		}
		messages := []map[string]interface{}{
			{
				"message_id":  "abc-123",
				"sender_name": "alice",
				"content":     "hello history",
				"sent_at":     "2024-01-01T00:00:00Z",
				"is_deleted":  false,
				"reactions":   []interface{}{},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(messages)
	}))
	defer msgSvc.Close()

	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(manager, store, nil, del, nil, testSecret, msgSvc.URL, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	defer srv.Close()

	token := makeToken(1, "alice")
	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws/1?token=" + token
	c, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer c.Close()

	// Read join frame.
	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	var joinMsg map[string]interface{}
	if err := c.ReadJSON(&joinMsg); err != nil {
		t.Fatalf("read join: %v", err)
	}

	// Read history frame.
	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	var historyMsg map[string]interface{}
	if err := c.ReadJSON(&historyMsg); err != nil {
		t.Fatalf("read history: %v", err)
	}

	if historyMsg["type"] != "history" {
		t.Errorf("expected type 'history', got %v", historyMsg["type"])
	}

	messages, ok := historyMsg["messages"].([]interface{})
	if !ok {
		t.Fatalf("expected messages to be a slice, got %T", historyMsg["messages"])
	}
	if len(messages) != 1 {
		t.Fatalf("expected 1 message in history, got %d", len(messages))
	}

	m, ok := messages[0].(map[string]interface{})
	if !ok {
		t.Fatalf("expected message to be a map")
	}
	// Field name transformation: sender_name -> from, content -> text.
	if m["from"] != "alice" {
		t.Errorf("expected from='alice', got %v", m["from"])
	}
	if m["text"] != "hello history" {
		t.Errorf("expected text='hello history', got %v", m["text"])
	}
	if m["msg_id"] != "abc-123" {
		t.Errorf("expected msg_id='abc-123', got %v", m["msg_id"])
	}
}

// TestSendHistoryMessageServiceNonOK verifies that a non-200 response from the
// message service results in an empty history frame sent to the client.
func TestSendHistoryMessageServiceNonOK(t *testing.T) {
	msgSvc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer msgSvc.Close()

	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	roomStore := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(manager, roomStore, nil, del, nil, testSecret, msgSvc.URL, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	defer srv.Close()

	token := makeToken(1, "alice")
	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws/1?token=" + token
	c, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer c.Close()

	drainMessages(c, 1) // join

	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	var historyMsg map[string]interface{}
	if err := c.ReadJSON(&historyMsg); err != nil {
		t.Fatalf("read history: %v", err)
	}
	if historyMsg["type"] != "history" {
		t.Errorf("expected type 'history', got %v", historyMsg["type"])
	}
	messages, _ := historyMsg["messages"].([]interface{})
	if len(messages) != 0 {
		t.Errorf("expected 0 messages on 503, got %d", len(messages))
	}
}

// TestSendHistoryMessageServiceBadJSON verifies that when the message service returns
// invalid JSON, the handler falls back to an empty history without panicking.
func TestSendHistoryMessageServiceBadJSON(t *testing.T) {
	msgSvc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte("not valid json {"))
	}))
	defer msgSvc.Close()

	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	roomStore := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(manager, roomStore, nil, del, nil, testSecret, msgSvc.URL, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	defer srv.Close()

	token := makeToken(1, "alice")
	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws/1?token=" + token
	c, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer c.Close()

	drainMessages(c, 1) // join

	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	var historyMsg map[string]interface{}
	if err := c.ReadJSON(&historyMsg); err != nil {
		t.Fatalf("read history: %v", err)
	}
	if historyMsg["type"] != "history" {
		t.Errorf("expected type 'history', got %v", historyMsg["type"])
	}
}

// ---- sendReadPosition tests ----

// mockReadPositionStoreWithData is a mock that returns a read position on Get.
type mockReadPositionStoreWithData struct {
	pos *store.ReadPosition
	err error
}

func (m *mockReadPositionStoreWithData) Upsert(ctx context.Context, userID, roomID int, messageID string) error {
	return nil
}

func (m *mockReadPositionStoreWithData) Get(ctx context.Context, userID, roomID int) (*store.ReadPosition, error) {
	return m.pos, m.err
}

// TestSendReadPositionWithData verifies that when a read position exists, a
// read_position frame is sent to the client on join.
func TestSendReadPositionWithData(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	roomStore := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	rpStore := &mockReadPositionStoreWithData{
		pos: &store.ReadPosition{
			UserID:            1,
			RoomID:            1,
			LastReadMessageID: "550e8400-e29b-41d4-a716-446655440000",
		},
	}
	wsH := NewWSHandler(manager, roomStore, rpStore, del, nil, testSecret, "http://localhost:8004", logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	defer srv.Close()

	token := makeToken(1, "alice")
	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws/1?token=" + token
	c, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer c.Close()

	// Expect: join + history + read_position (order may vary due to goroutine).
	// Collect up to 3 messages within a timeout.
	c.SetReadDeadline(time.Now().Add(3 * time.Second))

	received := make(map[string]bool)
	for i := 0; i < 3; i++ {
		var m map[string]interface{}
		if err := c.ReadJSON(&m); err != nil {
			break
		}
		received[m["type"].(string)] = true
		if _, ok := m["last_read_message_id"]; ok {
			if m["last_read_message_id"] != "550e8400-e29b-41d4-a716-446655440000" {
				t.Errorf("expected last_read_message_id '550e8400-e29b-41d4-a716-446655440000', got %v", m["last_read_message_id"])
			}
		}
	}

	if !received["read_position"] {
		t.Error("expected to receive a read_position frame after joining")
	}
}

// TestSendReadPositionNoStore verifies that when no read position store is configured,
// no read_position frame is sent (graceful degradation).
func TestSendReadPositionNoStore(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	// The setupWSServerWithDelivery uses nil for readPositionStore.
	c := dialWS(t, srvURL, 1, "alice")
	defer c.Close()

	// Drain join + history. Should not receive a read_position frame.
	drainMessages(c, 2)

	c.SetReadDeadline(time.Now().Add(300 * time.Millisecond))
	var m map[string]interface{}
	err := c.ReadJSON(&m)
	if err == nil && m["type"] == "read_position" {
		t.Error("did not expect read_position frame when store is nil")
	}
}

// TestSendReadPositionStoreReturnsError verifies that when the store returns an error
// (e.g. pgx.ErrNoRows for first visit), no read_position frame is sent.
func TestSendReadPositionStoreReturnsError(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	roomStore := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	rpStore := &mockReadPositionStoreWithData{
		err: pgx.ErrNoRows, // first-time user has no read position
	}
	wsH := NewWSHandler(manager, roomStore, rpStore, del, nil, testSecret, "http://localhost:8004", logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	defer srv.Close()

	c := dialWS(t, srv.URL, 1, "alice")
	defer c.Close()

	drainMessages(c, 2) // join + history

	// Should NOT receive read_position on first visit.
	c.SetReadDeadline(time.Now().Add(300 * time.Millisecond))
	var m map[string]interface{}
	err := c.ReadJSON(&m)
	if err == nil && m["type"] == "read_position" {
		t.Error("did not expect read_position frame when store returns error")
	}
}
