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

func TestConnectAndDisconnectLobby(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	user := UserInfo{UserID: 1, Username: "alice"}
	m.ConnectLobby(conn, user)

	if m.TotalConnections() != 1 {
		t.Errorf("expected 1 connection, got %d", m.TotalConnections())
	}

	m.DisconnectLobby(conn)

	if m.TotalConnections() != 0 {
		t.Errorf("expected 0 connections after lobby disconnect, got %d", m.TotalConnections())
	}
}

func TestDisconnectLobbyUnknownConn(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	// Disconnecting a lobby conn that was never registered should not panic.
	m.DisconnectLobby(conn)
	if m.TotalConnections() != 0 {
		t.Errorf("expected 0, got %d", m.TotalConnections())
	}
}

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

func TestSendPersonalSuccess(t *testing.T) {
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

	m.ConnectLobby(serverConn, UserInfo{UserID: 42, Username: "bob"})

	msg := map[string]string{"type": "pm", "content": "hello bob"}
	sent := m.SendPersonal(42, msg)
	if !sent {
		t.Error("expected SendPersonal to return true")
	}

	var received map[string]string
	if err := client.ReadJSON(&received); err != nil {
		t.Fatalf("read: %v", err)
	}
	if received["content"] != "hello bob" {
		t.Errorf("expected 'hello bob', got %q", received["content"])
	}
}

func TestSendPersonalNoRecipient(t *testing.T) {
	m := newTestManager()

	msg := map[string]string{"type": "pm", "content": "hello"}
	sent := m.SendPersonal(999, msg)
	if sent {
		t.Error("expected SendPersonal to return false when no recipient connected")
	}
}

func TestSendPersonalFailedWrite(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)

	m.ConnectLobby(conn, UserInfo{UserID: 10, Username: "alice"})

	// Close the connection to simulate failure.
	cleanup()

	msg := map[string]string{"type": "pm", "content": "hello"}
	sent := m.SendPersonal(10, msg)
	if sent {
		t.Error("expected SendPersonal to return false when write fails")
	}
}

func TestGetUsersInRoomEmpty(t *testing.T) {
	m := newTestManager()
	users := m.GetUsersInRoom(99)
	if len(users) != 0 {
		t.Errorf("expected empty user list, got %v", users)
	}
}

func TestGetUsersInRoomDeduplicates(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	// Same user, two connections.
	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(1, conn2, UserInfo{UserID: 10, Username: "alice"})

	users := m.GetUsersInRoom(1)
	if len(users) != 1 {
		t.Errorf("expected 1 unique user, got %d", len(users))
	}
}

func TestRoomCount(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(2, conn2, UserInfo{UserID: 20, Username: "bob"})

	if m.RoomCount() != 2 {
		t.Errorf("expected 2 rooms, got %d", m.RoomCount())
	}
}

func TestTotalConnectionsMixedRoomAndLobby(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectLobby(conn2, UserInfo{UserID: 20, Username: "bob"})

	if m.TotalConnections() != 2 {
		t.Errorf("expected 2 total connections, got %d", m.TotalConnections())
	}
}
