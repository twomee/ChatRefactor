package handler

import (
	"fmt"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"
	"net/http/httptest"
)

// ---- handleMute missing branches ----

// TestWSMuteTargetIsAdmin verifies that an admin cannot mute another admin.
func TestWSMuteTargetIsAdmin(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Promote bob to admin first.
	c1.WriteJSON(map[string]string{"type": "promote", "target": "bob"})
	drainMessages(c1, 1)
	drainMessages(c2, 1)

	// Alice (admin) tries to mute bob (also admin) — should fail.
	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Cannot mute an admin" {
		t.Errorf("expected 'Cannot mute an admin', got %q", detail)
	}
}

// TestWSMuteAlreadyMuted verifies that muting an already-muted user returns an error.
func TestWSMuteAlreadyMuted(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// First mute — should succeed.
	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})
	drainMessages(c1, 1) // admin's broadcast
	drainMessages(c2, 1) // muted

	// Second mute of already-muted bob — should fail.
	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "User is already muted" {
		t.Errorf("expected 'User is already muted', got %q", detail)
	}
}

// TestWSMuteEmptyTarget verifies that mute with empty target returns an error.
func TestWSMuteEmptyTarget(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "mute", "target": ""})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Target username required" {
		t.Errorf("expected 'Target username required', got %q", detail)
	}
}

// TestWSMuteNonAdmin verifies that a non-admin cannot mute other users.
func TestWSMuteNonAdmin(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Bob (non-admin) tries to mute alice.
	c2.WriteJSON(map[string]string{"type": "mute", "target": "alice"})
	msg := readMsg(t, c2)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Admin access required" {
		t.Errorf("expected 'Admin access required', got %q", detail)
	}
}

// TestWSMuteUserNotInRoom verifies that muting a user not in the room returns an error.
func TestWSMuteUserNotInRoom(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "mute", "target": "ghost"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "User not in room" {
		t.Errorf("expected 'User not in room', got %q", detail)
	}
}

// TestWSMuteDatabaseError verifies that a database error during mute returns an error to client.
func TestWSMuteDatabaseError(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
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

	c1 := dialWS(t, srv.URL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srv.URL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Inject error so MuteUser fails.
	store.err = fmt.Errorf("db error")

	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Failed to mute user" {
		t.Errorf("expected 'Failed to mute user', got %q", detail)
	}
}

// ---- handleKick missing branches ----

// TestWSKickTargetIsAdmin verifies that an admin cannot kick another admin.
func TestWSKickTargetIsAdmin(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Promote bob first.
	c1.WriteJSON(map[string]string{"type": "promote", "target": "bob"})
	drainMessages(c1, 1)
	drainMessages(c2, 1)

	// Alice tries to kick bob (now admin) — should fail.
	c1.WriteJSON(map[string]string{"type": "kick", "target": "bob"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Cannot kick an admin" {
		t.Errorf("expected 'Cannot kick an admin', got %q", detail)
	}
}

// TestWSKickEmptyTarget verifies that kick with empty target returns an error.
func TestWSKickEmptyTarget(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "kick", "target": ""})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Target username required" {
		t.Errorf("expected 'Target username required', got %q", detail)
	}
}

// TestWSKickNonAdmin verifies that a non-admin cannot kick other users.
func TestWSKickNonAdmin(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Bob (non-admin) tries to kick alice.
	c2.WriteJSON(map[string]string{"type": "kick", "target": "alice"})
	msg := readMsg(t, c2)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Admin access required" {
		t.Errorf("expected 'Admin access required', got %q", detail)
	}
}

// TestWSKickUserNotInRoom verifies that kicking a user not in the room returns an error.
func TestWSKickUserNotInRoom(t *testing.T) {
	srvURL, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "kick", "target": "ghost"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "User not in room" {
		t.Errorf("expected 'User not in room', got %q", detail)
	}
}
