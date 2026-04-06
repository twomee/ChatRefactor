package handler

import (
	"context"
	"sort"
	"sync/atomic"
	"testing"
)

func TestMarkKicked_WasKicked(t *testing.T) {
	s := newLifecycleState()
	s.markKicked(1, 42)

	if !s.wasKicked(1, 42) {
		t.Fatal("expected wasKicked to return true after markKicked")
	}

	// Second call should return false — the flag is consumed.
	if s.wasKicked(1, 42) {
		t.Fatal("expected wasKicked to return false on second call (consumed)")
	}
}

func TestWasKicked_NotKicked(t *testing.T) {
	s := newLifecycleState()

	if s.wasKicked(1, 42) {
		t.Fatal("expected wasKicked to return false when not marked")
	}
}

func TestMarkLeft_WasLeft(t *testing.T) {
	s := newLifecycleState()
	s.markLeft(1, 42)

	if !s.wasLeft(1, 42) {
		t.Fatal("expected wasLeft to return true after markLeft")
	}

	// Second call should return false — the flag is consumed.
	if s.wasLeft(1, 42) {
		t.Fatal("expected wasLeft to return false on second call (consumed)")
	}
}

func TestWasLeft_NotLeft(t *testing.T) {
	s := newLifecycleState()

	if s.wasLeft(1, 42) {
		t.Fatal("expected wasLeft to return false when not marked")
	}
}

func TestStorePendingLeave_CancelPendingLeave(t *testing.T) {
	s := newLifecycleState()

	var cancelled atomic.Int32
	_, cancel := context.WithCancel(context.Background())
	wrappedCancel := func() {
		cancelled.Add(1)
		cancel()
	}

	s.storePendingLeave(1, 42, wrappedCancel)

	found := s.cancelPendingLeave(1, 42)
	if !found {
		t.Fatal("expected cancelPendingLeave to return true")
	}
	if cancelled.Load() != 1 {
		t.Fatal("expected cancel function to have been called")
	}

	// Calling again should return false — already cancelled and removed.
	if s.cancelPendingLeave(1, 42) {
		t.Fatal("expected cancelPendingLeave to return false on second call")
	}
}

func TestCancelPendingLeave_NotFound(t *testing.T) {
	s := newLifecycleState()

	if s.cancelPendingLeave(1, 42) {
		t.Fatal("expected cancelPendingLeave to return false when no pending leave")
	}
}

func TestClearPendingLeave(t *testing.T) {
	s := newLifecycleState()

	_, cancel := context.WithCancel(context.Background())
	s.storePendingLeave(1, 42, cancel)

	s.clearPendingLeave(1, 42)

	// After clearing, cancelPendingLeave should return false.
	if s.cancelPendingLeave(1, 42) {
		t.Fatal("expected cancelPendingLeave to return false after clearPendingLeave")
	}
}

func TestDrainPendingLeaves(t *testing.T) {
	s := newLifecycleState()

	var cancelled atomic.Int32
	for _, roomID := range []int{1, 2, 3} {
		_, cancel := context.WithCancel(context.Background())
		rid := roomID
		wrappedCancel := func() {
			_ = rid
			cancelled.Add(1)
			cancel()
		}
		s.storePendingLeave(rid, 42, wrappedCancel)
	}

	roomIDs := s.drainPendingLeaves(42)

	if cancelled.Load() != 3 {
		t.Fatalf("expected 3 cancels, got %d", cancelled.Load())
	}

	sort.Ints(roomIDs)
	if len(roomIDs) != 3 || roomIDs[0] != 1 || roomIDs[1] != 2 || roomIDs[2] != 3 {
		t.Fatalf("expected room IDs [1 2 3], got %v", roomIDs)
	}

	// All drained — should be empty now.
	if s.cancelPendingLeave(1, 42) {
		t.Fatal("expected no pending leaves after drain")
	}
}

func TestDrainPendingLeaves_OnlyTargetUser(t *testing.T) {
	s := newLifecycleState()

	var cancelledAlice atomic.Int32
	var cancelledBob atomic.Int32

	// Alice (userID=42) has leaves in rooms 1 and 2.
	for _, roomID := range []int{1, 2} {
		_, cancel := context.WithCancel(context.Background())
		wrappedCancel := func() {
			cancelledAlice.Add(1)
			cancel()
		}
		s.storePendingLeave(roomID, 42, wrappedCancel)
	}

	// Bob (userID=99) has a leave in room 1.
	_, cancelBob := context.WithCancel(context.Background())
	s.storePendingLeave(1, 99, func() {
		cancelledBob.Add(1)
		cancelBob()
	})

	// Drain only Alice's leaves.
	roomIDs := s.drainPendingLeaves(42)

	if cancelledAlice.Load() != 2 {
		t.Fatalf("expected 2 Alice cancels, got %d", cancelledAlice.Load())
	}
	if cancelledBob.Load() != 0 {
		t.Fatalf("expected 0 Bob cancels, got %d", cancelledBob.Load())
	}

	sort.Ints(roomIDs)
	if len(roomIDs) != 2 || roomIDs[0] != 1 || roomIDs[1] != 2 {
		t.Fatalf("expected room IDs [1 2], got %v", roomIDs)
	}

	// Bob's leave should still be there.
	if !s.cancelPendingLeave(1, 99) {
		t.Fatal("expected Bob's pending leave to still exist")
	}
}
