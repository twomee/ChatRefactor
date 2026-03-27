# tests/test_infrastructure_metrics.py — Tests for app/infrastructure/metrics.py
#
# Covers:
#   - /metrics endpoint returns 200 with Prometheus text format content-type
#   - /metrics response contains expected metric names
#   - Business metrics increment correctly after register/login
#   - The metrics module defines all expected counters and gauges (import test)
from prometheus_client import Counter, Gauge


class TestMetricsModuleDefinitions:
    """Verify that all expected metrics are defined with correct types."""

    def test_auth_registrations_total_is_counter(self):
        """auth_registrations_total should be a Counter with status label."""
        from app.infrastructure.metrics import auth_registrations_total

        assert isinstance(auth_registrations_total, Counter)
        # prometheus_client strips _total suffix internally; it is added on output
        assert auth_registrations_total._name == "auth_registrations"

    def test_auth_logins_total_is_counter(self):
        """auth_logins_total should be a Counter with status label."""
        from app.infrastructure.metrics import auth_logins_total

        assert isinstance(auth_logins_total, Counter)
        assert auth_logins_total._name == "auth_logins"

    def test_auth_logouts_total_is_counter(self):
        """auth_logouts_total should be a Counter with status label."""
        from app.infrastructure.metrics import auth_logouts_total

        assert isinstance(auth_logouts_total, Counter)
        assert auth_logouts_total._name == "auth_logouts"

    def test_kafka_events_produced_total_is_counter(self):
        """kafka_events_produced_total should be a Counter with topic and status labels."""
        from app.infrastructure.metrics import kafka_events_produced_total

        assert isinstance(kafka_events_produced_total, Counter)
        assert kafka_events_produced_total._name == "kafka_events_produced"

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

    def test_db_pool_overflow_is_gauge(self):
        """db_pool_overflow should be a Gauge."""
        from app.infrastructure.metrics import db_pool_overflow

        assert isinstance(db_pool_overflow, Gauge)
        assert db_pool_overflow._name == "db_pool_overflow"


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
        assert "text/plain" in content_type or "text/plain" in content_type

    def test_metrics_contains_http_requests_total(self, client):
        """/metrics should contain http_requests_total from the instrumentator."""
        resp = client.get("/metrics")
        body = resp.text
        assert "http_requests_total" in body or "http_request_duration" in body

    def test_metrics_contains_auth_registrations_total(self, client):
        """/metrics should contain auth_registrations_total."""
        resp = client.get("/metrics")
        body = resp.text
        assert "auth_registrations_total" in body

    def test_metrics_contains_auth_logins_total(self, client):
        """/metrics should contain auth_logins_total."""
        resp = client.get("/metrics")
        body = resp.text
        assert "auth_logins_total" in body

    def test_metrics_contains_auth_logouts_total(self, client):
        """/metrics should contain auth_logouts_total."""
        resp = client.get("/metrics")
        body = resp.text
        assert "auth_logouts_total" in body

    def test_metrics_contains_kafka_events_produced_total(self, client):
        """/metrics should contain kafka_events_produced_total."""
        resp = client.get("/metrics")
        body = resp.text
        assert "kafka_events_produced_total" in body

    def test_metrics_contains_db_pool_gauges(self, client):
        """/metrics should contain db_pool_size, db_pool_checked_out, db_pool_overflow."""
        resp = client.get("/metrics")
        body = resp.text
        assert "db_pool_size" in body
        assert "db_pool_checked_out" in body
        assert "db_pool_overflow" in body


class TestRegistrationMetrics:
    """Verify that registration increments auth_registrations_total."""

    def test_successful_registration_increments_metric(self, client):
        """After a successful registration, auth_registrations_total{status='success'} should increase."""
        # Capture the metric value before registration
        resp_before = client.get("/metrics")
        before_text = resp_before.text

        # Find current value of auth_registrations_total with status=success
        before_count = _extract_metric_value(
            before_text, 'auth_registrations_total{status="success"}'
        )

        # Register a new user
        resp = client.post(
            "/auth/register",
            json={"username": "metrics_test_user", "password": "StrongP@ss123"},
        )
        assert resp.status_code == 201

        # Check the metric incremented
        resp_after = client.get("/metrics")
        after_count = _extract_metric_value(
            resp_after.text, 'auth_registrations_total{status="success"}'
        )

        assert after_count == before_count + 1.0

    def test_duplicate_registration_increments_duplicate_metric(self, client):
        """Registering a duplicate username should increment status=duplicate."""
        # Register first
        client.post(
            "/auth/register",
            json={"username": "dup_metrics_user", "password": "StrongP@ss123"},
        )

        # Capture before
        resp_before = client.get("/metrics")
        before_count = _extract_metric_value(
            resp_before.text, 'auth_registrations_total{status="duplicate"}'
        )

        # Attempt duplicate registration
        resp = client.post(
            "/auth/register",
            json={"username": "dup_metrics_user", "password": "StrongP@ss123"},
        )
        assert resp.status_code == 409

        # Check metric incremented
        resp_after = client.get("/metrics")
        after_count = _extract_metric_value(
            resp_after.text, 'auth_registrations_total{status="duplicate"}'
        )

        assert after_count == before_count + 1.0


class TestLoginMetrics:
    """Verify that login increments auth_logins_total."""

    def test_successful_login_increments_metric(self, client):
        """After a successful login, auth_logins_total{status='success'} should increase."""
        # Register a user first
        client.post(
            "/auth/register",
            json={"username": "login_metrics_user", "password": "StrongP@ss123"},
        )

        # Capture before
        resp_before = client.get("/metrics")
        before_count = _extract_metric_value(
            resp_before.text, 'auth_logins_total{status="success"}'
        )

        # Login
        resp = client.post(
            "/auth/login",
            json={"username": "login_metrics_user", "password": "StrongP@ss123"},
        )
        assert resp.status_code == 200

        # Check metric incremented
        resp_after = client.get("/metrics")
        after_count = _extract_metric_value(
            resp_after.text, 'auth_logins_total{status="success"}'
        )

        assert after_count == before_count + 1.0

    def test_failed_login_increments_invalid_credentials_metric(self, client):
        """A failed login should increment auth_logins_total{status='invalid_credentials'}."""
        # Capture before
        resp_before = client.get("/metrics")
        before_count = _extract_metric_value(
            resp_before.text, 'auth_logins_total{status="invalid_credentials"}'
        )

        # Attempt login with wrong password
        resp = client.post(
            "/auth/login",
            json={"username": "nonexistent_user", "password": "wrong"},
        )
        assert resp.status_code == 401

        # Check metric incremented
        resp_after = client.get("/metrics")
        after_count = _extract_metric_value(
            resp_after.text, 'auth_logins_total{status="invalid_credentials"}'
        )

        assert after_count == before_count + 1.0


# ── Helpers ──────────────────────────────────────────────────────────


def _extract_metric_value(metrics_text: str, metric_line_prefix: str) -> float:
    """Extract a numeric value from Prometheus text format for a given metric line.

    Searches for a line starting with the given prefix and returns its float value.
    Returns 0.0 if the metric line is not found (metric not yet reported).

    Example line: auth_registrations_total{status="success"} 3.0
    """
    for line in metrics_text.splitlines():
        if line.startswith(metric_line_prefix):
            # The value is the last space-separated token on the line
            parts = line.rsplit(" ", 1)
            if len(parts) == 2:
                return float(parts[1])
    return 0.0
