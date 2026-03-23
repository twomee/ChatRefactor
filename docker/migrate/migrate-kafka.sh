#!/bin/bash
# migrate-kafka.sh — One-time Kafka topic creation.
# Runs as a Docker init container before services start.
# Idempotent: uses --if-not-exists.
set -e

echo "=== Creating Kafka topics ==="

KAFKA_BIN="/opt/kafka/bin/kafka-topics.sh"
BOOTSTRAP="--bootstrap-server kafka:9092"

$KAFKA_BIN $BOOTSTRAP --create --topic chat.messages --partitions 6 --replication-factor 1 --if-not-exists 2>/dev/null
$KAFKA_BIN $BOOTSTRAP --create --topic chat.private  --partitions 3 --replication-factor 1 --if-not-exists 2>/dev/null
$KAFKA_BIN $BOOTSTRAP --create --topic chat.events   --partitions 3 --replication-factor 1 --if-not-exists 2>/dev/null
$KAFKA_BIN $BOOTSTRAP --create --topic chat.dlq      --partitions 1 --replication-factor 1 --if-not-exists 2>/dev/null
$KAFKA_BIN $BOOTSTRAP --create --topic file.events   --partitions 3 --replication-factor 1 --if-not-exists 2>/dev/null
$KAFKA_BIN $BOOTSTRAP --create --topic auth.events   --partitions 3 --replication-factor 1 --if-not-exists 2>/dev/null

echo "=== Topics created ==="
$KAFKA_BIN $BOOTSTRAP --list
