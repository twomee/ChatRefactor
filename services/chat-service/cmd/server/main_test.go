package main

import (
	"context"
	"testing"
	"time"
)

func TestFileEventConsumer_PMFile_SendsPersonal(t *testing.T) {
	isPrivate := true
	recipientID := float64(42)

	var personalSent bool
	var broadcastSent bool

	routeFileEvent(
		context.Background(),
		map[string]interface{}{
			"file_id": float64(1), "filename": "x.png", "size": float64(100),
			"from": "alice", "to": "bob", "sender_id": float64(7), "recipient_id": recipientID,
			"room_id": nil, "is_private": isPrivate, "timestamp": "2026-01-01T00:00:00Z",
		},
		func(userID int, msg map[string]interface{}) { personalSent = true },
		func(roomID int, msg map[string]interface{}) { broadcastSent = true },
		nil, // deliverPM not needed for WS routing test
		nil, // deliverChat not needed for WS routing test
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
		context.Background(),
		map[string]interface{}{
			"file_id": float64(1), "filename": "x.png", "size": float64(100),
			"from": "alice", "room_id": float64(5), "is_private": false,
			"timestamp": "2026-01-01T00:00:00Z",
		},
		func(userID int, msg map[string]interface{}) { personalSent = true },
		func(roomID int, msg map[string]interface{}) { broadcastSent = true },
		nil, // deliverPM not needed for room broadcast test
		nil, // deliverChat not needed for WS routing test
	)

	if personalSent {
		t.Error("expected SendPersonal NOT to be called for room file")
	}
	if !broadcastSent {
		t.Error("expected BroadcastRoom to be called for room file")
	}
}

func TestFileEventConsumer_PMFile_ProducesPersistenceEvent(t *testing.T) {
	called := make(chan struct{}, 1)

	routeFileEvent(
		context.Background(),
		map[string]interface{}{
			"file_id": float64(1), "filename": "x.png", "size": float64(100),
			"from": "alice", "to": "bob", "sender_id": float64(7), "recipient_id": float64(42),
			"room_id": nil, "is_private": true, "timestamp": "2026-01-01T00:00:00Z",
		},
		func(userID int, msg map[string]interface{}) {},
		func(roomID int, msg map[string]interface{}) {},
		func(_ context.Context, _ int, _ []byte) error {
			called <- struct{}{}
			return nil
		},
		nil, // deliverChat not needed for PM test
	)

	select {
	case <-called:
		// deliverPM was called — PM file persistence goroutine ran
	case <-time.After(time.Second):
		t.Error("expected deliverPM to be called for PM file (persistence event)")
	}
}

func TestFileEventConsumer_RoomFile_ProducesPersistenceEvent(t *testing.T) {
	called := make(chan struct{}, 1)

	routeFileEvent(
		context.Background(),
		map[string]interface{}{
			"file_id": float64(1), "filename": "x.png", "size": float64(100),
			"from": "alice", "sender_id": float64(7), "room_id": float64(5),
			"is_private": false, "timestamp": "2026-01-01T00:00:00Z",
		},
		func(userID int, msg map[string]interface{}) {},
		func(roomID int, msg map[string]interface{}) {},
		nil, // deliverPM not needed for room test
		func(_ context.Context, _ int, _ []byte) error {
			called <- struct{}{}
			return nil
		},
	)

	select {
	case <-called:
		// deliverChat was called — room file persistence goroutine ran
	case <-time.After(time.Second):
		t.Error("expected deliverChat to be called for room file (persistence event)")
	}
}
