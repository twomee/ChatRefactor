# app/dal/reaction_dal.py — Data Access Layer for Reaction model
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Reaction


def add_reaction(
    db: Session,
    message_id: str,
    user_id: int,
    username: str,
    emoji: str,
) -> bool:
    """Add a reaction. Returns True if inserted, False if duplicate (idempotent)."""
    existing = (
        db.query(Reaction)
        .filter(
            Reaction.message_id == message_id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
        .first()
    )
    if existing:
        return False

    reaction = Reaction(
        message_id=message_id,
        user_id=user_id,
        username=username,
        emoji=emoji,
    )
    try:
        db.add(reaction)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False  # concurrent insert won the race — idempotent success


def remove_reaction(
    db: Session,
    message_id: str,
    user_id: int,
    emoji: str,
) -> bool:
    """Remove a reaction. Returns True if deleted, False if not found."""
    count = (
        db.query(Reaction)
        .filter(
            Reaction.message_id == message_id,
            Reaction.user_id == user_id,
            Reaction.emoji == emoji,
        )
        .delete()
    )
    db.commit()
    return count > 0


def get_reactions_for_message(db: Session, message_id: str) -> list[Reaction]:
    """Return all reactions for a single message."""
    return (
        db.query(Reaction)
        .filter(Reaction.message_id == message_id)
        .order_by(Reaction.created_at.asc())
        .all()
    )


def get_reactions_for_messages(
    db: Session, message_ids: list[str]
) -> dict[str, list[dict]]:
    """Return reactions grouped by message_id for a batch of messages.

    Returns a dict like: { "msg-001": [{"emoji": "👍", "username": "alice", "user_id": 1}, ...] }
    Messages with no reactions are omitted from the dict.
    """
    if not message_ids:
        return {}

    reactions = (
        db.query(Reaction)
        .filter(Reaction.message_id.in_(message_ids))
        .order_by(Reaction.created_at.asc())
        .all()
    )

    grouped: dict[str, list[dict]] = {}
    for r in reactions:
        grouped.setdefault(r.message_id, []).append(
            {
                "emoji": r.emoji,
                "username": r.username,
                "user_id": r.user_id,
            }
        )
    return grouped
