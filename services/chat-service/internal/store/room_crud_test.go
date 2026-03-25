package store

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v4"
)



func TestNewRoomStore(t *testing.T) {
	s := NewRoomStore(nil)
	if s == nil {
		t.Fatal("expected non-nil RoomStore")
	}
}

func TestGetAllSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	rows := pgxmock.NewRows([]string{"id", "name", "is_active", "created_at"}).
		AddRow(1, "general", true, time.Now()).
		AddRow(2, "random", true, time.Now())

	mock.ExpectQuery("SELECT id, name, is_active, created_at FROM rooms WHERE is_active = true ORDER BY created_at").
		WillReturnRows(rows)

	rooms, err := s.GetAll(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(rooms) != 2 {
		t.Errorf("expected 2 rooms, got %d", len(rooms))
	}
	if rooms[0].Name != "general" {
		t.Errorf("expected 'general', got %q", rooms[0].Name)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestGetAllEmpty(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	rows := pgxmock.NewRows([]string{"id", "name", "is_active", "created_at"})
	mock.ExpectQuery("SELECT id, name, is_active, created_at FROM rooms WHERE is_active = true ORDER BY created_at").
		WillReturnRows(rows)

	rooms, err := s.GetAll(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if rooms != nil {
		t.Errorf("expected nil rooms for empty result, got %v", rooms)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestGetAllError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectQuery("SELECT id, name, is_active, created_at FROM rooms WHERE is_active = true ORDER BY created_at").
		WillReturnError(pgx.ErrNoRows)

	_, err := s.GetAll(context.Background())
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestGetByIDSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	now := time.Now()
	rows := pgxmock.NewRows([]string{"id", "name", "is_active", "created_at"}).
		AddRow(1, "general", true, now)

	mock.ExpectQuery("SELECT id, name, is_active, created_at FROM rooms WHERE id =").
		WithArgs(1).
		WillReturnRows(rows)

	room, err := s.GetByID(context.Background(), 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if room.ID != 1 {
		t.Errorf("expected ID 1, got %d", room.ID)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestGetByIDNotFound(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectQuery("SELECT id, name, is_active, created_at FROM rooms WHERE id =").
		WithArgs(999).
		WillReturnError(pgx.ErrNoRows)

	_, err := s.GetByID(context.Background(), 999)
	if err == nil {
		t.Error("expected error for not found")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestCreateSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	now := time.Now()
	rows := pgxmock.NewRows([]string{"id", "name", "is_active", "created_at"}).
		AddRow(1, "new-room", true, now)

	mock.ExpectQuery("INSERT INTO rooms").
		WithArgs("new-room").
		WillReturnRows(rows)

	room, err := s.Create(context.Background(), "new-room")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if room.Name != "new-room" {
		t.Errorf("expected 'new-room', got %q", room.Name)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestCreateError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectQuery("INSERT INTO rooms").
		WithArgs("dup").
		WillReturnError(pgx.ErrNoRows)

	_, err := s.Create(context.Background(), "dup")
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestSetActiveSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("UPDATE rooms SET is_active").
		WithArgs(false, 1).
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))

	err := s.SetActive(context.Background(), 1, false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestSetActiveNotFound(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("UPDATE rooms SET is_active").
		WithArgs(false, 999).
		WillReturnResult(pgxmock.NewResult("UPDATE", 0))

	err := s.SetActive(context.Background(), 999, false)
	if err == nil {
		t.Error("expected error for not found")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestSetActiveDBError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("UPDATE rooms SET is_active").
		WithArgs(false, 1).
		WillReturnError(pgx.ErrNoRows)

	err := s.SetActive(context.Background(), 1, false)
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

