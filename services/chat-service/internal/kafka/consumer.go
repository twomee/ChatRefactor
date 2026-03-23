// Package kafka provides Kafka integration for the chat-service.
// consumer.go reads from Kafka topics and dispatches events to handlers.
package kafka

import (
	"context"
	"encoding/json"
	"time"

	kafkago "github.com/segmentio/kafka-go"
	"go.uber.org/zap"
)

// EventHandler processes a deserialized Kafka event.
type EventHandler func(ctx context.Context, value map[string]interface{}) error

// Consumer reads from a Kafka topic and dispatches events to a handler.
type Consumer struct {
	reader  *kafkago.Reader
	handler EventHandler
	logger  *zap.Logger
	done    chan struct{}
}

// NewConsumer creates a Kafka consumer for the given topic and consumer group.
func NewConsumer(brokers []string, topic, groupID string, handler EventHandler, logger *zap.Logger) *Consumer {
	reader := kafkago.NewReader(kafkago.ReaderConfig{
		Brokers:        brokers,
		Topic:          topic,
		GroupID:        groupID,
		MinBytes:       1,
		MaxBytes:       10e6, // 10 MB
		CommitInterval: time.Second,
		StartOffset:    kafkago.LastOffset,
	})
	return &Consumer{
		reader:  reader,
		handler: handler,
		logger:  logger,
		done:    make(chan struct{}),
	}
}

// Start begins consuming in a background goroutine.
func (c *Consumer) Start(ctx context.Context) {
	go c.run(ctx)
}

// Stop signals the consumer to shut down and waits for completion.
func (c *Consumer) Stop() {
	_ = c.reader.Close()
	<-c.done
}

func (c *Consumer) run(ctx context.Context) {
	defer close(c.done)
	c.logger.Info("kafka_consumer_started", zap.String("topic", c.reader.Config().Topic))

	for {
		msg, err := c.reader.ReadMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				// Context cancelled — clean shutdown.
				break
			}
			c.logger.Warn("kafka_consumer_read_error", zap.Error(err))
			time.Sleep(2 * time.Second)
			continue
		}

		var value map[string]interface{}
		if err := json.Unmarshal(msg.Value, &value); err != nil {
			c.logger.Warn("kafka_consumer_unmarshal_error", zap.Error(err))
			continue
		}

		if err := c.handler(ctx, value); err != nil {
			c.logger.Warn("kafka_consumer_handler_error", zap.Error(err))
		}
	}

	c.logger.Info("kafka_consumer_stopped", zap.String("topic", c.reader.Config().Topic))
}
