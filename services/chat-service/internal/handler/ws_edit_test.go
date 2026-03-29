package handler

import (
	"strings"
	"testing"
)

// ---- Edit message tests ----

func TestWSEditMessageBroadcast(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2) // join + history

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1) // alice gets bob's join

	// Alice sends an edit_message.
	c1.WriteJSON(map[string]string{
		"type":   "edit_message",
		"msg_id": "msg-123",
		"text":   "updated text",
	})

	// Bob should receive the broadcast.
	msg := readMsg(t, c2)
	if msg["type"] != "message_edited" {
		t.Errorf("expected message_edited, got %v", msg["type"])
	}
	if msg["msg_id"] != "msg-123" {
		t.Errorf("expected msg_id msg-123, got %v", msg["msg_id"])
	}
	if msg["text"] != "updated text" {
		t.Errorf("expected text 'updated text', got %v", msg["text"])
	}
}

func TestWSEditMessageEmptyID(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{
		"type":   "edit_message",
		"msg_id": "",
		"text":   "updated text",
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSEditMessageEmptyText(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{
		"type":   "edit_message",
		"msg_id": "msg-123",
		"text":   "",
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSEditMessageTooLong(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	longText := strings.Repeat("a", maxContentLength+1)
	c1.WriteJSON(map[string]string{
		"type":   "edit_message",
		"msg_id": "msg-123",
		"text":   longText,
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSEditMessageMutedUser(t *testing.T) {
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

	// Bob tries to edit — should get error.
	c2.WriteJSON(map[string]string{
		"type":   "edit_message",
		"msg_id": "msg-123",
		"text":   "edited",
	})

	msg := readMsg(t, c2)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

// ---- Delete message tests ----

func TestWSDeleteMessageBroadcast(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Alice sends a delete_message.
	c1.WriteJSON(map[string]string{
		"type":   "delete_message",
		"msg_id": "msg-456",
	})

	// Bob should receive the broadcast.
	msg := readMsg(t, c2)
	if msg["type"] != "message_deleted" {
		t.Errorf("expected message_deleted, got %v", msg["type"])
	}
	if msg["msg_id"] != "msg-456" {
		t.Errorf("expected msg_id msg-456, got %v", msg["msg_id"])
	}
}

func TestWSDeleteMessageEmptyID(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{
		"type":   "delete_message",
		"msg_id": "",
	})

	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSDeleteMessageMutedUser(t *testing.T) {
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
	drainMessages(c2, 1)
	drainMessages(c1, 1)

	// Bob tries to delete — should get error.
	c2.WriteJSON(map[string]string{
		"type":   "delete_message",
		"msg_id": "msg-456",
	})

	msg := readMsg(t, c2)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}
