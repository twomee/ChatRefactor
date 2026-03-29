package handler

import (
	"context"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5"

	"github.com/twomee/chatbox/chat-service/internal/model"
	"github.com/twomee/chatbox/chat-service/internal/store"
	"github.com/twomee/chatbox/chat-service/internal/ws"
)

// mockReadPositionStore is a thread-safe in-memory implementation of
// store.ReadPositionRepository used to verify that handleMarkRead calls
// Upsert with the correct arguments.
type mockReadPositionStore struct {
	mu         sync.Mutex
	upsertArgs []upsertCall
	upsertErr  error
}

type upsertCall struct {
	userID    int
	roomID    int
	messageID string
}

func (m *mockReadPositionStore) Upsert(ctx context.Context, userID, roomID int, messageID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.upsertArgs = append(m.upsertArgs, upsertCall{userID, roomID, messageID})
	return m.upsertErr
}

func (m *mockReadPositionStore) Get(ctx context.Context, userID, roomID int) (*store.ReadPosition, error) {
	// Return ErrNoRows to match the real store's behaviour when no read
	// position exists yet. sendReadPosition treats any error as "first visit"
	// and skips sending a frame — this prevents a nil pointer dereference.
	return nil, pgx.ErrNoRows
}

func (m *mockReadPositionStore) upsertCallCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.upsertArgs)
}

func (m *mockReadPositionStore) lastUpsertCall() (upsertCall, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.upsertArgs) == 0 {
		return upsertCall{}, false
	}
	return m.upsertArgs[len(m.upsertArgs)-1], true
}

// setupWSServerWithReadPositions creates a test WebSocket server that has a
// real mockReadPositionStore wired up, so mark_read tests can assert on Upsert.
func setupWSServerWithReadPositions(t *testing.T) (srvURL string, rpStore *mockReadPositionStore, cleanup func()) {
	t.Helper()
	logger := newLogger()
	manager := ws.NewManager(logger)
	del := &mockDelivery{}
	roomStore := &mockRoomStore{
		room:     &model.Room{ID: 1, Name: "test", IsActive: true},
		adminSet: make(map[string]bool),
		muteSet:  make(map[string]bool),
	}
	rpStore = &mockReadPositionStore{}
	wsH := NewWSHandler(manager, roomStore, rpStore, del, nil, testSecret, "http://localhost:8004", logger)

	r := gin.New()
	r.GET("/ws/:roomId", wsH.HandleRoomWS)
	srv := httptest.NewServer(r)
	return srv.URL, rpStore, srv.Close
}

// TestWSMarkReadEmptyMsgID verifies that sending mark_read with an empty msg_id
// returns an error frame and does NOT call Upsert.
func TestWSMarkReadEmptyMsgID(t *testing.T) {
	srvURL, rpStore, cleanup := setupWSServerWithReadPositions(t)
	defer cleanup()

	c := dialWS(t, srvURL, 1, "alice")
	defer c.Close()
	drainMessages(c, 2) // join + history

	c.WriteJSON(map[string]string{"type": "mark_read", "msg_id": ""})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "msg_id is required for mark_read" {
		t.Errorf("expected 'msg_id is required for mark_read', got %q", detail)
	}

	if rpStore.upsertCallCount() != 0 {
		t.Errorf("expected Upsert not to be called, but was called %d time(s)", rpStore.upsertCallCount())
	}
}

// TestWSMarkReadInvalidMsgID verifies that sending mark_read with a non-UUID
// msg_id returns an error frame and does NOT call Upsert.
func TestWSMarkReadInvalidMsgID(t *testing.T) {
	srvURL, rpStore, cleanup := setupWSServerWithReadPositions(t)
	defer cleanup()

	c := dialWS(t, srvURL, 1, "alice")
	defer c.Close()
	drainMessages(c, 2)

	c.WriteJSON(map[string]string{"type": "mark_read", "msg_id": "not-a-uuid"})

	msg := readMsg(t, c)
	if msg["type"] != "error" {
		t.Errorf("expected error, got %v", msg["type"])
	}
	detail, _ := msg["detail"].(string)
	if detail != "msg_id must be a valid UUID" {
		t.Errorf("expected 'msg_id must be a valid UUID', got %q", detail)
	}

	if rpStore.upsertCallCount() != 0 {
		t.Errorf("expected Upsert not to be called, but was called %d time(s)", rpStore.upsertCallCount())
	}
}

// TestWSMarkReadValidUUID verifies that sending mark_read with a valid UUID
// calls Upsert with the correct user_id, room_id, and msg_id.
func TestWSMarkReadValidUUID(t *testing.T) {
	srvURL, rpStore, cleanup := setupWSServerWithReadPositions(t)
	defer cleanup()

	const validUUID = "550e8400-e29b-41d4-a716-446655440000"

	c := dialWS(t, srvURL, 1, "alice")
	defer c.Close()
	drainMessages(c, 2)

	c.WriteJSON(map[string]string{"type": "mark_read", "msg_id": validUUID})

	// mark_read is silent on success — no response frame is sent to the client.
	// Give the server-side goroutine time to execute Upsert before asserting.
	time.Sleep(100 * time.Millisecond)

	if rpStore.upsertCallCount() != 1 {
		t.Fatalf("expected Upsert to be called once, got %d", rpStore.upsertCallCount())
	}

	call, _ := rpStore.lastUpsertCall()
	if call.userID != 1 {
		t.Errorf("expected userID 1, got %d", call.userID)
	}
	if call.roomID != 1 {
		t.Errorf("expected roomID 1, got %d", call.roomID)
	}
	if call.messageID != validUUID {
		t.Errorf("expected messageID %q, got %q", validUUID, call.messageID)
	}
}
