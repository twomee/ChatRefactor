# tests/test_url_preview_service.py — Tests for URL preview (link unfurling) service
#
# Covers:
#   - extract_urls: finds URLs, deduplicates, limits to 5, handles edge cases
#   - MetadataParser: parses OG tags, fallback to <title>, handles missing data
#   - fetch_preview: mocks httpx to test HTML parsing end-to-end
#   - SSRF protection: blocks private IPs, cloud metadata endpoints
#   - Redis caching: get/set/miss caching behavior
#   - API endpoint: returns preview, handles invalid URL, requires auth
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.url_preview_service import (
    CACHE_TTL,
    NEGATIVE_CACHE_TTL,
    MetadataParser,
    _cache_key,
    _is_url_safe,
    _sanitize,
    _sanitize_url,
    cache_preview,
    extract_urls,
    fetch_preview,
    get_cached_preview,
)


# ══════════════════════════════════════════════════════════════════════
# extract_urls
# ══════════════════════════════════════════════════════════════════════


class TestExtractUrls:
    """Tests for URL extraction from message text."""

    def test_extracts_single_url(self):
        text = "Check out https://example.com for more info"
        assert extract_urls(text) == ["https://example.com"]

    def test_extracts_multiple_urls(self):
        text = "Visit https://foo.com and http://bar.org/page"
        urls = extract_urls(text)
        assert len(urls) == 2
        assert urls[0] == "https://foo.com"
        assert urls[1] == "http://bar.org/page"

    def test_deduplicates_urls(self):
        text = "https://example.com is great https://example.com really"
        assert extract_urls(text) == ["https://example.com"]

    def test_limits_to_five_urls(self):
        urls_text = " ".join(f"https://site{i}.com" for i in range(10))
        result = extract_urls(urls_text)
        assert len(result) == 5

    def test_returns_empty_for_no_urls(self):
        assert extract_urls("Hello, no links here!") == []

    def test_returns_empty_for_empty_string(self):
        assert extract_urls("") == []

    def test_ignores_non_http_schemes(self):
        text = "ftp://files.example.com and mailto:x@y.com"
        assert extract_urls(text) == []

    def test_handles_url_with_path_and_query(self):
        text = "See https://example.com/path?q=1&r=2#section for details"
        urls = extract_urls(text)
        assert len(urls) == 1
        assert urls[0].startswith("https://example.com/path?q=1&r=2#section")

    def test_preserves_insertion_order(self):
        text = "https://z.com https://a.com https://m.com"
        assert extract_urls(text) == ["https://z.com", "https://a.com", "https://m.com"]


# ══════════════════════════════════════════════════════════════════════
# MetadataParser
# ══════════════════════════════════════════════════════════════════════


class TestMetadataParser:
    """Tests for Open Graph / meta tag parsing from HTML."""

    def test_parses_og_title(self):
        html = '<html><head><meta property="og:title" content="My Page"></head></html>'
        parser = MetadataParser()
        parser.feed(html)
        assert parser.title == "My Page"

    def test_parses_og_description(self):
        html = '<html><head><meta property="og:description" content="A description"></head></html>'
        parser = MetadataParser()
        parser.feed(html)
        assert parser.description == "A description"

    def test_parses_og_image(self):
        html = '<html><head><meta property="og:image" content="https://img.example.com/pic.jpg"></head></html>'
        parser = MetadataParser()
        parser.feed(html)
        assert parser.image == "https://img.example.com/pic.jpg"

    def test_falls_back_to_title_tag(self):
        html = "<html><head><title>Fallback Title</title></head></html>"
        parser = MetadataParser()
        parser.feed(html)
        assert parser.title == "Fallback Title"

    def test_og_title_takes_priority_over_title_tag(self):
        html = '<html><head><title>Tag Title</title><meta property="og:title" content="OG Title"></head></html>'
        parser = MetadataParser()
        parser.feed(html)
        assert parser.title == "OG Title"

    def test_falls_back_to_meta_description(self):
        html = '<html><head><meta name="description" content="Meta desc"></head></html>'
        parser = MetadataParser()
        parser.feed(html)
        assert parser.description == "Meta desc"

    def test_og_description_takes_priority(self):
        html = (
            '<html><head>'
            '<meta name="description" content="Meta desc">'
            '<meta property="og:description" content="OG desc">'
            '</head></html>'
        )
        parser = MetadataParser()
        parser.feed(html)
        assert parser.description == "OG desc"

    def test_stops_at_body_tag(self):
        html = (
            "<html><head><title>Head Title</title></head>"
            '<body><meta property="og:title" content="Body OG"></body></html>'
        )
        parser = MetadataParser()
        parser.feed(html)
        assert parser.title == "Head Title"

    def test_handles_empty_html(self):
        parser = MetadataParser()
        parser.feed("")
        assert parser.title == ""
        assert parser.description == ""
        assert parser.image == ""

    def test_handles_html_with_no_meta_tags(self):
        html = "<html><head></head><body><p>Hello</p></body></html>"
        parser = MetadataParser()
        parser.feed(html)
        assert parser.title == ""
        assert parser.description == ""


# ══════════════════════════════════════════════════════════════════════
# _sanitize
# ══════════════════════════════════════════════════════════════════════


class TestSanitize:
    """Tests for output sanitization."""

    def test_strips_whitespace(self):
        assert _sanitize("  hello  ", 100) == "hello"

    def test_escapes_html_entities(self):
        assert _sanitize('<script>alert("xss")</script>', 200) == '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'

    def test_truncates_to_max_len(self):
        result = _sanitize("a" * 300, 200)
        assert len(result) == 200

    def test_returns_none_for_empty_string(self):
        assert _sanitize("", 100) is None

    def test_returns_none_for_whitespace_only(self):
        assert _sanitize("   ", 100) is None


# ══════════════════════════════════════════════════════════════════════
# _sanitize_url
# ══════════════════════════════════════════════════════════════════════


class TestSanitizeUrl:
    """Tests for URL-specific sanitization that enforces http/https scheme."""

    def test_accepts_https_url(self):
        assert _sanitize_url("https://img.example.com/pic.jpg", 1000) == "https://img.example.com/pic.jpg"

    def test_accepts_http_url(self):
        assert _sanitize_url("http://img.example.com/pic.jpg", 1000) == "http://img.example.com/pic.jpg"

    def test_rejects_javascript_scheme(self):
        assert _sanitize_url("javascript:alert(1)", 1000) is None

    def test_rejects_data_scheme(self):
        assert _sanitize_url("data:image/png;base64,abc123", 1000) is None

    def test_rejects_empty_string(self):
        assert _sanitize_url("", 1000) is None

    def test_returns_none_for_none_input(self):
        assert _sanitize_url(None, 1000) is None

    def test_truncates_to_max_len(self):
        long_url = "https://example.com/" + "a" * 2000
        result = _sanitize_url(long_url, 1000)
        assert result is not None
        assert len(result) == 1000

    def test_strips_leading_whitespace(self):
        assert _sanitize_url("  https://example.com/img.jpg", 1000) == "https://example.com/img.jpg"


# ══════════════════════════════════════════════════════════════════════
# _cache_key
# ══════════════════════════════════════════════════════════════════════


class TestCacheKey:
    """Tests for the SHA-256 cache key helper."""

    def test_returns_prefixed_hash(self):
        url = "https://example.com"
        expected_hash = hashlib.sha256(url.encode()).hexdigest()
        assert _cache_key(url) == f"preview:{expected_hash}"

    def test_different_urls_produce_different_keys(self):
        assert _cache_key("https://a.com") != _cache_key("https://b.com")

    def test_same_url_produces_same_key(self):
        url = "https://example.com/path?q=1"
        assert _cache_key(url) == _cache_key(url)

    def test_url_with_newline_is_safely_hashed(self):
        # A crafted URL with a newline would break a raw-string key but is safe when hashed
        url = "https://example.com\npreview:injected"
        key = _cache_key(url)
        assert key.startswith("preview:")
        assert "\n" not in key


# ══════════════════════════════════════════════════════════════════════
# SSRF protection
# ══════════════════════════════════════════════════════════════════════


class TestSSRFProtection:
    """Tests for SSRF protection — blocking internal/private IP fetches.

    _is_url_safe is now async (DNS resolution runs in a thread executor
    to avoid blocking the event loop), so all tests are async.
    """

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service.socket.getaddrinfo")
    async def test_blocks_localhost(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("127.0.0.1", 80)),
        ]
        assert await _is_url_safe("http://localhost/admin") is False

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service.socket.getaddrinfo")
    async def test_blocks_private_10_network(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("10.0.0.1", 80)),
        ]
        assert await _is_url_safe("http://internal.corp/secret") is False

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service.socket.getaddrinfo")
    async def test_blocks_private_192_168_network(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("192.168.1.100", 80)),
        ]
        assert await _is_url_safe("http://router.local") is False

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service.socket.getaddrinfo")
    async def test_blocks_private_172_16_network(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("172.16.0.1", 80)),
        ]
        assert await _is_url_safe("http://k8s-service.internal") is False

    @pytest.mark.asyncio
    async def test_blocks_cloud_metadata_hostname(self):
        assert await _is_url_safe("http://169.254.169.254/latest/meta-data/") is False

    @pytest.mark.asyncio
    async def test_blocks_google_metadata_hostname(self):
        assert await _is_url_safe("http://metadata.google.internal/computeMetadata/v1/") is False

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service.socket.getaddrinfo")
    async def test_allows_public_ip(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 80)),
        ]
        assert await _is_url_safe("https://example.com") is True

    @pytest.mark.asyncio
    async def test_returns_false_for_invalid_url(self):
        assert await _is_url_safe("not-a-url") is False

    @pytest.mark.asyncio
    async def test_returns_false_for_dns_failure(self):
        # This domain should not resolve
        assert await _is_url_safe("http://this-domain-definitely-does-not-exist-qwerty12345.com") is False


# ══════════════════════════════════════════════════════════════════════
# fetch_preview (with mocked httpx)
# ══════════════════════════════════════════════════════════════════════


class TestFetchPreview:
    """Tests for the async preview fetcher with mocked HTTP calls."""

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_successful_fetch(self, mock_client_cls, mock_safe):
        html = (
            '<html><head>'
            '<meta property="og:title" content="Test Title">'
            '<meta property="og:description" content="Test Description">'
            '<meta property="og:image" content="https://img.example.com/pic.jpg">'
            '</head><body></body></html>'
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.text = html

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_preview("https://example.com")

        assert result is not None
        assert result["url"] == "https://example.com"
        assert result["title"] == "Test Title"
        assert result["description"] == "Test Description"
        assert result["image"] == "https://img.example.com/pic.jpg"

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_returns_none_for_non_html(self, mock_client_cls, mock_safe):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"key": "value"}'

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_preview("https://api.example.com/data")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_returns_none_for_non_200(self, mock_client_cls, mock_safe):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {"content-type": "text/html"}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_preview("https://example.com/missing")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_returns_none_for_redirect(self, mock_client_cls, mock_safe):
        """A redirect response must be refused to prevent SSRF bypass."""
        for redirect_code in (301, 302, 303, 307, 308):
            mock_response = MagicMock()
            mock_response.status_code = redirect_code
            mock_response.headers = {"location": "http://169.254.169.254/"}

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_preview("https://example.com/redirect")
            assert result is None, f"Expected None for redirect {redirect_code}"

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_returns_none_for_no_metadata(self, mock_client_cls, mock_safe):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><head></head><body><p>No meta</p></body></html>"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_preview("https://example.com/bare")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=False)
    async def test_returns_none_for_unsafe_url(self, mock_safe):
        result = await fetch_preview("http://169.254.169.254/meta-data")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_sanitizes_html_in_title(self, mock_client_cls, mock_safe):
        html = '<html><head><title><b>Bold</b> &amp; Title</title></head><body></body></html>'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_preview("https://example.com")
        assert result is not None
        # The parser extracts text content from <title> which includes "Bold"
        # then _sanitize escapes any remaining HTML
        assert "<b>" not in (result["title"] or "")

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_rejects_javascript_og_image(self, mock_client_cls, mock_safe):
        """og:image with javascript: scheme must be stripped."""
        html = (
            '<html><head>'
            '<meta property="og:title" content="XSS Test">'
            '<meta property="og:image" content="javascript:alert(1)">'
            '</head><body></body></html>'
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_preview("https://example.com")
        assert result is not None
        assert result["image"] is None

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_returns_none_on_timeout(self, mock_client_cls, mock_safe):
        """A TimeoutException from httpx must be caught and return None (lines 243-245)."""
        import httpx

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_preview("https://slow.example.com")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_returns_none_on_request_error(self, mock_client_cls, mock_safe):
        """A RequestError from httpx must be caught and return None (lines 246-248)."""
        import httpx

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_preview("https://unreachable.example.com")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.url_preview_service._is_url_safe", new_callable=AsyncMock, return_value=True)
    @patch("app.services.url_preview_service.httpx.AsyncClient")
    async def test_returns_none_on_unexpected_exception(self, mock_client_cls, mock_safe):
        """Any unexpected exception must be caught and return None (lines 249-251)."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = RuntimeError("unexpected failure")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_preview("https://buggy.example.com")
        assert result is None


# ══════════════════════════════════════════════════════════════════════
# Redis caching
# ══════════════════════════════════════════════════════════════════════


class TestRedisCache:
    """Tests for Redis-based preview caching.

    Cache keys are now SHA-256 hashes of the URL to prevent key injection.
    """

    @pytest.mark.asyncio
    async def test_get_cached_preview_returns_data(self):
        mock_redis = AsyncMock()
        data = {"url": "https://x.com", "title": "X", "description": None, "image": None}
        mock_redis.get.return_value = json.dumps(data)

        result = await get_cached_preview(mock_redis, "https://x.com")
        assert result == data
        expected_key = _cache_key("https://x.com")
        mock_redis.get.assert_called_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_get_cached_preview_returns_none_on_miss(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        result = await get_cached_preview(mock_redis, "https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_preview_returns_none_when_no_redis(self):
        result = await get_cached_preview(None, "https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_preview_stores_data(self):
        mock_redis = AsyncMock()
        data = {"url": "https://x.com", "title": "X", "description": None, "image": None}

        await cache_preview(mock_redis, "https://x.com", data)
        expected_key = _cache_key("https://x.com")
        mock_redis.setex.assert_called_once_with(
            expected_key, CACHE_TTL, json.dumps(data)
        )

    @pytest.mark.asyncio
    async def test_cache_preview_stores_negative_result(self):
        mock_redis = AsyncMock()

        await cache_preview(mock_redis, "https://bad.com", None)
        expected_key = _cache_key("https://bad.com")
        mock_redis.setex.assert_called_once_with(
            expected_key,
            NEGATIVE_CACHE_TTL,
            json.dumps({"_miss": True}),
        )

    @pytest.mark.asyncio
    async def test_cache_preview_noop_when_no_redis(self):
        # Should not raise
        await cache_preview(None, "https://x.com", {"url": "https://x.com"})

    @pytest.mark.asyncio
    async def test_get_cached_preview_handles_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis down")

        result = await get_cached_preview(mock_redis, "https://x.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_preview_handles_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = Exception("Redis down")

        # Should not raise
        await cache_preview(mock_redis, "https://x.com", {"url": "https://x.com"})


# ══════════════════════════════════════════════════════════════════════
# API endpoint (via TestClient)
# ══════════════════════════════════════════════════════════════════════


class TestPreviewEndpoint:
    """Tests for GET /messages/preview API endpoint."""

    def test_returns_preview_for_valid_url(self, client, auth_headers):
        preview_data = {
            "url": "https://example.com",
            "title": "Example",
            "description": "An example site",
            "image": None,
        }
        with (
            patch("app.routers.messages.get_redis", return_value=None),
            patch("app.routers.messages.get_cached_preview", new_callable=AsyncMock, return_value=None),
            patch("app.routers.messages.fetch_preview", new_callable=AsyncMock, return_value=preview_data),
            patch("app.routers.messages.cache_preview", new_callable=AsyncMock),
        ):
            response = client.get(
                "/messages/preview?url=https://example.com",
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "Example"
            assert data["url"] == "https://example.com"

    def test_returns_cached_preview(self, client, auth_headers):
        cached_data = {
            "url": "https://cached.com",
            "title": "Cached",
            "description": "From cache",
            "image": None,
        }
        with (
            patch("app.routers.messages.get_redis", return_value=MagicMock()),
            patch("app.routers.messages.get_cached_preview", new_callable=AsyncMock, return_value=cached_data),
        ):
            response = client.get(
                "/messages/preview?url=https://cached.com",
                headers=auth_headers,
            )
            assert response.status_code == 200
            assert response.json()["title"] == "Cached"

    def test_returns_404_for_cached_miss(self, client, auth_headers):
        with (
            patch("app.routers.messages.get_redis", return_value=MagicMock()),
            patch("app.routers.messages.get_cached_preview", new_callable=AsyncMock, return_value={"_miss": True}),
        ):
            response = client.get(
                "/messages/preview?url=https://bad.com",
                headers=auth_headers,
            )
            assert response.status_code == 404

    def test_rejects_invalid_url_scheme(self, client, auth_headers):
        response = client.get(
            "/messages/preview?url=ftp://files.example.com",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Invalid URL" in response.json()["detail"]

    def test_rejects_missing_url(self, client, auth_headers):
        response = client.get("/messages/preview", headers=auth_headers)
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client.get("/messages/preview?url=https://example.com")
        assert response.status_code == 401

    def test_returns_404_when_fetch_fails(self, client, auth_headers):
        with (
            patch("app.routers.messages.get_redis", return_value=None),
            patch("app.routers.messages.get_cached_preview", new_callable=AsyncMock, return_value=None),
            patch("app.routers.messages.fetch_preview", new_callable=AsyncMock, return_value=None),
            patch("app.routers.messages.cache_preview", new_callable=AsyncMock),
        ):
            response = client.get(
                "/messages/preview?url=https://nonexistent.example.com",
                headers=auth_headers,
            )
            assert response.status_code == 404
