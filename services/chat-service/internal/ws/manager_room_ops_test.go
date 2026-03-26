package ws

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gorilla/websocket"
)



// ---- Room operation tests ----

// ---------- CloseUserConnsInRoom ----------

func TestCloseUserConnsInRoom(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(1, conn2, UserInfo{UserID: 20, Username: "bob"})

	m.CloseUserConnsInRoom(1, 10)

	users := m.GetUsersInRoom(1)
	if len(users) != 1 {
		t.Errorf("expected 1 user after close, got %d", len(users))
	}
	if users[0] != 20 {
		t.Errorf("expected bob (20) remaining, got %d", users[0])
	}
}

func TestCloseUserConnsInRoomEmptiesRoom(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectRoom(1, conn, UserInfo{UserID: 10, Username: "alice"})
	m.CloseUserConnsInRoom(1, 10)

	if m.RoomCount() != 0 {
		t.Errorf("expected 0 rooms after closing last user, got %d", m.RoomCount())
	}
}

// ---------- SendToUserInRoom ----------

func TestSendToUserInRoom(t *testing.T) {
	m := newTestManager()

	upgrader := websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }}
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

	m.ConnectRoom(1, serverConn, UserInfo{UserID: 10, Username: "alice"})

	msg := map[string]string{"type": "test", "data": "hello"}
	m.SendToUserInRoom(1, 10, msg)

	var received map[string]string
	if err := client.ReadJSON(&received); err != nil {
		t.Fatalf("read: %v", err)
	}
	if received["data"] != "hello" {
		t.Errorf("expected 'hello', got %q", received["data"])
	}
}

// ---------- GetNextUserInRoom ----------

func TestGetNextUserInRoom(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(1, conn2, UserInfo{UserID: 20, Username: "bob"})

	nextID, nextName, found := m.GetNextUserInRoom(1, 10)
	if !found {
		t.Fatal("expected to find next user")
	}
	if nextID != 20 || nextName != "bob" {
		t.Errorf("expected bob (20), got %s (%d)", nextName, nextID)
	}
}

func TestGetNextUserInRoomNoOther(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectRoom(1, conn, UserInfo{UserID: 10, Username: "alice"})

	_, _, found := m.GetNextUserInRoom(1, 10)
	if found {
		t.Error("expected no next user when only one in room")
	}
}

func TestGetNextUserInRoomEmptyRoom(t *testing.T) {
	m := newTestManager()

	_, _, found := m.GetNextUserInRoom(99, 1)
	if found {
		t.Error("expected no next user in empty room")
	}
}

// ---------- CloseAllInRoom ----------

func TestCloseAllInRoom(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(1, conn2, UserInfo{UserID: 20, Username: "bob"})

	m.CloseAllInRoom(1)

	if m.RoomCount() != 0 {
		t.Errorf("expected 0 rooms after CloseAllInRoom, got %d", m.RoomCount())
	}
	if m.TotalConnections() != 0 {
		t.Errorf("expected 0 connections, got %d", m.TotalConnections())
	}
}

// ---------- CloseAll ----------

func TestCloseAll(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()
	conn3, cleanup3 := newWSConn(t)
	defer cleanup3()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(2, conn2, UserInfo{UserID: 20, Username: "bob"})
	m.ConnectLobby(conn3, UserInfo{UserID: 30, Username: "carol"})

	m.CloseAll()

	if m.RoomCount() != 0 {
		t.Errorf("expected 0 rooms after CloseAll, got %d", m.RoomCount())
	}
	if m.TotalConnections() != 0 {
		t.Errorf("expected 0 connections after CloseAll, got %d", m.TotalConnections())
	}
}

// ---------- GetUsernamesInRoom ----------

func TestGetUsernamesInRoom(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(1, conn2, UserInfo{UserID: 20, Username: "bob"})

	names := m.GetUsernamesInRoom(1)
	if len(names) != 2 {
		t.Errorf("expected 2 usernames, got %d", len(names))
	}
}

func TestGetUsernamesInRoomEmpty(t *testing.T) {
	m := newTestManager()
	names := m.GetUsernamesInRoom(99)
	if len(names) != 0 {
		t.Errorf("expected 0 usernames, got %d", len(names))
	}
}

// ---------- FindUserIDByUsername ----------

func TestFindUserIDByUsername(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectRoom(1, conn, UserInfo{UserID: 10, Username: "alice"})

	id, found := m.FindUserIDByUsername(1, "alice")
	if !found || id != 10 {
		t.Errorf("expected (10, true), got (%d, %v)", id, found)
	}

	_, found = m.FindUserIDByUsername(1, "nobody")
	if found {
		t.Error("expected not found for unknown user")
	}
}

// ---------- IsUserInRoom ----------

func TestIsUserInRoomTrue(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectRoom(1, conn, UserInfo{UserID: 10, Username: "alice"})

	if !m.IsUserInRoom(1, 10) {
		t.Error("expected alice to be in room")
	}
}

func TestIsUserInRoomFalse(t *testing.T) {
	m := newTestManager()

	if m.IsUserInRoom(1, 10) {
		t.Error("expected user not in empty room")
	}
}

// ---------- UserConnectionCount ----------

func TestUserConnectionCount(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()
	conn3, cleanup3 := newWSConn(t)
	defer cleanup3()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectRoom(2, conn2, UserInfo{UserID: 10, Username: "alice"})
	m.ConnectLobby(conn3, UserInfo{UserID: 10, Username: "alice"})

	// userConns tracks all 3 conns: 2 room connections + 1 lobby connection
	if m.UserConnectionCount(10) != 3 {
		t.Errorf("expected 3, got %d", m.UserConnectionCount(10))
	}
	if m.UserConnectionCount(99) != 0 {
		t.Errorf("expected 0 for unknown user, got %d", m.UserConnectionCount(99))
	}
}
