# tests/test_dal_reaction_dal.py — Tests for reaction Data Access Layer
import pytest

from app.dal import reaction_dal


class TestAddReaction:
    def test_add_reaction_success(self, db):
        result = reaction_dal.add_reaction(db, "msg-001", 1, "alice", "thumbsup")
        assert result is True

    def test_add_reaction_duplicate_returns_false(self, db):
        reaction_dal.add_reaction(db, "msg-001", 1, "alice", "thumbsup")
        result = reaction_dal.add_reaction(db, "msg-001", 1, "alice", "thumbsup")
        assert result is False

    def test_same_user_different_emoji_allowed(self, db):
        reaction_dal.add_reaction(db, "msg-001", 1, "alice", "thumbsup")
        result = reaction_dal.add_reaction(db, "msg-001", 1, "alice", "heart")
        assert result is True

    def test_different_user_same_emoji_allowed(self, db):
        reaction_dal.add_reaction(db, "msg-001", 1, "alice", "thumbsup")
        result = reaction_dal.add_reaction(db, "msg-001", 2, "bob", "thumbsup")
        assert result is True


class TestRemoveReaction:
    def test_remove_existing_reaction(self, db):
        reaction_dal.add_reaction(db, "msg-001", 1, "alice", "thumbsup")
        result = reaction_dal.remove_reaction(db, "msg-001", 1, "thumbsup")
        assert result is True

    def test_remove_nonexistent_returns_false(self, db):
        result = reaction_dal.remove_reaction(db, "msg-001", 1, "thumbsup")
        assert result is False


class TestGetReactionsForMessage:
    def test_returns_reactions_in_order(self, db):
        reaction_dal.add_reaction(db, "msg-001", 1, "alice", "thumbsup")
        reaction_dal.add_reaction(db, "msg-001", 2, "bob", "heart")
        reactions = reaction_dal.get_reactions_for_message(db, "msg-001")
        assert len(reactions) == 2
        assert reactions[0].emoji == "thumbsup"
        assert reactions[1].emoji == "heart"

    def test_empty_for_unknown_message(self, db):
        reactions = reaction_dal.get_reactions_for_message(db, "nonexistent")
        assert reactions == []


class TestGetReactionsForMessages:
    def test_batch_grouped_by_message(self, db):
        reaction_dal.add_reaction(db, "msg-001", 1, "alice", "thumbsup")
        reaction_dal.add_reaction(db, "msg-002", 2, "bob", "heart")
        reaction_dal.add_reaction(db, "msg-001", 3, "carol", "fire")

        result = reaction_dal.get_reactions_for_messages(db, ["msg-001", "msg-002"])
        assert len(result["msg-001"]) == 2
        assert len(result["msg-002"]) == 1
        assert result["msg-001"][0]["emoji"] == "thumbsup"
        assert result["msg-002"][0]["username"] == "bob"

    def test_empty_list_returns_empty_dict(self, db):
        result = reaction_dal.get_reactions_for_messages(db, [])
        assert result == {}

    def test_messages_without_reactions_omitted(self, db):
        result = reaction_dal.get_reactions_for_messages(db, ["msg-999"])
        assert "msg-999" not in result
