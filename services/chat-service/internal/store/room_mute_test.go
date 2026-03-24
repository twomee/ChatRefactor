package store

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v4"
)



func TestGetMutedUsersSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	now := time.Now()
	rows := pgxmock.NewRows([]string{"id", "user_id", "room_id", "muted_at"}).
		AddRow(1, 10, 1, now)

	mock.ExpectQuery("SELECT id, user_id, room_id, muted_at FROM muted_users WHERE room_id =").
		WithArgs(1).
		WillReturnRows(rows)

	muted, err := s.GetMutedUsers(context.Background(), 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(muted) != 1 {
		t.Errorf("expected 1 muted user, got %d", len(muted))
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestGetMutedUsersError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectQuery("SELECT id, user_id, room_id, muted_at FROM muted_users WHERE room_id =").
		WithArgs(1).
		WillReturnError(pgx.ErrNoRows)

	_, err := s.GetMutedUsers(context.Background(), 1)
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestMuteUserSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	now := time.Now()
	rows := pgxmock.NewRows([]string{"id", "user_id", "room_id", "muted_at"}).
		AddRow(1, 10, 1, now)

	mock.ExpectQuery("INSERT INTO muted_users").
		WithArgs(10, 1).
		WillReturnRows(rows)

	muted, err := s.MuteUser(context.Background(), 1, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if muted.UserID != 10 {
		t.Errorf("expected user_id 10, got %d", muted.UserID)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestMuteUserError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectQuery("INSERT INTO muted_users").
		WithArgs(10, 1).
		WillReturnError(pgx.ErrNoRows)

	_, err := s.MuteUser(context.Background(), 1, 10)
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestUnmuteUserSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("DELETE FROM muted_users WHERE room_id").
		WithArgs(1, 10).
		WillReturnResult(pgxmock.NewResult("DELETE", 1))

	err := s.UnmuteUser(context.Background(), 1, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestUnmuteUserNotFound(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("DELETE FROM muted_users WHERE room_id").
		WithArgs(1, 999).
		WillReturnResult(pgxmock.NewResult("DELETE", 0))

	err := s.UnmuteUser(context.Background(), 1, 999)
	if err == nil {
		t.Error("expected error for not found")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestUnmuteUserDBError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("DELETE FROM muted_users WHERE room_id").
		WithArgs(1, 10).
		WillReturnError(pgx.ErrNoRows)

	err := s.UnmuteUser(context.Background(), 1, 10)
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestIsMutedTrue(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	rows := pgxmock.NewRows([]string{"exists"}).AddRow(true)
	mock.ExpectQuery("SELECT EXISTS").
		WithArgs(1, 10).
		WillReturnRows(rows)

	isMuted, err := s.IsMuted(context.Background(), 1, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !isMuted {
		t.Error("expected isMuted to be true")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestIsMutedFalse(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	rows := pgxmock.NewRows([]string{"exists"}).AddRow(false)
	mock.ExpectQuery("SELECT EXISTS").
		WithArgs(1, 99).
		WillReturnRows(rows)

	isMuted, err := s.IsMuted(context.Background(), 1, 99)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if isMuted {
		t.Error("expected isMuted to be false")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

