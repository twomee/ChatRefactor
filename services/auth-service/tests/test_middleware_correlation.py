# tests/test_middleware_correlation.py — Unit tests for app/middleware/correlation.py
"""
Tests for:
- CorrelationIdMiddleware generates a UUID when X-Request-ID is missing
- CorrelationIdMiddleware propagates the X-Request-ID header from the request
- Response includes the X-Request-ID header
"""


class TestCorrelationIdMiddleware:
    """Tests for the CorrelationIdMiddleware."""

    def test_generates_correlation_id_when_missing(self, client):
        """When no X-Request-ID header is sent, the middleware should generate one."""
        resp = client.get("/health")
        assert resp.status_code == 200
        # The response must include an X-Request-ID header
        assert "x-request-id" in resp.headers
        # It should be a non-empty string (UUID format)
        assert len(resp.headers["x-request-id"]) > 0

    def test_propagates_provided_correlation_id(self, client):
        """When X-Request-ID is provided, the middleware should echo it back."""
        custom_id = "test-correlation-id-12345"
        resp = client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.status_code == 200
        assert resp.headers["x-request-id"] == custom_id

    def test_different_requests_get_different_ids(self, client):
        """Two requests without X-Request-ID should get different generated IDs."""
        resp1 = client.get("/health")
        resp2 = client.get("/health")
        id1 = resp1.headers["x-request-id"]
        id2 = resp2.headers["x-request-id"]
        assert id1 != id2
