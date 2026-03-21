# middleware/security_headers.py — Security headers for all HTTP responses
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import APP_ENV


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses.
    These headers defend against clickjacking, MIME sniffing, and XSS."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        # Prevent browser from MIME-sniffing content type
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent page from being embedded in iframes (clickjacking defense)
        response.headers["X-Frame-Options"] = "DENY"
        # Disable the XSS auditor (modern browsers) — CSP is the real defense
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Prevent referrer leaks
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Only allow HTTPS connections in production
        if APP_ENV == "prod":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
