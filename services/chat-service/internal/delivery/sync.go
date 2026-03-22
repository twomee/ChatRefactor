package delivery

import (
	"context"

	"go.uber.org/zap"
)

// SyncDelivery is a no-op fallback used in tests or when Kafka is unavailable.
// It logs messages instead of producing them.
type SyncDelivery struct {
	logger *zap.Logger
}

// NewSyncDelivery creates a synchronous (local-only) delivery strategy.
func NewSyncDelivery(logger *zap.Logger) *SyncDelivery {
	return &SyncDelivery{logger: logger}
}

func (s *SyncDelivery) DeliverChat(_ context.Context, roomID int, payload []byte) error {
	s.logger.Info("sync_deliver_chat",
		zap.Int("room_id", roomID),
		zap.Int("payload_bytes", len(payload)),
	)
	return nil
}

func (s *SyncDelivery) DeliverPM(_ context.Context, fromUserID int, payload []byte) error {
	s.logger.Info("sync_deliver_pm",
		zap.Int("from_user_id", fromUserID),
		zap.Int("payload_bytes", len(payload)),
	)
	return nil
}

func (s *SyncDelivery) DeliverEvent(_ context.Context, eventType string, payload []byte) error {
	s.logger.Info("sync_deliver_event",
		zap.String("event_type", eventType),
		zap.Int("payload_bytes", len(payload)),
	)
	return nil
}
