package ws

import (
	"testing"
	"time"
)

func TestForceDisconnectUserNoOp(t *testing.T) {
	m := newTestManager()
	// Disconnecting a user with no connections must not panic and must be a no-op.
	m.ForceDisconnectUser(999)
	if m.TotalConnections() != 0 {
		t.Errorf("expected 0 connections, got %d", m.TotalConnections())
	}
}

func TestForceDisconnectUserClosesRoomConn(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectRoom(1, conn, UserInfo{UserID: 42, Username: "alice"})
	if m.UserConnectionCount(42) != 1 {
		t.Fatalf("expected 1 connection before force-disconnect")
	}

	m.ForceDisconnectUser(42)

	// The connection is closed; the goroutine-driven cleanup has not run yet
	// (ForceDisconnectUser intentionally leaves map cleanup to the handler goroutine).
	// What we can assert is that the connection is no longer usable.
	conn.SetWriteDeadline(time.Now().Add(100 * time.Millisecond))
	err := conn.WriteMessage(1, []byte("ping"))
	if err == nil {
		t.Error("expected write to closed connection to fail")
	}
}

func TestForceDisconnectUserClosesLobbyConn(t *testing.T) {
	m := newTestManager()
	conn, cleanup := newWSConn(t)
	defer cleanup()

	m.ConnectLobby(conn, UserInfo{UserID: 7, Username: "bob"})
	if m.UserConnectionCount(7) != 1 {
		t.Fatalf("expected 1 connection before force-disconnect")
	}

	m.ForceDisconnectUser(7)

	conn.SetWriteDeadline(time.Now().Add(100 * time.Millisecond))
	err := conn.WriteMessage(1, []byte("ping"))
	if err == nil {
		t.Error("expected write to closed lobby connection to fail")
	}
}

func TestForceDisconnectUserMultipleConns(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	// Same user connected in two rooms (simulates two browser tabs).
	m.ConnectRoom(1, conn1, UserInfo{UserID: 5, Username: "carol"})
	m.ConnectRoom(2, conn2, UserInfo{UserID: 5, Username: "carol"})

	if m.UserConnectionCount(5) != 2 {
		t.Fatalf("expected 2 connections before force-disconnect")
	}

	m.ForceDisconnectUser(5)

	deadline := time.Now().Add(100 * time.Millisecond)
	conn1.SetWriteDeadline(deadline)
	conn2.SetWriteDeadline(deadline)

	if conn1.WriteMessage(1, []byte("ping")) == nil {
		t.Error("expected conn1 write to fail after force-disconnect")
	}
	if conn2.WriteMessage(1, []byte("ping")) == nil {
		t.Error("expected conn2 write to fail after force-disconnect")
	}
}

func TestForceDisconnectOnlyTargetUser(t *testing.T) {
	m := newTestManager()
	conn1, cleanup1 := newWSConn(t)
	defer cleanup1()
	conn2, cleanup2 := newWSConn(t)
	defer cleanup2()

	m.ConnectRoom(1, conn1, UserInfo{UserID: 1, Username: "alice"})
	m.ConnectRoom(1, conn2, UserInfo{UserID: 2, Username: "bob"})

	// Force-disconnect only alice.
	m.ForceDisconnectUser(1)

	// Bob's connection must still be tracked.
	if m.UserConnectionCount(2) != 1 {
		t.Errorf("expected bob to still have 1 connection, got %d", m.UserConnectionCount(2))
	}
}
