// Package store provides data access to the chatbox_chat database via pgx.
package store

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// ReadPosition represents a user's last-read position in a room.
type ReadPosition struct {
	UserID            int       `json:"user_id"`
	RoomID            int       `json:"room_id"`
	LastReadMessageID string    `json:"last_read_message_id"`
	LastReadAt        time.Time `json:"last_read_at"`
}

// ReadPositionRepository defines the interface for read-position database operations.
// Handlers depend on this interface rather than the concrete ReadPositionStore,
// making it straightforward to mock the store layer in tests.
type ReadPositionRepository interface {
	Upsert(ctx context.Context, userID, roomID int, messageID string) error
	Get(ctx context.Context, userID, roomID int) (*ReadPosition, error)
}

// Compile-time check that ReadPositionStore implements ReadPositionRepository.
var _ ReadPositionRepository = (*ReadPositionStore)(nil)

// ReadPositionStore handles all read-position-related database operations.
type ReadPositionStore struct {
	pool PgxPool
}

// NewReadPositionStore creates a ReadPositionStore backed by the given connection pool.
func NewReadPositionStore(pool *pgxpool.Pool) *ReadPositionStore {
	return &ReadPositionStore{pool: pool}
}

// NewReadPositionStoreWithPool creates a ReadPositionStore with a custom pool implementation.
// This is used for testing with mock pools.
func NewReadPositionStoreWithPool(pool PgxPool) *ReadPositionStore {
	return &ReadPositionStore{pool: pool}
}

// Upsert creates or updates a user's read position in a room.
// Uses ON CONFLICT to atomically insert or update.
func (s *ReadPositionStore) Upsert(ctx context.Context, userID, roomID int, messageID string) error {
	_, err := s.pool.Exec(ctx, `
		INSERT INTO read_positions (user_id, room_id, last_read_message_id, last_read_at, updated_at)
		VALUES ($1, $2, $3, NOW(), NOW())
		ON CONFLICT (user_id, room_id)
		DO UPDATE SET last_read_message_id = $3, last_read_at = NOW(), updated_at = NOW()
	`, userID, roomID, messageID)
	if err != nil {
		return fmt.Errorf("read_position Upsert: %w", err)
	}
	return nil
}

// Get fetches a user's read position for a room.
// Returns nil and pgx.ErrNoRows if no read position exists.
func (s *ReadPositionStore) Get(ctx context.Context, userID, roomID int) (*ReadPosition, error) {
	var rp ReadPosition
	err := s.pool.QueryRow(ctx, `
		SELECT user_id, room_id, last_read_message_id, last_read_at
		FROM read_positions WHERE user_id = $1 AND room_id = $2
	`, userID, roomID).Scan(&rp.UserID, &rp.RoomID, &rp.LastReadMessageID, &rp.LastReadAt)
	if err != nil {
		if err == pgx.ErrNoRows {
			return nil, err
		}
		return nil, fmt.Errorf("read_position Get: %w", err)
	}
	return &rp, nil
}
