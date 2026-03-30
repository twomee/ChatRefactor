# tests/test_routers_auth.py — Integration tests for app/routers/auth.py
"""
Tests for all auth router endpoints:
- POST /auth/register (success, duplicate username, invalid username, short password)
- POST /auth/login (success, wrong password, nonexistent user)
- POST /auth/logout (success, invalid token)
- POST /auth/ping (success)
- GET /auth/users/{id} (success, not found)
- GET /auth/users/by-username/{username} (success, not found)
"""


# -- Registration --------------------------------------------------------------


class TestRegister:
    """Tests for POST /auth/register."""

    def test_register_returns_201(self, client):
        resp = client.post("/auth/register", json={"username": "alice", "password": "password123", "email": "alice@test.com"})
        assert resp.status_code == 201
        assert resp.json()["message"] == "Registered successfully"

    def test_register_duplicate_username_returns_409(self, client):
        client.post("/auth/register", json={"username": "bob", "password": "password123", "email": "bob@test.com"})
        resp = client.post("/auth/register", json={"username": "bob", "password": "otherpass123", "email": "bob2@test.com"})
        assert resp.status_code == 409
        assert "already taken" in resp.json()["detail"]

    def test_register_short_username_returns_422(self, client):
        resp = client.post("/auth/register", json={"username": "ab", "password": "password123", "email": "ab@test.com"})
        assert resp.status_code == 422

    def test_register_invalid_username_chars_returns_422(self, client):
        resp = client.post("/auth/register", json={"username": "user@name!", "password": "password123", "email": "user@test.com"})
        assert resp.status_code == 422

    def test_register_short_password_returns_422(self, client):
        resp = client.post("/auth/register", json={"username": "carol", "password": "short", "email": "carol@test.com"})
        assert resp.status_code == 422

    def test_register_missing_fields_returns_422(self, client):
        resp = client.post("/auth/register", json={"username": "dave"})
        assert resp.status_code == 422

    def test_register_empty_body_returns_422(self, client):
        resp = client.post("/auth/register", json={})
        assert resp.status_code == 422


# -- Login ---------------------------------------------------------------------


class TestLogin:
    """Tests for POST /auth/login."""

    def test_login_returns_token_and_username(self, client):
        client.post("/auth/register", json={"username": "eve", "password": "secretpass1", "email": "eve@test.com"})
        resp = client.post("/auth/login", json={"username": "eve", "password": "secretpass1", "email": "eve@test.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == "eve"
        assert "is_global_admin" in data

    def test_login_regular_user_is_not_admin(self, client):
        client.post("/auth/register", json={"username": "frank", "password": "password123", "email": "frank@test.com"})
        resp = client.post("/auth/login", json={"username": "frank", "password": "password123", "email": "frank@test.com"})
        assert resp.json()["is_global_admin"] is False

    def test_login_wrong_password_returns_401(self, client):
        client.post("/auth/register", json={"username": "grace", "password": "correctpass1", "email": "grace@test.com"})
        resp = client.post("/auth/login", json={"username": "grace", "password": "wrongpass99"})
        assert resp.status_code == 401

    def test_login_nonexistent_user_returns_401(self, client):
        resp = client.post("/auth/login", json={"username": "nobody", "password": "password123"})
        assert resp.status_code == 401

    def test_login_missing_fields_returns_422(self, client):
        resp = client.post("/auth/login", json={"username": "heidi"})
        assert resp.status_code == 422


# -- Logout --------------------------------------------------------------------


class TestLogout:
    """Tests for POST /auth/logout."""

    def test_logout_success(self, client):
        client.post("/auth/register", json={"username": "ivan", "password": "password123", "email": "ivan@test.com"})
        token = client.post("/auth/login", json={"username": "ivan", "password": "password123", "email": "ivan@test.com"}).json()[
            "access_token"
        ]
        resp = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out"

    def test_logout_without_token_returns_401(self, client):
        resp = client.post("/auth/logout")
        assert resp.status_code == 401

    def test_logout_with_invalid_token_returns_401(self, client):
        resp = client.post("/auth/logout", headers={"Authorization": "Bearer not-a-valid-token"})
        assert resp.status_code == 401

    def test_logout_blacklists_token(self, client, mock_redis_instance):
        """After logout, the token should be blacklisted and rejected on subsequent use."""
        client.post("/auth/register", json={"username": "judy", "password": "password123", "email": "judy@test.com"})
        token = client.post("/auth/login", json={"username": "judy", "password": "password123", "email": "judy@test.com"}).json()[
            "access_token"
        ]
        # Logout should blacklist the token
        client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})

        # Verify the token is in the mock Redis blacklist
        assert mock_redis_instance.get(f"blacklist:{token}") is not None


# -- Ping ---------------------------------------------------------------------


class TestPing:
    """Tests for POST /auth/ping."""

    def test_ping_returns_ok(self, client):
        client.post("/auth/register", json={"username": "karl", "password": "password123", "email": "karl@test.com"})
        token = client.post("/auth/login", json={"username": "karl", "password": "password123", "email": "karl@test.com"}).json()[
            "access_token"
        ]
        resp = client.post("/auth/ping", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_ping_without_token_returns_401(self, client):
        resp = client.post("/auth/ping")
        assert resp.status_code == 401


# -- Internal: User lookup by ID ----------------------------------------------


class TestGetUserById:
    """Tests for GET /auth/users/{user_id}."""

    def test_get_user_by_id_success(self, client):
        client.post("/auth/register", json={"username": "luna", "password": "password123", "email": "luna@test.com"})
        # Login to get the user info and find the ID
        token_resp = client.post("/auth/login", json={"username": "luna", "password": "password123", "email": "luna@test.com"})
        # Look up by username first to get the ID
        user_resp = client.get("/auth/users/by-username/luna")
        assert user_resp.status_code == 200
        user_id = user_resp.json()["id"]

        resp = client.get(f"/auth/users/{user_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "luna"
        assert data["id"] == user_id
        assert "is_global_admin" in data
        assert "created_at" in data

    def test_get_user_by_id_not_found(self, client):
        resp = client.get("/auth/users/99999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# -- Internal: User lookup by username -----------------------------------------


class TestGetUserByUsername:
    """Tests for GET /auth/users/by-username/{username}."""

    def test_get_user_by_username_success(self, client):
        client.post("/auth/register", json={"username": "mara", "password": "password123", "email": "mara@test.com"})
        resp = client.get("/auth/users/by-username/mara")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "mara"
        assert "id" in data
        assert "is_global_admin" in data
        assert "created_at" in data

    def test_get_user_by_username_not_found(self, client):
        resp = client.get("/auth/users/by-username/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
