// Package model defines the domain types that map to the chatbox_chat database.
package model

import "time"

// Room represents a chat room.
type Room struct {
	ID        int       `json:"id"`
	Name      string    `json:"name"`
	IsActive  bool      `json:"is_active"`
	CreatedAt time.Time `json:"created_at"`
}

// CreateRoomRequest is the payload for creating a new room.
type CreateRoomRequest struct {
	Name string `json:"name" binding:"required,min=1,max=128"`
}

// SetActiveRequest is the payload for toggling room active state.
type SetActiveRequest struct {
	IsActive bool `json:"is_active"`
}
