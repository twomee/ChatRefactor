# app/dal/message_dal.py — Data Access Layer for Message model
from datetime import datetime, timezone

from sqlalchemy import func, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Message


def create_idempotent(
    db: Session,
    message_id: str,
    sender_id: int,
    room_id: int | None,
    content: str,
    is_private: bool = False,
    recipient_id: int | None = None,
    sent_at: datetime | None = None,
    sender_name: str | None = None,
    is_file: bool = False,
    file_id: int | None = None,
) -> bool:
    """Insert a message only if message_id doesn't already exist. Returns True if inserted."""
    existing = db.query(Message).filter(Message.message_id == message_id).first()
    if existing:
        return False

    msg = Message(
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        room_id=room_id,
        content=content,
        is_private=is_private,
        recipient_id=recipient_id,
        is_file=is_file,
        file_id=file_id,
    )
    if sent_at:
        msg.sent_at = sent_at
    try:
        db.add(msg)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False  # concurrent insert won the race — idempotent success


def get_by_room_since(
    db: Session, room_id: int, since: datetime, limit: int = 100
) -> list[Message]:
    """Return messages in a room since a given timestamp, for the replay API."""
    return (
        db.query(Message)
        .filter(
            Message.room_id == room_id,
            Message.is_private == False,  # noqa: E712
            Message.sent_at >= since,
        )
        .order_by(Message.sent_at.asc())
        .limit(limit)
        .all()
    )


def get_room_history(db: Session, room_id: int, limit: int = 50) -> list[Message]:
    """Return recent messages in a room, ordered oldest-first (for room join)."""
    msgs = (
        db.query(Message)
        .filter(
            Message.room_id == room_id,
            Message.is_private == False,  # noqa: E712
        )
        .order_by(Message.sent_at.desc())
        .limit(limit)
        .all()
    )
    msgs.reverse()
    return msgs


def get_pm_history(
    db: Session,
    me_id: int,
    other_id: int,
    limit: int = 50,
    before: datetime | None = None,
) -> list[Message]:
    """Return PM messages between two users, ordered oldest-first.

    Filters out soft-deleted messages. Caller is responsible for applying
    UserMessageClear and DeletedPMConversation filters on top of this result.
    """
    q = (
        db.query(Message)
        .filter(
            Message.is_private == True,  # noqa: E712
            or_(
                and_(Message.sender_id == me_id, Message.recipient_id == other_id),
                and_(Message.sender_id == other_id, Message.recipient_id == me_id),
            ),
            Message.is_deleted == False,  # noqa: E712
        )
    )
    if before is not None:
        q = q.filter(Message.sent_at < before)
    return q.order_by(Message.sent_at.asc()).limit(limit).all()


def edit_message(
    db: Session, message_id: str, sender_id: int, new_content: str
) -> bool:
    """Edit message content. Only the original sender can edit."""
    msg = (
        db.query(Message).filter_by(message_id=message_id, sender_id=sender_id).first()
    )
    if not msg or msg.is_deleted:
        return False
    msg.content = new_content
    msg.edited_at = datetime.now(timezone.utc)
    db.commit()
    return True


def soft_delete_message(db: Session, message_id: str, sender_id: int) -> bool:
    """Soft-delete a message. Only the original sender can delete."""
    msg = (
        db.query(Message).filter_by(message_id=message_id, sender_id=sender_id).first()
    )
    if not msg or msg.is_deleted:
        return False
    msg.is_deleted = True
    msg.content = "[deleted]"
    db.commit()
    return True


def search_messages(
    db: Session,
    query: str,
    room_id: int | None = None,
    limit: int = 50,
) -> list[Message]:
    """Full-text search across messages using PostgreSQL tsvector.

    On PostgreSQL, uses the GIN-indexed search_vector column with plainto_tsquery
    for relevance-ranked results. Falls back to case-insensitive LIKE on SQLite
    (used in tests) since tsvector is PostgreSQL-specific.

    Only searches public, non-deleted messages within the specified room.
    Results are ordered by relevance (ts_rank on PG) then recency.

    Args:
        db:      SQLAlchemy session.
        query:   Search terms (must be non-empty, min 2 chars enforced at router).
        room_id: Required — restricts results to a single room so users cannot
                 enumerate messages from rooms they have not joined.
        limit:   Maximum number of results to return (capped at 100).
    """
    capped_limit = min(limit, 100)
    try:
        dialect = db.get_bind().dialect.name
    except Exception:
        dialect = "postgresql"  # default to production path

    base_filters = [
        Message.is_private == False,  # noqa: E712
        Message.is_deleted == False,  # noqa: E712
    ]
    if room_id is not None:
        base_filters.append(Message.room_id == room_id)

    if dialect == "postgresql":
        ts_query = func.plainto_tsquery("english", query)
        q = (
            db.query(Message)
            .filter(*base_filters)
            .filter(Message.search_vector.op("@@")(ts_query))
            .order_by(
                func.ts_rank(Message.search_vector, ts_query).desc(),
                Message.sent_at.desc(),
            )
        )
    else:
        # SQLite fallback — safe case-insensitive search using autoescape=True so
        # that SQL wildcard characters (% and _) inside `query` are escaped and
        # cannot alter the LIKE pattern (prevents LIKE injection).
        q = (
            db.query(Message)
            .filter(*base_filters)
            .filter(
                func.lower(Message.content).contains(query.lower(), autoescape=True)
            )
            .order_by(Message.sent_at.desc())
        )

    return q.limit(capped_limit).all()


def get_messages_around(
    db: Session,
    room_id: int,
    message_id: str,
    before: int = 25,
    after: int = 25,
) -> list[Message]:
    """Get N messages before and N messages after a target message in a room.

    Returns the target message plus surrounding context, sorted by sent_at ASC.
    Used for scroll-to-message when a user clicks a search result.
    """
    target = (
        db.query(Message)
        .filter(Message.message_id == message_id, Message.room_id == room_id)
        .first()
    )
    if not target:
        return []

    # Messages before the target (ordered DESC, then reversed)
    before_msgs = (
        db.query(Message)
        .filter(
            Message.room_id == room_id,
            Message.is_private == False,  # noqa: E712
            Message.sent_at < target.sent_at,
        )
        .order_by(Message.sent_at.desc())
        .limit(before)
        .all()
    )
    before_msgs.reverse()

    # Messages after the target
    after_msgs = (
        db.query(Message)
        .filter(
            Message.room_id == room_id,
            Message.is_private == False,  # noqa: E712
            Message.sent_at > target.sent_at,
        )
        .order_by(Message.sent_at.asc())
        .limit(after)
        .all()
    )

    return before_msgs + [target] + after_msgs


def get_pm_messages_around(
    db: Session,
    user_id: int,
    message_id: str,
    before: int = 25,
    after: int = 25,
) -> list[Message]:
    """Get N messages before and N messages after a target PM message.

    Finds the target message and returns surrounding PM context for the user
    (messages where user is sender or recipient). Sorted by sent_at ASC.
    """
    target = (
        db.query(Message)
        .filter(
            Message.message_id == message_id,
            Message.is_private == True,  # noqa: E712
        )
        .first()
    )
    if not target:
        return []

    # Determine the other user in the PM conversation
    other_user_id = (
        target.recipient_id if target.sender_id == user_id else target.sender_id
    )

    # PM filter: messages between these two users
    pm_filter = [
        Message.is_private == True,  # noqa: E712
        (
            (Message.sender_id == user_id) & (Message.recipient_id == other_user_id)
            | (Message.sender_id == other_user_id) & (Message.recipient_id == user_id)
        ),
    ]

    before_msgs = (
        db.query(Message)
        .filter(*pm_filter, Message.sent_at < target.sent_at)
        .order_by(Message.sent_at.desc())
        .limit(before)
        .all()
    )
    before_msgs.reverse()

    after_msgs = (
        db.query(Message)
        .filter(*pm_filter, Message.sent_at > target.sent_at)
        .order_by(Message.sent_at.asc())
        .limit(after)
        .all()
    )

    return before_msgs + [target] + after_msgs


def delete_all(db: Session):
    """Delete all messages. Used in tests only."""
    db.query(Message).delete()
    db.commit()
