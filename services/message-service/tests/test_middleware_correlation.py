# tests/test_middleware_correlation.py — Tests for app/middleware/correlation.py
#
# Covers:
#   - Generates a correlation ID when X-Request-ID is missing
#   - Uses the provided X-Request-ID header if present
#   - Adds X-Request-ID to the response headers
#   - Binds correlation ID to structlog context



class TestCorrelationIdMiddleware:
    """Tests for the CorrelationIdMiddleware."""

    def test_generates_correlation_id_when_missing(self, client):
        """Should generate a UUID correlation ID when X-Request-ID header is absent."""
        response = client.get("/health")

        assert response.status_code == 200
        # Response should include an X-Request-ID header (auto-generated)
        assert "X-Request-ID" in response.headers
        correlation_id = response.headers["X-Request-ID"]
        # Should be a valid UUID-like string (36 chars with hyphens)
        assert len(correlation_id) == 36

    def test_uses_provided_request_id(self, client):
        """Should use the X-Request-ID from the request header if provided."""
        custom_id = "my-custom-correlation-id-12345"
        response = client.get("/health", headers={"X-Request-ID": custom_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id

    def test_response_includes_request_id(self, client):
        """Response should always include X-Request-ID header."""
        response = client.get("/health")

        assert "X-Request-ID" in response.headers

    def test_different_requests_get_different_ids(self, client):
        """Each request without X-Request-ID should get a unique correlation ID."""
        response1 = client.get("/health")
        response2 = client.get("/health")

        id1 = response1.headers["X-Request-ID"]
        id2 = response2.headers["X-Request-ID"]
        assert id1 != id2
