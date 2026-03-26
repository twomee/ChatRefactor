package ws

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gorilla/websocket"
)



// ---- Lobby + broadcast tests ----

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
	m.ConnectLobby(serverConns[1], UserInfo{UserID: 20, Username: "bob"})

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

// ---- GetLobbyUsernames tests ----

func TestGetLobbyUsernamesEmpty(t *testing.T) {
	m := newTestManager()
	names := m.GetLobbyUsernames()
	if len(names) != 0 {
		t.Errorf("expected empty list, got %v", names)
	}
}

func TestGetLobbyUsernamesSingleUser(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectLobby(conn, UserInfo{UserID: 1, Username: "alice"})

	names := m.GetLobbyUsernames()
	if len(names) != 1 {
		t.Fatalf("expected 1 username, got %d", len(names))
	}
	if names[0] != "alice" {
		t.Errorf("expected 'alice', got %q", names[0])
	}
}

func TestGetLobbyUsernamesMultipleUsers(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectLobby(conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectLobby(conn2, UserInfo{UserID: 20, Username: "bob"})

	names := m.GetLobbyUsernames()
	if len(names) != 2 {
		t.Fatalf("expected 2 usernames, got %d", len(names))
	}

	nameSet := make(map[string]bool)
	for _, n := range names {
		nameSet[n] = true
	}
	if !nameSet["alice"] || !nameSet["bob"] {
		t.Errorf("expected alice and bob, got %v", names)
	}
}

func TestGetLobbyUsernamesDeduplicates(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	// Same user with two lobby connections (e.g. two browser tabs).
	m.ConnectLobby(conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectLobby(conn2, UserInfo{UserID: 10, Username: "alice"})

	names := m.GetLobbyUsernames()
	if len(names) != 1 {
		t.Errorf("expected 1 deduplicated username, got %d: %v", len(names), names)
	}
	if names[0] != "alice" {
		t.Errorf("expected 'alice', got %q", names[0])
	}
}

func TestGetLobbyUsernamesAfterDisconnect(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectLobby(conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectLobby(conn2, UserInfo{UserID: 20, Username: "bob"})

	m.DisconnectLobby(conn1)

	names := m.GetLobbyUsernames()
	if len(names) != 1 {
		t.Fatalf("expected 1 username after disconnect, got %d", len(names))
	}
	if names[0] != "bob" {
		t.Errorf("expected 'bob', got %q", names[0])
	}
}

// ---- SendPersonal edge case tests ----

func TestSendPersonalMarshalError(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectLobby(conn, UserInfo{UserID: 1, Username: "alice"})

	// json.Marshal cannot handle channels — triggers marshal error path.
	sent := m.SendPersonal(1, make(chan int))
	if sent {
		t.Error("expected SendPersonal to return false on marshal error")
	}
}

func TestSendPersonalMultipleConns(t *testing.T) {
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

	// Same user on two lobby connections (two browser tabs).
	m.ConnectLobby(serverConns[0], UserInfo{UserID: 42, Username: "alice"})
	m.ConnectLobby(serverConns[1], UserInfo{UserID: 42, Username: "alice"})

	msg := map[string]string{"type": "pm", "content": "hello both tabs"}
	sent := m.SendPersonal(42, msg)
	if !sent {
		t.Error("expected SendPersonal to return true")
	}

	// Both clients should receive the message.
	var received map[string]string
	if err := client1.ReadJSON(&received); err != nil {
		t.Fatalf("client1 read: %v", err)
	}
	if received["content"] != "hello both tabs" {
		t.Errorf("client1: expected 'hello both tabs', got %q", received["content"])
	}

	if err := client2.ReadJSON(&received); err != nil {
		t.Fatalf("client2 read: %v", err)
	}
	if received["content"] != "hello both tabs" {
		t.Errorf("client2: expected 'hello both tabs', got %q", received["content"])
	}
}

func TestSendPersonalOnlyTargetsCorrectUser(t *testing.T) {
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

	clientAlice, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer clientAlice.Close()
	for len(serverConns) < 1 {
	}

	clientBob, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer clientBob.Close()
	for len(serverConns) < 2 {
	}

	m.ConnectLobby(serverConns[0], UserInfo{UserID: 10, Username: "alice"})
	m.ConnectLobby(serverConns[1], UserInfo{UserID: 20, Username: "bob"})

	// Send a personal message only to alice.
	msg := map[string]string{"type": "pm", "content": "for alice only"}
	sent := m.SendPersonal(10, msg)
	if !sent {
		t.Error("expected SendPersonal to return true")
	}

	// Alice should receive the message.
	var received map[string]string
	if err := clientAlice.ReadJSON(&received); err != nil {
		t.Fatalf("alice read: %v", err)
	}
	if received["content"] != "for alice only" {
		t.Errorf("expected 'for alice only', got %q", received["content"])
	}

	// Send a second personal message to bob to confirm bob's conn is live
	// and didn't receive Alice's message.
	msg2 := map[string]string{"type": "pm", "content": "for bob"}
	sent = m.SendPersonal(20, msg2)
	if !sent {
		t.Error("expected SendPersonal to return true for bob")
	}

	if err := clientBob.ReadJSON(&received); err != nil {
		t.Fatalf("bob read: %v", err)
	}
	if received["content"] != "for bob" {
		t.Errorf("bob: expected 'for bob', got %q", received["content"])
	}
}

