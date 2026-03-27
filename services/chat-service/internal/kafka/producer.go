// Package kafka provides a thin wrapper around segmentio/kafka-go for
// producing messages to Kafka topics.
//
// We use segmentio/kafka-go instead of confluent-kafka-go because it is
// pure Go — no CGO / librdkafka dependency. This simplifies Docker builds
// (scratch / distroless base images work out of the box) and cross-compilation.
package kafka

import (
	"context"
	"fmt"
	"time"

	kafkago "github.com/segmentio/kafka-go"
	"go.uber.org/zap"

	"github.com/twomee/chatbox/chat-service/internal/metrics"
)

// MessageWriter is the interface for writing Kafka messages. This allows
// the Producer to be tested with a mock writer.
type MessageWriter interface {
	WriteMessages(ctx context.Context, msgs ...kafkago.Message) error
	Close() error
}

// Producer wraps a kafka-go Writer for topic-based message production.
type Producer struct {
	writer MessageWriter
	logger *zap.Logger
}

// NewProducer creates a Kafka producer targeting the given broker addresses.
// The writer is configured for automatic topic creation at the broker level
// (ensure auto.create.topics.enable=true in Kafka config for dev).
func NewProducer(brokers []string, logger *zap.Logger) *Producer {
	w := &kafkago.Writer{
		Addr:         kafkago.TCP(brokers...),
		Balancer:     &kafkago.LeastBytes{},
		BatchTimeout: 10 * time.Millisecond, // low latency for chat
		RequiredAcks: kafkago.RequireOne,
		Async:        false, // synchronous writes so callers know about failures
	}
	return &Producer{writer: w, logger: logger}
}

// NewProducerWithWriter creates a Producer with a custom writer, useful for
// testing with mock writers.
func NewProducerWithWriter(w MessageWriter, logger *zap.Logger) *Producer {
	return &Producer{writer: w, logger: logger}
}

// Produce sends a single message to the given topic. The key is used for
// partition routing (e.g. room_id for chat messages, user_id for PMs).
func (p *Producer) Produce(ctx context.Context, topic, key string, value []byte) error {
	msg := kafkago.Message{
		Topic: topic,
		Key:   []byte(key),
		Value: value,
	}
	if err := p.writer.WriteMessages(ctx, msg); err != nil {
		metrics.KafkaProduceTotal.WithLabelValues(topic, "error").Inc()
		p.logger.Error("kafka_produce_failed",
			zap.String("topic", topic),
			zap.String("key", key),
			zap.Error(err),
		)
		return fmt.Errorf("kafka produce to %s: %w", topic, err)
	}
	metrics.KafkaProduceTotal.WithLabelValues(topic, "success").Inc()
	p.logger.Debug("kafka_produced",
		zap.String("topic", topic),
		zap.String("key", key),
	)
	return nil
}

// Close shuts down the Kafka writer, flushing any pending messages.
func (p *Producer) Close() error {
	return p.writer.Close()
}

// Ping checks connectivity by looking up the broker metadata.
// This is used by the readiness probe.
func (p *Producer) Ping(ctx context.Context, brokers []string) error {
	if len(brokers) == 0 {
		return fmt.Errorf("no kafka brokers configured")
	}
	conn, err := kafkago.DialContext(ctx, "tcp", brokers[0])
	if err != nil {
		return fmt.Errorf("kafka ping: %w", err)
	}
	_ = conn.Close()
	return nil
}
