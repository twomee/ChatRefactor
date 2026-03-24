package handler

import (
	"github.com/gin-gonic/gin"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
	"github.com/gorilla/websocket"

	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- WebSocket admin command integration tests ----
// These use a real WebSocket connection via httptest, following the same
// pattern as TestWSHandlerRoomWSUpgradeAndMessage.

func setupWSServer(t *testing.T) (srvURL string, cleanup func()) {
	t.Helper()
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(manager, store, del, testSecret, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	return srv.URL, srv.Close
}

func dialWS(t *testing.T, srvURL string, userID int, username string) *websocket.Conn {
	t.Helper()
	token := makeToken(userID, username)
	wsURL := "ws" + strings.TrimPrefix(srvURL, "http") + "/ws/1?token=" + token
	c, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		status := 0
		if resp != nil {
			status = resp.StatusCode
		}
		t.Fatalf("dial error for %s (HTTP %d): %v", username, status, err)
	}
	return c
}

func drainMessages(c *websocket.Conn, n int) {
	c.SetReadDeadline(time.Now().Add(2 * time.Second))
	for i := 0; i < n; i++ {
		var m map[string]interface{}
		if err := c.ReadJSON(&m); err != nil {
			break
		}
	}
}

func readMsg(t *testing.T, c *websocket.Conn) map[string]interface{} {
	t.Helper()
	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	var msg map[string]interface{}
	if err := c.ReadJSON(&msg); err != nil {
		t.Fatalf("readMsg: %v", err)
	}
	return msg
}

func TestWSMuteCommand(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2) // join + history

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2) // join + history
	drainMessages(c1, 1) // alice gets bob's join

	// Alice (auto-admin) mutes Bob.
	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})

	msg := readMsg(t, c2)
	if msg["type"] != "muted" {
		t.Errorf("expected muted, got %v", msg["type"])
	}

	// Bob tries to send — should get error.
	drainMessages(c1, 1) // drain admin's mute broadcast
	c2.WriteJSON(map[string]string{"type": "message", "text": "blocked"})
	msg = readMsg(t, c2)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSUnmuteCommand(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)
	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Mute then unmute.
	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})
	drainMessages(c2, 1) // muted
	drainMessages(c1, 1) // admin's broadcast

	c1.WriteJSON(map[string]string{"type": "unmute", "target": "bob"})
	msg := readMsg(t, c2)
	if msg["type"] != "unmuted" {
		t.Errorf("expected unmuted, got %v", msg["type"])
	}
}

func TestWSPromoteCommand(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)
	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	c1.WriteJSON(map[string]string{"type": "promote", "target": "bob"})
	msg := readMsg(t, c2)
	if msg["type"] != "new_admin" {
		t.Errorf("expected new_admin, got %v", msg["type"])
	}
}

func TestWSKickCommand(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)
	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	c1.WriteJSON(map[string]string{"type": "kick", "target": "bob"})
	msg := readMsg(t, c2)
	if msg["type"] != "kicked" {
		t.Errorf("expected kicked, got %v", msg["type"])
	}
}

func TestWSKickSelfRejected(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "kick", "target": "alice"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSMuteSelfRejected(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "mute", "target": "alice"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSPrivateMessage(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)
	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	c1.WriteJSON(map[string]string{"type": "private_message", "to": "bob", "text": "hello pm"})

	msg := readMsg(t, c2)
	if msg["type"] != "private_message" {
		t.Errorf("expected private_message, got %v", msg["type"])
	}
	if msg["text"] != "hello pm" {
		t.Errorf("expected 'hello pm', got %v", msg["text"])
	}

	// Alice gets echo with self=true.
	msg = readMsg(t, c1)
	if msg["self"] != true {
		t.Errorf("expected self=true, got %v", msg["self"])
	}
}

func TestWSPrivateMessageSelfRejected(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "private_message", "to": "alice", "text": "self pm"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}
