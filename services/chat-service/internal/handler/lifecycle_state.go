package handler

import (
	"context"
	"fmt"
	"sync"
)

// lifecycleState manages the mutable state for connection lifecycle tracking.
// Extracted from WSHandler to isolate mutex-guarded maps that only lifecycle
// handlers need.
type lifecycleState struct {
	kickedMu    sync.Mutex
	kickedUsers map[string]bool
	leftMu      sync.Mutex
	leftUsers   map[string]bool
	pendingLeaveMu sync.Mutex
	pendingLeaves  map[string]context.CancelFunc
}

func newLifecycleState() lifecycleState {
	return lifecycleState{
		kickedUsers:   make(map[string]bool),
		leftUsers:     make(map[string]bool),
		pendingLeaves: make(map[string]context.CancelFunc),
	}
}

// markKicked records that a user was kicked from a room.
func (s *lifecycleState) markKicked(roomID, userID int) {
	s.kickedMu.Lock()
	s.kickedUsers[fmt.Sprintf("%d:%d", roomID, userID)] = true
	s.kickedMu.Unlock()
}

// wasKicked checks and clears the kicked flag for a user.
func (s *lifecycleState) wasKicked(roomID, userID int) bool {
	key := fmt.Sprintf("%d:%d", roomID, userID)
	s.kickedMu.Lock()
	defer s.kickedMu.Unlock()
	if s.kickedUsers[key] {
		delete(s.kickedUsers, key)
		return true
	}
	return false
}

// wasLeft checks and clears the intentional-leave flag for a room/user pair.
func (s *lifecycleState) wasLeft(roomID, userID int) bool {
	key := fmt.Sprintf("%d:%d", roomID, userID)
	s.leftMu.Lock()
	defer s.leftMu.Unlock()
	if s.leftUsers[key] {
		delete(s.leftUsers, key)
		return true
	}
	return false
}

// markLeft records that a user intentionally left a room.
func (s *lifecycleState) markLeft(roomID, userID int) {
	key := fmt.Sprintf("%d:%d", roomID, userID)
	s.leftMu.Lock()
	s.leftUsers[key] = true
	s.leftMu.Unlock()
}

// storePendingLeave registers a pending leave cancel function for a room/user pair.
func (s *lifecycleState) storePendingLeave(roomID, userID int, cancel context.CancelFunc) {
	leaveKey := fmt.Sprintf("%d:%d", roomID, userID)
	s.pendingLeaveMu.Lock()
	s.pendingLeaves[leaveKey] = cancel
	s.pendingLeaveMu.Unlock()
}

// cancelPendingLeave cancels a pending leave for a room/user pair if one exists.
// Returns true if a pending leave was found and cancelled.
func (s *lifecycleState) cancelPendingLeave(roomID, userID int) bool {
	leaveKey := fmt.Sprintf("%d:%d", roomID, userID)
	s.pendingLeaveMu.Lock()
	cancel, found := s.pendingLeaves[leaveKey]
	if found {
		cancel()
		delete(s.pendingLeaves, leaveKey)
	}
	s.pendingLeaveMu.Unlock()
	return found
}

// clearPendingLeave removes a pending leave entry without cancelling it.
// Used when the grace period timer fires naturally.
func (s *lifecycleState) clearPendingLeave(roomID, userID int) {
	leaveKey := fmt.Sprintf("%d:%d", roomID, userID)
	s.pendingLeaveMu.Lock()
	delete(s.pendingLeaves, leaveKey)
	s.pendingLeaveMu.Unlock()
}

// drainPendingLeaves cancels all pending leave timers for a given user and
// returns the room IDs that had pending leaves. Used when a user fully logs
// out (last lobby closes).
func (s *lifecycleState) drainPendingLeaves(userID int) []int {
	s.pendingLeaveMu.Lock()
	var roomIDs []int
	for key, cancel := range s.pendingLeaves {
		var rid, uid int
		fmt.Sscanf(key, "%d:%d", &rid, &uid)
		if uid == userID {
			cancel()
			delete(s.pendingLeaves, key)
			roomIDs = append(roomIDs, rid)
		}
	}
	s.pendingLeaveMu.Unlock()
	return roomIDs
}
