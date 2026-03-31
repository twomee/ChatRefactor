# PM File Sharing & PM Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add file sharing inside DM conversations and make PM threads survive page refresh/re-login via lazy-loaded backend history.

**Architecture:** File uploads extend the existing file-service with an optional `recipient` param; PM files route via the `file.events` Kafka topic to lobby WebSocket personal delivery. PM history is loaded lazily per-conversation from a new `GET /messages/pm/history/{username}` endpoint in the message-service; localStorage stores only the list of conversation usernames (not content). `user_id` is added to the auth-service login response and AuthContext so the frontend can determine message ownership.

**Tech Stack:** FastAPI (auth-service, message-service), TypeScript/Express (file-service), Go (chat-service), React/Vitest (frontend), SQLAlchemy + Alembic (message-service DB), Prisma (file-service DB), Kafka, httpx

---

> **Note on prerequisite:** The spec mentions adding `recipient_id` to the chat-service Kafka PM payload as a prerequisite. This is NOT needed — the message-service `_persist_private_message` consumer already resolves usernames to IDs via auth-service and stores `recipient_id` correctly. Skip that prerequisite.

---

## File Map

| File | Change |
|---|---|
| `services/auth-service/app/schemas/auth.py` | Add `user_id: int` to `TokenResponse` |
| `services/auth-service/app/services/auth_service.py` | Return `user_id=user.id` in `login` and `verify_login_2fa` |
| `services/auth-service/tests/test_routers_auth.py` | Assert `user_id` in login response |
| `services/message-service/alembic/versions/008_add_pm_participants_index.py` | New Alembic migration |
| `services/message-service/app/dal/pm_deletion_dal.py` | Add `get_pm_deletion_timestamp` |
| `services/message-service/app/dal/message_dal.py` | Add `get_pm_history` |
| `services/message-service/app/routers/messages.py` | Add `GET /messages/pm/history/{username}` endpoint |
| `services/message-service/tests/test_pm_history.py` | New test file |
| `services/file-service/prisma/schema.prisma` | Make `roomId` optional; add `recipientId`, `isPrivate` |
| `services/file-service/src/config/env.config.ts` | Add `authServiceUrl` |
| `services/file-service/src/clients/auth.client.ts` | New — HTTP client for auth-service user lookup |
| `services/file-service/src/services/file.service.ts` | PM upload logic, Kafka event extension |
| `services/file-service/src/routes/file.route.ts` | Validate params; PM download authorization |
| `services/file-service/tests/routes/file.route.test.ts` | New PM upload/download tests |
| `services/chat-service/cmd/server/main.go` | Route PM files via `SendPersonal` in Kafka consumer |
| `frontend/src/context/AuthContext.jsx` | No change — `login(token, userData)` already stores whatever is passed |
| `frontend/src/pages/LoginPage.jsx` | Pass `user_id` from login response into `login()` call |
| `frontend/src/utils/storage.js` | Add `getPMThreadList`, `savePMThreadList`, `addPMThread` |
| `frontend/src/context/PMContext.jsx` | Add `loadedThreads`; add `SET_PM_THREAD`, `INIT_PM_THREAD`, `MARK_THREAD_LOADED` |
| `frontend/src/services/pmApi.js` | Add `getPMHistory` |
| `frontend/src/services/fileApi.js` | Add `uploadPMFile` |
| `frontend/src/hooks/useMultiRoomChat.js` | Route PM `file_shared` to pmDispatch; call `addPMThread` on new PM |
| `frontend/src/pages/ChatPage.jsx` | Restore PM sidebar on mount; lazy-load history in `handleSelectPM` |
| `frontend/src/components/pm/PMView.jsx` | Add file attachment button |

---

## Task 1: Auth-service — add `user_id` to login response

**Files:**
- Modify: `services/auth-service/app/schemas/auth.py`
- Modify: `services/auth-service/app/services/auth_service.py`
- Modify: `services/auth-service/tests/test_routers_auth.py`

- [ ] **Step 1: Write the failing tests**

In `services/auth-service/tests/test_routers_auth.py`, inside `class TestLogin`, add after the existing `test_login_returns_token_and_username` test:

```python
def test_login_returns_user_id(self, client):
    client.post("/auth/register", json={"username": "testuid", "password": "pass1234w", "email": "uid@test.com"})
    resp = client.post("/auth/login", json={"username": "testuid", "password": "pass1234w"})
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert isinstance(data["user_id"], int)
    assert data["user_id"] > 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd services/auth-service && python -m pytest tests/test_routers_auth.py::TestLogin::test_login_returns_user_id -v
```
Expected: `FAILED — KeyError: 'user_id'`

- [ ] **Step 3: Add `user_id` to `TokenResponse` schema**

In `services/auth-service/app/schemas/auth.py`, change `TokenResponse`:

```python
class TokenResponse(BaseModel):
    """Schema for login response — returns JWT + user metadata."""

    access_token: str
    token_type: str = "bearer"
    username: str
    is_global_admin: bool
    user_id: int
```

- [ ] **Step 4: Return `user_id` in `auth_service.login`**

In `services/auth-service/app/services/auth_service.py`, change the final `return TokenResponse(...)` in `login` (line ~184):

```python
    return TokenResponse(
        access_token=token,
        username=user.username,
        is_global_admin=user.is_global_admin,
        user_id=user.id,
    )
```

- [ ] **Step 5: Return `user_id` in `verify_login_2fa`**

Find the final `return TokenResponse(...)` in `verify_login_2fa` in the same file and add `user_id=user.id`:

```python
    return TokenResponse(
        access_token=token,
        username=user.username,
        is_global_admin=user.is_global_admin,
        user_id=user.id,
    )
```

- [ ] **Step 6: Run tests**

```bash
cd services/auth-service && python -m pytest tests/test_routers_auth.py -v
```
Expected: All pass including `test_login_returns_user_id`.

- [ ] **Step 7: Commit**

```bash
git add services/auth-service/app/schemas/auth.py \
        services/auth-service/app/services/auth_service.py \
        services/auth-service/tests/test_routers_auth.py
git commit -m "feat(auth): add user_id to login TokenResponse

Exposes the user's numeric ID in the login response so the frontend can
store it in AuthContext and use it to determine PM message ownership.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Message-service — DB migration for PM participants index

**Files:**
- Create: `services/message-service/alembic/versions/008_add_pm_participants_index.py`

- [ ] **Step 1: Create migration file**

```python
"""Add partial index on messages for PM participant lookups

Speeds up GET /messages/pm/history/{username} queries which filter by
(is_private, sender_id, recipient_id).

Revision ID: 008
Revises: 007
Create Date: 2026-03-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, Sequence[str], None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial index on messages for PM participant queries."""
    op.create_index(
        "idx_messages_pm_participants",
        "messages",
        ["sender_id", "recipient_id"],
        postgresql_where=sa.text("is_private = true"),
    )


def downgrade() -> None:
    """Remove PM participants index."""
    op.drop_index("idx_messages_pm_participants", table_name="messages")
```

- [ ] **Step 2: Commit**

```bash
git add services/message-service/alembic/versions/008_add_pm_participants_index.py
git commit -m "feat(message-service): add DB index for PM participant history queries

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Message-service — PM deletion timestamp DAL helper

**Files:**
- Modify: `services/message-service/app/dal/pm_deletion_dal.py`
- Modify: `services/message-service/tests/test_clear_and_pm_deletion.py` (or the closest test file covering pm_deletion_dal)

- [ ] **Step 1: Write failing test**

In the test file that covers `pm_deletion_dal` (find it with `grep -rl "pm_deletion_dal" services/message-service/tests/`), add:

```python
def test_get_pm_deletion_timestamp_returns_none_when_not_deleted(db_session):
    result = pm_deletion_dal.get_pm_deletion_timestamp(db_session, user_id=1, other_user_id=2)
    assert result is None


def test_get_pm_deletion_timestamp_returns_datetime_after_deletion(db_session):
    pm_deletion_dal.delete_conversation(db_session, user_id=1, other_user_id=2)
    result = pm_deletion_dal.get_pm_deletion_timestamp(db_session, user_id=1, other_user_id=2)
    assert result is not None
    from datetime import datetime
    assert isinstance(result, datetime)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd services/message-service && python -m pytest tests/ -k "get_pm_deletion_timestamp" -v
```
Expected: `FAILED — AttributeError: module has no attribute 'get_pm_deletion_timestamp'`

- [ ] **Step 3: Implement**

In `services/message-service/app/dal/pm_deletion_dal.py`, add after `delete_conversation`:

```python
def get_pm_deletion_timestamp(
    db: Session,
    user_id: int,
    other_user_id: int,
) -> datetime | None:
    """Return the deleted_at timestamp for a specific PM conversation, or None.

    Mirrors clear_dal.get_clear — used by the PM history endpoint to filter
    messages sent before the user deleted this conversation.
    """
    record = (
        db.query(DeletedPMConversation)
        .filter(
            DeletedPMConversation.user_id == user_id,
            DeletedPMConversation.other_user_id == other_user_id,
        )
        .first()
    )
    return record.deleted_at if record else None
```

Make sure `datetime` is imported at the top — it already is via `from datetime import datetime, timezone`.

- [ ] **Step 4: Run tests**

```bash
cd services/message-service && python -m pytest tests/ -k "get_pm_deletion_timestamp" -v
```
Expected: Both pass.

- [ ] **Step 5: Commit**

```bash
git add services/message-service/app/dal/pm_deletion_dal.py \
        services/message-service/tests/
git commit -m "feat(message-service): add get_pm_deletion_timestamp DAL helper

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Message-service — `get_pm_history` DAL function

**Files:**
- Modify: `services/message-service/app/dal/message_dal.py`

- [ ] **Step 1: Write failing test**

In `services/message-service/tests/`, find the file covering `message_dal` (likely `test_message_dal.py` or similar). Add:

```python
def test_get_pm_history_returns_messages_between_two_users(db_session):
    from datetime import datetime, timezone
    from app.dal import message_dal

    # Create PM messages between user 1 and user 2
    message_dal.create_idempotent(db_session, message_id="pm-test-1", sender_id=1,
        sender_name="alice", room_id=None, content="Hello", is_private=True,
        recipient_id=2, sent_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc))
    message_dal.create_idempotent(db_session, message_id="pm-test-2", sender_id=2,
        sender_name="bob", room_id=None, content="Hi back", is_private=True,
        recipient_id=1, sent_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc))
    # Room message — must not appear
    message_dal.create_idempotent(db_session, message_id="room-test-1", sender_id=1,
        sender_name="alice", room_id=5, content="Room msg", is_private=False,
        recipient_id=None)

    result = message_dal.get_pm_history(db_session, me_id=1, other_id=2)
    assert len(result) == 2
    assert result[0].content == "Hello"
    assert result[1].content == "Hi back"


def test_get_pm_history_excludes_deleted_messages(db_session):
    from datetime import datetime, timezone
    from app.dal import message_dal

    message_dal.create_idempotent(db_session, message_id="pm-del-1", sender_id=1,
        sender_name="alice", room_id=None, content="Deleted msg", is_private=True,
        recipient_id=2)
    # Mark as deleted
    db_session.query(message_dal.Message).filter_by(message_id="pm-del-1").update({"is_deleted": True})
    db_session.commit()

    result = message_dal.get_pm_history(db_session, me_id=1, other_id=2)
    assert all(not m.is_deleted for m in result)


def test_get_pm_history_pagination_before(db_session):
    from datetime import datetime, timezone
    from app.dal import message_dal

    t1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    message_dal.create_idempotent(db_session, message_id="pm-page-1", sender_id=1,
        sender_name="alice", room_id=None, content="Early", is_private=True,
        recipient_id=2, sent_at=t1)
    message_dal.create_idempotent(db_session, message_id="pm-page-2", sender_id=1,
        sender_name="alice", room_id=None, content="Late", is_private=True,
        recipient_id=2, sent_at=t2)

    result = message_dal.get_pm_history(db_session, me_id=1, other_id=2, before=t2)
    assert len(result) == 1
    assert result[0].content == "Early"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd services/message-service && python -m pytest tests/ -k "test_get_pm_history" -v
```
Expected: `FAILED — AttributeError: module 'app.dal.message_dal' has no attribute 'get_pm_history'`

- [ ] **Step 3: Implement in `message_dal.py`**

Add these imports at the top if not already there:
```python
from sqlalchemy import or_, and_
```

Then add the function after `get_room_history`:

```python
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
```

Also add `datetime` to the imports at the top of `message_dal.py` if not already:
```python
from datetime import datetime
```

- [ ] **Step 4: Run tests**

```bash
cd services/message-service && python -m pytest tests/ -k "test_get_pm_history" -v
```
Expected: All 3 pass.

- [ ] **Step 5: Commit**

```bash
git add services/message-service/app/dal/message_dal.py services/message-service/tests/
git commit -m "feat(message-service): add get_pm_history DAL function

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Message-service — PM history endpoint

**Files:**
- Modify: `services/message-service/app/routers/messages.py`
- Create: `services/message-service/tests/test_pm_history.py`

- [ ] **Step 1: Write failing tests**

Create `services/message-service/tests/test_pm_history.py`:

```python
"""Tests for GET /messages/pm/history/{username}"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dal import message_dal
from app.models import Message


@pytest.fixture
def client(db_session):
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_token(user_id: int, username: str) -> str:
    """Generate a valid JWT for tests — reuse the pattern from other test files."""
    import os
    import jwt
    secret = os.environ.get("SECRET_KEY", "test-secret")
    return jwt.encode({"sub": str(user_id), "username": username}, secret, algorithm="HS256")


def _seed_pm(db_session, msg_id, sender_id, sender_name, recipient_id, content, sent_at=None):
    message_dal.create_idempotent(
        db_session, message_id=msg_id, sender_id=sender_id, sender_name=sender_name,
        room_id=None, content=content, is_private=True, recipient_id=recipient_id,
        sent_at=sent_at or datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_returns_messages(mock_lookup, client, db_session):
    mock_lookup.return_value = {"id": 2, "username": "bob"}
    _seed_pm(db_session, "pm-h-1", sender_id=1, sender_name="alice", recipient_id=2, content="Hello Bob")
    _seed_pm(db_session, "pm-h-2", sender_id=2, sender_name="bob", recipient_id=1, content="Hi Alice")

    token = _make_token(1, "alice")
    resp = client.get("/messages/pm/history/bob", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["content"] == "Hello Bob"
    assert data[1]["content"] == "Hi Alice"


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_returns_404_when_user_not_found(mock_lookup, client, db_session):
    mock_lookup.return_value = None
    token = _make_token(1, "alice")
    resp = client.get("/messages/pm/history/nobody", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_applies_clear_filter(mock_lookup, client, db_session):
    from app.dal import clear_dal
    mock_lookup.return_value = {"id": 2, "username": "bob"}

    t_old = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    t_new = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    _seed_pm(db_session, "pm-cl-1", 1, "alice", 2, "Old message", sent_at=t_old)
    _seed_pm(db_session, "pm-cl-2", 1, "alice", 2, "New message", sent_at=t_new)

    clear_dal.upsert_clear(db_session, user_id=1, context_type="pm", context_id=2)

    token = _make_token(1, "alice")
    resp = client.get("/messages/pm/history/bob", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    contents = [m["content"] for m in resp.json()]
    assert "Old message" not in contents
    assert "New message" in contents


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_applies_deletion_filter(mock_lookup, client, db_session):
    from app.dal import pm_deletion_dal
    mock_lookup.return_value = {"id": 2, "username": "bob"}

    t_old = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    t_new = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    _seed_pm(db_session, "pm-dl-1", 1, "alice", 2, "Before delete", sent_at=t_old)
    _seed_pm(db_session, "pm-dl-2", 1, "alice", 2, "After delete", sent_at=t_new)

    pm_deletion_dal.delete_conversation(db_session, user_id=1, other_user_id=2)

    token = _make_token(1, "alice")
    resp = client.get("/messages/pm/history/bob", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    contents = [m["content"] for m in resp.json()]
    assert "Before delete" not in contents
    assert "After delete" in contents


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_requires_auth(mock_lookup, client, db_session):
    mock_lookup.return_value = {"id": 2, "username": "bob"}
    resp = client.get("/messages/pm/history/bob")
    assert resp.status_code == 401


@patch("app.routers.messages.get_user_by_username", new_callable=AsyncMock)
def test_pm_history_pagination_before(mock_lookup, client, db_session):
    mock_lookup.return_value = {"id": 2, "username": "bob"}

    t1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    _seed_pm(db_session, "pm-pg-1", 1, "alice", 2, "Early", sent_at=t1)
    _seed_pm(db_session, "pm-pg-2", 1, "alice", 2, "Late", sent_at=t2)

    token = _make_token(1, "alice")
    resp = client.get(
        f"/messages/pm/history/bob?before={t2.isoformat()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "Early"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd services/message-service && python -m pytest tests/test_pm_history.py -v
```
Expected: `FAILED — 404 Not Found` (route doesn't exist yet)

- [ ] **Step 3: Add endpoint to `messages.py`**

At the top of `services/message-service/app/routers/messages.py`, add to imports:

```python
from datetime import datetime

from app.dal import pm_deletion_dal
from app.infrastructure.auth_client import get_user_by_username
```

Then add the endpoint (place it near other PM endpoints, around line 210+):

```python
@router.get("/pm/history/{username}", response_model=list[MessageWithReactionsResponse])
async def get_pm_history_endpoint(
    username: str,
    limit: int = Query(50, ge=1, le=200),
    before: str | None = Query(None, description="ISO timestamp — return messages before this time"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Fetch PM history between the current user and another user.

    Applies UserMessageClear and DeletedPMConversation filters so cleared/
    deleted history is never returned. Supports backward pagination via
    the `before` query parameter (ISO 8601 timestamp).
    """
    other = await get_user_by_username(username)
    if not other:
        raise HTTPException(status_code=404, detail="User not found")

    me_id: int = current_user["user_id"]
    other_id: int = other["id"]

    before_dt: datetime | None = None
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid 'before' timestamp format")

    messages = message_dal.get_pm_history(db, me_id=me_id, other_id=other_id,
                                           limit=limit, before=before_dt)
    validated = [MessageResponse.model_validate(m) for m in messages]

    # Apply UserMessageClear filter
    validated = _apply_clear_filter(db, me_id, "pm", other_id, validated)

    # Apply DeletedPMConversation filter
    deleted_at = pm_deletion_dal.get_pm_deletion_timestamp(db, me_id, other_id)
    if deleted_at is not None:
        validated = [m for m in validated if m.sent_at > deleted_at]

    return _enrich_with_reactions(db, validated)
```

- [ ] **Step 4: Run tests**

```bash
cd services/message-service && python -m pytest tests/test_pm_history.py -v
```
Expected: All 6 pass.

- [ ] **Step 5: Run full message-service test suite**

```bash
cd services/message-service && python -m pytest tests/ -v
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add services/message-service/app/routers/messages.py \
        services/message-service/app/dal/pm_deletion_dal.py \
        services/message-service/alembic/versions/008_add_pm_participants_index.py \
        services/message-service/tests/test_pm_history.py
git commit -m "feat(message-service): add GET /messages/pm/history/{username} endpoint

Lazy-loads PM history per conversation with UserMessageClear and
DeletedPMConversation filters applied. Backed by partial DB index on
(sender_id, recipient_id) WHERE is_private = true.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: File-service — Prisma schema for PM files

**Files:**
- Modify: `services/file-service/prisma/schema.prisma`
- Modify: `services/file-service/src/config/env.config.ts`

- [ ] **Step 1: Update Prisma schema**

In `services/file-service/prisma/schema.prisma`, replace the `File` model:

```prisma
model File {
  id           Int      @id @default(autoincrement())
  originalName String
  storedPath   String
  fileSize     Int
  senderId     Int
  senderName   String
  roomId       Int?
  recipientId  Int?
  isPrivate    Boolean  @default(false)
  uploadedAt   DateTime @default(now())
}
```

- [ ] **Step 2: Add `authServiceUrl` to config**

In `services/file-service/src/config/env.config.ts`, add inside the exported `config` object (after `maxFileSizeBytes`):

```typescript
  // Auth Service — used to resolve recipient usernames to user IDs for PM files.
  authServiceUrl: requireEnv("AUTH_SERVICE_URL", "http://auth-service:8001"),
```

- [ ] **Step 3: Generate Prisma migration**

```bash
cd services/file-service && npx prisma migrate dev --name add_pm_file_support
```
Expected: Migration created and applied; Prisma client regenerated.

- [ ] **Step 4: Commit**

```bash
git add services/file-service/prisma/ services/file-service/src/config/env.config.ts
git commit -m "feat(file-service): extend File schema with recipientId, isPrivate for PM files

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: File-service — auth-service HTTP client

**Files:**
- Create: `services/file-service/src/clients/auth.client.ts`

- [ ] **Step 1: Write failing test**

In `services/file-service/tests/routes/file.route.test.ts`, add a mock for the auth client at the top of the file alongside the existing mocks:

```typescript
const mockGetUserByUsername = vi.hoisted(() => vi.fn());
vi.mock("../../src/clients/auth.client.js", () => ({
  getUserByUsername: mockGetUserByUsername,
}));
```

This will fail if the module doesn't exist yet — which is the desired state.

- [ ] **Step 2: Run to confirm failure**

```bash
cd services/file-service && npm test
```
Expected: `Error: Cannot find module '../../src/clients/auth.client.js'`

- [ ] **Step 3: Create the auth client**

Create `services/file-service/src/clients/auth.client.ts`:

```typescript
// src/clients/auth.client.ts — Resolves usernames to user IDs via Auth Service.
//
// Used exclusively during PM file uploads to look up the recipient's numeric ID.
// Keeps a simple in-process cache (Map) to avoid repeated lookups for the same
// username within a short window.

import { config } from "../config/env.config.js";

interface AuthUser {
  id: number;
  username: string;
}

const cache = new Map<string, { user: AuthUser | null; expiresAt: number }>();
const CACHE_TTL_MS = 60_000; // 1 minute

/**
 * Look up a user by username via the Auth Service.
 * Returns the user object or null if not found.
 * Throws if the Auth Service is unreachable.
 */
export async function getUserByUsername(username: string): Promise<AuthUser | null> {
  const now = Date.now();
  const cached = cache.get(username);
  if (cached && cached.expiresAt > now) {
    return cached.user;
  }

  const url = `${config.authServiceUrl}/auth/users/by-username/${encodeURIComponent(username)}`;
  const response = await fetch(url, { signal: AbortSignal.timeout(3000) });

  if (response.status === 404) {
    cache.set(username, { user: null, expiresAt: now + CACHE_TTL_MS });
    return null;
  }

  if (!response.ok) {
    throw new Error(`Auth service returned ${response.status} for username lookup`);
  }

  const user: AuthUser = await response.json();
  cache.set(username, { user, expiresAt: now + CACHE_TTL_MS });
  return user;
}

/** Clear the cache — used in tests. */
export function clearAuthCache(): void {
  cache.clear();
}
```

- [ ] **Step 4: Run tests to verify mock is resolved**

```bash
cd services/file-service && npm test
```
Expected: Test suite runs (no module-not-found error). Existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add services/file-service/src/clients/auth.client.ts \
        services/file-service/tests/routes/file.route.test.ts
git commit -m "feat(file-service): add auth-service HTTP client for recipient username lookup

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: File-service — PM file upload support

**Files:**
- Modify: `services/file-service/src/services/file.service.ts`
- Modify: `services/file-service/src/routes/file.route.ts`
- Modify: `services/file-service/tests/routes/file.route.test.ts`

- [ ] **Step 1: Write failing tests**

In `services/file-service/tests/routes/file.route.test.ts`, add inside `describe("POST /files/upload")`:

```typescript
it("should upload a PM file with ?recipient=bob", async () => {
  mockGetUserByUsername.mockResolvedValue({ id: 7, username: "bob" });
  const mockRecord = {
    id: 2, originalName: "doc.pdf", storedPath: "/app/uploads/abc_doc.pdf",
    fileSize: 500, senderId: 1, roomId: null, recipientId: 7, isPrivate: true,
    uploadedAt: new Date(),
  };
  mockPrismaFile.create.mockResolvedValue(mockRecord);

  const res = await request(app)
    .post("/files/upload?recipient=bob")
    .set("Authorization", `Bearer ${validToken}`)
    .attach("file", Buffer.from("pdf content"), "doc.pdf");

  expect(res.status).toBe(201);
  expect(res.body.recipientId).toBe(7);
  expect(res.body.isPrivate).toBe(true);
  expect(mockProducerSend).toHaveBeenCalledWith(
    expect.objectContaining({
      messages: expect.arrayContaining([
        expect.objectContaining({
          value: expect.stringContaining('"is_private":true'),
        }),
      ]),
    })
  );
});

it("should return 400 if both room_id and recipient are provided", async () => {
  const res = await request(app)
    .post("/files/upload?room_id=1&recipient=bob")
    .set("Authorization", `Bearer ${validToken}`)
    .attach("file", Buffer.from("content"), "test.txt");

  expect(res.status).toBe(400);
  expect(res.body.error).toMatch(/room_id.*recipient|mutually exclusive/i);
});

it("should return 400 if neither room_id nor recipient is provided", async () => {
  const res = await request(app)
    .post("/files/upload")
    .set("Authorization", `Bearer ${validToken}`)
    .attach("file", Buffer.from("content"), "test.txt");

  expect(res.status).toBe(400);
});

it("should return 404 if recipient username does not exist", async () => {
  mockGetUserByUsername.mockResolvedValue(null);
  const res = await request(app)
    .post("/files/upload?recipient=ghost")
    .set("Authorization", `Bearer ${validToken}`)
    .attach("file", Buffer.from("content"), "test.txt");

  expect(res.status).toBe(404);
  expect(res.body.error).toMatch(/recipient|not found/i);
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd services/file-service && npm test -- --reporter=verbose 2>&1 | grep -E "PASS|FAIL|✓|✗|Error"
```
Expected: New PM upload tests fail.

- [ ] **Step 3: Update `file.service.ts`**

In `services/file-service/src/services/file.service.ts`, add `recipientId` and `isPrivate` to the upload function's parameters and DB create call:

Find the `uploadFile` function and update its signature and Prisma create:

```typescript
// Add to imports at top:
import { getUserByUsername } from "../clients/auth.client.js";

// Update the upload function signature to accept recipientId:
export async function uploadFile(params: {
  file: Express.Multer.File;
  senderId: number;
  senderName: string;
  roomId?: number;
  recipientId?: number;
  isPrivate?: boolean;
}): Promise<FileRecord> {
  const { file, senderId, senderName, roomId, recipientId, isPrivate = false } = params;

  // ... existing sanitize / validate / write-to-disk logic unchanged ...

  const record = await prisma.file.create({
    data: {
      originalName: cleanName,
      storedPath: storedPath,
      fileSize: file.size,
      senderId,
      senderName,
      roomId: roomId ?? null,
      recipientId: recipientId ?? null,
      isPrivate,
    },
  });

  // Produce Kafka event — extend with PM fields
  await producer.send({
    topic: "file.events",
    messages: [{
      value: JSON.stringify({
        file_id: record.id,
        filename: record.originalName,
        size: record.fileSize,
        from: senderName,
        room_id: roomId ?? null,
        to: isPrivate ? params.recipientName : undefined,
        recipient_id: recipientId ?? null,
        is_private: isPrivate,
        timestamp: new Date().toISOString(),
      }),
    }],
  });

  return record;
}
```

Note: `recipientName` needs to be passed through too. Update the params type to include `recipientName?: string`.

- [ ] **Step 4: Update `file.route.ts`**

In `services/file-service/src/routes/file.route.ts`, update the upload handler:

```typescript
import { getUserByUsername } from "../clients/auth.client.js";

router.post("/upload", async (req, res) => {
  const roomIdParam = req.query.room_id as string | undefined;
  const recipientParam = req.query.recipient as string | undefined;

  // Exactly one of room_id or recipient is required
  if (roomIdParam && recipientParam) {
    return res.status(400).json({ error: "room_id and recipient are mutually exclusive" });
  }
  if (!roomIdParam && !recipientParam) {
    return res.status(400).json({ error: "Either room_id or recipient is required" });
  }

  const file = req.file;
  if (!file) return res.status(400).json({ error: "No file provided" });

  const senderId: number = (req as any).user.id;
  const senderName: string = (req as any).user.username;

  let roomId: number | undefined;
  let recipientId: number | undefined;
  let recipientName: string | undefined;

  if (roomIdParam) {
    roomId = parseInt(roomIdParam, 10);
    if (isNaN(roomId)) return res.status(400).json({ error: "Invalid room_id" });
  } else {
    // PM file: resolve recipient username → id
    const recipient = await getUserByUsername(recipientParam!);
    if (!recipient) return res.status(404).json({ error: "Recipient not found" });
    recipientId = recipient.id;
    recipientName = recipient.username;
  }

  const record = await uploadFile({
    file, senderId, senderName, roomId, recipientId, recipientName,
    isPrivate: !!recipientId,
  });

  return res.status(201).json(record);
});
```

- [ ] **Step 5: Run tests**

```bash
cd services/file-service && npm test
```
Expected: All tests pass including the new PM upload tests.

- [ ] **Step 6: Commit**

```bash
git add services/file-service/src/services/file.service.ts \
        services/file-service/src/routes/file.route.ts \
        services/file-service/tests/routes/file.route.test.ts
git commit -m "feat(file-service): support PM file uploads via ?recipient=username param

Validates room_id XOR recipient; resolves recipient via auth-service;
stores recipientId + isPrivate on File record; extends Kafka event with
to/recipient_id/is_private fields.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9: File-service — PM download authorization

**Files:**
- Modify: `services/file-service/src/routes/file.route.ts`
- Modify: `services/file-service/tests/routes/file.route.test.ts`

- [ ] **Step 1: Write failing tests**

In `services/file-service/tests/routes/file.route.test.ts`, add inside `describe("GET /files/download/:fileId")`:

```typescript
it("should return 403 if requester is not sender or recipient of a private file", async () => {
  // File belongs to sender=1, recipient=7; current user from validToken is user 1
  const privateFile = {
    id: 99, originalName: "secret.txt", storedPath: path.join(uploadDir, "secret.txt"),
    fileSize: 10, senderId: 2, recipientId: 7, isPrivate: true,
    senderName: "other", roomId: null, uploadedAt: new Date(),
  };
  mockPrismaFile.findUnique.mockResolvedValue(privateFile);

  // validToken is for user id=1, who is neither sender(2) nor recipient(7)
  const res = await request(app)
    .get("/files/download/99")
    .set("Authorization", `Bearer ${validToken}`);

  expect(res.status).toBe(403);
});

it("should allow sender to download their own private file", async () => {
  const privateFile = {
    id: 100, originalName: "mine.txt", storedPath: path.join(uploadDir, "mine.txt"),
    fileSize: 4, senderId: 1, recipientId: 7, isPrivate: true,
    senderName: "alice", roomId: null, uploadedAt: new Date(),
  };
  // Create the actual file so the stream works
  fs.writeFileSync(privateFile.storedPath, "data");
  mockPrismaFile.findUnique.mockResolvedValue(privateFile);

  const res = await request(app)
    .get("/files/download/100")
    .set("Authorization", `Bearer ${validToken}`);

  expect(res.status).toBe(200);
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd services/file-service && npm test -- --reporter=verbose 2>&1 | grep -E "403|download"
```
Expected: 403 test fails (currently returns 200 or 404).

- [ ] **Step 3: Add authorization check to download handler in `file.route.ts`**

In the `GET /download/:fileId` handler, after fetching the file record from Prisma, add:

```typescript
// Authorization: private files are only accessible to sender and recipient
if (record.isPrivate) {
  const currentUserId: number = (req as any).user.id;
  if (record.senderId !== currentUserId && record.recipientId !== currentUserId) {
    return res.status(403).json({ error: "Forbidden" });
  }
}
```

- [ ] **Step 4: Run tests**

```bash
cd services/file-service && npm test
```
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/file-service/src/routes/file.route.ts \
        services/file-service/tests/routes/file.route.test.ts
git commit -m "feat(file-service): enforce participant-only authorization for private file downloads

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Chat-service — route PM files in Kafka consumer

**Files:**
- Modify: `services/chat-service/cmd/server/main.go`

- [ ] **Step 1: Write failing test**

In `services/chat-service/internal/handler/` (or `cmd/server/`), find or create a test for the file event consumer. If no test exists, add one to the nearest `*_test.go` file:

```go
func TestFileEventConsumer_PMFile_SendsPersonal(t *testing.T) {
    // This is an integration/unit test verifying the consumer routing logic.
    // Since the consumer is inline in main.go, test the routing logic by
    // extracting it to a helper function (see step 3).
    isPrivate := true
    recipientID := float64(42)

    var personalSent bool
    var broadcastSent bool

    routeFileEvent(
        map[string]interface{}{
            "file_id": float64(1), "filename": "x.png", "size": float64(100),
            "from": "alice", "to": "bob", "recipient_id": recipientID,
            "room_id": nil, "is_private": isPrivate, "timestamp": "2026-01-01T00:00:00Z",
        },
        func(userID int, msg map[string]interface{}) { personalSent = true },
        func(roomID int, msg map[string]interface{}) { broadcastSent = true },
    )

    if !personalSent {
        t.Error("expected SendPersonal to be called for PM file")
    }
    if broadcastSent {
        t.Error("expected BroadcastRoom NOT to be called for PM file")
    }
}

func TestFileEventConsumer_RoomFile_Broadcasts(t *testing.T) {
    var personalSent bool
    var broadcastSent bool

    routeFileEvent(
        map[string]interface{}{
            "file_id": float64(1), "filename": "x.png", "size": float64(100),
            "from": "alice", "room_id": float64(5), "is_private": false,
            "timestamp": "2026-01-01T00:00:00Z",
        },
        func(userID int, msg map[string]interface{}) { personalSent = true },
        func(roomID int, msg map[string]interface{}) { broadcastSent = true },
    )

    if personalSent {
        t.Error("expected SendPersonal NOT to be called for room file")
    }
    if !broadcastSent {
        t.Error("expected BroadcastRoom to be called for room file")
    }
}
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd services/chat-service && go test ./... 2>&1 | grep -E "FAIL|routeFileEvent"
```
Expected: `undefined: routeFileEvent`

- [ ] **Step 3: Extract routing logic and update consumer in `main.go`**

In `services/chat-service/cmd/server/main.go`, extract the file routing into a package-level function and update the consumer:

```go
// routeFileEvent dispatches a file.events Kafka message to either personal
// delivery (PM file) or room broadcast (room file).
// sendPersonal and broadcastRoom are injected so this function is testable.
func routeFileEvent(
    value map[string]interface{},
    sendPersonal func(userID int, msg map[string]interface{}),
    broadcastRoom func(roomID int, msg map[string]interface{}),
) {
    msg := map[string]interface{}{
        "type":      "file_shared",
        "file_id":   value["file_id"],
        "filename":  value["filename"],
        "size":      value["size"],
        "from":      value["from"],
        "room_id":   value["room_id"],
        "timestamp": value["timestamp"],
    }

    isPrivate, _ := value["is_private"].(bool)
    if isPrivate {
        msg["to"] = value["to"]
        msg["is_private"] = true
        if recipientID, ok := value["recipient_id"].(float64); ok {
            sendPersonal(int(recipientID), msg)
        }
        return
    }

    if roomID, ok := value["room_id"].(float64); ok {
        broadcastRoom(int(roomID), msg)
    }
}
```

Then update the Kafka consumer callback in `main.go` to call `routeFileEvent`:

```go
fileEventsConsumer = kafka.NewConsumer(brokers, "file.events", "chat-file-events",
    func(_ context.Context, value map[string]interface{}) error {
        routeFileEvent(
            value,
            func(userID int, msg map[string]interface{}) { wsManager.SendPersonal(userID, msg) },
            func(roomID int, msg map[string]interface{}) { wsManager.BroadcastRoom(roomID, msg) },
        )
        return nil
    }, logger)
```

- [ ] **Step 4: Run tests**

```bash
cd services/chat-service && go test ./... -v 2>&1 | grep -E "PASS|FAIL|ok"
```
Expected: All pass including the two new routing tests.

- [ ] **Step 5: Commit**

```bash
git add services/chat-service/cmd/server/main.go \
        services/chat-service/cmd/server/main_test.go
git commit -m "feat(chat-service): route PM files to lobby personal delivery in file.events consumer

Extracts routeFileEvent helper for testability; PM files (is_private=true)
use SendPersonal(recipientID); room files use BroadcastRoom(roomID).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11: Frontend — store `user_id` in AuthContext

**Files:**
- Modify: `frontend/src/pages/LoginPage.jsx`
- Modify: `frontend/src/context/AuthContext.jsx` (add `user_id` to sessionStorage init)

- [ ] **Step 1: Write failing test**

Find the AuthContext or LoginPage test file. If it's `frontend/src/pages/__tests__/LoginPage.test.jsx`, add:

```javascript
it('stores user_id from login response in user context', async () => {
  const mockLogin = vi.fn();
  // Mock useAuth to capture what login is called with
  vi.mocked(useAuth).mockReturnValue({ login: mockLogin, user: null, token: null, logout: vi.fn() });

  // Mock the login API to return user_id
  vi.mocked(authApi.login).mockResolvedValue({
    data: { access_token: 'tok', username: 'alice', is_global_admin: false, user_id: 42 }
  });

  render(<LoginPage />);
  await userEvent.type(screen.getByLabelText(/username/i), 'alice');
  await userEvent.type(screen.getByLabelText(/password/i), 'pass');
  await userEvent.click(screen.getByRole('button', { name: /login/i }));

  await waitFor(() => {
    expect(mockLogin).toHaveBeenCalledWith(
      'tok',
      expect.objectContaining({ username: 'alice', user_id: 42 })
    );
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm test -- --run src/pages/__tests__/LoginPage.test.jsx 2>&1 | tail -20
```
Expected: Test fails — `login` called without `user_id`.

- [ ] **Step 3: Update `LoginPage.jsx`**

Find the successful login handler in `frontend/src/pages/LoginPage.jsx`. Currently it calls:
```javascript
login(res.data.access_token, { username: res.data.username, is_global_admin: res.data.is_global_admin });
```

Change it to:
```javascript
login(res.data.access_token, {
  username: res.data.username,
  is_global_admin: res.data.is_global_admin,
  user_id: res.data.user_id,
});
```

- [ ] **Step 4: Update `AuthContext.jsx` initial state**

In `frontend/src/context/AuthContext.jsx`, the `user` is loaded from `sessionStorage.getItem('user')`. Since `login()` stores whatever `userData` is passed via `JSON.stringify`, no change is needed to `AuthContext.jsx` itself — `user.user_id` will be available automatically once `LoginPage.jsx` passes it.

However, add a guard for existing sessions without `user_id` (users logged in before this deploy). In `AuthContext.jsx`, find where `user` is initialized from sessionStorage and ensure it handles `user_id` being absent gracefully — `user.user_id` will just be `undefined` in that case and the user will need to re-login.

- [ ] **Step 5: Run test**

```bash
cd frontend && npm test -- --run src/pages/__tests__/LoginPage.test.jsx
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/LoginPage.jsx frontend/src/pages/__tests__/LoginPage.test.jsx
git commit -m "feat(frontend): persist user_id from login response in AuthContext

Required for PM history transformPMHistory to determine isSelf.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 12: Frontend — `storage.js` PM thread list helpers

**Files:**
- Modify: `frontend/src/utils/storage.js`
- Create: `frontend/src/utils/__tests__/storage.test.js` (or add to existing)

- [ ] **Step 1: Write failing tests**

Find or create `frontend/src/utils/__tests__/storage.test.js`:

```javascript
import { describe, it, expect, beforeEach } from 'vitest';
import {
  getPMThreadList,
  savePMThreadList,
  addPMThread,
} from '../storage';

describe('PM thread list helpers', () => {
  beforeEach(() => localStorage.clear());

  it('getPMThreadList returns empty array when nothing saved', () => {
    expect(getPMThreadList('alice')).toEqual([]);
  });

  it('savePMThreadList persists list under per-user key', () => {
    savePMThreadList('alice', ['bob', 'charlie']);
    expect(getPMThreadList('alice')).toEqual(['bob', 'charlie']);
  });

  it('getPMThreadList is isolated per user', () => {
    savePMThreadList('alice', ['bob']);
    expect(getPMThreadList('carol')).toEqual([]);
  });

  it('addPMThread appends a new username', () => {
    addPMThread('alice', 'bob');
    expect(getPMThreadList('alice')).toContain('bob');
  });

  it('addPMThread is idempotent — does not duplicate', () => {
    addPMThread('alice', 'bob');
    addPMThread('alice', 'bob');
    const list = getPMThreadList('alice');
    expect(list.filter(u => u === 'bob').length).toBe(1);
  });

  it('addPMThread preserves existing entries', () => {
    addPMThread('alice', 'bob');
    addPMThread('alice', 'charlie');
    expect(getPMThreadList('alice')).toEqual(['bob', 'charlie']);
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm test -- --run src/utils/__tests__/storage.test.js
```
Expected: `FAILED — getPMThreadList is not a function`

- [ ] **Step 3: Implement in `storage.js`**

In `frontend/src/utils/storage.js`, add after the existing `getJoinedRooms` helpers:

```javascript
// ── PM thread list helpers ────────────────────────────────────────────────
// Stores only usernames (not message content) to restore the DM sidebar.

function pmThreadKey(username) {
  return `chatbox_pm_threads_${username ?? 'anonymous'}`;
}

export function getPMThreadList(username) {
  try {
    return JSON.parse(localStorage.getItem(pmThreadKey(username)) || '[]');
  } catch {
    return [];
  }
}

export function savePMThreadList(username, usernames) {
  try {
    localStorage.setItem(pmThreadKey(username), JSON.stringify(usernames));
  } catch { /* storage full — ignore */ }
}

export function addPMThread(currentUsername, partnerUsername) {
  const existing = getPMThreadList(currentUsername);
  if (!existing.includes(partnerUsername)) {
    savePMThreadList(currentUsername, [...existing, partnerUsername]);
  }
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- --run src/utils/__tests__/storage.test.js
```
Expected: All 6 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/storage.js frontend/src/utils/__tests__/storage.test.js
git commit -m "feat(frontend): add PM thread list helpers to storage.js

Stores DM conversation usernames in localStorage so the sidebar can be
restored on login without loading message content.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 13: Frontend — new PMContext actions

**Files:**
- Modify: `frontend/src/context/PMContext.jsx`
- Find/create PMContext reducer test file

- [ ] **Step 1: Write failing tests**

Find the PMContext reducer test file. If it doesn't exist, search with:
```bash
grep -rl "pmReducer\|PMContext" frontend/src --include="*.test.*"
```

Add tests for the three new actions:

```javascript
import { pmReducer } from '../PMContext';

describe('pmReducer new actions', () => {
  const baseState = {
    threads: {}, pmUnread: {}, activePM: null, deletedPMs: {}, loadedThreads: {},
  };

  describe('SET_PM_THREAD', () => {
    it('replaces the thread for the given username', () => {
      const messages = [{ from: 'alice', text: 'hi', msg_id: '1' }];
      const state = pmReducer(baseState, { type: 'SET_PM_THREAD', username: 'alice', messages });
      expect(state.threads.alice).toEqual(messages);
    });

    it('overwrites existing thread', () => {
      const existing = { ...baseState, threads: { alice: [{ text: 'old' }] } };
      const state = pmReducer(existing, {
        type: 'SET_PM_THREAD', username: 'alice', messages: [{ text: 'new' }],
      });
      expect(state.threads.alice).toEqual([{ text: 'new' }]);
    });
  });

  describe('MARK_THREAD_LOADED', () => {
    it('sets loadedThreads[username] to true', () => {
      const state = pmReducer(baseState, { type: 'MARK_THREAD_LOADED', username: 'alice' });
      expect(state.loadedThreads.alice).toBe(true);
    });
  });

  describe('INIT_PM_THREAD', () => {
    it('creates an empty thread if none exists', () => {
      const state = pmReducer(baseState, { type: 'INIT_PM_THREAD', username: 'alice' });
      expect(state.threads.alice).toEqual([]);
    });

    it('does not overwrite an existing live thread', () => {
      const existing = { ...baseState, threads: { alice: [{ text: 'live msg' }] } };
      const state = pmReducer(existing, { type: 'INIT_PM_THREAD', username: 'alice' });
      expect(state.threads.alice).toEqual([{ text: 'live msg' }]);
    });
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm test -- --run 2>&1 | grep -E "SET_PM_THREAD|MARK_THREAD|INIT_PM"
```
Expected: Tests fail — actions not implemented.

- [ ] **Step 3: Update `PMContext.jsx`**

In `frontend/src/context/PMContext.jsx`:

1. Add `loadedThreads: {}` to `initialPMState`:
```javascript
const initialPMState = {
  threads: {},
  pmUnread: {},
  activePM: null,
  deletedPMs: {},
  loadedThreads: {},  // { username: true } — prevents double-fetching
};
```

2. Add three new cases to `pmReducer` switch:
```javascript
    case 'SET_PM_THREAD':
      return {
        ...state,
        threads: { ...state.threads, [action.username]: action.messages },
      };

    case 'MARK_THREAD_LOADED':
      return {
        ...state,
        loadedThreads: { ...state.loadedThreads, [action.username]: true },
      };

    case 'INIT_PM_THREAD':
      // Don't overwrite a thread that already has live messages
      if (state.threads[action.username]) return state;
      return {
        ...state,
        threads: { ...state.threads, [action.username]: [] },
      };
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- --run
```
Expected: All 389+ tests pass (new ones included).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/context/PMContext.jsx
git commit -m "feat(frontend): add SET_PM_THREAD, MARK_THREAD_LOADED, INIT_PM_THREAD to PMContext

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 14: Frontend — `pmApi.js` and `fileApi.js` new functions

**Files:**
- Modify: `frontend/src/services/pmApi.js`
- Modify: `frontend/src/services/fileApi.js`

- [ ] **Step 1: Add `getPMHistory` to `pmApi.js`**

In `frontend/src/services/pmApi.js`, add:

```javascript
/**
 * Fetch PM history with a specific user from the backend.
 * Loaded lazily — only called when a conversation is opened and not yet in state.
 * @param {string} username - The other participant's username
 * @param {{ limit?: number, before?: string }} options
 */
export function getPMHistory(username, { limit = 50, before } = {}) {
  return http.get(`/messages/pm/history/${encodeURIComponent(username)}`, {
    params: { limit, ...(before && { before }) },
  });
}
```

- [ ] **Step 2: Add `uploadPMFile` to `fileApi.js`**

In `frontend/src/services/fileApi.js`, add:

```javascript
/**
 * Upload a file into a PM conversation.
 * @param {string} recipientUsername - The recipient's username
 * @param {File} file - The file to upload
 * @param {function} onProgress - Progress callback (optional)
 */
export function uploadPMFile(recipientUsername, file, onProgress) {
  const form = new FormData();
  form.append('file', file);
  return http.post(`/files/upload?recipient=${encodeURIComponent(recipientUsername)}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/pmApi.js frontend/src/services/fileApi.js
git commit -m "feat(frontend): add getPMHistory and uploadPMFile API functions

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 15: Frontend — `useMultiRoomChat.js` updates

**Files:**
- Modify: `frontend/src/hooks/useMultiRoomChat.js`
- Modify: `frontend/src/hooks/__tests__/useMultiRoomChat.test.jsx` (or nearest test)

- [ ] **Step 1: Write failing tests**

Find the test file for `useMultiRoomChat`. Add:

```javascript
describe('file_shared event', () => {
  it('dispatches to pmDispatch for PM files (is_private: true)', () => {
    // ... render hook with mocked dispatch and pmDispatch ...
    // send file_shared WS message with is_private: true, to: 'bob', from: 'alice'
    // expect pmDispatch to be called with ADD_PM_MESSAGE
    // expect dispatch NOT to be called with ADD_MESSAGE for room
  });

  it('dispatches to room dispatch for room files (is_private: false)', () => {
    // send file_shared WS message with is_private: false, room_id: 5
    // expect dispatch to be called with ADD_MESSAGE
    // expect pmDispatch NOT to be called
  });
});

describe('private_message event', () => {
  it('calls addPMThread when a new PM arrives', () => {
    // Mock addPMThread from storage
    // send private_message WS event
    // expect addPMThread to have been called with (currentUsername, otherUser)
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm test -- --run src/hooks/__tests__/ 2>&1 | grep -E "FAIL|file_shared|addPMThread"
```
Expected: New tests fail.

- [ ] **Step 3: Update `useMultiRoomChat.js`**

At the top of `frontend/src/hooks/useMultiRoomChat.js`, add the import:
```javascript
import { addPMThread } from '../utils/storage';
```

Find the `case 'file_shared':` handler and replace it:

```javascript
      case 'file_shared': {
        if (msg.is_private) {
          // PM file: route to the correct PM thread
          const otherUser = msg.from === user?.username ? msg.to : msg.from;
          pmDispatch({
            type: 'ADD_PM_MESSAGE',
            username: otherUser,
            message: {
              isFile: true,
              from: msg.from,
              text: msg.filename,
              fileId: msg.file_id,
              fileSize: msg.size,
              isSelf: false,
              msg_id: `pm-file-${msg.file_id}`,
              timestamp: msg.timestamp,
            },
          });
        } else {
          // Room file: existing behaviour
          dispatch({
            type: 'ADD_MESSAGE',
            roomId: msg.room_id,
            message: {
              isFile: true,
              from: msg.from,
              text: msg.filename,
              fileId: msg.file_id,
              fileSize: msg.size,
            },
          });
        }
        break;
      }
```

Find the `case 'private_message':` handler. After the existing `pmDispatch({ type: 'ADD_PM_MESSAGE', ... })` call, add:

```javascript
        // Persist conversation to localStorage so sidebar survives refresh
        addPMThread(user?.username, otherUser);
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- --run
```
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useMultiRoomChat.js
git commit -m "feat(frontend): route PM file_shared events to pmDispatch; persist DM threads

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 16: Frontend — `ChatPage.jsx` sidebar restore and lazy history

**Files:**
- Modify: `frontend/src/pages/ChatPage.jsx`

- [ ] **Step 1: Write failing tests**

In the ChatPage test file, add:

```javascript
describe('PM persistence', () => {
  it('restores PM thread list from localStorage on mount', () => {
    savePMThreadList('alice', ['bob', 'carol']);
    // render ChatPage with user = { username: 'alice', user_id: 1 }
    // expect INIT_PM_THREAD dispatched for 'bob' and 'carol'
  });

  it('fetches PM history on first conversation open', async () => {
    vi.mocked(pmApi.getPMHistory).mockResolvedValue({ data: [] });
    // render ChatPage, click on PM 'bob' in sidebar (who has empty/unloaded thread)
    // expect getPMHistory('bob') to have been called
    // expect MARK_THREAD_LOADED dispatched for 'bob'
  });

  it('does NOT fetch PM history if thread already loaded', async () => {
    vi.mocked(pmApi.getPMHistory).mockResolvedValue({ data: [] });
    // render with loadedThreads: { bob: true }
    // click PM 'bob'
    // expect getPMHistory NOT called
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm test -- --run src/pages/__tests__/ChatPage.test.jsx 2>&1 | tail -20
```
Expected: New tests fail.

- [ ] **Step 3: Add imports to `ChatPage.jsx`**

At the top of `frontend/src/pages/ChatPage.jsx`, add:
```javascript
import { getPMThreadList } from '../utils/storage';
import * as pmApi from '../services/pmApi';
```

(If `pmApi` is already imported, ensure `getPMHistory` is available via the namespace import.)

- [ ] **Step 4: Add `transformPMHistory` helper to `ChatPage.jsx`**

Add this helper function inside the component (or as a module-level function):

```javascript
function transformPMHistory(messages, currentUsername) {
  return messages.map(m => ({
    from: m.sender_name,
    text: m.content,
    msg_id: m.message_id,
    isSelf: m.sender_name === currentUsername,
    timestamp: m.sent_at,
    edited_at: m.edited_at ?? null,
    is_deleted: m.is_deleted ?? false,
    reactions: m.reactions || [],
    to: m.sender_name === currentUsername ? undefined : currentUsername,
  }));
}
```

- [ ] **Step 5: Add mount effect to restore sidebar**

In `ChatPage.jsx`, add a `useEffect` after the existing effects:

```javascript
  // Restore PM thread list from localStorage on login
  useEffect(() => {
    if (!user?.username) return;
    const saved = getPMThreadList(user.username);
    saved.forEach(username => {
      pmDispatch({ type: 'INIT_PM_THREAD', username });
    });
  }, [user?.username]); // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 6: Update `handleSelectPM` with lazy loading**

Find `handleSelectPM` in `ChatPage.jsx` and replace it:

```javascript
  async function handleSelectPM(username) {
    pmDispatch({ type: 'SET_ACTIVE_PM', username });
    pmDispatch({ type: 'CLEAR_PM_UNREAD', username });
    dispatch({ type: 'SET_ACTIVE_ROOM', roomId: null });

    // Lazy-load history on first open — skip if already loaded this session
    if (!pmState.loadedThreads[username]) {
      try {
        const res = await pmApi.getPMHistory(username);
        const transformed = transformPMHistory(res.data || [], user?.username);
        pmDispatch({ type: 'SET_PM_THREAD', username, messages: transformed });
      } catch {
        // Non-fatal: thread stays empty; user can still send new messages
      }
      pmDispatch({ type: 'MARK_THREAD_LOADED', username });
    }
  }
```

- [ ] **Step 7: Run tests**

```bash
cd frontend && npm test -- --run
```
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/ChatPage.jsx
git commit -m "feat(frontend): restore PM sidebar from localStorage; lazy-load history per conversation

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 17: Frontend — PMView file attachment button

**Files:**
- Modify: `frontend/src/components/pm/PMView.jsx`
- Modify: `frontend/src/components/pm/__tests__/PMView.test.jsx`

- [ ] **Step 1: Write failing tests**

In `frontend/src/components/pm/__tests__/PMView.test.jsx`, add:

```javascript
describe('file attachment', () => {
  it('renders a file attachment button', () => {
    render(<PMView messages={[]} activePM="bob" currentUser="alice" onSend={vi.fn()} />);
    expect(screen.getByTestId('pm-attach-btn')).toBeInTheDocument();
  });

  it('dispatches ADD_PM_MESSAGE after successful file upload', async () => {
    const mockUpload = vi.fn().mockResolvedValue({
      data: { id: 5, originalName: 'photo.png', fileSize: 1234 }
    });
    vi.mocked(fileApi.uploadPMFile).mockImplementation(mockUpload);
    const mockDispatch = vi.fn();

    render(
      <PMView messages={[]} activePM="bob" currentUser="alice"
               onSend={vi.fn()} pmDispatch={mockDispatch} />
    );

    const file = new File(['content'], 'photo.png', { type: 'image/png' });
    const input = screen.getByTestId('pm-file-input');
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'ADD_PM_MESSAGE', username: 'bob' })
      );
    });
  });

  it('shows an error message if upload fails', async () => {
    vi.mocked(fileApi.uploadPMFile).mockRejectedValue(new Error('Network error'));
    render(<PMView messages={[]} activePM="bob" currentUser="alice" onSend={vi.fn()} pmDispatch={vi.fn()} />);

    const file = new File(['x'], 'bad.png', { type: 'image/png' });
    const input = screen.getByTestId('pm-file-input');
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText(/failed|error/i)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npm test -- --run src/components/pm/__tests__/PMView.test.jsx 2>&1 | tail -20
```
Expected: New tests fail — no attachment button exists.

- [ ] **Step 3: Update `PMView.jsx`**

At the top of `frontend/src/components/pm/PMView.jsx`, add imports:

```javascript
import { useRef, useState } from 'react';
import * as fileApi from '../../services/fileApi';
```

Add `pmDispatch` and `currentUser` to the component props. Then add file upload state and handler:

```javascript
export default function PMView({
  messages, activePM, currentUser, onSend, onClearHistory,
  editingMessage, onEditMessage, onDeleteMessage, onAddReaction,
  onRemoveReaction, highlightMessageId,
  pmDispatch,   // ← new
}) {
  const fileInputRef = useRef(null);
  const [uploadError, setUploadError] = useState(null);
  const [uploading, setUploading] = useState(false);

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';  // reset so same file can be re-selected
    setUploadError(null);
    setUploading(true);
    try {
      const res = await fileApi.uploadPMFile(activePM, file);
      pmDispatch?.({
        type: 'ADD_PM_MESSAGE',
        username: activePM,
        message: {
          isFile: true,
          from: currentUser,
          text: res.data.originalName,
          fileId: res.data.id,
          fileSize: res.data.fileSize,
          isSelf: true,
          msg_id: `pm-file-${res.data.id}`,
          timestamp: new Date().toISOString(),
        },
      });
    } catch {
      setUploadError('File upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  }
```

In the JSX, add the attachment button and hidden file input next to the message input area:

```jsx
      {/* File attachment */}
      <input
        ref={fileInputRef}
        type="file"
        data-testid="pm-file-input"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />
      <button
        className="btn-icon-sm"
        data-testid="pm-attach-btn"
        title="Attach file"
        disabled={uploading}
        onClick={() => fileInputRef.current?.click()}
      >
        {/* Paperclip SVG */}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19
                   a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
        </svg>
      </button>
      {uploadError && <span className="upload-error">{uploadError}</span>}
```

Also update `PropTypes`:
```javascript
PMView.propTypes = {
  // ... existing props ...
  pmDispatch: PropTypes.func,
  currentUser: PropTypes.string,
};
```

- [ ] **Step 4: Update `ChatPage.jsx` to pass new props to `PMView`**

In `ChatPage.jsx`, find `<PMView` and add:

```jsx
<PMView
  ...existing props...
  pmDispatch={pmDispatch}
  currentUser={user?.username}
/>
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm test -- --run
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/pm/PMView.jsx \
        frontend/src/components/pm/__tests__/PMView.test.jsx \
        frontend/src/pages/ChatPage.jsx
git commit -m "feat(frontend): add file attachment button to PMView

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 18: Run all 4 services tests

- [ ] **Step 1: Frontend**

```bash
cd frontend && npm test -- --run
```
Expected: All tests pass (389+).

- [ ] **Step 2: Message-service**

```bash
cd services/message-service && python -m pytest tests/ -v
```
Expected: All pass including `test_pm_history.py`.

- [ ] **Step 3: Chat-service**

```bash
cd services/chat-service && go test ./...
```
Expected: `ok` for all packages.

- [ ] **Step 4: File-service**

```bash
cd services/file-service && npm test
```
Expected: All pass including PM upload/download tests.

- [ ] **Step 5: If any test fails — fix before moving on**

Do not proceed to PR until all 4 suites are green.

- [ ] **Step 6: Final commit and PR**

```bash
git add -A
git commit -m "test: verify all 4 service test suites pass for PM files + persistence

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

Then open a pull request from `feat/pm-files-and-persistence` → `feat/pm-fixes` with:
- Summary of both features
- Note on known limitation: messages sent before this deploy won't appear in PM history (recipient_id was already stored by the consumer, so this only affects messages from before a prior fix)
- Tech debt items: E2EE, Redis cache, room file auth
