# tests/test_dal_user_dal.py — Unit tests for app/dal/user_dal.py
"""
Tests for:
- get_by_id: returns user or None
- get_by_username: returns user or None
- create: creates and returns a user
- delete_all: removes all users
"""

from app.core.security import hash_password
from app.dal import user_dal


class TestGetById:
    """Tests for user_dal.get_by_id()."""

    def test_returns_user_when_exists(self, db_session):
        """get_by_id should return the user when the ID exists."""
        user = user_dal.create(db_session, "alice", hash_password("password123"))
        found = user_dal.get_by_id(db_session, user.id)
        assert found is not None
        assert found.username == "alice"

    def test_returns_none_when_not_exists(self, db_session):
        """get_by_id should return None when the ID doesn't exist."""
        found = user_dal.get_by_id(db_session, 99999)
        assert found is None


class TestGetByUsername:
    """Tests for user_dal.get_by_username()."""

    def test_returns_user_when_exists(self, db_session):
        """get_by_username should return the user when the username exists."""
        user_dal.create(db_session, "bob", hash_password("password123"))
        found = user_dal.get_by_username(db_session, "bob")
        assert found is not None
        assert found.username == "bob"

    def test_returns_none_when_not_exists(self, db_session):
        """get_by_username should return None for a non-existent username."""
        found = user_dal.get_by_username(db_session, "nonexistent")
        assert found is None


class TestCreate:
    """Tests for user_dal.create()."""

    def test_creates_user_with_correct_fields(self, db_session):
        """create should persist a user with the given username and password hash."""
        pw_hash = hash_password("securepass")
        user = user_dal.create(db_session, "carol", pw_hash)
        assert user.id is not None
        assert user.username == "carol"
        assert user.password_hash == pw_hash
        assert user.is_global_admin is False

    def test_creates_admin_user(self, db_session):
        """create with is_global_admin=True should set the admin flag."""
        user = user_dal.create(
            db_session, "admin_user", hash_password("adminpass"), is_global_admin=True
        )
        assert user.is_global_admin is True


class TestDeleteAll:
    """Tests for user_dal.delete_all()."""

    def test_removes_all_users(self, db_session):
        """delete_all should remove every user from the database."""
        user_dal.create(db_session, "dave", hash_password("pass1"))
        user_dal.create(db_session, "erin", hash_password("pass2"))
        user_dal.delete_all(db_session)
        assert user_dal.get_by_username(db_session, "dave") is None
        assert user_dal.get_by_username(db_session, "erin") is None
