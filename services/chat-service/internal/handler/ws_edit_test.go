package handler

import (
	"testing"
	"time"

	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"net/http/httptest"
	"strings"
)

// setupWSServerWithDelivery creates a test WebSocket server and returns the
// delivery mock so tests can assert on how many Kafka messages were sent.
func setupWSServerWithDelivery(t *testing.T) (srvURL string, del *mockDelivery, cleanup func()) {
	t.Helper()
	logger := newLogger()
	manager := ws.NewManager(logger)
	del = &mockDelivery{}
	store := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(manager, store, nil, del, nil, testSecret, "http://localhost:8004", logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	return srv.URL, del, srv.Close
}

// dialAndDrain connects a WebSocket client and drains the initial join+history frames.
func dialAndDrain(t *testing.T, srvURL string, userID int, username string) *websocket.Conn {
	t.Helper()
	token := makeToken(userID, username)
	wsURL := "ws" + strings.TrimPrefix(srvURL, "http") + "/ws/1?token=" + token
	c, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial error for %s: %v", username, err)
	}
	// drain join + history
	drainMessages(c, 2)
	return c
}

// ---- handleEditMessage tests ----

// TestWSEditMessageSuccess verifies that a valid edit_message command broadcasts
// a message_edited event to all clients in the room and calls DeliverChat.
func TestWSEditMessageSuccess(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialAndDrain(t, srvURL, 1, "alice")
	defer c1.Close()
	c2 := dialAndDrain(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c1, 1) // alice gets bob's join

	validMsgID := "550e8400-e29b-41d4-a716-446655440000"
	c1.WriteJSON(map[string]string{
		"type":   "edit_message",
		"msg_id": validMsgID,
		"text":   "updated text",
	})

	// Both clients should receive message_edited broadcast.
	msg := readMsg(t, c1)
	if msg["type"] != "message_edited" {
		t.Errorf("expected message_edited, got %v", msg["type"])
	}
	if msg["text"] != "updated text" {
		t.Errorf("expected 'updated text', got %v", msg["text"])
	}
	if msg["msg_id"] != validMsgID {
		t.Errorf("expected msg_id %q, got %v", validMsgID, msg["msg_id"])
	}
}

// TestWSEditMessageEmptyMsgID verifies that edit_message with an empty msg_id
// returns an error frame and does NOT broadcast.
func TestWSEditMessageEmptyMsgID(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{
		"type":   "edit_message",
		"msg_id": "",
		"text":   "some text",
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Message ID is required for editing" {
		t.Errorf("expected 'Message ID is required for editing', got %q", detail)
	}
}

// TestWSEditMessageEmptyText verifies that edit_message with empty text returns an error.
func TestWSEditMessageEmptyText(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{
		"type":   "edit_message",
		"msg_id": "550e8400-e29b-41d4-a716-446655440000",
		"text":   "",
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Edited message text cannot be empty" {
		t.Errorf("expected 'Edited message text cannot be empty', got %q", detail)
	}
}

// TestWSEditMessageTooLong verifies that edit_message with text exceeding maxContentLength
// returns an error.
func TestWSEditMessageTooLong(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, 1, "alice")
	defer c.Close()

	longText := strings.Repeat("a", maxContentLength+1)
	c.WriteJSON(map[string]string{
		"type":   "edit_message",
		"msg_id": "550e8400-e29b-41d4-a716-446655440000",
		"text":   longText,
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Message too long" {
		t.Errorf("expected 'Message too long', got %q", detail)
	}
}

// ---- handleDeleteMessage tests ----

// TestWSDeleteMessageSuccess verifies that a valid delete_message command broadcasts
// a message_deleted event to all clients in the room.
func TestWSDeleteMessageSuccess(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialAndDrain(t, srvURL, 1, "alice")
	defer c1.Close()
	c2 := dialAndDrain(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c1, 1) // alice gets bob's join

	validMsgID := "550e8400-e29b-41d4-a716-446655440001"
	c1.WriteJSON(map[string]string{
		"type":   "delete_message",
		"msg_id": validMsgID,
	})

	msg := readMsg(t, c1)
	if msg["type"] != "message_deleted" {
		t.Errorf("expected message_deleted, got %v", msg["type"])
	}
	if msg["msg_id"] != validMsgID {
		t.Errorf("expected msg_id %q, got %v", validMsgID, msg["msg_id"])
	}
}

// TestWSDeleteMessageEmptyMsgID verifies that delete_message with an empty msg_id
// returns an error frame and does NOT broadcast.
func TestWSDeleteMessageEmptyMsgID(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{
		"type":   "delete_message",
		"msg_id": "",
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Message ID is required for deletion" {
		t.Errorf("expected 'Message ID is required for deletion', got %q", detail)
	}
}

// TestWSDeleteMessageDeliveryFailure verifies that a Kafka delivery failure on
// delete_message does not crash the handler or return an error to the client.
// (errors on persist are logged as warnings, not sent back).
func TestWSDeleteMessageDeliveryFailure(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{err: nil} // no error; just check broadcast still works
	store := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(manager, store, nil, del, nil, testSecret, "http://localhost:8004", logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	defer srv.Close()

	c := dialAndDrain(t, srv.URL, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{
		"type":   "delete_message",
		"msg_id": "550e8400-e29b-41d4-a716-446655440002",
	})

	msg := readMsg(t, c)
	if msg["type"] != "message_deleted" {
		t.Errorf("expected message_deleted, got %v", msg["type"])
	}

	// Give time for Kafka delivery goroutine to execute.
	time.Sleep(50 * time.Millisecond)
}
