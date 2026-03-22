# app/middleware/correlation.py — Correlation ID middleware for request tracing
"""
Reads the X-Request-ID header (set by Kong or upstream callers), binds it to the
structlog context so every log line includes the correlation ID, and adds it to the
response headers for downstream tracing.

If no X-Request-ID is provided, generates a new UUID. This ensures every request
has a traceable ID even when called directly (not through Kong).
"""
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extracts or generates a correlation ID and binds it to structured logging."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Read correlation ID from header, or generate a new one
        correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Bind to structlog context so all log lines in this request include it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        response = await call_next(request)

        # Echo the correlation ID back in the response headers
        response.headers["X-Request-ID"] = correlation_id

        return response
