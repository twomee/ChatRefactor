package delivery

import (
	"context"
	"fmt"

	"github.com/twomee/chatbox/chat-service/internal/kafka"
)

const (
	topicChatMessages = "chat.messages"
	topicChatPrivate  = "chat.private"
	topicChatEvents   = "chat.events"
)

// KafkaDelivery routes messages through Kafka topics.
type KafkaDelivery struct {
	producer *kafka.Producer
}

// NewKafkaDelivery creates a Kafka-backed delivery strategy.
func NewKafkaDelivery(producer *kafka.Producer) *KafkaDelivery {
	return &KafkaDelivery{producer: producer}
}

func (k *KafkaDelivery) DeliverChat(ctx context.Context, roomID int, payload []byte) error {
	key := fmt.Sprintf("room_%d", roomID)
	return k.producer.Produce(ctx, topicChatMessages, key, payload)
}

func (k *KafkaDelivery) DeliverPM(ctx context.Context, fromUserID int, payload []byte) error {
	key := fmt.Sprintf("user_%d", fromUserID)
	return k.producer.Produce(ctx, topicChatPrivate, key, payload)
}

func (k *KafkaDelivery) DeliverEvent(ctx context.Context, eventType string, payload []byte) error {
	return k.producer.Produce(ctx, topicChatEvents, eventType, payload)
}
