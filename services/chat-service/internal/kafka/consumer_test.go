package kafka

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"
	"time"

	kafkago "github.com/segmentio/kafka-go"
	"go.uber.org/zap"
)

// mockReader implements MessageReader for testing.
type mockReader struct {
	mu       sync.Mutex
	messages []kafkago.Message
	idx      int
	err      error
	closed   bool
	topic    string
}

func (m *mockReader) ReadMessage(ctx context.Context) (kafkago.Message, error) {
	// Block until cancelled if no more messages.
	m.mu.Lock()
	if m.idx >= len(m.messages) {
		m.mu.Unlock()
		if m.err != nil {
			return kafkago.Message{}, m.err
		}
		<-ctx.Done()
		return kafkago.Message{}, ctx.Err()
	}
	msg := m.messages[m.idx]
	m.idx++
	m.mu.Unlock()
	return msg, nil
}

func (m *mockReader) Close() error {
	m.closed = true
	return nil
}

func (m *mockReader) Config() kafkago.ReaderConfig {
	return kafkago.ReaderConfig{Topic: m.topic}
}

func TestNewConsumerWithReader(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	reader := &mockReader{topic: "test-topic"}
	handler := func(ctx context.Context, value map[string]interface{}) error { return nil }

	c := NewConsumerWithReader(reader, handler, logger)
	if c.reader != reader {
		t.Error("expected reader to be set")
	}
	if c.logger != logger {
		t.Error("expected logger to be set")
	}
}

func TestConsumerProcessesMessages(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	payload, _ := json.Marshal(map[string]interface{}{
		"msg_id":  "abc-123",
		"room_id": 1,
		"text":    "hello",
	})

	reader := &mockReader{
		topic:    "chat.messages",
		messages: []kafkago.Message{{Value: payload}},
	}

	var received map[string]interface{}
	var mu sync.Mutex
	handler := func(ctx context.Context, value map[string]interface{}) error {
		mu.Lock()
		received = value
		mu.Unlock()
		return nil
	}

	c := NewConsumerWithReader(reader, handler, logger)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	c.Start(ctx)
	<-c.done

	mu.Lock()
	defer mu.Unlock()
	if received == nil {
		t.Fatal("handler was not called")
	}
	if received["msg_id"] != "abc-123" {
		t.Errorf("expected msg_id 'abc-123', got %v", received["msg_id"])
	}
}

func TestConsumerHandlerError(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	payload, _ := json.Marshal(map[string]interface{}{"key": "value"})
	reader := &mockReader{
		topic:    "test",
		messages: []kafkago.Message{{Value: payload}},
	}

	handlerCalled := false
	handler := func(ctx context.Context, value map[string]interface{}) error {
		handlerCalled = true
		return errors.New("handler failed")
	}

	c := NewConsumerWithReader(reader, handler, logger)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	c.Start(ctx)
	<-c.done

	if !handlerCalled {
		t.Error("handler should have been called even though it returns error")
	}
}

func TestConsumerInvalidJSON(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	reader := &mockReader{
		topic:    "test",
		messages: []kafkago.Message{{Value: []byte("not json")}},
	}

	handlerCalled := false
	handler := func(ctx context.Context, value map[string]interface{}) error {
		handlerCalled = true
		return nil
	}

	c := NewConsumerWithReader(reader, handler, logger)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	c.Start(ctx)
	<-c.done

	if handlerCalled {
		t.Error("handler should NOT be called for invalid JSON")
	}
}

func TestConsumerStopClosesReader(t *testing.T) {
	logger, _ := zap.NewDevelopment()
	reader := &mockReader{topic: "test"}
	handler := func(ctx context.Context, value map[string]interface{}) error { return nil }

	c := NewConsumerWithReader(reader, handler, logger)
	ctx, cancel := context.WithCancel(context.Background())

	c.Start(ctx)
	cancel() // triggers context cancellation in the run loop
	c.Stop()

	if !reader.closed {
		t.Error("expected reader to be closed after Stop")
	}
}

func TestConsumerMultipleMessages(t *testing.T) {
	logger, _ := zap.NewDevelopment()

	var msgs []kafkago.Message
	for i := 0; i < 3; i++ {
		payload, _ := json.Marshal(map[string]interface{}{"idx": i})
		msgs = append(msgs, kafkago.Message{Value: payload})
	}

	reader := &mockReader{topic: "test", messages: msgs}

	var mu sync.Mutex
	count := 0
	handler := func(ctx context.Context, value map[string]interface{}) error {
		mu.Lock()
		count++
		mu.Unlock()
		return nil
	}

	c := NewConsumerWithReader(reader, handler, logger)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	c.Start(ctx)
	<-c.done

	mu.Lock()
	defer mu.Unlock()
	if count != 3 {
		t.Errorf("expected handler called 3 times, got %d", count)
	}
}
