from prometheus_client import Counter, Histogram, Gauge

# Kafka consumer metrics
kafka_messages_consumed_total = Counter(
    "kafka_messages_consumed_total",
    "Total Kafka messages consumed by persistence consumer",
    ["topic", "status"],  # success, retry, dlq
)
kafka_consume_duration_seconds = Histogram(
    "kafka_consume_duration_seconds",
    "Time to process a single Kafka message",
    ["topic"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5],
)

# Message persistence metrics
messages_persisted_total = Counter(
    "messages_persisted_total",
    "Total messages persisted to DB",
    ["type"],  # room, private
)
messages_dlq_total = Counter(
    "messages_dlq_total",
    "Total messages sent to Dead Letter Queue",
)

# Auth service call metrics
auth_service_calls_total = Counter(
    "auth_service_calls_total",
    "Total calls to auth service for user resolution",
    ["status"],  # success, error
)
auth_service_call_duration_seconds = Histogram(
    "auth_service_call_duration_seconds",
    "Duration of auth service HTTP calls",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],
)

# Database pool metrics
db_pool_size = Gauge("db_pool_size", "Current DB connection pool size")
db_pool_checked_out = Gauge("db_pool_checked_out", "DB connections in use")
