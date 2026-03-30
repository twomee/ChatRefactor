package main

import "testing"

func TestFileEventConsumer_PMFile_SendsPersonal(t *testing.T) {
	isPrivate := true
	recipientID := float64(42)

	var personalSent bool
	var broadcastSent bool

	routeFileEvent(
		map[string]interface{}{
			"file_id": float64(1), "filename": "x.png", "size": float64(100),
			"from": "alice", "to": "bob", "recipient_id": recipientID,
			"room_id": nil, "is_private": isPrivate, "timestamp": "2026-01-01T00:00:00Z",
		},
		func(userID int, msg map[string]interface{}) { personalSent = true },
		func(roomID int, msg map[string]interface{}) { broadcastSent = true },
	)

	if !personalSent {
		t.Error("expected SendPersonal to be called for PM file")
	}
	if broadcastSent {
		t.Error("expected BroadcastRoom NOT to be called for PM file")
	}
}

func TestFileEventConsumer_RoomFile_Broadcasts(t *testing.T) {
	var personalSent bool
	var broadcastSent bool

	routeFileEvent(
		map[string]interface{}{
			"file_id": float64(1), "filename": "x.png", "size": float64(100),
			"from": "alice", "room_id": float64(5), "is_private": false,
			"timestamp": "2026-01-01T00:00:00Z",
		},
		func(userID int, msg map[string]interface{}) { personalSent = true },
		func(roomID int, msg map[string]interface{}) { broadcastSent = true },
	)

	if personalSent {
		t.Error("expected SendPersonal NOT to be called for room file")
	}
	if !broadcastSent {
		t.Error("expected BroadcastRoom to be called for room file")
	}
}
