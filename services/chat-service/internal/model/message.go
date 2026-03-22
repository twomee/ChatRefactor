package model

import "time"

// ChatMessage is the envelope sent over WebSocket and to Kafka.
type ChatMessage struct {
	Type      string    `json:"type"`
	RoomID    int       `json:"room_id,omitempty"`
	UserID    int       `json:"user_id"`
	Username  string    `json:"username"`
	Content   string    `json:"content"`
	Timestamp time.Time `json:"timestamp"`
}

// PrivateMessage is the envelope for PM delivery.
type PrivateMessage struct {
	Type       string    `json:"type"`
	FromUserID int       `json:"from_user_id"`
	FromUser   string    `json:"from_user"`
	ToUserID   int       `json:"to_user_id"`
	ToUser     string    `json:"to_user"`
	Content    string    `json:"content"`
	Timestamp  time.Time `json:"timestamp"`
}

// SendPMRequest is the REST payload for sending a PM.
type SendPMRequest struct {
	ToUsername string `json:"to_username" binding:"required"`
	Content    string `json:"content" binding:"required,min=1"`
}
