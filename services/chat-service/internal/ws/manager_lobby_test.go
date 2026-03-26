package ws

import (
	"testing"
)

// ---- Lobby connect/disconnect and query tests ----

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
