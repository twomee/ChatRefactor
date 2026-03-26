package ws

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

func newTestManager() *Manager {
	logger, _ := zap.NewDevelopment()
	return NewManager(logger)
}

// helper: create a real websocket connection pair via httptest.
func newWSConn(t *testing.T) (*websocket.Conn, func()) {
	t.Helper()
	var serverConn *websocket.Conn
	upgrader := websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true },
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var err error
		serverConn, err = upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Fatalf("upgrade error: %v", err)
		}
	}))

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http")
	clientConn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial error: %v", err)
	}

	cleanup := func() {
		clientConn.Close()
		if serverConn != nil {
			serverConn.Close()
		}
		srv.Close()
	}

	// Wait for upgrade to complete by reading the server conn.
	// Give a moment for server to assign serverConn.
	for serverConn == nil {
		// busy wait -- fine in tests
	}

	return serverConn, cleanup
}

func TestNewManager(t *testing.T) {
	m := newTestManager()
	if m.RoomCount() != 0 {
		t.Errorf("expected 0 rooms, got %d", m.RoomCount())
	}
	if m.TotalConnections() != 0 {
		t.Errorf("expected 0 connections, got %d", m.TotalConnections())
	}
}

func TestConnectRoomAndDisconnect(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	user := UserInfo{UserID: 1, Username: "alice"}
	m.ConnectRoom(42, conn, user)

	if m.RoomCount() != 1 {
		t.Errorf("expected 1 room, got %d", m.RoomCount())
	}
	if m.TotalConnections() != 1 {
		t.Errorf("expected 1 connection, got %d", m.TotalConnections())
	}

	users := m.GetUsersInRoom(42)
	if len(users) != 1 || users[0] != 1 {
		t.Errorf("expected [1], got %v", users)
	}

	m.DisconnectRoom(42, conn)

	if m.RoomCount() != 0 {
		t.Errorf("expected 0 rooms after disconnect, got %d", m.RoomCount())
	}
	if m.TotalConnections() != 0 {
		t.Errorf("expected 0 connections after disconnect, got %d", m.TotalConnections())
	}
}

func TestMultipleUsersInRoom(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(1, conn2, UserInfo{UserID: 20, Username: "bob"})

	users := m.GetUsersInRoom(1)
	if len(users) != 2 {
		t.Errorf("expected 2 users, got %d", len(users))
	}
	if m.TotalConnections() != 2 {
		t.Errorf("expected 2 total connections, got %d", m.TotalConnections())
	}
}

func TestDisconnectRoomUnknownConn(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	// Disconnecting a conn that was never registered should not panic.
	m.DisconnectRoom(99, conn)
	if m.RoomCount() != 0 {
		t.Errorf("expected 0 rooms, got %d", m.RoomCount())
	}
}

// ---- SendToConn tests ----

func TestSendToConnSuccess(t *testing.T) {
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
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http")
	client, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer client.Close()

	for serverConn == nil {
	}

	// Register the connection so connMu is populated (via ConnectRoom).
	m.ConnectRoom(1, serverConn, UserInfo{UserID: 1, Username: "alice"})

	msg := map[string]string{"type": "test", "content": "hello"}
	if err := m.SendToConn(serverConn, msg); err != nil {
		t.Fatalf("SendToConn returned error: %v", err)
	}

	var received map[string]string
	if err := client.ReadJSON(&received); err != nil {
		t.Fatalf("client read: %v", err)
	}
	if received["content"] != "hello" {
		t.Errorf("expected 'hello', got %q", received["content"])
	}
	if received["type"] != "test" {
		t.Errorf("expected 'test', got %q", received["type"])
	}
}

func TestSendToConnMarshalError(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectRoom(1, conn, UserInfo{UserID: 1, Username: "alice"})

	// json.Marshal cannot handle channels — this triggers a marshal error.
	err := m.SendToConn(conn, make(chan int))
	if err == nil {
		t.Error("expected marshal error, got nil")
	}
}

func TestSendToConnUnregistered(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	// conn is never registered with the manager, so connMu lookup fails.
	msg := map[string]string{"type": "test"}
	err := m.SendToConn(conn, msg)
	if err == nil {
		t.Error("expected error for unregistered connection, got nil")
	}
}

func TestSendToConnClosedConn(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)

	m.ConnectRoom(1, conn, UserInfo{UserID: 1, Username: "alice"})

	// Close the connection to simulate failure.
	cleanup()

	msg := map[string]string{"type": "test"}
	err := m.SendToConn(conn, msg)
	if err == nil {
		t.Error("expected write error on closed connection, got nil")
	}
}

