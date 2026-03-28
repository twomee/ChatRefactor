# Phase 1: Critical Production Features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 10 critical features that every production chat app must have — without these, users will abandon the app within minutes.

**Architecture:** Each feature follows the established pattern: database migration → backend service logic → Kafka event (if needed) → WebSocket broadcast → REST API → React state/reducer → UI component. All features are independent and can be built in any order, though the recommended order minimizes rework.

**Tech Stack:** Go (chat-service), Python/FastAPI (auth-service, message-service), Node.js/TypeScript (file-service), React 19 (frontend), PostgreSQL, Kafka, Redis, WebSocket

---

## Feature Overview

| # | Feature | Primary Service | Estimated Time |
|---|---------|----------------|----------------|
| 1 | Message Editing & Deletion | chat-service (Go) + message-service (Python) + frontend | 3-4 hours |
| 2 | Emoji Reactions | chat-service (Go) + message-service (Python) + frontend | 3-4 hours |
| 3 | @Mentions & Browser Notifications | chat-service (Go) + frontend | 2-3 hours |
| 4 | Typing Indicators | chat-service (Go) + frontend | 1-2 hours |
| 5 | Markdown Formatting | frontend only | 1-2 hours |
| 6 | Inline Image Previews | frontend + file-service (minor) | 1-2 hours |
| 7 | Message Search | message-service (Python) + frontend | 3-4 hours |
| 8 | Two-Factor Authentication (2FA) | auth-service (Python) + frontend | 4-5 hours |
| 9 | Link Previews (URL Unfurling) | new link-preview endpoint in message-service + frontend | 3-4 hours |
| 10 | Read Position Tracking | chat-service (Go) + frontend | 2-3 hours |

---

## Feature 1: Message Editing & Deletion

### Task 1.1: Add edited/deleted columns to messages table

**Files:**
- Create: `services/message-service/alembic/versions/003_add_edit_delete_columns.py`

- [ ] **Step 1: Create the migration file**

```python
"""Add edit and delete columns to messages table

Revision ID: 003
Revises: 002
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("edited_at", sa.DateTime, nullable=True))
    op.add_column("messages", sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("messages", "is_deleted")
    op.drop_column("messages", "edited_at")
```

- [ ] **Step 2: Update the SQLAlchemy model**

Modify: `services/message-service/app/models/__init__.py`

Add after `sent_at` column:
```python
    edited_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
```

- [ ] **Step 3: Update Pydantic response schemas**

Modify: `services/message-service/app/schemas/message.py`

Add to `MessageResponse` class:
```python
    edited_at: datetime | None = None
    is_deleted: bool = False
```

Add to `MessageHistoryResponse` class:
```python
    edited_at: datetime | None = None
    is_deleted: bool = False
```

- [ ] **Step 4: Commit**

```bash
git add services/message-service/alembic/versions/003_add_edit_delete_columns.py \
      services/message-service/app/models/__init__.py \
      services/message-service/app/schemas/message.py
git commit -m "feat(message-service): add edited_at and is_deleted columns to messages"
```

### Task 1.2: Add edit/delete DAL methods and API endpoints

**Files:**
- Modify: `services/message-service/app/dal/message_dal.py`
- Modify: `services/message-service/app/routers/messages.py`
- Test: `services/message-service/tests/test_dal_messages.py`
- Test: `services/message-service/tests/test_routers_messages.py`

- [ ] **Step 1: Write failing tests for DAL edit/delete**

Add to `services/message-service/tests/test_dal_messages.py`:
```python
class TestEditMessage:
    def test_edit_existing_message_returns_true(self, db_session):
        """Editing a message updates content and sets edited_at."""
        from app.dal.message_dal import create_idempotent, edit_message
        create_idempotent(db_session, "msg-1", sender_id=1, room_id=1, content="original")
        db_session.commit()

        result = edit_message(db_session, message_id="msg-1", sender_id=1, new_content="edited text")
        assert result is True

        from app.models import Message
        msg = db_session.query(Message).filter_by(message_id="msg-1").first()
        assert msg.content == "edited text"
        assert msg.edited_at is not None

    def test_edit_nonexistent_message_returns_false(self, db_session):
        from app.dal.message_dal import edit_message
        result = edit_message(db_session, message_id="nonexistent", sender_id=1, new_content="text")
        assert result is False

    def test_edit_message_wrong_sender_returns_false(self, db_session):
        """Only the original sender can edit their message."""
        from app.dal.message_dal import create_idempotent, edit_message
        create_idempotent(db_session, "msg-2", sender_id=1, room_id=1, content="original")
        db_session.commit()

        result = edit_message(db_session, message_id="msg-2", sender_id=999, new_content="hacked")
        assert result is False


class TestDeleteMessage:
    def test_soft_delete_message_returns_true(self, db_session):
        from app.dal.message_dal import create_idempotent, soft_delete_message
        create_idempotent(db_session, "msg-3", sender_id=1, room_id=1, content="to delete")
        db_session.commit()

        result = soft_delete_message(db_session, message_id="msg-3", sender_id=1)
        assert result is True

        from app.models import Message
        msg = db_session.query(Message).filter_by(message_id="msg-3").first()
        assert msg.is_deleted is True
        assert msg.content == "[deleted]"

    def test_soft_delete_wrong_sender_returns_false(self, db_session):
        from app.dal.message_dal import create_idempotent, soft_delete_message
        create_idempotent(db_session, "msg-4", sender_id=1, room_id=1, content="protected")
        db_session.commit()

        result = soft_delete_message(db_session, message_id="msg-4", sender_id=999)
        assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/message-service && python -m pytest tests/test_dal_messages.py -v -k "TestEditMessage or TestDeleteMessage"`
Expected: FAIL — `edit_message` and `soft_delete_message` not defined

- [ ] **Step 3: Implement DAL methods**

Add to `services/message-service/app/dal/message_dal.py`:
```python
def edit_message(
    db: Session,
    message_id: str,
    sender_id: int,
    new_content: str,
) -> bool:
    """Edit message content. Only the original sender can edit. Returns True if edited."""
    msg = db.query(Message).filter_by(message_id=message_id, sender_id=sender_id).first()
    if not msg or msg.is_deleted:
        return False
    msg.content = new_content
    msg.edited_at = datetime.utcnow()
    db.commit()
    return True


def soft_delete_message(
    db: Session,
    message_id: str,
    sender_id: int,
) -> bool:
    """Soft-delete a message. Only the original sender can delete. Returns True if deleted."""
    msg = db.query(Message).filter_by(message_id=message_id, sender_id=sender_id).first()
    if not msg or msg.is_deleted:
        return False
    msg.is_deleted = True
    msg.content = "[deleted]"
    db.commit()
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/message-service && python -m pytest tests/test_dal_messages.py -v -k "TestEditMessage or TestDeleteMessage"`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Write failing tests for API endpoints**

Add to `services/message-service/tests/test_routers_messages.py`:
```python
class TestEditEndpoint:
    def test_edit_message_returns_200(self, client, auth_headers, db_session):
        from app.dal.message_dal import create_idempotent
        create_idempotent(db_session, "edit-msg-1", sender_id=1, room_id=1, content="original")
        db_session.commit()

        response = client.patch(
            "/messages/edit/edit-msg-1",
            json={"content": "updated text"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["edited"] is True

    def test_edit_nonexistent_message_returns_404(self, client, auth_headers):
        response = client.patch(
            "/messages/edit/nonexistent",
            json={"content": "text"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_edit_without_auth_returns_401(self, client):
        response = client.patch(
            "/messages/edit/msg-1",
            json={"content": "text"},
        )
        assert response.status_code == 401


class TestDeleteEndpoint:
    def test_delete_message_returns_200(self, client, auth_headers, db_session):
        from app.dal.message_dal import create_idempotent
        create_idempotent(db_session, "del-msg-1", sender_id=1, room_id=1, content="to delete")
        db_session.commit()

        response = client.delete(
            "/messages/delete/del-msg-1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is True

    def test_delete_nonexistent_message_returns_404(self, client, auth_headers):
        response = client.delete(
            "/messages/delete/nonexistent",
            headers=auth_headers,
        )
        assert response.status_code == 404
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd services/message-service && python -m pytest tests/test_routers_messages.py -v -k "TestEditEndpoint or TestDeleteEndpoint"`
Expected: FAIL — routes not defined

- [ ] **Step 7: Implement API endpoints**

Add to `services/message-service/app/routers/messages.py`:
```python
from app.dal.message_dal import edit_message, soft_delete_message
from pydantic import BaseModel, Field


class EditMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


@router.patch("/messages/edit/{message_id}")
def edit_msg(
    message_id: str,
    body: EditMessageRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    success = edit_message(db, message_id=message_id, sender_id=current_user["user_id"], new_content=body.content)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found or not yours")
    return {"edited": True, "message_id": message_id}


@router.delete("/messages/delete/{message_id}")
def delete_msg(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    success = soft_delete_message(db, message_id=message_id, sender_id=current_user["user_id"])
    if not success:
        raise HTTPException(status_code=404, detail="Message not found or not yours")
    return {"deleted": True, "message_id": message_id}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd services/message-service && python -m pytest tests/test_routers_messages.py -v -k "TestEditEndpoint or TestDeleteEndpoint"`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add services/message-service/app/dal/message_dal.py \
      services/message-service/app/routers/messages.py \
      services/message-service/tests/
git commit -m "feat(message-service): add edit and delete message API endpoints"
```

### Task 1.3: Add edit/delete WebSocket handlers in chat-service

**Files:**
- Modify: `services/chat-service/internal/handler/ws_message.go`
- Modify: `services/chat-service/internal/handler/websocket.go`
- Create: `services/chat-service/internal/handler/ws_edit.go`

- [ ] **Step 1: Create edit/delete WebSocket handler**

Create: `services/chat-service/internal/handler/ws_edit.go`
```go
package handler

import (
	"net/http"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// handleEditMessage processes incoming "edit_message" WebSocket commands.
// Only the original sender can edit their message.
func (h *WebSocketHandler) handleEditMessage(
	conn *websocket.Conn,
	roomID, userID int,
	username string,
	msg IncomingMessage,
) {
	msgID := strings.TrimSpace(msg.MessageID)
	newText := strings.TrimSpace(msg.Text)

	if msgID == "" || newText == "" {
		h.sendError(conn, "edit_message requires msg_id and text")
		return
	}

	if len(newText) > maxContentLength {
		h.sendError(conn, "message too long")
		return
	}

	// Broadcast edit to all users in the room
	editPayload := map[string]interface{}{
		"type":      "message_edited",
		"room_id":   roomID,
		"msg_id":    msgID,
		"from":      username,
		"text":      newText,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	h.manager.BroadcastRoom(roomID, editPayload)

	// Publish to Kafka for persistence
	h.publishEdit(roomID, userID, username, msgID, newText)

	h.logger.Debug("message edited",
		zap.Int("room_id", roomID),
		zap.String("msg_id", msgID),
		zap.String("user", username),
	)
}

// handleDeleteMessage processes incoming "delete_message" WebSocket commands.
// Only the original sender can delete their message.
func (h *WebSocketHandler) handleDeleteMessage(
	conn *websocket.Conn,
	roomID, userID int,
	username string,
	msg IncomingMessage,
) {
	msgID := strings.TrimSpace(msg.MessageID)
	if msgID == "" {
		h.sendError(conn, "delete_message requires msg_id")
		return
	}

	// Broadcast deletion to all users in the room
	deletePayload := map[string]interface{}{
		"type":      "message_deleted",
		"room_id":   roomID,
		"msg_id":    msgID,
		"from":      username,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	h.manager.BroadcastRoom(roomID, deletePayload)

	// Publish to Kafka for persistence
	h.publishDelete(roomID, userID, username, msgID)

	h.logger.Debug("message deleted",
		zap.Int("room_id", roomID),
		zap.String("msg_id", msgID),
		zap.String("user", username),
	)
}

func (h *WebSocketHandler) publishEdit(roomID, userID int, username, msgID, newText string) {
	payload := map[string]interface{}{
		"type":      "edit_message",
		"room_id":   roomID,
		"sender_id": userID,
		"username":  username,
		"msg_id":    msgID,
		"text":      newText,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	h.produceEvent("chat.messages", msgID, payload)
}

func (h *WebSocketHandler) publishDelete(roomID, userID int, username, msgID string) {
	payload := map[string]interface{}{
		"type":      "delete_message",
		"room_id":   roomID,
		"sender_id": userID,
		"username":  username,
		"msg_id":    msgID,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	h.produceEvent("chat.messages", msgID, payload)
}
```

- [ ] **Step 2: Add `MessageID` field to IncomingMessage struct**

Modify `services/chat-service/internal/handler/websocket.go`, add to `IncomingMessage`:
```go
type IncomingMessage struct {
	Type      string `json:"type"`
	Text      string `json:"text"`
	Target    string `json:"target"`
	To        string `json:"to"`
	MessageID string `json:"msg_id"` // NEW: for edit/delete
}
```

- [ ] **Step 3: Add routing for new message types in the WebSocket message switch**

In the main message handling switch in `services/chat-service/internal/handler/websocket.go`, add cases:
```go
case "edit_message":
    h.handleEditMessage(conn, roomID, userID, username, msg)
case "delete_message":
    h.handleDeleteMessage(conn, roomID, userID, username, msg)
```

- [ ] **Step 4: Commit**

```bash
git add services/chat-service/internal/handler/ws_edit.go \
      services/chat-service/internal/handler/websocket.go
git commit -m "feat(chat-service): add edit and delete message WebSocket handlers"
```

### Task 1.4: Handle edit/delete events in message-service Kafka consumer

**Files:**
- Modify: `services/message-service/app/consumers/persistence_consumer.py`

- [ ] **Step 1: Add edit/delete handling to persistence consumer**

Add to the consumer's message handler (after the existing `_persist_room_message` handling):
```python
async def _handle_edit_message(self, db: Session, value: dict) -> None:
    """Handle edit_message event from Kafka."""
    msg_id = value.get("msg_id")
    sender_id = value.get("sender_id")
    new_text = value.get("text", "")
    if not msg_id or not sender_id:
        logger.warning("edit_message missing required fields", extra={"value": value})
        return
    from app.dal.message_dal import edit_message
    success = edit_message(db, message_id=msg_id, sender_id=sender_id, new_content=new_text)
    if success:
        logger.info("message edited via Kafka", extra={"msg_id": msg_id})
    else:
        logger.warning("edit_message failed — not found or wrong sender", extra={"msg_id": msg_id})


async def _handle_delete_message(self, db: Session, value: dict) -> None:
    """Handle delete_message event from Kafka."""
    msg_id = value.get("msg_id")
    sender_id = value.get("sender_id")
    if not msg_id or not sender_id:
        logger.warning("delete_message missing required fields", extra={"value": value})
        return
    from app.dal.message_dal import soft_delete_message
    success = soft_delete_message(db, message_id=msg_id, sender_id=sender_id)
    if success:
        logger.info("message deleted via Kafka", extra={"msg_id": msg_id})
    else:
        logger.warning("delete_message failed — not found or wrong sender", extra={"msg_id": msg_id})
```

Then in the main consume loop, add to the type routing:
```python
msg_type = value.get("type", "message")
if msg_type == "edit_message":
    await self._handle_edit_message(db, value)
elif msg_type == "delete_message":
    await self._handle_delete_message(db, value)
elif msg_type == "message":
    await self._persist_room_message(db, value)
```

- [ ] **Step 2: Commit**

```bash
git add services/message-service/app/consumers/persistence_consumer.py
git commit -m "feat(message-service): handle edit/delete events in Kafka consumer"
```

### Task 1.5: Add edit/delete Kong routes

**Files:**
- Modify: `infra/kong/kong.yml`

- [ ] **Step 1: Add message edit/delete routes to Kong**

Add under the message-service section in `infra/kong/kong.yml`:
```yaml
  - name: message-edit-delete
    url: http://message-service:8004
    routes:
      - name: message-edit-delete-route
        paths:
          - /messages/edit
          - /messages/delete
        methods:
          - PATCH
          - DELETE
          - OPTIONS
        strip_path: false
    plugins:
      - name: rate-limiting
        config:
          minute: 30
          policy: local
```

- [ ] **Step 2: Commit**

```bash
git add infra/kong/kong.yml
git commit -m "feat(kong): add routes for message edit and delete endpoints"
```

### Task 1.6: Frontend — add edit/delete to ChatContext, MessageList, and WebSocket handler

**Files:**
- Modify: `frontend/src/context/ChatContext.jsx`
- Modify: `frontend/src/components/chat/MessageList.jsx`
- Modify: `frontend/src/hooks/useMultiRoomChat.js`
- Create: `frontend/src/services/messageApi.js`

- [ ] **Step 1: Create messageApi service**

Create `frontend/src/services/messageApi.js`:
```javascript
import http from './http';

export function editMessage(messageId, content) {
  return http.patch(`/messages/edit/${messageId}`, { content });
}

export function deleteMessage(messageId) {
  return http.delete(`/messages/delete/${messageId}`);
}
```

- [ ] **Step 2: Add reducer actions for edit/delete in ChatContext**

Add to `frontend/src/context/ChatContext.jsx` action types and reducer cases:

Action types (add constants):
```javascript
// Add to action type handling in chatReducer
case 'EDIT_MESSAGE': {
  const { roomId, msgId, newText, editedAt } = action;
  const roomMsgs = state.messages[roomId] || [];
  return {
    ...state,
    messages: {
      ...state.messages,
      [roomId]: roomMsgs.map(m =>
        m.msg_id === msgId ? { ...m, text: newText, edited_at: editedAt } : m
      ),
    },
  };
}
case 'DELETE_MESSAGE': {
  const { roomId, msgId } = action;
  const roomMsgs = state.messages[roomId] || [];
  return {
    ...state,
    messages: {
      ...state.messages,
      [roomId]: roomMsgs.map(m =>
        m.msg_id === msgId ? { ...m, text: '[deleted]', is_deleted: true } : m
      ),
    },
  };
}
```

- [ ] **Step 3: Handle WebSocket events in useMultiRoomChat**

Add to the WebSocket message handler switch in `frontend/src/hooks/useMultiRoomChat.js`:
```javascript
case 'message_edited':
  dispatch({
    type: 'EDIT_MESSAGE',
    roomId: data.room_id,
    msgId: data.msg_id,
    newText: data.text,
    editedAt: data.timestamp,
  });
  break;

case 'message_deleted':
  dispatch({
    type: 'DELETE_MESSAGE',
    roomId: data.room_id,
    msgId: data.msg_id,
  });
  break;
```

- [ ] **Step 4: Update MessageList to show edit/delete controls and edited badge**

Modify `frontend/src/components/chat/MessageList.jsx` to:
1. Track `msg_id` in the message object (already passed from WebSocket)
2. Show "(edited)" label when `edited_at` is set
3. Show edit/delete buttons on hover for own messages
4. Render `[deleted]` in muted style for deleted messages

Add to message rendering:
```jsx
{/* After the message text span */}
{m.edited_at && !m.is_deleted && (
  <span className="msg-edited-badge">(edited)</span>
)}

{/* Delete message styling */}
{m.is_deleted && (
  <span className="msg-deleted-text">[deleted]</span>
)}

{/* Edit/delete controls on hover — only for own messages */}
{m.from === currentUser && !m.isSystem && !m.is_deleted && (
  <span className="msg-actions">
    <button
      className="msg-action-btn"
      title="Edit"
      onClick={() => onEditMessage(m.msg_id, m.text)}
    >✏️</button>
    <button
      className="msg-action-btn"
      title="Delete"
      onClick={() => onDeleteMessage(m.msg_id)}
    >🗑️</button>
  </span>
)}
```

Add new props to MessageList:
```javascript
function MessageList({ messages, onScrollToBottom, currentUser, onEditMessage, onDeleteMessage })
```

- [ ] **Step 5: Add edit mode to MessageInput**

Modify `frontend/src/components/chat/MessageInput.jsx` to accept an `editingMessage` prop:
```javascript
function MessageInput({ onSend, roomName, roomId, isPM, editingMessage, onCancelEdit }) {
  // If editingMessage is set, pre-fill the input and change the submit behavior
  useEffect(() => {
    if (editingMessage) {
      setText(editingMessage.text);
    }
  }, [editingMessage]);

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;

    if (editingMessage) {
      // Send edit via WebSocket
      onSend(trimmed, editingMessage.msgId);
      onCancelEdit();
    } else {
      onSend(trimmed);
    }
    setText('');
  }

  return (
    <form onSubmit={handleSubmit}>
      {editingMessage && (
        <div className="edit-banner">
          Editing message
          <button type="button" onClick={onCancelEdit}>Cancel</button>
        </div>
      )}
      {/* ...existing input... */}
    </form>
  );
}
```

- [ ] **Step 6: Wire edit/delete in ChatPage**

Add to `frontend/src/pages/ChatPage.jsx`:
```javascript
const [editingMessage, setEditingMessage] = useState(null);

function handleEditMessage(msgId, text) {
  setEditingMessage({ msgId, text });
}

function handleDeleteMessage(msgId) {
  if (!confirm('Delete this message?')) return;
  const ws = socketsRef.current?.get(chatState.activeRoomId);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'delete_message', msg_id: msgId }));
  }
}

function handleSend(text, editMsgId) {
  if (editMsgId) {
    // Edit mode — send edit via WebSocket
    const ws = socketsRef.current?.get(chatState.activeRoomId);
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'edit_message', msg_id: editMsgId, text }));
    }
  } else {
    // Normal send
    sendMessage(chatState.activeRoomId, { type: 'message', text });
  }
}
```

- [ ] **Step 7: Add CSS styles**

Add to `frontend/src/App.css`:
```css
.msg-edited-badge {
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-left: 4px;
  font-style: italic;
}

.msg-deleted-text {
  color: var(--text-muted);
  font-style: italic;
}

.msg-actions {
  display: none;
  margin-left: 8px;
  gap: 2px;
}

.msg:hover .msg-actions {
  display: inline-flex;
}

.msg-action-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.8rem;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  opacity: 0.6;
}

.msg-action-btn:hover {
  opacity: 1;
  background: var(--surface-hover);
}

.edit-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  background: var(--surface);
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  color: var(--accent);
  margin-bottom: 4px;
}
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/services/messageApi.js \
      frontend/src/context/ChatContext.jsx \
      frontend/src/hooks/useMultiRoomChat.js \
      frontend/src/components/chat/MessageList.jsx \
      frontend/src/components/chat/MessageInput.jsx \
      frontend/src/pages/ChatPage.jsx \
      frontend/src/App.css
git commit -m "feat(frontend): add message editing and deletion UI"
```

### Task 1.7: Add Kafka event contract for edit/delete

**Files:**
- Create: `services/contracts/events/chat.edit.schema.json`
- Create: `services/contracts/events/chat.delete.schema.json`

- [ ] **Step 1: Create edit event schema**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Chat Message Edit Event",
  "description": "Produced by chat-service when a user edits a message",
  "topic": "chat.messages",
  "key": "msg_id",
  "producer": "Chat Service (Go)",
  "consumer": "Message Service (Python)",
  "type": "object",
  "required": ["type", "msg_id", "sender_id", "text", "timestamp"],
  "properties": {
    "type": { "const": "edit_message" },
    "room_id": { "type": "integer" },
    "sender_id": { "type": "integer" },
    "username": { "type": "string" },
    "msg_id": { "type": "string", "format": "uuid" },
    "text": { "type": "string", "maxLength": 10000 },
    "timestamp": { "type": "string", "format": "date-time" }
  }
}
```

- [ ] **Step 2: Create delete event schema**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Chat Message Delete Event",
  "description": "Produced by chat-service when a user deletes a message",
  "topic": "chat.messages",
  "key": "msg_id",
  "producer": "Chat Service (Go)",
  "consumer": "Message Service (Python)",
  "type": "object",
  "required": ["type", "msg_id", "sender_id", "timestamp"],
  "properties": {
    "type": { "const": "delete_message" },
    "room_id": { "type": "integer" },
    "sender_id": { "type": "integer" },
    "username": { "type": "string" },
    "msg_id": { "type": "string", "format": "uuid" },
    "timestamp": { "type": "string", "format": "date-time" }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add services/contracts/events/chat.edit.schema.json \
      services/contracts/events/chat.delete.schema.json
git commit -m "docs(contracts): add Kafka event schemas for message edit and delete"
```

---

## Feature 2: Emoji Reactions

### Task 2.1: Create reactions table in message-service

**Files:**
- Create: `services/message-service/alembic/versions/004_create_reactions_table.py`
- Modify: `services/message-service/app/models/__init__.py`

- [ ] **Step 1: Create migration**

```python
"""Create reactions table

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("message_id", sa.String(36), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("emoji", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction_per_user_per_emoji"),
    )


def downgrade() -> None:
    op.drop_table("reactions")
```

- [ ] **Step 2: Add Reaction model**

Add to `services/message-service/app/models/__init__.py`:
```python
class Reaction(Base):
    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True)
    message_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(64), nullable=False)
    emoji = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction_per_user_per_emoji"),
    )
```

- [ ] **Step 3: Commit**

```bash
git add services/message-service/alembic/versions/004_create_reactions_table.py \
      services/message-service/app/models/__init__.py
git commit -m "feat(message-service): create reactions table and model"
```

### Task 2.2: Add reaction DAL and API endpoints

**Files:**
- Create: `services/message-service/app/dal/reaction_dal.py`
- Create: `services/message-service/app/schemas/reaction.py`
- Modify: `services/message-service/app/routers/messages.py`
- Create: `services/message-service/tests/test_dal_reactions.py`

- [ ] **Step 1: Write failing DAL tests**

Create `services/message-service/tests/test_dal_reactions.py`:
```python
import pytest
from app.dal.reaction_dal import add_reaction, remove_reaction, get_reactions_for_message


class TestAddReaction:
    def test_add_reaction_returns_true(self, db_session):
        result = add_reaction(db_session, message_id="msg-1", user_id=1, username="alice", emoji="👍")
        assert result is True

    def test_add_duplicate_reaction_returns_false(self, db_session):
        add_reaction(db_session, message_id="msg-1", user_id=1, username="alice", emoji="👍")
        result = add_reaction(db_session, message_id="msg-1", user_id=1, username="alice", emoji="👍")
        assert result is False

    def test_same_user_different_emoji_allowed(self, db_session):
        add_reaction(db_session, message_id="msg-1", user_id=1, username="alice", emoji="👍")
        result = add_reaction(db_session, message_id="msg-1", user_id=1, username="alice", emoji="❤️")
        assert result is True


class TestRemoveReaction:
    def test_remove_existing_reaction_returns_true(self, db_session):
        add_reaction(db_session, message_id="msg-1", user_id=1, username="alice", emoji="👍")
        result = remove_reaction(db_session, message_id="msg-1", user_id=1, emoji="👍")
        assert result is True

    def test_remove_nonexistent_reaction_returns_false(self, db_session):
        result = remove_reaction(db_session, message_id="msg-1", user_id=1, emoji="👍")
        assert result is False


class TestGetReactions:
    def test_get_reactions_for_message(self, db_session):
        add_reaction(db_session, message_id="msg-1", user_id=1, username="alice", emoji="👍")
        add_reaction(db_session, message_id="msg-1", user_id=2, username="bob", emoji="👍")
        add_reaction(db_session, message_id="msg-1", user_id=1, username="alice", emoji="❤️")

        reactions = get_reactions_for_message(db_session, message_id="msg-1")
        assert len(reactions) == 3

    def test_get_reactions_empty_returns_empty_list(self, db_session):
        reactions = get_reactions_for_message(db_session, message_id="nonexistent")
        assert reactions == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/message-service && python -m pytest tests/test_dal_reactions.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement reaction DAL**

Create `services/message-service/app/dal/reaction_dal.py`:
```python
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import Reaction


def add_reaction(db: Session, message_id: str, user_id: int, username: str, emoji: str) -> bool:
    """Add a reaction. Returns False if already exists (unique constraint)."""
    try:
        reaction = Reaction(
            message_id=message_id,
            user_id=user_id,
            username=username,
            emoji=emoji,
        )
        db.add(reaction)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def remove_reaction(db: Session, message_id: str, user_id: int, emoji: str) -> bool:
    """Remove a reaction. Returns False if not found."""
    count = (
        db.query(Reaction)
        .filter_by(message_id=message_id, user_id=user_id, emoji=emoji)
        .delete()
    )
    db.commit()
    return count > 0


def get_reactions_for_message(db: Session, message_id: str) -> list[Reaction]:
    """Get all reactions for a message."""
    return db.query(Reaction).filter_by(message_id=message_id).all()


def get_reactions_for_messages(db: Session, message_ids: list[str]) -> dict[str, list[dict]]:
    """Get reactions for multiple messages, grouped by message_id.
    Returns: { message_id: [{ emoji, username, user_id }] }
    """
    if not message_ids:
        return {}
    reactions = db.query(Reaction).filter(Reaction.message_id.in_(message_ids)).all()
    grouped: dict[str, list[dict]] = {}
    for r in reactions:
        grouped.setdefault(r.message_id, []).append({
            "emoji": r.emoji,
            "username": r.username,
            "user_id": r.user_id,
        })
    return grouped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/message-service && python -m pytest tests/test_dal_reactions.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Create reaction schema**

Create `services/message-service/app/schemas/reaction.py`:
```python
from pydantic import BaseModel, Field


class ReactionResponse(BaseModel):
    emoji: str
    username: str
    user_id: int


class AddReactionRequest(BaseModel):
    message_id: str = Field(..., min_length=1)
    emoji: str = Field(..., min_length=1, max_length=32)
```

- [ ] **Step 6: Add reaction API endpoints**

Add to `services/message-service/app/routers/messages.py`:
```python
from app.dal.reaction_dal import get_reactions_for_messages


@router.get("/messages/{message_id}/reactions")
def get_reactions(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.dal.reaction_dal import get_reactions_for_message
    reactions = get_reactions_for_message(db, message_id=message_id)
    return [
        {"emoji": r.emoji, "username": r.username, "user_id": r.user_id}
        for r in reactions
    ]
```

Also modify the existing history/replay endpoints to include reactions in the response. In `get_room_history` and `get_messages_since`, after fetching messages:
```python
# After fetching messages, enrich with reactions
msg_ids = [m.message_id for m in messages if m.message_id]
reactions_map = get_reactions_for_messages(db, msg_ids) if msg_ids else {}

return [
    {
        **MessageResponse.model_validate(m).model_dump(),
        "reactions": reactions_map.get(m.message_id, []),
    }
    for m in messages
]
```

- [ ] **Step 7: Commit**

```bash
git add services/message-service/app/dal/reaction_dal.py \
      services/message-service/app/schemas/reaction.py \
      services/message-service/app/routers/messages.py \
      services/message-service/tests/test_dal_reactions.py
git commit -m "feat(message-service): add emoji reaction DAL and API endpoints"
```

### Task 2.3: Add reaction WebSocket handler in chat-service

**Files:**
- Create: `services/chat-service/internal/handler/ws_reaction.go`
- Modify: `services/chat-service/internal/handler/websocket.go`

- [ ] **Step 1: Create reaction WebSocket handler**

Create `services/chat-service/internal/handler/ws_reaction.go`:
```go
package handler

import (
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

func (h *WebSocketHandler) handleAddReaction(
	conn *websocket.Conn,
	roomID, userID int,
	username string,
	msg IncomingMessage,
) {
	msgID := strings.TrimSpace(msg.MessageID)
	emoji := strings.TrimSpace(msg.Emoji)

	if msgID == "" || emoji == "" {
		h.sendError(conn, "add_reaction requires msg_id and emoji")
		return
	}

	payload := map[string]interface{}{
		"type":      "reaction_added",
		"room_id":   roomID,
		"msg_id":    msgID,
		"emoji":     emoji,
		"user_id":   userID,
		"username":  username,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	h.manager.BroadcastRoom(roomID, payload)

	// Persist via Kafka
	h.produceEvent("chat.messages", msgID, map[string]interface{}{
		"type":      "add_reaction",
		"room_id":   roomID,
		"sender_id": userID,
		"username":  username,
		"msg_id":    msgID,
		"emoji":     emoji,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	})

	h.logger.Debug("reaction added",
		zap.String("msg_id", msgID),
		zap.String("emoji", emoji),
		zap.String("user", username),
	)
}

func (h *WebSocketHandler) handleRemoveReaction(
	conn *websocket.Conn,
	roomID, userID int,
	username string,
	msg IncomingMessage,
) {
	msgID := strings.TrimSpace(msg.MessageID)
	emoji := strings.TrimSpace(msg.Emoji)

	if msgID == "" || emoji == "" {
		h.sendError(conn, "remove_reaction requires msg_id and emoji")
		return
	}

	payload := map[string]interface{}{
		"type":      "reaction_removed",
		"room_id":   roomID,
		"msg_id":    msgID,
		"emoji":     emoji,
		"user_id":   userID,
		"username":  username,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	h.manager.BroadcastRoom(roomID, payload)

	h.produceEvent("chat.messages", msgID, map[string]interface{}{
		"type":      "remove_reaction",
		"room_id":   roomID,
		"sender_id": userID,
		"username":  username,
		"msg_id":    msgID,
		"emoji":     emoji,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	})

	h.logger.Debug("reaction removed",
		zap.String("msg_id", msgID),
		zap.String("emoji", emoji),
		zap.String("user", username),
	)
}
```

- [ ] **Step 2: Add Emoji field to IncomingMessage and route new types**

Modify `services/chat-service/internal/handler/websocket.go`:
```go
type IncomingMessage struct {
	Type      string `json:"type"`
	Text      string `json:"text"`
	Target    string `json:"target"`
	To        string `json:"to"`
	MessageID string `json:"msg_id"`
	Emoji     string `json:"emoji"` // NEW: for reactions
}
```

Add to the message type switch:
```go
case "add_reaction":
    h.handleAddReaction(conn, roomID, userID, username, msg)
case "remove_reaction":
    h.handleRemoveReaction(conn, roomID, userID, username, msg)
```

- [ ] **Step 3: Handle reaction events in message-service Kafka consumer**

Add to `services/message-service/app/consumers/persistence_consumer.py`:
```python
async def _handle_add_reaction(self, db: Session, value: dict) -> None:
    from app.dal.reaction_dal import add_reaction
    msg_id = value.get("msg_id")
    sender_id = value.get("sender_id")
    username = value.get("username", "")
    emoji = value.get("emoji", "")
    if msg_id and sender_id and emoji:
        add_reaction(db, message_id=msg_id, user_id=sender_id, username=username, emoji=emoji)

async def _handle_remove_reaction(self, db: Session, value: dict) -> None:
    from app.dal.reaction_dal import remove_reaction
    msg_id = value.get("msg_id")
    sender_id = value.get("sender_id")
    emoji = value.get("emoji", "")
    if msg_id and sender_id and emoji:
        remove_reaction(db, message_id=msg_id, user_id=sender_id, emoji=emoji)
```

Add to the type routing:
```python
elif msg_type == "add_reaction":
    await self._handle_add_reaction(db, value)
elif msg_type == "remove_reaction":
    await self._handle_remove_reaction(db, value)
```

- [ ] **Step 4: Commit**

```bash
git add services/chat-service/internal/handler/ws_reaction.go \
      services/chat-service/internal/handler/websocket.go \
      services/message-service/app/consumers/persistence_consumer.py
git commit -m "feat: add emoji reaction WebSocket handlers and Kafka persistence"
```

### Task 2.4: Frontend — emoji picker and reaction display

**Files:**
- Modify: `frontend/src/context/ChatContext.jsx`
- Modify: `frontend/src/components/chat/MessageList.jsx`
- Modify: `frontend/src/hooks/useMultiRoomChat.js`
- Modify: `frontend/package.json`

- [ ] **Step 1: Install emoji picker library**

Run: `cd frontend && npm install @emoji-mart/react @emoji-mart/data`

- [ ] **Step 2: Add reaction state to ChatContext**

Add new reducer cases to `frontend/src/context/ChatContext.jsx`:
```javascript
case 'ADD_REACTION': {
  const { roomId, msgId, emoji, username, userId } = action;
  const roomMsgs = state.messages[roomId] || [];
  return {
    ...state,
    messages: {
      ...state.messages,
      [roomId]: roomMsgs.map(m => {
        if (m.msg_id !== msgId) return m;
        const reactions = [...(m.reactions || [])];
        // Avoid duplicates
        const exists = reactions.some(r => r.emoji === emoji && r.user_id === userId);
        if (!exists) reactions.push({ emoji, username, user_id: userId });
        return { ...m, reactions };
      }),
    },
  };
}
case 'REMOVE_REACTION': {
  const { roomId, msgId, emoji, userId } = action;
  const roomMsgs = state.messages[roomId] || [];
  return {
    ...state,
    messages: {
      ...state.messages,
      [roomId]: roomMsgs.map(m => {
        if (m.msg_id !== msgId) return m;
        return {
          ...m,
          reactions: (m.reactions || []).filter(
            r => !(r.emoji === emoji && r.user_id === userId)
          ),
        };
      }),
    },
  };
}
```

- [ ] **Step 3: Handle WebSocket events in useMultiRoomChat**

Add to the message handler switch:
```javascript
case 'reaction_added':
  dispatch({
    type: 'ADD_REACTION',
    roomId: data.room_id,
    msgId: data.msg_id,
    emoji: data.emoji,
    username: data.username,
    userId: data.user_id,
  });
  break;

case 'reaction_removed':
  dispatch({
    type: 'REMOVE_REACTION',
    roomId: data.room_id,
    msgId: data.msg_id,
    emoji: data.emoji,
    userId: data.user_id,
  });
  break;
```

- [ ] **Step 4: Add reaction display and picker to MessageList**

Add to each message in `MessageList.jsx`:
```jsx
import { useState, useRef } from 'react';
import data from '@emoji-mart/data';
import Picker from '@emoji-mart/react';

// Inside the message render, after the message text:
{m.reactions?.length > 0 && (
  <div className="msg-reactions">
    {Object.entries(
      m.reactions.reduce((acc, r) => {
        acc[r.emoji] = acc[r.emoji] || { emoji: r.emoji, users: [] };
        acc[r.emoji].users.push(r.username);
        return acc;
      }, {})
    ).map(([emoji, { users }]) => (
      <button
        key={emoji}
        className={`reaction-chip ${users.includes(currentUser) ? 'reaction-mine' : ''}`}
        title={users.join(', ')}
        onClick={() => {
          if (users.includes(currentUser)) {
            onRemoveReaction(m.msg_id, emoji);
          } else {
            onAddReaction(m.msg_id, emoji);
          }
        }}
      >
        {emoji} {users.length}
      </button>
    ))}
    <button
      className="reaction-add-btn"
      onClick={() => setPickerMsgId(m.msg_id === pickerMsgId ? null : m.msg_id)}
    >
      +
    </button>
  </div>
)}

{/* Emoji picker popover */}
{pickerMsgId === m.msg_id && (
  <div className="emoji-picker-popover">
    <Picker
      data={data}
      onEmojiSelect={(e) => {
        onAddReaction(m.msg_id, e.native);
        setPickerMsgId(null);
      }}
      theme="dark"
      previewPosition="none"
      skinTonePosition="none"
    />
  </div>
)}
```

Add new props:
```javascript
function MessageList({
  messages, onScrollToBottom, currentUser,
  onEditMessage, onDeleteMessage,
  onAddReaction, onRemoveReaction
})
```

- [ ] **Step 5: Wire reaction handlers in ChatPage**

Add to `ChatPage.jsx`:
```javascript
function handleAddReaction(msgId, emoji) {
  const ws = socketsRef.current?.get(chatState.activeRoomId);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'add_reaction', msg_id: msgId, emoji }));
  }
}

function handleRemoveReaction(msgId, emoji) {
  const ws = socketsRef.current?.get(chatState.activeRoomId);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'remove_reaction', msg_id: msgId, emoji }));
  }
}
```

- [ ] **Step 6: Add CSS for reactions**

Add to `frontend/src/App.css`:
```css
.msg-reactions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.reaction-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 12px;
  border: 1px solid var(--surface-hover);
  background: var(--surface);
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.15s;
}

.reaction-chip:hover {
  background: var(--surface-hover);
}

.reaction-mine {
  border-color: var(--accent);
  background: rgba(14, 165, 233, 0.15);
}

.reaction-add-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 12px;
  border: 1px dashed var(--surface-hover);
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.8rem;
}

.reaction-add-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.emoji-picker-popover {
  position: absolute;
  z-index: 100;
  margin-top: 4px;
}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json \
      frontend/src/context/ChatContext.jsx \
      frontend/src/hooks/useMultiRoomChat.js \
      frontend/src/components/chat/MessageList.jsx \
      frontend/src/pages/ChatPage.jsx \
      frontend/src/App.css
git commit -m "feat(frontend): add emoji reactions with picker and inline display"
```

---

## Feature 3: @Mentions & Browser Notifications

### Task 3.1: Parse @mentions in chat-service

**Files:**
- Create: `services/chat-service/internal/handler/ws_mention.go`
- Modify: `services/chat-service/internal/handler/ws_message.go`

- [ ] **Step 1: Create mention parser and notification broadcaster**

Create `services/chat-service/internal/handler/ws_mention.go`:
```go
package handler

import (
	"regexp"
	"strings"
)

var mentionRegex = regexp.MustCompile(`@(\w+)`)

// parseMentions extracts @usernames from message text.
// Returns a list of unique mentioned usernames (lowercase).
func parseMentions(text string) []string {
	matches := mentionRegex.FindAllStringSubmatch(text, -1)
	seen := make(map[string]bool)
	var mentions []string
	for _, match := range matches {
		username := strings.ToLower(match[1])
		if !seen[username] {
			seen[username] = true
			mentions = append(mentions, username)
		}
	}
	return mentions
}

// isRoomMention returns true if the text contains @room or @channel or @everyone
func isRoomMention(text string) bool {
	lower := strings.ToLower(text)
	return strings.Contains(lower, "@room") ||
		strings.Contains(lower, "@channel") ||
		strings.Contains(lower, "@everyone")
}
```

- [ ] **Step 2: Modify message broadcast to include mentions**

In `services/chat-service/internal/handler/ws_message.go`, after building the broadcast payload, add:
```go
// Parse mentions from message text
mentions := parseMentions(text)
isRoom := isRoomMention(text)

broadcastPayload["mentions"] = mentions
broadcastPayload["mention_room"] = isRoom
```

- [ ] **Step 3: Commit**

```bash
git add services/chat-service/internal/handler/ws_mention.go \
      services/chat-service/internal/handler/ws_message.go
git commit -m "feat(chat-service): parse @mentions in messages and include in broadcast"
```

### Task 3.2: Frontend — highlight mentions and browser notifications

**Files:**
- Modify: `frontend/src/components/chat/MessageList.jsx`
- Modify: `frontend/src/hooks/useMultiRoomChat.js`
- Create: `frontend/src/utils/notifications.js`

- [ ] **Step 1: Create notification utility**

Create `frontend/src/utils/notifications.js`:
```javascript
let permissionGranted = false;

export async function requestNotificationPermission() {
  if (!('Notification' in window)) return false;
  if (Notification.permission === 'granted') {
    permissionGranted = true;
    return true;
  }
  if (Notification.permission === 'denied') return false;
  const result = await Notification.requestPermission();
  permissionGranted = result === 'granted';
  return permissionGranted;
}

export function sendBrowserNotification(title, body, onClick) {
  if (!permissionGranted || document.hasFocus()) return;
  const notification = new Notification(title, {
    body,
    icon: '/logo.png',
    tag: 'chatbox-mention',
  });
  if (onClick) {
    notification.onclick = () => {
      window.focus();
      onClick();
      notification.close();
    };
  }
  setTimeout(() => notification.close(), 5000);
}
```

- [ ] **Step 2: Request permission on login and send notifications on mention**

In `frontend/src/hooks/useMultiRoomChat.js`, import and call:
```javascript
import { requestNotificationPermission, sendBrowserNotification } from '../utils/notifications';

// On mount (inside useEffect):
requestNotificationPermission();

// In the WebSocket message handler, for 'message' type:
if (data.mentions?.includes(currentUsername.toLowerCase()) || data.mention_room) {
  sendBrowserNotification(
    `@${data.from} in #${roomName}`,
    data.text.substring(0, 100),
    () => dispatch({ type: 'SET_ACTIVE_ROOM', roomId: data.room_id })
  );
}
```

- [ ] **Step 3: Highlight @mentions in message text**

Modify `frontend/src/components/chat/MessageList.jsx` to render mentions:
```javascript
function renderMessageText(text, currentUser) {
  if (!text) return text;
  const parts = text.split(/(@\w+)/g);
  return parts.map((part, i) => {
    if (part.startsWith('@')) {
      const isSelf = part.toLowerCase() === `@${currentUser.toLowerCase()}`;
      return (
        <span key={i} className={`mention ${isSelf ? 'mention-self' : ''}`}>
          {part}
        </span>
      );
    }
    return part;
  });
}
```

Use `renderMessageText(m.text, currentUser)` instead of raw `m.text` in the message render.

- [ ] **Step 4: Add CSS for mentions**

Add to `frontend/src/App.css`:
```css
.mention {
  color: var(--accent);
  font-weight: 600;
  background: rgba(14, 165, 233, 0.1);
  padding: 0 2px;
  border-radius: 3px;
}

.mention-self {
  background: rgba(14, 165, 233, 0.25);
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/notifications.js \
      frontend/src/hooks/useMultiRoomChat.js \
      frontend/src/components/chat/MessageList.jsx \
      frontend/src/App.css
git commit -m "feat(frontend): add @mention highlighting and browser notifications"
```

---

## Feature 4: Typing Indicators

### Task 4.1: Add typing event handling in chat-service

**Files:**
- Modify: `services/chat-service/internal/handler/websocket.go`

- [ ] **Step 1: Add typing handler**

Add a case to the message type switch in the WebSocket handler:
```go
case "typing":
    // Broadcast typing indicator to room (except sender)
    typingPayload := map[string]interface{}{
        "type":     "typing",
        "room_id":  roomID,
        "username": username,
    }
    // Broadcast to room but skip the sender's connection
    h.manager.BroadcastRoomExcept(roomID, conn, typingPayload)
```

- [ ] **Step 2: Add BroadcastRoomExcept to manager**

Add to `services/chat-service/internal/ws/manager_room.go`:
```go
// BroadcastRoomExcept sends a message to all connections in a room except the given connection.
func (m *Manager) BroadcastRoomExcept(roomID int, except *websocket.Conn, msg interface{}) {
	m.mu.RLock()
	conns := m.rooms[roomID]
	m.mu.RUnlock()

	for c := range conns {
		if c != except {
			m.SendToConn(c, msg)
		}
	}
}
```

- [ ] **Step 3: Commit**

```bash
git add services/chat-service/internal/handler/websocket.go \
      services/chat-service/internal/ws/manager_room.go
git commit -m "feat(chat-service): add typing indicator WebSocket broadcast"
```

### Task 4.2: Frontend typing indicator

**Files:**
- Modify: `frontend/src/hooks/useMultiRoomChat.js`
- Modify: `frontend/src/context/ChatContext.jsx`
- Modify: `frontend/src/components/chat/MessageList.jsx`

- [ ] **Step 1: Add typing state to ChatContext**

Add reducer case:
```javascript
case 'SET_TYPING': {
  const { roomId, username, isTyping } = action;
  const current = state.typingUsers?.[roomId] || {};
  const updated = { ...current };
  if (isTyping) {
    updated[username] = Date.now();
  } else {
    delete updated[username];
  }
  return {
    ...state,
    typingUsers: { ...state.typingUsers, [roomId]: updated },
  };
}
```

Add `typingUsers: {}` to `initialState`.

- [ ] **Step 2: Handle typing in useMultiRoomChat**

Add to the WebSocket message handler:
```javascript
case 'typing':
  dispatch({
    type: 'SET_TYPING',
    roomId: data.room_id,
    username: data.username,
    isTyping: true,
  });
  // Auto-clear after 3 seconds
  setTimeout(() => {
    dispatch({
      type: 'SET_TYPING',
      roomId: data.room_id,
      username: data.username,
      isTyping: false,
    });
  }, 3000);
  break;
```

Add a `sendTyping` function:
```javascript
function sendTyping(roomId) {
  const ws = socketsRef.current?.get(roomId);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'typing' }));
  }
}
```

Return `sendTyping` from the hook.

- [ ] **Step 3: Emit typing events from MessageInput**

Modify `frontend/src/components/chat/MessageInput.jsx`:
```javascript
// Add prop: onTyping
// Inside the input onChange handler, debounce typing emission:
const typingTimeoutRef = useRef(null);

function handleChange(e) {
  setText(e.target.value);
  if (onTyping && !typingTimeoutRef.current) {
    onTyping();
    typingTimeoutRef.current = setTimeout(() => {
      typingTimeoutRef.current = null;
    }, 2000);
  }
}
```

- [ ] **Step 4: Show typing indicator below messages**

Add to `MessageList.jsx` (below the message list):
```jsx
{typingUsers && Object.keys(typingUsers).length > 0 && (
  <div className="typing-indicator">
    {Object.keys(typingUsers).join(', ')}
    {Object.keys(typingUsers).length === 1 ? ' is' : ' are'} typing
    <span className="typing-dots">
      <span>.</span><span>.</span><span>.</span>
    </span>
  </div>
)}
```

- [ ] **Step 5: Add CSS for typing indicator**

```css
.typing-indicator {
  padding: 4px 12px;
  font-size: 0.8rem;
  color: var(--text-muted);
  font-style: italic;
  min-height: 20px;
}

.typing-dots span {
  animation: typingBlink 1.4s infinite;
  animation-fill-mode: both;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typingBlink {
  0%, 80%, 100% { opacity: 0; }
  40% { opacity: 1; }
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/context/ChatContext.jsx \
      frontend/src/hooks/useMultiRoomChat.js \
      frontend/src/components/chat/MessageInput.jsx \
      frontend/src/components/chat/MessageList.jsx \
      frontend/src/App.css
git commit -m "feat(frontend): add typing indicators with debounced emission"
```

---

## Feature 5: Markdown Formatting

### Task 5.1: Add markdown rendering to frontend

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/components/chat/MessageList.jsx`

- [ ] **Step 1: Install markdown library**

Run: `cd frontend && npm install react-markdown remark-gfm`

- [ ] **Step 2: Create markdown renderer component**

Create `frontend/src/components/chat/MarkdownMessage.jsx`:
```jsx
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const ALLOWED_ELEMENTS = [
  'p', 'strong', 'em', 'del', 'code', 'pre', 'a',
  'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3',
  'br', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
];

export default function MarkdownMessage({ text }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      allowedElements={ALLOWED_ELEMENTS}
      unwrapDisallowed
      components={{
        // Open links in new tab
        a: ({ children, href, ...props }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
            {children}
          </a>
        ),
        // Inline code styling
        code: ({ children, className, ...props }) => {
          const isBlock = className?.includes('language-');
          return isBlock ? (
            <pre className="code-block">
              <code className={className} {...props}>{children}</code>
            </pre>
          ) : (
            <code className="inline-code" {...props}>{children}</code>
          );
        },
        // Remove wrapping <p> for single-line messages
        p: ({ children }) => <>{children}</>,
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
```

- [ ] **Step 3: Use MarkdownMessage in MessageList**

Replace raw `{m.text}` with `<MarkdownMessage text={m.text} />` for regular messages (not system, not deleted).

- [ ] **Step 4: Add CSS for markdown elements**

```css
.inline-code {
  background: var(--surface-hover);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 0.85em;
}

.code-block {
  background: rgba(0, 0, 0, 0.3);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  font-family: var(--mono);
  font-size: 0.85em;
  margin: 4px 0;
}

.msg-text blockquote {
  border-left: 3px solid var(--accent);
  padding-left: 8px;
  margin: 4px 0;
  color: var(--text-secondary);
}

.msg-text a {
  color: var(--accent);
  text-decoration: underline;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json \
      frontend/src/components/chat/MarkdownMessage.jsx \
      frontend/src/components/chat/MessageList.jsx \
      frontend/src/App.css
git commit -m "feat(frontend): add markdown rendering for chat messages"
```

---

## Feature 6: Inline Image Previews

### Task 6.1: Detect image files and render inline

**Files:**
- Modify: `frontend/src/components/chat/MessageList.jsx`

- [ ] **Step 1: Create image detection utility**

Add to `frontend/src/utils/formatting.js`:
```javascript
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']);

export function isImageFile(filename) {
  if (!filename) return false;
  const ext = filename.toLowerCase().slice(filename.lastIndexOf('.'));
  return IMAGE_EXTENSIONS.has(ext);
}
```

- [ ] **Step 2: Render inline image preview for file messages**

In `MessageList.jsx`, modify the file message rendering:
```jsx
import { isImageFile } from '../../utils/formatting';

// Replace the file message section:
{m.isFile && (
  <div className="msg-file-content">
    {isImageFile(m.text) ? (
      <div className="msg-image-preview">
        <img
          src={`${API_BASE}/files/download/${m.fileId}?token=${sessionStorage.getItem('token')}`}
          alt={m.text}
          className="msg-inline-image"
          loading="lazy"
          onClick={() => window.open(
            `${API_BASE}/files/download/${m.fileId}?token=${sessionStorage.getItem('token')}`,
            '_blank'
          )}
        />
        <span className="msg-file-name">{m.text}</span>
      </div>
    ) : (
      <a className="file-download-link" onClick={() => downloadFile(m.fileId, m.text)}>
        📎 {m.text} ({formatSize(m.fileSize)})
      </a>
    )}
  </div>
)}
```

- [ ] **Step 3: Add CSS for inline images**

```css
.msg-inline-image {
  max-width: 400px;
  max-height: 300px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: opacity 0.15s;
  display: block;
  margin: 4px 0;
}

.msg-inline-image:hover {
  opacity: 0.9;
}

.msg-image-preview {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.msg-file-name {
  font-size: 0.75rem;
  color: var(--text-muted);
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/utils/formatting.js \
      frontend/src/components/chat/MessageList.jsx \
      frontend/src/App.css
git commit -m "feat(frontend): add inline image previews for shared images"
```

---

## Features 7-10: Remaining Critical Features

Due to plan size constraints, features 7-10 will be in a continuation document.

### Feature 7: Message Search
- Add PostgreSQL full-text search index to messages table
- New `GET /messages/search?q=...&room_id=...` endpoint
- Frontend search modal with results and navigation

### Feature 8: Two-Factor Authentication (2FA)
- Add `totp_secret` and `totp_enabled` columns to users table
- TOTP setup endpoint (generate secret + QR code)
- TOTP verification on login
- Recovery codes

### Feature 9: Link Previews (URL Unfurling)
- Backend endpoint that fetches Open Graph metadata from URLs
- Cache previews in Redis (1-hour TTL)
- Frontend renders preview cards below messages containing URLs

### Feature 10: Read Position Tracking
- Add `read_positions` table (user_id, room_id, last_read_msg_id)
- WebSocket event to update read position on scroll
- "New messages" divider in MessageList

---

## Verification Checklist

After implementing all features, verify:

- [ ] All existing tests still pass: `pytest`, `go test`, `vitest`
- [ ] New tests pass with required coverage thresholds
- [ ] Docker Compose builds successfully: `docker compose build`
- [ ] Application starts and all health checks pass
- [ ] Manual testing: edit a message, delete a message, add a reaction, @mention someone, see typing indicator, send markdown, share an image inline
- [ ] WebSocket reconnection still works after all changes
- [ ] Kafka consumer processes edit/delete/reaction events correctly
