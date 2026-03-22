package kafka

import (
	"context"
	"errors"
	"testing"

	kafkago "github.com/segmentio/kafka-go"
	"go.uber.org/zap"
)

// mockWriter implements MessageWriter for testing.
type mockWriter struct {
	messages []kafkago.Message
	err      error
	closed   bool
}

func (m *mockWriter) WriteMessages(ctx context.Context, msgs ...kafkago.Message) error {
	if m.err != nil {
		return m.err
	}
	m.messages = append(m.messages, msgs...)
	return nil
}

func (m *mockWriter) Close() error {
	m.closed = true
	return nil
}

func TestProduceSuccess(t *testing.T) {
	mw := &mockWriter{}
	logger, _ := zap.NewDevelopment()
	p := NewProducerWithWriter(mw, logger)

	err := p.Produce(context.Background(), "test-topic", "key1", []byte("hello"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(mw.messages) != 1 {
		t.Fatalf("expected 1 message, got %d", len(mw.messages))
	}
	if mw.messages[0].Topic != "test-topic" {
		t.Errorf("expected topic 'test-topic', got %q", mw.messages[0].Topic)
	}
	if string(mw.messages[0].Key) != "key1" {
		t.Errorf("expected key 'key1', got %q", string(mw.messages[0].Key))
	}
	if string(mw.messages[0].Value) != "hello" {
		t.Errorf("expected value 'hello', got %q", string(mw.messages[0].Value))
	}
}

func TestProduceError(t *testing.T) {
	mw := &mockWriter{err: errors.New("write failed")}
	logger, _ := zap.NewDevelopment()
	p := NewProducerWithWriter(mw, logger)

	err := p.Produce(context.Background(), "test-topic", "key1", []byte("hello"))
	if err == nil {
		t.Error("expected error when writer fails")
	}
}

func TestProduceMultipleMessages(t *testing.T) {
	mw := &mockWriter{}
	logger, _ := zap.NewDevelopment()
	p := NewProducerWithWriter(mw, logger)

	for i := 0; i < 3; i++ {
		err := p.Produce(context.Background(), "topic", "k", []byte("v"))
		if err != nil {
			t.Fatalf("unexpected error on message %d: %v", i, err)
		}
	}

	if len(mw.messages) != 3 {
		t.Errorf("expected 3 messages, got %d", len(mw.messages))
	}
}

func TestClose(t *testing.T) {
	mw := &mockWriter{}
	logger, _ := zap.NewDevelopment()
	p := NewProducerWithWriter(mw, logger)

	err := p.Close()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !mw.closed {
		t.Error("expected writer to be closed")
	}
}

func TestPingNoBrokers(t *testing.T) {
	mw := &mockWriter{}
	logger, _ := zap.NewDevelopment()
	p := NewProducerWithWriter(mw, logger)

	err := p.Ping(context.Background(), nil)
	if err == nil {
		t.Error("expected error for no brokers")
	}
}

func TestPingEmptyBrokers(t *testing.T) {
	mw := &mockWriter{}
	logger, _ := zap.NewDevelopment()
	p := NewProducerWithWriter(mw, logger)

	err := p.Ping(context.Background(), []string{})
	if err == nil {
		t.Error("expected error for empty brokers")
	}
}

func TestPingUnreachableBroker(t *testing.T) {
	mw := &mockWriter{}
	logger, _ := zap.NewDevelopment()
	p := NewProducerWithWriter(mw, logger)

	// Use a port that won't have Kafka.
	err := p.Ping(context.Background(), []string{"127.0.0.1:1"})
	if err == nil {
		t.Error("expected error for unreachable broker")
	}
}

func TestNewProducerWithWriter(t *testing.T) {
	mw := &mockWriter{}
	logger, _ := zap.NewDevelopment()
	p := NewProducerWithWriter(mw, logger)

	if p.writer != mw {
		t.Error("expected writer to be set")
	}
	if p.logger != logger {
		t.Error("expected logger to be set")
	}
}
