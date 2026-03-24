package store

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v4"
)



// ---------- GetAllIncludingInactive ----------

func TestGetAllIncludingInactiveSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	rows := pgxmock.NewRows([]string{"id", "name", "is_active", "created_at"}).
		AddRow(1, "general", true, time.Now()).
		AddRow(2, "closed", false, time.Now())
	mock.ExpectQuery("SELECT id, name, is_active, created_at FROM rooms ORDER BY created_at").
		WillReturnRows(rows)

	rooms, err := s.GetAllIncludingInactive(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(rooms) != 2 {
		t.Errorf("expected 2 rooms, got %d", len(rooms))
	}
}

func TestGetAllIncludingInactiveError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectQuery("SELECT id, name, is_active, created_at FROM rooms ORDER BY created_at").
		WillReturnError(pgx.ErrNoRows)

	_, err := s.GetAllIncludingInactive(context.Background())
	if err == nil {
		t.Error("expected error")
	}
}

// ---------- SetAllActive ----------

func TestSetAllActiveSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("UPDATE rooms SET is_active").
		WithArgs(false).
		WillReturnResult(pgxmock.NewResult("UPDATE", 3))

	n, err := s.SetAllActive(context.Background(), false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if n != 3 {
		t.Errorf("expected 3 affected, got %d", n)
	}
}

func TestSetAllActiveError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("UPDATE rooms SET is_active").
		WithArgs(true).
		WillReturnError(pgx.ErrNoRows)

	_, err := s.SetAllActive(context.Background(), true)
	if err == nil {
		t.Error("expected error")
	}
}

// ---------- DeleteAllData ----------

func TestDeleteAllDataSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("TRUNCATE muted_users, room_admins, rooms RESTART IDENTITY CASCADE").
		WillReturnResult(pgxmock.NewResult("TRUNCATE", 0))

	err := s.DeleteAllData(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestDeleteAllDataError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("TRUNCATE muted_users, room_admins, rooms RESTART IDENTITY CASCADE").
		WillReturnError(pgx.ErrNoRows)

	err := s.DeleteAllData(context.Background())
	if err == nil {
		t.Error("expected error")
	}
}
