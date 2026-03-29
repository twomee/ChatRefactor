package store

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v4"
)

func TestNewReadPositionStore(t *testing.T) {
	s := NewReadPositionStore(nil)
	if s == nil {
		t.Fatal("expected non-nil ReadPositionStore")
	}
}

func TestUpsertReadPositionSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewReadPositionStoreWithPool(mock)

	mock.ExpectExec("INSERT INTO read_positions").
		WithArgs(1, 2, "msg-abc-123").
		WillReturnResult(pgxmock.NewResult("INSERT", 1))

	err := s.Upsert(context.Background(), 1, 2, "msg-abc-123")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestUpsertReadPositionError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewReadPositionStoreWithPool(mock)

	mock.ExpectExec("INSERT INTO read_positions").
		WithArgs(1, 2, "msg-abc-123").
		WillReturnError(pgx.ErrNoRows)

	err := s.Upsert(context.Background(), 1, 2, "msg-abc-123")
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestGetReadPositionSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewReadPositionStoreWithPool(mock)

	now := time.Now()
	rows := pgxmock.NewRows([]string{"user_id", "room_id", "last_read_message_id", "last_read_at"}).
		AddRow(1, 2, "msg-abc-123", now)

	mock.ExpectQuery("SELECT user_id, room_id, last_read_message_id, last_read_at").
		WithArgs(1, 2).
		WillReturnRows(rows)

	rp, err := s.Get(context.Background(), 1, 2)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if rp.UserID != 1 {
		t.Errorf("expected UserID 1, got %d", rp.UserID)
	}
	if rp.RoomID != 2 {
		t.Errorf("expected RoomID 2, got %d", rp.RoomID)
	}
	if rp.LastReadMessageID != "msg-abc-123" {
		t.Errorf("expected LastReadMessageID 'msg-abc-123', got %q", rp.LastReadMessageID)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestGetReadPositionNotFound(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewReadPositionStoreWithPool(mock)

	mock.ExpectQuery("SELECT user_id, room_id, last_read_message_id, last_read_at").
		WithArgs(1, 999).
		WillReturnError(pgx.ErrNoRows)

	rp, err := s.Get(context.Background(), 1, 999)
	if err == nil {
		t.Error("expected error for not found")
	}
	if rp != nil {
		t.Error("expected nil result for not found")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestGetReadPositionDBError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewReadPositionStoreWithPool(mock)

	mock.ExpectQuery("SELECT user_id, room_id, last_read_message_id, last_read_at").
		WithArgs(1, 2).
		WillReturnError(pgx.ErrTxClosed)

	rp, err := s.Get(context.Background(), 1, 2)
	if err == nil {
		t.Error("expected error")
	}
	if rp != nil {
		t.Error("expected nil result for error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}
