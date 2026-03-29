package handler

import (
	"testing"
)

// ---- handlePrivateMessage additional edge case tests ----

// TestWSPrivateMsgEmptyText verifies that PM with empty text returns an error.
func TestWSPrivateMsgEmptyText(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c1.Close()
	c2 := dialAndDrain(t, srvURL, mgr, 2, "bob")
	defer c2.Close()
	drainMessages(c1, 1)

	c1.WriteJSON(map[string]string{"type": "private_message", "to": "bob", "text": ""})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Message text cannot be empty" {
		t.Errorf("expected 'Message text cannot be empty', got %q", detail)
	}
}

// TestWSPrivateMsgTooLong verifies that PM text exceeding maxContentLength returns an error.
func TestWSPrivateMsgTooLong(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c1 := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c1.Close()
	c2 := dialAndDrain(t, srvURL, mgr, 2, "bob")
	defer c2.Close()
	drainMessages(c1, 1)

	longText := make([]byte, maxContentLength+1)
	for i := range longText {
		longText[i] = 'a'
	}
	c1.WriteJSON(map[string]string{"type": "private_message", "to": "bob", "text": string(longText)})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Message too long" {
		t.Errorf("expected 'Message too long', got %q", detail)
	}
}

// TestWSPrivateMsgEmptyTo verifies that PM with empty recipient returns an error.
func TestWSPrivateMsgEmptyTo(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{"type": "private_message", "to": "", "text": "hello"})
	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "Recipient username required" {
		t.Errorf("expected 'Recipient username required', got %q", detail)
	}
}

// TestWSPrivateMsgTargetNotInRoom verifies that PM to a user not in the room returns an error.
func TestWSPrivateMsgTargetNotInRoom(t *testing.T) {
	srvURL, mgr, _, cleanup := setupWSServerWithDelivery(t)
	defer cleanup()

	c := dialAndDrain(t, srvURL, mgr, 1, "alice")
	defer c.Close()

	c.WriteJSON(map[string]string{"type": "private_message", "to": "ghost", "text": "hello"})
	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "User not in room" {
		t.Errorf("expected 'User not in room', got %q", detail)
	}
}
