"""File service tests — upload, download, list, PM files, image handling."""

import os
import tempfile

import pytest
import requests

from conftest import auth_header


@pytest.fixture(scope="module")
def uploaded_file(api, kong_url: str, user1: dict, test_room: dict):
    """Upload a test file and return its metadata."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"E2E test file content for file service tests")
        tmp_path = f.name

    try:
        with open(tmp_path, "rb") as f:
            resp = api.post(
                f"{kong_url}/files/upload?room_id={test_room['id']}",
                files={"file": ("e2e-test.txt", f, "text/plain")},
                headers={"Authorization": f"Bearer {user1['token']}"},
            )
        assert resp.status_code == 201
        return resp.json()
    finally:
        os.unlink(tmp_path)


class TestFileUploadDownload:
    """Core file operations."""

    @pytest.mark.smoke
    def test_upload_file_to_room(self, uploaded_file: dict):
        assert "id" in uploaded_file
        assert uploaded_file["originalName"] == "e2e-test.txt"
        assert uploaded_file["isPrivate"] is False

    @pytest.mark.smoke
    def test_list_room_files(self, api: requests.Session, kong_url: str, user1: dict, test_room: dict, uploaded_file: dict):
        resp = api.get(
            f"{kong_url}/files/room/{test_room['id']}",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        files = resp.json()
        names = [f["originalName"] for f in files]
        assert "e2e-test.txt" in names

    @pytest.mark.smoke
    def test_download_file(self, api: requests.Session, kong_url: str, user1: dict, uploaded_file: dict):
        resp = api.get(
            f"{kong_url}/files/download/{uploaded_file['id']}",
            headers=auth_header(user1["token"]),
        )
        assert resp.status_code == 200
        assert b"E2E test file content" in resp.content

    def test_upload_without_auth(self, api: requests.Session, kong_url: str, test_room: dict):
        with tempfile.NamedTemporaryFile(suffix=".txt") as f:
            f.write(b"no auth")
            f.seek(0)
            resp = requests.post(
                f"{kong_url}/files/upload?room_id={test_room['id']}",
                files={"file": ("noauth.txt", f, "text/plain")},
            )
        assert resp.status_code == 401


class TestPMFiles:
    """PM file upload and access."""

    def test_upload_pm_file(self, api: requests.Session, kong_url: str, user1: dict, user2: dict):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"PM file content")
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as f:
                resp = api.post(
                    f"{kong_url}/files/upload?recipient={user2['username']}",
                    files={"file": ("pm-file.txt", f, "text/plain")},
                    headers={"Authorization": f"Bearer {user1['token']}"},
                )
            assert resp.status_code == 201
            data = resp.json()
            assert data["isPrivate"] is True
            self.__class__._pm_file_id = data["id"]
        finally:
            os.unlink(tmp_path)

    def test_download_pm_file_by_recipient(self, api: requests.Session, kong_url: str, user2: dict):
        file_id = getattr(self.__class__, "_pm_file_id", None)
        if file_id is None:
            pytest.skip("Depends on test_upload_pm_file")
        resp = api.get(
            f"{kong_url}/files/download/{file_id}",
            headers=auth_header(user2["token"]),
        )
        assert resp.status_code == 200
        assert b"PM file content" in resp.content

    def test_download_pm_file_forbidden_for_others(self, api: requests.Session, kong_url: str, user3: dict):
        file_id = getattr(self.__class__, "_pm_file_id", None)
        if file_id is None:
            pytest.skip("Depends on test_upload_pm_file")
        resp = api.get(
            f"{kong_url}/files/download/{file_id}",
            headers=auth_header(user3["token"]),
        )
        assert resp.status_code == 403


class TestImageUpload:
    """Image upload returns proper metadata for rendering."""

    def test_upload_image(self, api: requests.Session, kong_url: str, user1: dict, test_room: dict):
        png_header = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
            b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_header)
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as f:
                resp = api.post(
                    f"{kong_url}/files/upload?room_id={test_room['id']}",
                    files={"file": ("test-image.png", f, "image/png")},
                    headers={"Authorization": f"Bearer {user1['token']}"},
                )
            assert resp.status_code == 201
            data = resp.json()
            assert data["originalName"] == "test-image.png"

            resp = api.get(
                f"{kong_url}/files/download/{data['id']}",
                headers=auth_header(user1["token"]),
            )
            assert resp.status_code == 200
            assert "image/png" in resp.headers.get("Content-Type", "")
        finally:
            os.unlink(tmp_path)

    def test_upload_invalid_file_type(self, api: requests.Session, kong_url: str, user1: dict, test_room: dict):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(b"MZ\x90\x00")
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as f:
                resp = api.post(
                    f"{kong_url}/files/upload?room_id={test_room['id']}",
                    files={"file": ("malware.exe", f, "application/octet-stream")},
                    headers={"Authorization": f"Bearer {user1['token']}"},
                )
            assert resp.status_code == 400
        finally:
            os.unlink(tmp_path)
