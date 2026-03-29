# app/services/url_preview_service.py — URL preview / link unfurling service
#
# Extracts URLs from message text, fetches HTML, and parses Open Graph metadata
# for rendering link preview cards in the frontend.
#
# Security considerations:
# - Only http/https URLs are accepted
# - SSRF protection: private/internal IPs are blocked before fetching
# - DNS pinning: the resolved IP is used for the actual HTTP request, closing
#   the DNS rebinding window between the SSRF check and the fetch
# - For HTTPS, the original hostname is forwarded as TLS SNI so certificate
#   validation still works against the domain name, not the raw IP
# - Redirects are refused to prevent SSRF bypass via open-redirect chains
# - Response size capped at 500KB to prevent memory exhaustion
# - 5-second timeout to prevent slow-loris style hangs
# - All extracted text is stripped of HTML to prevent XSS
# - og:image URL is scheme-validated to prevent javascript:/data: injection
# - Cache keys are SHA-256 hashed to prevent key injection via crafted URLs
import asyncio
import hashlib
import ipaddress
import json
import re
import socket
from html import escape as html_escape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from app.core.logging import get_logger

logger = get_logger("services.url_preview")

URL_REGEX = re.compile(r"https?://[^\s<>\"{}|\\^`\[\]]+")
MAX_FETCH_SIZE = 500_000  # 500KB max response
FETCH_TIMEOUT = 5.0  # seconds

# ── SSRF Protection ──────────────────────────────────────────────────────

# Private/reserved IP ranges that should never be fetched (SSRF prevention).
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),  # NOSONAR — intentional SSRF blocklist
    ipaddress.ip_network("10.0.0.0/8"),  # NOSONAR
    ipaddress.ip_network("100.64.0.0/10"),  # NOSONAR
    ipaddress.ip_network("127.0.0.0/8"),  # NOSONAR
    ipaddress.ip_network("169.254.0.0/16"),  # NOSONAR
    ipaddress.ip_network("172.16.0.0/12"),  # NOSONAR
    ipaddress.ip_network("192.0.0.0/24"),  # NOSONAR
    ipaddress.ip_network("192.0.2.0/24"),  # NOSONAR
    ipaddress.ip_network("192.168.0.0/16"),  # NOSONAR
    ipaddress.ip_network("198.18.0.0/15"),  # NOSONAR
    ipaddress.ip_network("198.51.100.0/24"),  # NOSONAR
    ipaddress.ip_network("203.0.113.0/24"),  # NOSONAR
    ipaddress.ip_network("224.0.0.0/4"),  # NOSONAR
    ipaddress.ip_network("240.0.0.0/4"),  # NOSONAR
    ipaddress.ip_network("255.255.255.255/32"),  # NOSONAR
    # IPv6
    ipaddress.ip_network("::1/128"),  # NOSONAR
    ipaddress.ip_network("fc00::/7"),  # NOSONAR
    ipaddress.ip_network("fe80::/10"),  # NOSONAR
    ipaddress.ip_network("ff00::/8"),  # NOSONAR
]

# Hostnames that must never be resolved (cloud metadata endpoints).
_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.google.com",
        "169.254.169.254",  # NOSONAR — cloud metadata endpoint, intentionally blocked
    }
)


async def _resolve_safe_ip(url: str) -> str | None:
    """Resolve the URL's hostname to a safe public IP and return it.

    Returns the resolved IP address string if the URL is safe to fetch,
    or None if the hostname resolves to a private/internal address
    (SSRF protection) or if DNS resolution fails.

    Returning the IP (rather than a boolean) lets callers use the
    pre-resolved address directly for HTTP connections, closing the DNS
    rebinding window that exists between a safety check and the actual
    request when the original hostname is used.

    DNS resolution is offloaded to a thread via run_in_executor so it
    does not block the async event loop.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return None

        # Block known cloud metadata hostnames outright
        if hostname.lower() in _BLOCKED_HOSTNAMES:
            return None

        # Resolve hostname to IPs off the event loop (socket.getaddrinfo is blocking)
        loop = asyncio.get_event_loop()
        addr_infos = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(
                hostname, parsed.port or 80, proto=socket.IPPROTO_TCP
            ),
        )

        first_safe_ip: str | None = None
        for family, _type, _proto, _canonname, sockaddr in addr_infos:
            ip = ipaddress.ip_address(sockaddr[0])
            for network in _BLOCKED_NETWORKS:
                if ip in network:
                    logger.warning(
                        "ssrf_blocked",
                        url=url,
                        resolved_ip=str(ip),
                        blocked_network=str(network),
                    )
                    return None
            if first_safe_ip is None:
                first_safe_ip = str(ip)

        return first_safe_ip
    except (socket.gaierror, ValueError, OSError):
        # DNS resolution failed or invalid URL — treat as unsafe
        return None


async def _is_url_safe(url: str) -> bool:
    """Return True if the URL targets a public, non-internal address.

    Thin wrapper around _resolve_safe_ip.  Prefer calling _resolve_safe_ip
    directly when you need the resolved IP for DNS-pinned connections.
    """
    return await _resolve_safe_ip(url) is not None


# ── HTML Metadata Parser ─────────────────────────────────────────────────────


class MetadataParser(HTMLParser):
    """Extract Open Graph and basic meta tags from the HTML <head>.

    Stops parsing once <body> is encountered (we don't need body content).
    Prioritizes og: tags over generic meta tags for title and description.
    """

    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.image = ""
        self.in_title = False
        self._done = False

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        attrs_dict = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            prop = attrs_dict.get("property", "") or attrs_dict.get("name", "")
            content = attrs_dict.get("content", "")
            if prop == "og:title":
                self.title = content
            elif prop in ("og:description", "description"):
                # og:description takes priority; only set if not already set by og:
                if prop == "og:description" or not self.description:
                    self.description = content
            elif prop == "og:image":
                self.image = content
        elif tag == "body":
            self._done = True

    def handle_data(self, data):
        if self.in_title and not self.title:
            self.title = data.strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False


# ── Public API ───────────────────────────────────────────────────────────────


def extract_urls(text: str) -> list[str]:
    """Extract unique URLs from message text, capped at 5."""
    return list(dict.fromkeys(URL_REGEX.findall(text)))[:5]


def _sanitize(text: str, max_len: int) -> str | None:
    """Sanitize extracted text: strip whitespace, escape HTML, truncate."""
    cleaned = text.strip()
    if not cleaned:
        return None
    # Escape any HTML entities to prevent XSS
    return html_escape(cleaned)[:max_len]


def _sanitize_url(raw: str | None, max_len: int) -> str | None:
    """Sanitize a URL value extracted from a page's metadata.

    Only http:// and https:// schemes are accepted.  Anything else
    (javascript:, data:, etc.) is rejected outright to prevent XSS.
    """
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned.startswith(
        ("http://", "https://")  # NOSONAR
    ):
        return None
    return cleaned[:max_len]


def _build_connection_url(parsed, safe_ip: str) -> str:
    """Build the DNS-pinned connection URL using the pre-resolved IP address.

    IPv6 literal addresses are wrapped in brackets as required by RFC 2732.
    Fragment is intentionally omitted — it is a client-side-only construct.
    """
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"
    ip_obj = ipaddress.ip_address(safe_ip)
    ip_in_url = f"[{safe_ip}]" if ip_obj.version == 6 else safe_ip
    return f"{parsed.scheme}://{ip_in_url}:{port}{path}"


async def _fetch_html(connection_url: str, hostname: str, parsed_scheme: str) -> str | None:
    """Perform the HTTP request and return raw HTML, or None on failure.

    Refuses 3xx redirects to prevent SSRF-via-open-redirect bypasses.
    Only accepts 200 OK responses with a text/html content type.
    """
    request_extensions: dict = {}
    if parsed_scheme == "https" and hostname:
        # Forward original hostname as TLS SNI so certificate validation works
        # against the domain name rather than the raw IP address.
        request_extensions["sni_hostname"] = hostname.encode("ascii")

    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=FETCH_TIMEOUT,
    ) as client:
        response = await client.get(
            connection_url,
            headers={
                "User-Agent": "cHATBOX-LinkPreview/1.0",
                "Accept": "text/html",
                "Host": hostname,
            },
            extensions=request_extensions,
        )
        # Refuse to follow redirects — the destination is unknown and could
        # point to an internal address that bypassed the SSRF DNS check.
        if response.status_code in (301, 302, 303, 307, 308):
            return None
        if response.status_code != 200:
            return None
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return None
        return response.text[:MAX_FETCH_SIZE]


async def fetch_preview(url: str) -> dict | None:
    """Fetch a URL and extract Open Graph metadata for a link preview card.

    Returns a dict with url, title, description, image — or None on failure.

    DNS pinning: the hostname is resolved once by _resolve_safe_ip() which
    also performs the SSRF blocklist check.  The actual HTTP request uses
    the pre-resolved IP address, not the original hostname, so an attacker
    cannot change the DNS record between the safety check and the fetch
    (DNS rebinding attack).

    For HTTPS, the original hostname is forwarded as the TLS SNI value via
    the ``sni_hostname`` request extension so that certificate validation
    still works against the domain name rather than the raw IP address.

    Redirects are refused: a server returning 3xx is treated as a failure.
    This closes the SSRF-via-open-redirect attack vector where a public domain
    DNS-checks clean but then redirects to an internal address.
    """
    # Resolve hostname to a safe public IP (SSRF check + DNS pinning).
    # safe_ip comes from DNS resolution — it is NOT derived from user input,
    # so the subsequent client.get(connection_url) call is not an SSRF risk.
    safe_ip = await _resolve_safe_ip(url)
    if safe_ip is None:
        return None

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        connection_url = _build_connection_url(parsed, safe_ip)
        html = await _fetch_html(connection_url, hostname, parsed.scheme)
        if html is None:
            return None

        parser = MetadataParser()
        parser.feed(html)

        if not parser.title and not parser.description:
            return None

        return {
            "url": url,  # Return original URL (not IP) so callers see the domain
            "title": _sanitize(parser.title, 200),
            "description": _sanitize(parser.description, 500),
            # Use _sanitize_url (not _sanitize) so javascript:/data: are rejected
            "image": _sanitize_url(parser.image, 1000),
        }
    except httpx.TimeoutException:
        logger.warning("fetch_preview_timeout", url=url)
        return None
    except httpx.RequestError as exc:
        logger.info("fetch_preview_network_error", url=url, error=str(exc))
        return None
    except Exception:
        logger.error("fetch_preview_unexpected_error", url=url, exc_info=True)
        return None


# ── Redis Cache Layer ────────────────────────────────────────────────────────

CACHE_TTL = 3600  # 1 hour
NEGATIVE_CACHE_TTL = 300  # 5 minutes for failed lookups


def _cache_key(url: str) -> str:
    """Return a stable, injection-safe Redis key for a URL.

    Raw URLs as Redis keys can be exploited via crafted URLs containing
    newlines or colons.  Hashing with SHA-256 produces a fixed-length,
    safe alphanumeric key regardless of URL content.
    """
    return f"preview:{hashlib.sha256(url.encode()).hexdigest()}"


async def get_cached_preview(redis_client, url: str) -> dict | None:
    """Return cached preview data for a URL, or None if not cached."""
    if redis_client is None:
        return None
    try:
        key = _cache_key(url)
        cached = await redis_client.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.debug("redis_cache_get_failed", url=url, exc_info=True)
    return None


async def cache_preview(redis_client, url: str, data: dict | None):
    """Cache preview data (or a negative result) in Redis."""
    if redis_client is None:
        return
    try:
        key = _cache_key(url)
        if data is not None:
            await redis_client.setex(key, CACHE_TTL, json.dumps(data))
        else:
            # Cache the miss too, so we don't keep retrying dead URLs
            await redis_client.setex(
                key, NEGATIVE_CACHE_TTL, json.dumps({"_miss": True})
            )
    except Exception:
        logger.debug("redis_cache_set_failed", url=url, exc_info=True)
