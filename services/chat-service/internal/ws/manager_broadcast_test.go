package ws

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// drainOneBroadcast reads and discards one JSON message from a client.
// Used to skip the user_online broadcast from ConnectLobby.
func drainOneBroadcast(t *testing.T, c *websocket.Conn) {
	t.Helper()
	c.SetReadDeadline(time.Now().Add(time.Second))
	var discard map[string]interface{}
	_ = c.ReadJSON(&discard)
	c.SetReadDeadline(time.Time{})
}

// ---- BroadcastRoom tests ----

func TestBroadcastRoom(t *testing.T) {
	m := newTestManager()

	// Create server-side connections via httptest and client connections
	// that can actually read.
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

	// Create 2 client connections.
	client1, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer client1.Close()

	// Wait for server to register.
	for len(serverConns) < 1 {
	}

	client2, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer client2.Close()

	for len(serverConns) < 2 {
	}

	m.ConnectRoom(1, serverConns[0], UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(1, serverConns[1], UserInfo{UserID: 20, Username: "bob"})

	msg := map[string]string{"type": "message", "content": "hello"}
	m.BroadcastRoom(1, msg)

	// Read from client side.
	var received map[string]string
	if err := client1.ReadJSON(&received); err != nil {
		t.Fatalf("client1 read: %v", err)
	}
	if received["content"] != "hello" {
		t.Errorf("expected 'hello', got %q", received["content"])
	}

	if err := client2.ReadJSON(&received); err != nil {
		t.Fatalf("client2 read: %v", err)
	}
	if received["content"] != "hello" {
		t.Errorf("expected 'hello', got %q", received["content"])
	}
}

func TestBroadcastRoomEmptyRoom(t *testing.T) {
	m := newTestManager()

	// Should not panic on empty room.
	msg := map[string]string{"type": "message"}
	m.BroadcastRoom(999, msg)
}

func TestBroadcastRoomRemovesFailedConns(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)

	m.ConnectRoom(1, conn, UserInfo{UserID: 10, Username: "alice"})

	// Close the connection to simulate failure.
	cleanup()

	msg := map[string]string{"type": "message", "content": "hello"}
	m.BroadcastRoom(1, msg)

	// After broadcast with failed write, the connection should be cleaned up.
	if m.TotalConnections() != 0 {
		t.Errorf("expected 0 connections after failed broadcast, got %d", m.TotalConnections())
	}
}

// ---- BroadcastLobby tests ----

func TestBroadcastLobbyMultipleClients(t *testing.T) {
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
		t.Fatalf("dial: %v", err)
	}
	defer client1.Close()
	for len(serverConns) < 1 {
	}

	client2, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer client2.Close()
	for len(serverConns) < 2 {
	}

	m.ConnectLobby(serverConns[0], UserInfo{UserID: 10, Username: "alice"})
	drainOneBroadcast(t, client1) // alice user_online
	m.ConnectLobby(serverConns[1], UserInfo{UserID: 20, Username: "bob"})
	drainOneBroadcast(t, client1) // bob user_online
	drainOneBroadcast(t, client2) // bob user_online

	msg := map[string]string{"type": "room_list_updated", "action": "created"}
	m.BroadcastLobby(msg)

	// Both clients should receive the message.
	var received map[string]string
	if err := client1.ReadJSON(&received); err != nil {
		t.Fatalf("client1 read: %v", err)
	}
	if received["type"] != "room_list_updated" {
		t.Errorf("client1: expected type 'room_list_updated', got %q", received["type"])
	}

	if err := client2.ReadJSON(&received); err != nil {
		t.Fatalf("client2 read: %v", err)
	}
	if received["action"] != "created" {
		t.Errorf("client2: expected action 'created', got %q", received["action"])
	}
}

func TestBroadcastLobbyEmptyLobby(t *testing.T) {
	m := newTestManager()

	// Should not panic when no lobby connections exist.
	msg := map[string]string{"type": "room_list_updated"}
	m.BroadcastLobby(msg)
}

func TestBroadcastLobbyMarshalError(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectLobby(conn, UserInfo{UserID: 1, Username: "alice"})

	// json.Marshal cannot handle channels — triggers early return.
	m.BroadcastLobby(make(chan int))

	// Test passes if no panic occurs. The function logs and returns.
}

func TestBroadcastLobbyClosedConn(t *testing.T) {
	m := newTestManager()

	upgrader := websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true },
	}
	var serverConn *websocket.Conn
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var err error
		serverConn, err = upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Fatalf("upgrade: %v", err)
		}
	}))

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http")
	client, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	for serverConn == nil {
	}

	m.ConnectLobby(serverConn, UserInfo{UserID: 10, Username: "alice"})

	// Close both sides to simulate failure.
	client.Close()
	serverConn.Close()
	srv.Close()

	// Should not panic; safeWrite errors are silently ignored.
	msg := map[string]string{"type": "room_list_updated"}
	m.BroadcastLobby(msg)
}
