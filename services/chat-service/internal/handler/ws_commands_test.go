package handler

import (
	"context"
	"fmt"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"

	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// ---- WebSocket admin command integration tests ----
// These use a real WebSocket connection via httptest, following the same
// pattern as TestWSHandlerRoomWSUpgradeAndMessage.

func setupWSServer(t *testing.T) (srvURL string, cleanup func()) {
	t.Helper()
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(manager, store, nil, del, nil, testSecret, "http://localhost:8004", logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	return srv.URL, srv.Close
}

func dialWS(t *testing.T, srvURL string, userID int, username string) *websocket.Conn {
	t.Helper()
	token := makeToken(userID, username)
	wsURL := "ws" + strings.TrimPrefix(srvURL, "http") + "/ws/1?token=" + token
	c, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		status := 0
		if resp != nil {
			status = resp.StatusCode
		}
		t.Fatalf("dial error for %s (HTTP %d): %v", username, status, err)
	}
	return c
}

func drainMessages(c *websocket.Conn, n int) {
	c.SetReadDeadline(time.Now().Add(2 * time.Second))
	for i := 0; i < n; i++ {
		var m map[string]interface{}
		if err := c.ReadJSON(&m); err != nil {
			break
		}
	}
}

func readMsg(t *testing.T, c *websocket.Conn) map[string]interface{} {
	t.Helper()
	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	var msg map[string]interface{}
	if err := c.ReadJSON(&msg); err != nil {
		t.Fatalf("readMsg: %v", err)
	}
	return msg
}

func TestWSMuteCommand(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2) // join + history

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2) // join + history
	drainMessages(c1, 1) // alice gets bob's join

	// Alice (auto-admin) mutes Bob.
	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})

	msg := readMsg(t, c2)
	if msg["type"] != "muted" {
		t.Errorf("expected muted, got %v", msg["type"])
	}

	// Bob tries to send — should get error.
	drainMessages(c1, 1) // drain admin's mute broadcast
	c2.WriteJSON(map[string]string{"type": "message", "text": "blocked"})
	msg = readMsg(t, c2)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSUnmuteCommand(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)
	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Mute then unmute.
	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})
	drainMessages(c2, 1) // muted
	drainMessages(c1, 1) // admin's broadcast

	c1.WriteJSON(map[string]string{"type": "unmute", "target": "bob"})
	msg := readMsg(t, c2)
	if msg["type"] != "unmuted" {
		t.Errorf("expected unmuted, got %v", msg["type"])
	}
}

func TestWSPromoteCommand(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)
	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	c1.WriteJSON(map[string]string{"type": "promote", "target": "bob"})
	msg := readMsg(t, c2)
	if msg["type"] != "new_admin" {
		t.Errorf("expected new_admin, got %v", msg["type"])
	}
}

func TestWSKickCommand(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)
	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	c1.WriteJSON(map[string]string{"type": "kick", "target": "bob"})
	msg := readMsg(t, c2)
	if msg["type"] != "kicked" {
		t.Errorf("expected kicked, got %v", msg["type"])
	}
}

func TestWSKickSelfRejected(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "kick", "target": "alice"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSMuteSelfRejected(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "mute", "target": "alice"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

func TestWSPrivateMessage(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)
	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	c1.WriteJSON(map[string]string{"type": "private_message", "to": "bob", "text": "hello pm"})

	msg := readMsg(t, c2)
	if msg["type"] != "private_message" {
		t.Errorf("expected private_message, got %v", msg["type"])
	}
	if msg["text"] != "hello pm" {
		t.Errorf("expected 'hello pm', got %v", msg["text"])
	}

	// Alice gets echo with self=true.
	msg = readMsg(t, c1)
	if msg["self"] != true {
		t.Errorf("expected self=true, got %v", msg["self"])
	}
}

func TestWSPrivateMessageSelfRejected(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "private_message", "to": "alice", "text": "self pm"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
}

// ---- handleUnmute edge case tests ----

func TestWSUnmuteEmptyTarget(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	// Send unmute with empty target.
	c1.WriteJSON(map[string]string{"type": "unmute", "target": ""})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "Target username required" {
		t.Errorf("expected 'Target username required', got %v", msg["detail"])
	}
}

func TestWSUnmuteNonAdmin(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Bob (non-admin) tries to unmute — should fail.
	c2.WriteJSON(map[string]string{"type": "unmute", "target": "alice"})
	msg := readMsg(t, c2)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "Admin access required" {
		t.Errorf("expected 'Admin access required', got %v", msg["detail"])
	}
}

func TestWSUnmuteUserNotInRoom(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	// Alice (admin) tries to unmute someone not in the room.
	c1.WriteJSON(map[string]string{"type": "unmute", "target": "ghost"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "User not in room" {
		t.Errorf("expected 'User not in room', got %v", msg["detail"])
	}
}

func TestWSUnmuteUserNotMuted(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Alice (admin) tries to unmute bob who is not muted.
	c1.WriteJSON(map[string]string{"type": "unmute", "target": "bob"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "User is not muted" {
		t.Errorf("expected 'User is not muted', got %v", msg["detail"])
	}
}

// ---- handlePromote edge case tests ----

func TestWSPromoteEmptyTarget(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "promote", "target": ""})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "Target username required" {
		t.Errorf("expected 'Target username required', got %v", msg["detail"])
	}
}

func TestWSPromoteNonAdmin(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Bob (non-admin) tries to promote — should fail.
	c2.WriteJSON(map[string]string{"type": "promote", "target": "alice"})
	msg := readMsg(t, c2)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "Admin access required" {
		t.Errorf("expected 'Admin access required', got %v", msg["detail"])
	}
}

func TestWSPromoteSelfRejected(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "promote", "target": "alice"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "Cannot promote yourself" {
		t.Errorf("expected 'Cannot promote yourself', got %v", msg["detail"])
	}
}

func TestWSPromoteUserNotInRoom(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c1.WriteJSON(map[string]string{"type": "promote", "target": "ghost"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "User not in room" {
		t.Errorf("expected 'User not in room', got %v", msg["detail"])
	}
}

func TestWSPromoteAlreadyAdmin(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// First promote succeeds.
	c1.WriteJSON(map[string]string{"type": "promote", "target": "bob"})
	drainMessages(c1, 1) // new_admin broadcast
	drainMessages(c2, 1) // new_admin broadcast

	// Second promote should fail — bob already admin.
	c1.WriteJSON(map[string]string{"type": "promote", "target": "bob"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "User is already an admin" {
		t.Errorf("expected 'User is already an admin', got %v", msg["detail"])
	}
}

func TestWSPromoteMutedUser(t *testing.T) {
	srvURL, cleanup := setupWSServer(t)
	defer cleanup()

	c1 := dialWS(t, srvURL, 1, "alice")
	defer c1.Close()
	drainMessages(c1, 2)

	c2 := dialWS(t, srvURL, 2, "bob")
	defer c2.Close()
	drainMessages(c2, 2)
	drainMessages(c1, 1)

	// Mute bob first.
	c1.WriteJSON(map[string]string{"type": "mute", "target": "bob"})
	drainMessages(c1, 1)
	drainMessages(c2, 1)

	// Try to promote muted bob — should fail.
	c1.WriteJSON(map[string]string{"type": "promote", "target": "bob"})
	msg := readMsg(t, c1)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	if msg["detail"] != "Cannot promote a muted user" {
		t.Errorf("expected 'Cannot promote a muted user', got %v", msg["detail"])
	}
}

// ---- handleAdminSuccession unit tests ----
// handleAdminSuccession is called when an admin disconnects. We test it by
// calling the method directly with a pre-configured WSHandler and ws.Manager.

func TestAdminSuccessionNonAdminLeaves(t *testing.T) {
	logger := newLogger()
	mgr := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(mgr, store, nil, del, nil, testSecret, "http://localhost:8004", logger)

	ctx := context.Background()

	// Non-admin leaves — should be a no-op (no errors, no promotion).
	wsH.handleAdminSuccession(ctx, 1, 99, "nonexistent")

	// Verify no admins were added.
	admins, _ := store.GetAdmins(ctx, 1)
	if len(admins) != 0 {
		t.Errorf("expected 0 admins after non-admin leaves, got %d", len(admins))
	}
}

func TestAdminSuccessionAdminLeavesEmptyRoom(t *testing.T) {
	logger := newLogger()
	mgr := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(mgr, store, nil, del, nil, testSecret, "http://localhost:8004", logger)

	ctx := context.Background()

	// Make user 1 an admin.
	store.adminSet[adminKey(1, 1)] = true

	// Admin leaves empty room — no one to promote.
	wsH.handleAdminSuccession(ctx, 1, 1, "alice")

	// Admin should be removed.
	isAdmin, _ := store.IsAdmin(ctx, 1, 1)
	if isAdmin {
		t.Error("expected departing admin to be removed")
	}
}

func TestAdminSuccessionPromotesNextUser(t *testing.T) {
	logger := newLogger()
	mgr := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(mgr, store, nil, del, nil, testSecret, "http://localhost:8004", logger)

	ctx := context.Background()

	// Simulate two users connected: alice (user 1) is admin, bob (user 2) is next in line.
	// We need to register bob as connected in the manager so GetNextUserInRoom finds him.
	// Use a mock websocket.Conn — since we only need mgr to track it, not send messages.
	srv := httptest.NewServer(gin.New())
	defer srv.Close()
	// Create a pipe-based websocket conn pair for bob.
	bobServer, bobClient := createWSPair(t)
	defer bobServer.Close()
	defer bobClient.Close()

	mgr.ConnectRoom(1, bobServer, ws.UserInfo{UserID: 2, Username: "bob"})

	// Make alice (user 1) admin.
	store.adminSet[adminKey(1, 1)] = true

	// Alice leaves — bob should be promoted.
	wsH.handleAdminSuccession(ctx, 1, 1, "alice")

	// Alice should no longer be admin.
	isAliceAdmin, _ := store.IsAdmin(ctx, 1, 1)
	if isAliceAdmin {
		t.Error("expected alice to be removed as admin")
	}

	// Bob should now be admin.
	isBobAdmin, _ := store.IsAdmin(ctx, 1, 2)
	if !isBobAdmin {
		t.Error("expected bob to be promoted to admin")
	}
}

func TestAdminSuccessionClearsMutes(t *testing.T) {
	logger := newLogger()
	mgr := ws.NewManager(logger)
	del := &mockDelivery{}
	store := &mockRoomStore{
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(mgr, store, nil, del, nil, testSecret, "http://localhost:8004", logger)

	ctx := context.Background()

	// Setup: alice is admin, charlie is muted.
	store.adminSet[adminKey(1, 1)] = true
	store.muteSet[adminKey(1, 3)] = true

	// Connect bob so succession has someone to promote.
	bobServer, bobClient := createWSPair(t)
	defer bobServer.Close()
	defer bobClient.Close()
	mgr.ConnectRoom(1, bobServer, ws.UserInfo{UserID: 2, Username: "bob"})

	// Alice leaves — mutes should be cleared (amnesty).
	wsH.handleAdminSuccession(ctx, 1, 1, "alice")

	isCharlieMuted, _ := store.IsMuted(ctx, 1, 3)
	if isCharlieMuted {
		t.Error("expected mutes to be cleared on admin succession")
	}
}

func TestAdminSuccessionAddAdminError(t *testing.T) {
	logger := newLogger()
	mgr := ws.NewManager(logger)
	del := &mockDelivery{}

	// Use a store that will fail on AddAdmin but succeed on other ops.
	store := &mockRoomStore{
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	wsH := NewWSHandler(mgr, store, nil, del, nil, testSecret, "http://localhost:8004", logger)

	ctx := context.Background()

	// Connect bob.
	bobServer, bobClient := createWSPair(t)
	defer bobServer.Close()
	defer bobClient.Close()
	mgr.ConnectRoom(1, bobServer, ws.UserInfo{UserID: 2, Username: "bob"})

	// Make alice admin.
	store.adminSet[adminKey(1, 1)] = true

	// Now set the store to return error on AddAdmin. We need to remove the adminSet
	// and set err so AddAdmin fails.
	store.err = fmt.Errorf("db write error")
	// Need to reset adminSet to nil so IsAdmin and RemoveAdmin use the err field,
	// but that would break IsAdmin. Instead, let's manually delete alice from adminSet
	// then set err after RemoveAdmin would have succeeded.
	// The simplest approach: set err on the store after IsAdmin + RemoveAdmin succeed.
	// Since we can't intercept mid-call, let's just verify the function doesn't panic.
	// Reset to use a fresh approach: adminSet for read ops, err for AddAdmin.

	// Actually, the mockRoomStore.AddAdmin checks m.err first. So setting m.err will
	// make AddAdmin return an error, but it will also affect IsAdmin (via fallback),
	// GetMutedUsers, and UnmuteUser when adminSet/muteSet are nil.
	// Since we have adminSet and muteSet set, those ops use the map path and ignore m.err.
	// Only AddAdmin checks m.err first before using adminSet. Let's verify.

	// mockRoomStore.AddAdmin: if m.err != nil { return nil, m.err }
	// mockRoomStore.IsAdmin: if m.adminSet != nil { return m.adminSet[key], nil }
	// So setting m.err + having adminSet set means: IsAdmin uses map (works),
	// AddAdmin returns error. That's what we want.

	wsH.handleAdminSuccession(ctx, 1, 1, "alice")

	// Bob should NOT be admin since AddAdmin failed.
	isBobAdmin, _ := store.IsAdmin(ctx, 1, 2)
	if isBobAdmin {
		t.Error("expected bob not to be admin when AddAdmin fails")
	}
}

// createWSPair creates a connected pair of WebSocket connections using an
// in-memory HTTP test server. Returns the server-side and client-side
// connections. Both must be closed by the caller.
func createWSPair(t *testing.T) (server *websocket.Conn, client *websocket.Conn) {
	t.Helper()
	var serverConn *websocket.Conn
	upgrader := websocket.Upgrader{}

	handler := gin.New()
	handler.GET("/ws", func(c *gin.Context) {
		conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
		if err != nil {
			t.Fatalf("upgrade: %v", err)
		}
		serverConn = conn
	})

	srv := httptest.NewServer(handler)
	defer srv.Close()

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http") + "/ws"
	clientConn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}

	// Wait briefly for the upgrade to complete on the server side.
	time.Sleep(50 * time.Millisecond)

	if serverConn == nil {
		t.Fatal("server-side WebSocket connection was not established")
	}

	return serverConn, clientConn
}
