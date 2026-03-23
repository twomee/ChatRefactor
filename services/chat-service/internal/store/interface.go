// Package store provides data access to the chatbox_chat database via pgx.
package store

import (
	"context"

	"github.com/twomee/chatbox/chat-service/internal/model"
)

// RoomRepository defines the interface for room-related database operations.
// Handlers depend on this interface rather than the concrete RoomStore, making
// it straightforward to mock the store layer in tests.
type RoomRepository interface {
	GetAll(ctx context.Context) ([]model.Room, error)
	GetAllIncludingInactive(ctx context.Context) ([]model.Room, error)
	GetByID(ctx context.Context, id int) (*model.Room, error)
	Create(ctx context.Context, name string) (*model.Room, error)
	SetActive(ctx context.Context, id int, active bool) error
	SetAllActive(ctx context.Context, active bool) (int, error)
	GetAdmins(ctx context.Context, roomID int) ([]model.RoomAdmin, error)
	AddAdmin(ctx context.Context, roomID, userID int) (*model.RoomAdmin, error)
	RemoveAdmin(ctx context.Context, roomID, userID int) error
	IsAdmin(ctx context.Context, roomID, userID int) (bool, error)
	GetMutedUsers(ctx context.Context, roomID int) ([]model.MutedUser, error)
	MuteUser(ctx context.Context, roomID, userID int) (*model.MutedUser, error)
	UnmuteUser(ctx context.Context, roomID, userID int) error
	IsMuted(ctx context.Context, roomID, userID int) (bool, error)
	DeleteAllData(ctx context.Context) error
}

// Compile-time check that RoomStore implements RoomRepository.
var _ RoomRepository = (*RoomStore)(nil)
