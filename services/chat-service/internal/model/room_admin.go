package model

import "time"

// RoomAdmin represents an admin appointment for a room.
type RoomAdmin struct {
	ID          int       `json:"id"`
	UserID      int       `json:"user_id"`
	RoomID      int       `json:"room_id"`
	AppointedAt time.Time `json:"appointed_at"`
}

// AddAdminRequest is the payload for appointing a room admin.
type AddAdminRequest struct {
	UserID int `json:"user_id" binding:"required"`
}
