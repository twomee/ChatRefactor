# tests/test_kafka_consumer.py — Unit tests for the Kafka persistence consumer
#
# Tests the persistence methods directly with an in-memory SQLite DB.
# No actual Kafka connection required.
import sys
import os
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from auth import hash_password
from kafka_topics import TOPIC_MESSAGES, TOPIC_PRIVATE

test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)


@pytest.fixture()
def db():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def room(db):
    r = models.Room(name="kafka_test_room")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@pytest.fixture()
def sender(db):
    u = models.User(username="alice", password_hash=hash_password("pw"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def recipient(db):
    u = models.User(username="bob", password_hash=hash_password("pw2"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def consumer():
    from kafka_consumers import MessagePersistenceConsumer
    return MessagePersistenceConsumer()


# ── Room message persistence ──────────────────────────────────────────


def test_persist_room_message(db, room, sender, consumer):
    """Consumer should persist a room message to the DB."""
    ts = datetime.now(timezone.utc).isoformat()
    consumer._persist_room_message(db, {
        "msg_id": "test-uuid-001",
        "sender_id": sender.id,
        "sender": sender.username,
        "room_id": room.id,
        "text": "Hello from Kafka!",
        "timestamp": ts,
    })

    msg = db.query(models.Message).filter(models.Message.message_id == "test-uuid-001").first()
    assert msg is not None
    assert msg.content == "Hello from Kafka!"
    assert msg.sender_id == sender.id
    assert msg.room_id == room.id
    assert msg.is_private is False


def test_idempotent_room_message(db, room, sender, consumer):
    """Duplicate msg_id should NOT create a second row."""
    value = {
        "msg_id": "test-uuid-dup",
        "sender_id": sender.id,
        "sender": sender.username,
        "room_id": room.id,
        "text": "first write",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    consumer._persist_room_message(db, value)
    consumer._persist_room_message(db, value)  # duplicate

    count = db.query(models.Message).filter(models.Message.message_id == "test-uuid-dup").count()
    assert count == 1


# ── Private message persistence ───────────────────────────────────────


def test_persist_private_message(db, sender, recipient, consumer):
    """Consumer should persist a PM to the DB."""
    consumer._persist_private_message(db, {
        "msg_id": "pm-uuid-001",
        "sender": sender.username,
        "recipient": recipient.username,
        "text": "Secret PM",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    msg = db.query(models.Message).filter(models.Message.message_id == "pm-uuid-001").first()
    assert msg is not None
    assert msg.content == "Secret PM"
    assert msg.is_private is True
    assert msg.sender_id == sender.id
    assert msg.recipient_id == recipient.id
    assert msg.room_id is None


def test_private_message_unknown_sender_raises(db, recipient, consumer):
    """Consumer should raise if the sender username doesn't exist."""
    with pytest.raises(ValueError, match="Unknown user"):
        consumer._persist_private_message(db, {
            "msg_id": "pm-uuid-bad",
            "sender": "nonexistent_user",
            "recipient": recipient.username,
            "text": "Should fail",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# ── Edge cases ────────────────────────────────────────────────────────


def test_persist_message_without_timestamp(db, room, sender, consumer):
    """Consumer should handle messages without a timestamp (uses DB default)."""
    consumer._persist_room_message(db, {
        "msg_id": "test-uuid-no-ts",
        "sender_id": sender.id,
        "sender": sender.username,
        "room_id": room.id,
        "text": "No timestamp",
    })

    msg = db.query(models.Message).filter(models.Message.message_id == "test-uuid-no-ts").first()
    assert msg is not None
    assert msg.sent_at is not None  # DB default should kick in


def test_process_dispatches_room_message(db, room, sender, consumer, monkeypatch):
    """_process() should route TOPIC_MESSAGES to _persist_room_message via SessionLocal."""
    monkeypatch.setattr("database.SessionLocal", lambda: db)

    consumer._process(TOPIC_MESSAGES, {
        "msg_id": "dispatch-test",
        "sender_id": sender.id,
        "sender": sender.username,
        "room_id": room.id,
        "text": "Dispatched!",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    msg = db.query(models.Message).filter(models.Message.message_id == "dispatch-test").first()
    assert msg is not None
    assert msg.content == "Dispatched!"


def test_process_dispatches_private_message(db, sender, recipient, consumer, monkeypatch):
    """_process() should route TOPIC_PRIVATE to _persist_private_message via SessionLocal."""
    monkeypatch.setattr("database.SessionLocal", lambda: db)

    consumer._process(TOPIC_PRIVATE, {
        "msg_id": "dispatch-pm-test",
        "sender": sender.username,
        "recipient": recipient.username,
        "text": "PM dispatched!",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    msg = db.query(models.Message).filter(models.Message.message_id == "dispatch-pm-test").first()
    assert msg is not None
    assert msg.content == "PM dispatched!"
    assert msg.is_private is True
