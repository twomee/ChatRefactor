// Package store provides data access to the chatbox_chat database via pgx.
package store

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/twomee/chatbox/chat-service/internal/model"
)

// PgxPool defines the subset of pgxpool.Pool methods used by the store.
// Both *pgxpool.Pool and pgxmock satisfy this interface, enabling unit tests.
type PgxPool interface {
	Query(ctx context.Context, sql string, args ...interface{}) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...interface{}) pgx.Row
	Exec(ctx context.Context, sql string, args ...interface{}) (pgconn.CommandTag, error)
}

// RoomStore handles all room-related database operations.
type RoomStore struct {
	pool PgxPool
}

// NewRoomStore creates a RoomStore backed by the given connection pool.
func NewRoomStore(pool *pgxpool.Pool) *RoomStore {
	return &RoomStore{pool: pool}
}

// NewRoomStoreWithPool creates a RoomStore with a custom pool implementation.
// This is used for testing with mock pools.
func NewRoomStoreWithPool(pool PgxPool) *RoomStore {
	return &RoomStore{pool: pool}
}

// ---------- Room CRUD ----------

// GetAll returns every active room ordered by creation time.
func (s *RoomStore) GetAll(ctx context.Context) ([]model.Room, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, name, is_active, created_at FROM rooms WHERE is_active = true ORDER BY created_at`)
	if err != nil {
		return nil, fmt.Errorf("room GetAll: %w", err)
	}
	defer rows.Close()

	var rooms []model.Room
	for rows.Next() {
		var r model.Room
		if err := rows.Scan(&r.ID, &r.Name, &r.IsActive, &r.CreatedAt); err != nil {
			return nil, fmt.Errorf("room GetAll scan: %w", err)
		}
		rooms = append(rooms, r)
	}
	return rooms, rows.Err()
}

// GetByID returns a single room or ErrNoRows.
func (s *RoomStore) GetByID(ctx context.Context, id int) (*model.Room, error) {
	var r model.Room
	err := s.pool.QueryRow(ctx,
		`SELECT id, name, is_active, created_at FROM rooms WHERE id = $1`, id,
	).Scan(&r.ID, &r.Name, &r.IsActive, &r.CreatedAt)
	if err != nil {
		return nil, fmt.Errorf("room GetByID: %w", err)
	}
	return &r, nil
}

// Create inserts a new room and returns it with the generated ID.
func (s *RoomStore) Create(ctx context.Context, name string) (*model.Room, error) {
	var r model.Room
	err := s.pool.QueryRow(ctx,
		`INSERT INTO rooms (name) VALUES ($1) RETURNING id, name, is_active, created_at`, name,
	).Scan(&r.ID, &r.Name, &r.IsActive, &r.CreatedAt)
	if err != nil {
		return nil, fmt.Errorf("room Create: %w", err)
	}
	return &r, nil
}

// SetActive toggles the is_active flag on a room.
func (s *RoomStore) SetActive(ctx context.Context, id int, active bool) error {
	tag, err := s.pool.Exec(ctx,
		`UPDATE rooms SET is_active = $1 WHERE id = $2`, active, id)
	if err != nil {
		return fmt.Errorf("room SetActive: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

// ---------- Admins ----------

// GetAdmins returns all admins for a room.
func (s *RoomStore) GetAdmins(ctx context.Context, roomID int) ([]model.RoomAdmin, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, user_id, room_id, appointed_at FROM room_admins WHERE room_id = $1`, roomID)
	if err != nil {
		return nil, fmt.Errorf("room GetAdmins: %w", err)
	}
	defer rows.Close()

	var admins []model.RoomAdmin
	for rows.Next() {
		var a model.RoomAdmin
		if err := rows.Scan(&a.ID, &a.UserID, &a.RoomID, &a.AppointedAt); err != nil {
			return nil, fmt.Errorf("room GetAdmins scan: %w", err)
		}
		admins = append(admins, a)
	}
	return admins, rows.Err()
}

// AddAdmin appoints a user as room admin. Returns the new record.
func (s *RoomStore) AddAdmin(ctx context.Context, roomID, userID int) (*model.RoomAdmin, error) {
	var a model.RoomAdmin
	err := s.pool.QueryRow(ctx,
		`INSERT INTO room_admins (user_id, room_id) VALUES ($1, $2)
		 RETURNING id, user_id, room_id, appointed_at`, userID, roomID,
	).Scan(&a.ID, &a.UserID, &a.RoomID, &a.AppointedAt)
	if err != nil {
		return nil, fmt.Errorf("room AddAdmin: %w", err)
	}
	return &a, nil
}

// RemoveAdmin removes a user's admin role in a room.
func (s *RoomStore) RemoveAdmin(ctx context.Context, roomID, userID int) error {
	tag, err := s.pool.Exec(ctx,
		`DELETE FROM room_admins WHERE room_id = $1 AND user_id = $2`, roomID, userID)
	if err != nil {
		return fmt.Errorf("room RemoveAdmin: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

// IsAdmin checks whether a user is an admin of a specific room.
func (s *RoomStore) IsAdmin(ctx context.Context, roomID, userID int) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM room_admins WHERE room_id = $1 AND user_id = $2)`,
		roomID, userID,
	).Scan(&exists)
	return exists, err
}

// ---------- Muted users ----------

// GetMutedUsers returns all muted users for a room.
func (s *RoomStore) GetMutedUsers(ctx context.Context, roomID int) ([]model.MutedUser, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, user_id, room_id, muted_at FROM muted_users WHERE room_id = $1`, roomID)
	if err != nil {
		return nil, fmt.Errorf("room GetMutedUsers: %w", err)
	}
	defer rows.Close()

	var muted []model.MutedUser
	for rows.Next() {
		var m model.MutedUser
		if err := rows.Scan(&m.ID, &m.UserID, &m.RoomID, &m.MutedAt); err != nil {
			return nil, fmt.Errorf("room GetMutedUsers scan: %w", err)
		}
		muted = append(muted, m)
	}
	return muted, rows.Err()
}

// MuteUser mutes a user in a room.
func (s *RoomStore) MuteUser(ctx context.Context, roomID, userID int) (*model.MutedUser, error) {
	var m model.MutedUser
	err := s.pool.QueryRow(ctx,
		`INSERT INTO muted_users (user_id, room_id) VALUES ($1, $2)
		 RETURNING id, user_id, room_id, muted_at`, userID, roomID,
	).Scan(&m.ID, &m.UserID, &m.RoomID, &m.MutedAt)
	if err != nil {
		return nil, fmt.Errorf("room MuteUser: %w", err)
	}
	return &m, nil
}

// UnmuteUser removes a mute on a user in a room.
func (s *RoomStore) UnmuteUser(ctx context.Context, roomID, userID int) error {
	tag, err := s.pool.Exec(ctx,
		`DELETE FROM muted_users WHERE room_id = $1 AND user_id = $2`, roomID, userID)
	if err != nil {
		return fmt.Errorf("room UnmuteUser: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

// IsMuted checks whether a user is muted in a specific room.
func (s *RoomStore) IsMuted(ctx context.Context, roomID, userID int) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM muted_users WHERE room_id = $1 AND user_id = $2)`,
		roomID, userID,
	).Scan(&exists)
	return exists, err
}

// ---------- Admin operations (global) ----------

// GetAllIncludingInactive returns every room regardless of active status.
func (s *RoomStore) GetAllIncludingInactive(ctx context.Context) ([]model.Room, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, name, is_active, created_at FROM rooms ORDER BY created_at`)
	if err != nil {
		return nil, fmt.Errorf("room GetAllIncludingInactive: %w", err)
	}
	defer rows.Close()

	var rooms []model.Room
	for rows.Next() {
		var r model.Room
		if err := rows.Scan(&r.ID, &r.Name, &r.IsActive, &r.CreatedAt); err != nil {
			return nil, fmt.Errorf("room GetAllIncludingInactive scan: %w", err)
		}
		rooms = append(rooms, r)
	}
	return rooms, rows.Err()
}

// SetAllActive sets the is_active flag on all rooms. Returns the number of affected rows.
func (s *RoomStore) SetAllActive(ctx context.Context, active bool) (int, error) {
	tag, err := s.pool.Exec(ctx,
		`UPDATE rooms SET is_active = $1`, active)
	if err != nil {
		return 0, fmt.Errorf("room SetAllActive: %w", err)
	}
	return int(tag.RowsAffected()), nil
}

// DeleteAllData truncates rooms, room_admins, and muted_users tables.
// Only for dev/staging use.
func (s *RoomStore) DeleteAllData(ctx context.Context) error {
	_, err := s.pool.Exec(ctx,
		`TRUNCATE muted_users, room_admins, rooms RESTART IDENTITY CASCADE`)
	if err != nil {
		return fmt.Errorf("room DeleteAllData: %w", err)
	}
	return nil
}
