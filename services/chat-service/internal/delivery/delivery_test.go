package delivery

import (
	"context"
	"errors"
	"testing"

	kafkago "github.com/segmentio/kafka-go"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/kafka"
)

// mockWriter implements kafka.MessageWriter for testing.
type mockWriter struct {
	messages []kafkago.Message
	err      error
}

func (m *mockWriter) WriteMessages(ctx context.Context, msgs ...kafkago.Message) error {
	if m.err != nil {
		return m.err
	}
	m.messages = append(m.messages, msgs...)
	return nil
}

func (m *mockWriter) Close() error {
	return nil
}

// ---------- SyncDelivery tests ----------

func TestSyncDeliveryDeliverChat(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	s := NewSyncDelivery(logger)

	err := s.DeliverChat(context.Background(), 42, []byte(`{"msg":"hello"}`))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestSyncDeliveryDeliverPM(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	s := NewSyncDelivery(logger)

	err := s.DeliverPM(context.Background(), 1, []byte(`{"pm":"hello"}`))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestSyncDeliveryDeliverEvent(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	s := NewSyncDelivery(logger)

	err := s.DeliverEvent(context.Background(), "join", []byte(`{"event":"join"}`))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestSyncDeliveryImplementsStrategy(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	var _ Strategy = NewSyncDelivery(logger)
}

// ---------- KafkaDelivery tests ----------

func TestKafkaDeliveryDeliverChat(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	mw := &mockWriter{}
	producer := kafka.NewProducerWithWriter(mw, logger)
	k := NewKafkaDelivery(producer)

	err := k.DeliverChat(context.Background(), 42, []byte(`{"msg":"hello"}`))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(mw.messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(mw.messages))
	}
	if mw.messages[0].Topic != topicChatMessages {
		t.Errorf("expected topic %q, got %q", topicChatMessages, mw.messages[0].Topic)
	}
	if string(mw.messages[0].Key) != "room_42" {
		t.Errorf("expected key 'room_42', got %q", string(mw.messages[0].Key))
	}
}

func TestKafkaDeliveryDeliverPM(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	mw := &mockWriter{}
	producer := kafka.NewProducerWithWriter(mw, logger)
	k := NewKafkaDelivery(producer)

	err := k.DeliverPM(context.Background(), 5, []byte(`{"pm":"hello"}`))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(mw.messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(mw.messages))
	}
	if mw.messages[0].Topic != topicChatPrivate {
		t.Errorf("expected topic %q, got %q", topicChatPrivate, mw.messages[0].Topic)
	}
	if string(mw.messages[0].Key) != "user_5" {
		t.Errorf("expected key 'user_5', got %q", string(mw.messages[0].Key))
	}
}

func TestKafkaDeliveryDeliverEvent(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	mw := &mockWriter{}
	producer := kafka.NewProducerWithWriter(mw, logger)
	k := NewKafkaDelivery(producer)

	err := k.DeliverEvent(context.Background(), "leave", []byte(`{"event":"leave"}`))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(mw.messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(mw.messages))
	}
	if mw.messages[0].Topic != topicChatEvents {
		t.Errorf("expected topic %q, got %q", topicChatEvents, mw.messages[0].Topic)
	}
}

func TestKafkaDeliveryWriteError(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	producer := kafka.NewProducerWithWriter(&mockWriter{err: errors.New("kafka down")}, logger)
	k := NewKafkaDelivery(producer)

	err := k.DeliverChat(context.Background(), 1, []byte(`{"msg":"test"}`))
	if err == nil {
		t.Error("expected error when kafka writer fails")
	}
}

func TestKafkaDeliveryImplementsStrategy(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	producer := kafka.NewProducerWithWriter(&mockWriter{}, logger)
	var _ Strategy = NewKafkaDelivery(producer)
}
