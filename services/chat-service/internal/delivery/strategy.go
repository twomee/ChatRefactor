// Package delivery defines the DeliveryStrategy interface and its
// implementations. This follows the Strategy pattern so the service
// layer doesn't couple directly to Kafka — we can swap in a synchronous
// fallback for tests or when Kafka is unavailable.
package delivery

import "context"

// Strategy is the interface for delivering messages to downstream consumers.
type Strategy interface {
	// DeliverChat sends a room chat message.
	DeliverChat(ctx context.Context, roomID int, payload []byte) error
	// DeliverPM sends a private message.
	DeliverPM(ctx context.Context, fromUserID int, payload []byte) error
	// DeliverEvent sends a system event (join, leave, mute, etc.).
	DeliverEvent(ctx context.Context, eventType string, payload []byte) error
}
