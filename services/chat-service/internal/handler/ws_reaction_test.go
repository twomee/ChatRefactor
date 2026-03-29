package handler

import (
	"strings"
	"testing"
)

// ---- Add reaction tests ----

func TestWSAddReactionBroadcast(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2) // join + history

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1) // alice gets bob's join

	// Alice adds a reaction.
	c1.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": "msg-100",
		"emoji":  "thumbsup",
	})

	// Bob should receive the broadcast.
	msg := readMsg(t, c2)
	if msg["type"] != "reaction_added" {
		t.Errorf("expected reaction_added, got %v", msg["type"])
	}
	if msg["msg_id"] != "msg-100" {
		t.Errorf("expected msg_id msg-100, got %v", msg["msg_id"])
	}
	if msg["emoji"] != "thumbsup" {
		t.Errorf("expected emoji thumbsup, got %v", msg["emoji"])
	}
}

func TestWSAddReactionEmptyMsgID(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": "",
		"emoji":  "thumbsup",
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSAddReactionEmptyEmoji(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": "msg-100",
		"emoji":  "",
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSAddReactionEmojiTooLong(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	longEmoji := strings.Repeat("x", 33)
	c1.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": "msg-100",
		"emoji":  longEmoji,
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSAddReactionMutedUser(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Alice mutes Bob.
	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})
	drainMessages(c2, 1) // muted notification
	drainMessages(c1, 1) // admin broadcast

	// Bob tries to add reaction — should get error.
	c2.WriteJSON(map[string]string{
		"type":   "add_reaction",
		"msg_id": "msg-100",
		"emoji":  "thumbsup",
	})

	msg := readMsg(t, c2)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

// ---- Remove reaction tests ----

func TestWSRemoveReactionBroadcast(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Alice removes a reaction.
	c1.WriteJSON(map[string]string{
		"type":   "remove_reaction",
		"msg_id": "msg-200",
		"emoji":  "heart",
	})

	// Bob should receive the broadcast.
	msg := readMsg(t, c2)
	if msg["type"] != "reaction_removed" {
		t.Errorf("expected reaction_removed, got %v", msg["type"])
	}
	if msg["msg_id"] != "msg-200" {
		t.Errorf("expected msg_id msg-200, got %v", msg["msg_id"])
	}
}

func TestWSRemoveReactionEmptyMsgID(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{
		"type":   "remove_reaction",
		"msg_id": "",
		"emoji":  "heart",
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSRemoveReactionEmptyEmoji(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{
		"type":   "remove_reaction",
		"msg_id": "msg-200",
		"emoji":  "",
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSRemoveReactionEmojiTooLong(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	longEmoji := strings.Repeat("x", 33)
	c1.WriteJSON(map[string]string{
		"type":   "remove_reaction",
		"msg_id": "msg-200",
		"emoji":  longEmoji,
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}
