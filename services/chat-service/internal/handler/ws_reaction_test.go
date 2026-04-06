package handler

import (
	"testing"

	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"

	"github.com/gin-gonic/gin"
	"net/http/httptest"
	"strings"
)

// ---- handleAddReaction tests ----

// TestWSAddReactionSuccess verifies that a valid add_reaction command broadcasts
// a reaction_added event to all clients in the room.
func TestWSAddReactionSuccess(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c1.Close()
	c2 := dialAndDrain(t, srvURL, mgr, 2, "bob")
	defer c2.Close()
	drainMessages(c1, 1) // alice gets bob's join

	validMsgID := "550e8400-e29b-41d4-a716-446655440000"
	c1.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": validMsgID,
		"emoji":  "👍",
	})

	// Alice should receive the reaction_added broadcast (sent to all in room).
	msg := readMsg(t, c1)
	if msg["type"] != "reaction_added" {
		t.Errorf("expected reaction_added, got %v", msg["type"])
	}
	if msg["emoji"] != "👍" {
		t.Errorf("expected emoji '👍', got %v", msg["emoji"])
	}
	if msg["msg_id"] != validMsgID {
		t.Errorf("expected msg_id %q, got %v", validMsgID, msg["msg_id"])
	}
}

// TestWSAddReactionEmptyMsgID verifies that add_reaction with empty msg_id returns an error.
func TestWSAddReactionEmptyMsgID(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": "",
		"emoji":  "👍",
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "msg_id is required for reactions" {
		t.Errorf("expected 'msg_id is required for reactions', got %q", detail)
	}
}

// TestWSAddReactionEmptyEmoji verifies that add_reaction with empty emoji returns an error.
func TestWSAddReactionEmptyEmoji(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": "550e8400-e29b-41d4-a716-446655440000",
		"emoji":  "",
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "emoji is required for reactions" {
		t.Errorf("expected 'emoji is required for reactions', got %q", detail)
	}
}

// TestWSAddReactionEmojiTooLong verifies that add_reaction with an emoji exceeding 32
// characters returns an error.
func TestWSAddReactionEmojiTooLong(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c.Close()

	longEmoji := strings.Repeat("x", 33)
	c.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": "550e8400-e29b-41d4-a716-446655440000",
		"emoji":  longEmoji,
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "emoji too long" {
		t.Errorf("expected 'emoji too long', got %q", detail)
	}
}

// TestWSAddReactionMutedUser verifies that a muted user cannot add reactions.
func TestWSAddReactionMutedUser(t *testing.T) {
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		isMuted:  true, // alice is muted by default
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	// Override muteSet so alice (user 1) is muted.
	store.muteSet[adminKey(1, 1)] = true

	wsH := NewWSHandler(manager, store, nil, del, nil, testSecret, nil, logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	defer srv.Close()

	c := dialAndDrain(t, srv.URL, manager, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": "550e8400-e29b-41d4-a716-446655440000",
		"emoji":  "👍",
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error for muted user, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "You are muted in this room" {
		t.Errorf("expected 'You are muted in this room', got %q", detail)
	}
}

// ---- handleRemoveReaction tests ----

// TestWSRemoveReactionSuccess verifies that a valid remove_reaction command broadcasts
// a reaction_removed event to all clients in the room.
func TestWSRemoveReactionSuccess(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c1.Close()
	c2 := dialAndDrain(t, srvURL, mgr, 2, "bob")
	defer c2.Close()
	drainMessages(c1, 1)

	validMsgID := "550e8400-e29b-41d4-a716-446655440000"
	c1.WriteJSON(map[string]string{
		"type":   "remove_reaction",
		"msg_id": validMsgID,
		"emoji":  "👍",
	})

	msg := readMsg(t, c1)
	if msg["type"] != "reaction_removed" {
		t.Errorf("expected reaction_removed, got %v", msg["type"])
	}
	if msg["emoji"] != "👍" {
		t.Errorf("expected emoji '👍', got %v", msg["emoji"])
	}
}

// TestWSRemoveReactionEmptyMsgID verifies that remove_reaction with empty msg_id returns an error.
func TestWSRemoveReactionEmptyMsgID(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{
		"type":   "remove_reaction",
		"msg_id": "",
		"emoji":  "👍",
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "msg_id is required for reactions" {
		t.Errorf("expected 'msg_id is required for reactions', got %q", detail)
	}
}

// TestWSRemoveReactionEmptyEmoji verifies that remove_reaction with empty emoji returns an error.
func TestWSRemoveReactionEmptyEmoji(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{
		"type":   "remove_reaction",
		"msg_id": "550e8400-e29b-41d4-a716-446655440000",
		"emoji":  "",
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "emoji is required for reactions" {
		t.Errorf("expected 'emoji is required for reactions', got %q", detail)
	}
}

// TestWSRemoveReactionEmojiTooLong verifies that remove_reaction with an emoji exceeding 32
// characters returns an error.
func TestWSRemoveReactionEmojiTooLong(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c.Close()

	longEmoji := strings.Repeat("z", 33)
	c.WriteJSON(map[string]string{
		"type":   "remove_reaction",
		"msg_id": "550e8400-e29b-41d4-a716-446655440000",
		"emoji":  longEmoji,
	})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "emoji too long" {
		t.Errorf("expected 'emoji too long', got %q", detail)
	}
}
