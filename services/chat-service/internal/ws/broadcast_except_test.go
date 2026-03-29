package ws

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// TestBroadcastRoomExceptSkipsSender verifies that BroadcastRoomExcept sends
// the message to all room members except the specified "except" connection.
func TestBroadcastRoomExceptSkipsSender(t *testing.T) {
	m := newTestManager()

	upgrader := websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true },
	}

	var serverConns []*websocket.Conn
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Fatalf("upgrade: %v", err)
		}
		serverConns = append(serverConns, c)
	}))
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http")

	client1, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial c1: %v", err)
	}
	defer client1.Close()
	for len(serverConns) < 1 {
	}

	client2, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial c2: %v", err)
	}
	defer client2.Close()
	for len(serverConns) < 2 {
	}

	// Register server-side connections.
	m.ConnectRoom(1, serverConns[0], UserInfo{UserID: 1, Username: "alice"})
	m.ConnectRoom(1, serverConns[1], UserInfo{UserID: 2, Username: "bob"})

	msg := map[string]string{"type": "typing", "username": "alice"}

	// BroadcastRoomExcept serverConns[0] (alice) — bob should receive, alice should NOT.
	m.BroadcastRoomExcept(1, serverConns[0], msg)

	// bob (client2) should receive.
	client2.SetReadDeadline(time.Now().Add(2 * time.Second))
	var received map[string]string
	if err := client2.ReadJSON(&received); err != nil {
		t.Fatalf("bob read: %v", err)
	}
	if received["type"] != "typing" {
		t.Errorf("expected type 'typing', got %q", received["type"])
	}
	if received["username"] != "alice" {
		t.Errorf("expected username 'alice', got %q", received["username"])
	}

	// alice (client1) should NOT receive the message.
	client1.SetReadDeadline(time.Now().Add(200 * time.Millisecond))
	var echo map[string]string
	err = client1.ReadJSON(&echo)
	if err == nil && echo["type"] == "typing" {
		t.Error("alice should NOT receive her own typing indicator via BroadcastRoomExcept")
	}
}

// TestBroadcastRoomExceptEmptyRoom verifies that calling BroadcastRoomExcept
// on an empty room does not panic.
func TestBroadcastRoomExceptEmptyRoom(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	// Should not panic on room with no registered connections.
	msg := map[string]string{"type": "typing"}
	m.BroadcastRoomExcept(999, conn, msg)
}

// TestBroadcastRoomExceptSingleUser verifies that when only one user is in a room
// and they are excluded, no messages are sent.
func TestBroadcastRoomExceptSingleUser(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectRoom(1, conn, UserInfo{UserID: 1, Username: "alice"})

	// Exclude the only user — nobody should receive this.
	msg := map[string]string{"type": "typing", "username": "alice"}
	m.BroadcastRoomExcept(1, conn, msg)
	// Test passes if it does not panic or deadlock.
}

// TestBroadcastRoomExceptMarshalError verifies that a marshal error (e.g. channel
// value) causes an early return without panicking.
func TestBroadcastRoomExceptMarshalError(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectRoom(1, conn, UserInfo{UserID: 1, Username: "alice"})

	// json.Marshal cannot handle channels — triggers early return.
	m.BroadcastRoomExcept(1, conn, make(chan int))
	// Test passes if no panic occurs.
}

// TestBroadcastRoomExceptRemovesFailedConn verifies that when a non-excluded
// connection fails during write, it is removed from the room.
func TestBroadcastRoomExceptRemovesFailedConn(t *testing.T) {
	m := newTestManager()

	upgrader := websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true },
	}
	var serverConns []*websocket.Conn
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Fatalf("upgrade: %v", err)
		}
		serverConns = append(serverConns, c)
	}))
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http")

	client1, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial c1: %v", err)
	}
	for len(serverConns) < 1 {
	}
	client2, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial c2: %v", err)
	}
	for len(serverConns) < 2 {
	}

	m.ConnectRoom(1, serverConns[0], UserInfo{UserID: 1, Username: "alice"})
	m.ConnectRoom(1, serverConns[1], UserInfo{UserID: 2, Username: "bob"})

	// Close bob's client connection to simulate a dead connection.
	client2.Close()
	serverConns[1].Close()

	// BroadcastRoomExcept excluding alice — bob's dead conn should be cleaned up.
	msg := map[string]string{"type": "typing", "username": "alice"}
	m.BroadcastRoomExcept(1, serverConns[0], msg)

	// Wait briefly for cleanup goroutine.
	time.Sleep(50 * time.Millisecond)

	// bob's connection should have been removed; only alice remains.
	if m.TotalConnections() != 1 {
		t.Errorf("expected 1 connection after failed broadcast, got %d", m.TotalConnections())
	}

	client1.Close()
}
