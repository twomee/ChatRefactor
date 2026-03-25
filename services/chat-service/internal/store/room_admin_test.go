package store

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v4"
)



func TestGetAdminsSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	now := time.Now()
	rows := pgxmock.NewRows([]string{"id", "user_id", "room_id", "appointed_at"}).
		AddRow(1, 10, 1, now)

	mock.ExpectQuery("SELECT id, user_id, room_id, appointed_at FROM room_admins WHERE room_id =").
		WithArgs(1).
		WillReturnRows(rows)

	admins, err := s.GetAdmins(context.Background(), 1)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(admins) != 1 {
		t.Errorf("expected 1 admin, got %d", len(admins))
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestGetAdminsError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectQuery("SELECT id, user_id, room_id, appointed_at FROM room_admins WHERE room_id =").
		WithArgs(1).
		WillReturnError(pgx.ErrNoRows)

	_, err := s.GetAdmins(context.Background(), 1)
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestAddAdminSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	now := time.Now()
	rows := pgxmock.NewRows([]string{"id", "user_id", "room_id", "appointed_at"}).
		AddRow(1, 10, 1, now)

	mock.ExpectQuery("INSERT INTO room_admins").
		WithArgs(10, 1).
		WillReturnRows(rows)

	admin, err := s.AddAdmin(context.Background(), 1, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if admin.UserID != 10 {
		t.Errorf("expected user_id 10, got %d", admin.UserID)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestAddAdminError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectQuery("INSERT INTO room_admins").
		WithArgs(10, 1).
		WillReturnError(pgx.ErrNoRows)

	_, err := s.AddAdmin(context.Background(), 1, 10)
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestRemoveAdminSuccess(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("DELETE FROM room_admins WHERE room_id").
		WithArgs(1, 10).
		WillReturnResult(pgxmock.NewResult("DELETE", 1))

	err := s.RemoveAdmin(context.Background(), 1, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestRemoveAdminNotFound(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("DELETE FROM room_admins WHERE room_id").
		WithArgs(1, 999).
		WillReturnResult(pgxmock.NewResult("DELETE", 0))

	err := s.RemoveAdmin(context.Background(), 1, 999)
	if err == nil {
		t.Error("expected error for not found")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestRemoveAdminDBError(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	mock.ExpectExec("DELETE FROM room_admins WHERE room_id").
		WithArgs(1, 10).
		WillReturnError(pgx.ErrNoRows)

	err := s.RemoveAdmin(context.Background(), 1, 10)
	if err == nil {
		t.Error("expected error")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestIsAdminTrue(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	rows := pgxmock.NewRows([]string{"exists"}).AddRow(true)
	mock.ExpectQuery("SELECT EXISTS").
		WithArgs(1, 10).
		WillReturnRows(rows)

	isAdmin, err := s.IsAdmin(context.Background(), 1, 10)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !isAdmin {
		t.Error("expected isAdmin to be true")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestIsAdminFalse(t *testing.T) {
	mock := newMockPool(t)
	defer mock.Close()
	s := NewRoomStoreWithPool(mock)

	rows := pgxmock.NewRows([]string{"exists"}).AddRow(false)
	mock.ExpectQuery("SELECT EXISTS").
		WithArgs(1, 99).
		WillReturnRows(rows)

	isAdmin, err := s.IsAdmin(context.Background(), 1, 99)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if isAdmin {
		t.Error("expected isAdmin to be false")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

