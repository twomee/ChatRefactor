"""Frontend loading tests."""

import pytest
import requests

from conftest import auth_header


class TestFrontend:
    """Verify the frontend is served through Kong."""

    @pytest.mark.smoke
    def test_frontend_returns_200(self, api: requests.Session, kong_url: str):
        resp = api.get(f"{kong_url}/")
        assert resp.status_code == 200

    @pytest.mark.smoke
    def test_frontend_returns_html(self, api: requests.Session, kong_url: str):
        resp = api.get(f"{kong_url}/")
        body = resp.text.lower()
        assert "<!doctype" in body or "<html" in body
