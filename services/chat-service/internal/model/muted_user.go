package model

import "time"

// MutedUser represents a muted user in a specific room.
type MutedUser struct {
	ID      int       `json:"id"`
	UserID  int       `json:"user_id"`
	RoomID  int       `json:"room_id"`
	MutedAt time.Time `json:"muted_at"`
}

// MuteRequest is the payload for muting a user in a room.
type MuteRequest struct {
	UserID int `json:"user_id" binding:"required"`
}
