# kafka_topics.py — Idempotent topic creation on startup
from logging_config import get_logger

logger = get_logger("kafka_topics")

# Topic configuration: {name: {partitions, retention_ms}}
TOPIC_CONFIG = {
    "chat.messages": {"partitions": 6, "retention_ms": 7 * 24 * 60 * 60 * 1000},    # 7 days
    "chat.private":  {"partitions": 3, "retention_ms": 7 * 24 * 60 * 60 * 1000},    # 7 days
    "chat.events":   {"partitions": 3, "retention_ms": 3 * 24 * 60 * 60 * 1000},    # 3 days
    "chat.dlq":      {"partitions": 1, "retention_ms": 30 * 24 * 60 * 60 * 1000},   # 30 days
}

# Convenience constants for use in producers/consumers
TOPIC_MESSAGES = "chat.messages"
TOPIC_PRIVATE = "chat.private"
TOPIC_EVENTS = "chat.events"
TOPIC_DLQ = "chat.dlq"


async def ensure_topics():
    """Create Kafka topics if they don't exist. Idempotent — safe to call on every startup."""
    try:
        from aiokafka.admin import AIOKafkaAdminClient, NewTopic
        from config import KAFKA_BOOTSTRAP_SERVERS

        admin = AIOKafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        await admin.start()

        try:
            existing = await admin.list_topics()
            to_create = []

            for name, cfg in TOPIC_CONFIG.items():
                if name not in existing:
                    to_create.append(NewTopic(
                        name=name,
                        num_partitions=cfg["partitions"],
                        replication_factor=1,
                        topic_configs={"retention.ms": str(cfg["retention_ms"])},
                    ))

            if to_create:
                await admin.create_topics(to_create)
                created_names = [t.name for t in to_create]
                logger.info("kafka_topics_created", topics=created_names)
            else:
                logger.info("kafka_topics_exist", count=len(TOPIC_CONFIG))
        finally:
            await admin.close()

    except Exception as e:
        logger.warning("kafka_topics_setup_failed", error=str(e))
