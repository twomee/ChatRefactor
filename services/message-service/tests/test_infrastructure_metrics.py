# tests/test_infrastructure_metrics.py — Tests for app/infrastructure/metrics.py
#
# Covers:
#   - /metrics endpoint returns 200 with Prometheus text format content-type
#   - /metrics response contains expected metric names
#   - The metrics module defines all expected counters, histograms, and gauges
#   - Consumer and auth client metric definitions (import tests)
from prometheus_client import Counter, Gauge, Histogram


class TestMetricsModuleDefinitions:
    """Verify that all expected metrics are defined with correct types."""

    # ── Kafka consumer metrics ───────────────────────────────────────

    def test_kafka_messages_consumed_total_is_counter(self):
        """kafka_messages_consumed_total should be a Counter with topic and status labels."""
        from app.infrastructure.metrics import kafka_messages_consumed_total

        assert isinstance(kafka_messages_consumed_total, Counter)
        # prometheus_client strips _total suffix internally; it is added on output
        assert kafka_messages_consumed_total._name == "kafka_messages_consumed"

    def test_kafka_consume_duration_seconds_is_histogram(self):
        """kafka_consume_duration_seconds should be a Histogram with topic label."""
        from app.infrastructure.metrics import kafka_consume_duration_seconds

        assert isinstance(kafka_consume_duration_seconds, Histogram)
        assert kafka_consume_duration_seconds._name == "kafka_consume_duration_seconds"

    # ── Message persistence metrics ──────────────────────────────────

    def test_messages_persisted_total_is_counter(self):
        """messages_persisted_total should be a Counter with type label."""
        from app.infrastructure.metrics import messages_persisted_total

        assert isinstance(messages_persisted_total, Counter)
        assert messages_persisted_total._name == "messages_persisted"

    def test_messages_dlq_total_is_counter(self):
        """messages_dlq_total should be a Counter."""
        from app.infrastructure.metrics import messages_dlq_total

        assert isinstance(messages_dlq_total, Counter)
        assert messages_dlq_total._name == "messages_dlq"

    # ── Auth service call metrics ────────────────────────────────────

    def test_auth_service_calls_total_is_counter(self):
        """auth_service_calls_total should be a Counter with status label."""
        from app.infrastructure.metrics import auth_service_calls_total

        assert isinstance(auth_service_calls_total, Counter)
        assert auth_service_calls_total._name == "auth_service_calls"

    def test_auth_service_call_duration_seconds_is_histogram(self):
        """auth_service_call_duration_seconds should be a Histogram."""
        from app.infrastructure.metrics import auth_service_call_duration_seconds

        assert isinstance(auth_service_call_duration_seconds, Histogram)
        assert (
            auth_service_call_duration_seconds._name
            == "auth_service_call_duration_seconds"
        )

    # ── Database pool metrics ────────────────────────────────────────

    def test_db_pool_size_is_gauge(self):
        """db_pool_size should be a Gauge."""
        from app.infrastructure.metrics import db_pool_size

        assert isinstance(db_pool_size, Gauge)
        assert db_pool_size._name == "db_pool_size"

    def test_db_pool_checked_out_is_gauge(self):
        """db_pool_checked_out should be a Gauge."""
        from app.infrastructure.metrics import db_pool_checked_out

        assert isinstance(db_pool_checked_out, Gauge)
        assert db_pool_checked_out._name == "db_pool_checked_out"


class TestMetricsEndpoint:
    """Tests for the /metrics endpoint exposed by prometheus_fastapi_instrumentator."""

    def test_metrics_endpoint_returns_200(self, client):
        """/metrics should return HTTP 200."""
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_endpoint_content_type(self, client):
        """/metrics should return Prometheus text format content-type."""
        resp = client.get("/metrics")
        content_type = resp.headers["content-type"]
        assert "text/plain" in content_type

    def test_metrics_contains_http_requests_total(self, client):
        """/metrics should contain HTTP request metrics from the instrumentator."""
        resp = client.get("/metrics")
        body = resp.text
        assert "http_requests_total" in body or "http_request_duration" in body

    def test_metrics_contains_kafka_messages_consumed_total(self, client):
        """/metrics should contain kafka_messages_consumed_total."""
        resp = client.get("/metrics")
        body = resp.text
        assert "kafka_messages_consumed_total" in body

    def test_metrics_contains_kafka_consume_duration_seconds(self, client):
        """/metrics should contain kafka_consume_duration_seconds."""
        resp = client.get("/metrics")
        body = resp.text
        assert "kafka_consume_duration_seconds" in body

    def test_metrics_contains_messages_persisted_total(self, client):
        """/metrics should contain messages_persisted_total."""
        resp = client.get("/metrics")
        body = resp.text
        assert "messages_persisted_total" in body

    def test_metrics_contains_messages_dlq_total(self, client):
        """/metrics should contain messages_dlq_total."""
        resp = client.get("/metrics")
        body = resp.text
        assert "messages_dlq_total" in body

    def test_metrics_contains_auth_service_calls_total(self, client):
        """/metrics should contain auth_service_calls_total."""
        resp = client.get("/metrics")
        body = resp.text
        assert "auth_service_calls_total" in body

    def test_metrics_contains_auth_service_call_duration_seconds(self, client):
        """/metrics should contain auth_service_call_duration_seconds."""
        resp = client.get("/metrics")
        body = resp.text
        assert "auth_service_call_duration_seconds" in body

    def test_metrics_contains_db_pool_gauges(self, client):
        """/metrics should contain db_pool_size and db_pool_checked_out."""
        resp = client.get("/metrics")
        body = resp.text
        assert "db_pool_size" in body
        assert "db_pool_checked_out" in body


class TestMetricLabels:
    """Verify that labeled metrics accept the expected label values."""

    def test_kafka_messages_consumed_total_accepts_labels(self):
        """kafka_messages_consumed_total should accept topic and status labels."""
        from app.infrastructure.metrics import kafka_messages_consumed_total

        # Calling .labels() with the expected keys should not raise
        child = kafka_messages_consumed_total.labels(
            topic="test-topic", status="success"
        )
        assert child is not None

    def test_messages_persisted_total_accepts_type_label(self):
        """messages_persisted_total should accept a type label."""
        from app.infrastructure.metrics import messages_persisted_total

        child = messages_persisted_total.labels(type="room")
        assert child is not None

    def test_auth_service_calls_total_accepts_status_label(self):
        """auth_service_calls_total should accept a status label."""
        from app.infrastructure.metrics import auth_service_calls_total

        child = auth_service_calls_total.labels(status="success")
        assert child is not None

    def test_kafka_consume_duration_seconds_accepts_topic_label(self):
        """kafka_consume_duration_seconds should accept a topic label."""
        from app.infrastructure.metrics import kafka_consume_duration_seconds

        child = kafka_consume_duration_seconds.labels(topic="test-topic")
        assert child is not None
