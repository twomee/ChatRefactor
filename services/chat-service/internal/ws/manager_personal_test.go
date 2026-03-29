package ws

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// drainOne reads and discards one JSON message from a client connection.
// Used to skip the user_online broadcast from ConnectLobby.
func drainOne(t *testing.T, c *websocket.Conn) {
	t.Helper()
	c.SetReadDeadline(time.Now().Add(time.Second))
	var discard map[string]interface{}
	_ = c.ReadJSON(&discard)
	c.SetReadDeadline(time.Time{})
}

// ---- SendPersonal tests ----

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
	drainOne(t, client) // user_online broadcast

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
	drainOne(t, client1) // user_online broadcast
	m.ConnectLobby(serverConns[1], UserInfo{UserID: 42, Username: "alice"})
	// Second conn for same user — no user_online broadcast (not first lobby).

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
	drainOne(t, clientAlice) // user_online broadcast
	m.ConnectLobby(serverConns[1], UserInfo{UserID: 20, Username: "bob"})
	drainOne(t, clientAlice) // bob's user_online broadcast
	drainOne(t, clientBob)   // bob's user_online broadcast

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
