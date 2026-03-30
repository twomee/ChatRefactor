from prometheus_client import Counter, Gauge

# Business metrics
auth_registrations_total = Counter(
    "auth_registrations_total",
    "Total user registrations",
    ["status"],  # success, duplicate, error
)
auth_logins_total = Counter(
    "auth_logins_total",
    "Total login attempts",
    ["status"],  # success, invalid_credentials, error
)
auth_logouts_total = Counter(
    "auth_logouts_total",
    "Total logout operations",
    ["status"],  # success, error
)
auth_2fa_operations_total = Counter(
    "auth_2fa_operations_total",
    "Total 2FA operations",
    ["operation", "status"],  # operation: setup, verify_setup, disable, verify_login
)

# Kafka producer metrics
kafka_events_produced_total = Counter(
    "kafka_events_produced_total",
    "Total Kafka events produced",
    ["topic", "status"],  # success, failed
)

# Database pool metrics (updated periodically from SQLAlchemy pool stats)
db_pool_size = Gauge("db_pool_size", "Current DB connection pool size")
db_pool_checked_out = Gauge("db_pool_checked_out", "DB connections currently in use")
db_pool_overflow = Gauge("db_pool_overflow", "DB connections in overflow")
