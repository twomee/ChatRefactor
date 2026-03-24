package store

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/pashagolub/pgxmock/v4"
)

func newMockPool(t *testing.T) pgxmock.PgxPoolIface {
	t.Helper()
	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatalf("pgxmock.NewPool: %v", err)
	}
	return mock
}

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
