# cHATBOX — Agent Refactoring Guide
**From: Python 2 / wxPython / raw sockets / shelve (2015)**
**To: Python 3.11 / React / FastAPI / SQLite (2025)**

Reference document: `chatbox_architecture.docx` (same folder — read it for full design rationale).

---

## How to use this file

Work through the phases **in order**. Each phase ends with a **Verification** section — do not move to the next phase until verification passes. Every phase is independently runnable and testable.

When you start a phase, read the entire phase first, then execute.

---

## Original Code Map (what each old file becomes)

| Old file | What it does | New equivalent |
|---|---|---|
| `Database.py` | shelve key-value store (Windows-only paths) | `server/database.py` + `server/models.py` |
| `chatServer.py` | monolithic server: sockets, routing, admin, web | `server/routers/` + `server/services/` + `server/ws_manager.py` |
| `chatClient.py` | monolithic client: sockets, binary protocol, GUI | `client/src/api/websocket.js` + `client/src/api/http.js` |
| `Message.py` | hand-crafted binary protocol (struct pack/unpack) | JSON over WebSocket — no equivalent needed |
| `Room.py` + `Rooms.py` | in-memory room state | `server/ws_manager.py` (ConnectionManager) + `rooms` table |
| `User.py` + `Users.py` | in-memory user state | `server/ws_manager.py` + `users` table |
| `File.py` + `Files.py` | file metadata tracking | `server/services/file_service.py` + `files` table |
| `loginWindow.py` | wxPython login/register GUI | `client/src/pages/LoginPage.jsx` |
| `chooseRoomWindow.py` | wxPython room picker GUI | `client/src/components/RoomList.jsx` |
| `chatWindow.py` | wxPython main chat GUI | `client/src/pages/ChatPage.jsx` |
| `tornadoWeb.py` | Tornado template admin site | `client/src/pages/AdminPage.jsx` + `server/routers/admin.py` |
| `ServerMain.py` | server entry point | `server/main.py` |
| `ClientMain.py` | client entry point | `client/package.json` → `npm start` |
| `Settings.py` | Windows-only static path config | `server/config.py` |
| `log.py` | custom logger writing to /logs/ | Python `logging` module (built-in) |

---

## Key Python 2 Gotchas to Watch For

These patterns appear throughout the original code and will break in Python 3:

- `print "text"` → `print("text")`
- `except Exception, e:` → `except Exception as e:`
- `db.has_key(k)` → `k in db`
- `socket.error, e` → `socket.error as e`
- `"\xf7\x92..."` raw byte strings used as password hash → replace with Argon2id (do not port)
- `shell.SHGetFolderPath(...)` (win32com) → `pathlib.Path.home()` or `os.path.expanduser("~")`
- `"\\".join(...)` Windows paths → `pathlib.Path(...) / "subdir"`
- The hardcoded admin credentials in `chatServer.py` (`USERNAME="ido"`, `PASSWORD='\xf7...'`, `SALT="\x18..."`) — **do not port these**. The new system registers the admin via the normal flow with Argon2id hashing.
- The binary protocol in `Message.py` (struct pack/unpack with custom opcodes) is **entirely replaced** by JSON over WebSocket. Do not port it.

---

## Phase 1 — Backend Foundation

**Goal:** A running FastAPI server with working auth endpoints and SQLite database.
No WebSocket yet. Test with curl or Postman.

### 1.1 Create the project structure

```
mkdir chatbox-server
cd chatbox-server

mkdir -p routers services
touch main.py config.py database.py models.py schemas.py auth.py ws_manager.py
touch routers/__init__.py routers/auth.py routers/rooms.py routers/files.py routers/admin.py routers/websocket.py
touch services/__init__.py services/auth_service.py services/room_service.py services/file_service.py services/admin_service.py
mkdir -p uploads
```

### 1.2 Install dependencies

```bash
pip install fastapi uvicorn[standard] sqlalchemy argon2-cffi python-jose[cryptography] python-multipart aiofiles
```

Save to `requirements.txt`:
```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
sqlalchemy>=2.0.0
argon2-cffi>=23.1.0
python-jose[cryptography]>=3.3.0
python-multipart>=0.0.9
aiofiles>=23.2.1
```

### 1.3 Write `config.py`

Replaces `Settings.py`. No Windows paths — fully cross-platform.

```python
# config.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATABASE_URL = f"sqlite:///{BASE_DIR}/chatbox.db"
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production-use-openssl-rand-hex-32")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
MAX_FILE_SIZE_BYTES = 150 * 1024 * 1024  # 150 MB
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Admin credentials — set these via environment variables in production
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ido")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
```

### 1.4 Write `database.py`

Replaces `Database.py`. Uses SQLAlchemy instead of shelve.

```python
# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 1.5 Write `models.py`

Replaces `User.py`, `Room.py`, `File.py` (the persistent parts). The old code stored users in a shelve dict (`username -> hashed_password`) and kept rooms/admins/mutes only in memory (lost on restart). The new models persist everything.

```python
# models.py
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    is_global_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sent_messages = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id")
    uploaded_files = relationship("File", back_populates="sender")


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    files = relationship("File", back_populates="room")
    messages = relationship("Message", back_populates="room")


class RoomAdmin(Base):
    """A row = user is admin in that room. Delete row to demote.
    Replaces the in-memory admins list + text file from chatServer.py."""
    __tablename__ = "room_admins"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    appointed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MutedUser(Base):
    """A row = user is muted in that room. Delete row to unmute.
    Replaces the in-memory _usersToMute list in chatServer.py."""
    __tablename__ = "muted_users"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    muted_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class File(Base):
    """Replaces File.py + Files.py. Files are stored on disk; metadata here."""
    __tablename__ = "files"
    id = Column(Integer, primary_key=True)
    original_name = Column(String(256), nullable=False)
    stored_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sender = relationship("User", back_populates="uploaded_files")
    room = relationship("Room", back_populates="files")


class Message(Base):
    """New — the original app had no message persistence. Optional for v1."""
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)   # null = private message
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # set for private messages
    content = Column(Text, nullable=False)
    is_private = Column(Boolean, default=False, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sender = relationship("User", back_populates="sent_messages", foreign_keys=[sender_id])
    room = relationship("Room", back_populates="messages")
```

### 1.6 Write `schemas.py`

Pydantic models for request/response validation. Replaces the custom binary packing in `Message.py`.

```python
# schemas.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class UserRegister(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_global_admin: bool

class RoomCreate(BaseModel):
    name: str

class RoomResponse(BaseModel):
    id: int
    name: str
    is_active: bool

    class Config:
        from_attributes = True

class FileResponse(BaseModel):
    id: int
    original_name: str
    file_size: int
    sender: str
    room_id: int
    uploaded_at: datetime

    class Config:
        from_attributes = True
```

### 1.7 Write `auth.py`

Replaces the `hashlib` + `uuid` salt approach in `chatClient.py`. The old code hashed the password on the CLIENT and sent the hash. The new approach: password travels over TLS, is hashed SERVER-SIDE with Argon2id.

```python
# auth.py
from datetime import datetime, timedelta
from jose import JWTError, jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_HOURS
from database import get_db
import models

ph = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        ph.verify(hashed, plain)
        return True
    except VerifyMismatchError:
        return False


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_global_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
```

### 1.8 Write `routers/auth.py`

Replaces the login/register handling scattered through `chatServer.py` (`_login()`, `_register()`, `_checkPassword()`).

```python
# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from auth import hash_password, verify_password, create_access_token
import models, schemas

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: schemas.UserRegister, db: Session = Depends(get_db)):
    # Old code: chatServer._register() checked shelve DB for duplicate username
    if db.query(models.User).filter(models.User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    if not body.username.strip() or not body.password.strip():
        raise HTTPException(status_code=400, detail="Username and password required")

    user = models.User(
        username=body.username.strip(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Registered successfully"}


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.UserLogin, db: Session = Depends(get_db)):
    # Old code: chatServer._login() checked shelve DB then compared hashed passwords
    user = db.query(models.User).filter(models.User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": user.id, "username": user.username})
    return schemas.TokenResponse(
        access_token=token,
        username=user.username,
        is_global_admin=user.is_global_admin,
    )
```

### 1.9 Write `routers/rooms.py`

```python
# routers/rooms.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from auth import get_current_user, require_admin
import models, schemas

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("/", response_model=List[schemas.RoomResponse])
def list_rooms(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.Room).filter(models.Room.is_active == True).all()


@router.post("/", response_model=schemas.RoomResponse, status_code=201)
def create_room(body: schemas.RoomCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    # Old code: tornadoWeb addRoomHandler — only global admin could add rooms
    if db.query(models.Room).filter(models.Room.name == body.name).first():
        raise HTTPException(status_code=409, detail="Room name already exists")
    room = models.Room(name=body.name.strip())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room
```

### 1.10 Write `main.py`

```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import auth, rooms, files, admin, websocket
from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD
import models
from sqlalchemy.orm import Session

app = FastAPI(title="cHATBOX API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(files.router)
app.include_router(admin.router)
app.include_router(websocket.router)


@app.on_event("startup")
def startup():
    """Create all tables and seed the default rooms + admin user.
    Old code: chatServer.__init__() called addRoom() for 'politics','sports','movies'
    and hardcoded ADMINS=["ido"] with a pre-hashed password."""
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        # Seed default rooms
        for room_name in ["politics", "sports", "movies"]:
            if not db.query(models.Room).filter(models.Room.name == room_name).first():
                db.add(models.Room(name=room_name))

        # Seed global admin (idempotent — skip if already exists)
        admin_user = db.query(models.User).filter(models.User.username == ADMIN_USERNAME).first()
        if not admin_user:
            db.add(models.User(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                is_global_admin=True,
            ))
        elif not admin_user.is_global_admin:
            admin_user.is_global_admin = True

        db.commit()
```

### 1.11 Phase 1 Verification

```bash
cd chatbox-server
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000/docs — the Swagger UI should show all endpoints.

Run these curl tests:

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"secret123"}'
# Expected: {"message":"Registered successfully"}

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"secret123"}'
# Expected: {"access_token":"eyJ...","username":"testuser","is_global_admin":false}

# List rooms (paste your token)
curl http://localhost:8000/rooms/ \
  -H "Authorization: Bearer <token>"
# Expected: [{"id":1,"name":"politics",...}, ...]

# Duplicate username
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"other"}'
# Expected: 409 Conflict

# Wrong password
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"wrong"}'
# Expected: 401 Unauthorized
```

✅ Phase 1 complete when all 5 curl tests return the expected responses.

---

## Phase 2 — WebSocket Core

**Goal:** Real-time chat working end-to-end between multiple browser tabs using wscat or Postman. Admin actions (kick, mute, promote) working.

### 2.1 Write `ws_manager.py`

Replaces `Room.py`, `Rooms.py`, `User.py`, `Users.py` (the in-memory parts). The old server used `Room._openSockets` lists and `sendToGroup()`. The new manager is async and handles all rooms.

```python
# ws_manager.py
from fastapi import WebSocket
from typing import Dict, List


class ConnectionManager:
    """
    In-memory state of active WebSocket connections.

    Old equivalent:
      - self._roomlist (Rooms object)  →  self.rooms
      - room._openSockets              →  self.rooms[room_id]
      - self._loggedUserList (Users)   →  self.socket_to_user + self.user_to_socket
    """

    def __init__(self):
        # room_id -> list of active WebSocket connections
        self.rooms: Dict[int, List[WebSocket]] = {}
        # WebSocket -> username
        self.socket_to_user: Dict[WebSocket, str] = {}
        # username -> WebSocket (one connection per user for personal messages)
        self.user_to_socket: Dict[str, WebSocket] = {}
        # room_id -> first socket (for admin succession)
        self.room_join_order: Dict[int, List[str]] = {}

    async def connect(self, websocket: WebSocket, room_id: int, username: str):
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = []
            self.room_join_order[room_id] = []
        self.rooms[room_id].append(websocket)
        self.socket_to_user[websocket] = username
        self.user_to_socket[username] = websocket
        self.room_join_order[room_id].append(username)

    def disconnect(self, websocket: WebSocket, room_id: int):
        username = self.socket_to_user.get(websocket)
        if room_id in self.rooms and websocket in self.rooms[room_id]:
            self.rooms[room_id].remove(websocket)
        if websocket in self.socket_to_user:
            del self.socket_to_user[websocket]
        if username and username in self.user_to_socket:
            del self.user_to_socket[username]
        if username and room_id in self.room_join_order:
            if username in self.room_join_order[room_id]:
                self.room_join_order[room_id].remove(username)

    async def broadcast(self, room_id: int, message: dict, exclude: WebSocket = None):
        """Send to all sockets in a room. Old equivalent: Room.sendToGroup()."""
        for ws in list(self.rooms.get(room_id, [])):
            if ws != exclude:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

    async def send_personal(self, username: str, message: dict):
        """Send to a specific user. Old equivalent: the private message flow."""
        ws = self.user_to_socket.get(username)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    def get_users_in_room(self, room_id: int) -> List[str]:
        return [self.socket_to_user[ws] for ws in self.rooms.get(room_id, []) if ws in self.socket_to_user]

    def get_admin_successor(self, room_id: int) -> str | None:
        """
        Old code: chatServer logic — when admin leaves, the next user in join order becomes admin.
        Returns the username of the next user, or None if room is empty.
        """
        order = self.room_join_order.get(room_id, [])
        return order[0] if order else None

    def is_user_in_room(self, username: str, room_id: int) -> bool:
        return username in self.get_users_in_room(room_id)


manager = ConnectionManager()  # singleton shared across requests
```

### 2.2 Write `services/room_service.py`

Replaces the admin action handling in `chatServer.py` (`_adminGetOut`, `_adminMute`, `_adminUnMute`, `_adminAppendToAdmins`). All business rules from the original are preserved.

```python
# services/room_service.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
import models
from ws_manager import ConnectionManager


def is_admin_in_room(username: str, room_id: int, db: Session) -> bool:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return False
    return db.query(models.RoomAdmin).filter(
        models.RoomAdmin.user_id == user.id,
        models.RoomAdmin.room_id == room_id,
    ).first() is not None


def is_muted_in_room(username: str, room_id: int, db: Session) -> bool:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return False
    return db.query(models.MutedUser).filter(
        models.MutedUser.user_id == user.id,
        models.MutedUser.room_id == room_id,
    ).first() is not None


def promote_to_admin(actor: str, target: str, room_id: int, db: Session):
    """Old: chatServer._adminAppendToAdmins() — admin adds user to admin text file."""
    if actor == target:
        raise HTTPException(400, "Cannot promote yourself")
    if not is_admin_in_room(actor, room_id, db):
        raise HTTPException(403, "Only admins can promote users")
    if is_admin_in_room(target, room_id, db):
        raise HTTPException(409, "User is already an admin")  # old: server sent error message to client

    target_user = db.query(models.User).filter(models.User.username == target).first()
    if not target_user:
        raise HTTPException(404, "Target user not found")

    db.add(models.RoomAdmin(user_id=target_user.id, room_id=room_id))
    db.commit()


def mute_user(actor: str, target: str, room_id: int, db: Session):
    """Old: chatServer._adminMute() — added to _usersToMute list (lost on restart)."""
    if actor == target:
        raise HTTPException(400, "Cannot mute yourself")
    if is_admin_in_room(target, room_id, db):
        raise HTTPException(403, "Cannot mute another admin")  # old: security rule
    if not is_admin_in_room(actor, room_id, db):
        raise HTTPException(403, "Only admins can mute users")
    if is_muted_in_room(target, room_id, db):
        raise HTTPException(409, "User is already muted")

    target_user = db.query(models.User).filter(models.User.username == target).first()
    if not target_user:
        raise HTTPException(404, "Target user not found")

    db.add(models.MutedUser(user_id=target_user.id, room_id=room_id))
    db.commit()


def unmute_user(actor: str, target: str, room_id: int, db: Session):
    """Old: chatServer._adminUnMute()."""
    if not is_admin_in_room(actor, room_id, db):
        raise HTTPException(403, "Only admins can unmute users")
    target_user = db.query(models.User).filter(models.User.username == target).first()
    if not target_user:
        raise HTTPException(404, "Target user not found")

    mute = db.query(models.MutedUser).filter(
        models.MutedUser.user_id == target_user.id,
        models.MutedUser.room_id == room_id,
    ).first()
    if not mute:
        raise HTTPException(409, "User is not muted")  # old: server sent error to client
    db.delete(mute)
    db.commit()


async def handle_admin_succession(room_id: int, leaving_username: str, db: Session, manager: ConnectionManager):
    """
    Old: chatServer logic — when admin leaves, next user in join order becomes admin.
    'כאשר מנהל יוצא מן החדר, המשתמש שנכנס אחרי המנהל הוא זה שיהפוך למנהל'
    """
    # Remove admin status for the leaving user
    leaving_user = db.query(models.User).filter(models.User.username == leaving_username).first()
    if leaving_user:
        db.query(models.RoomAdmin).filter(
            models.RoomAdmin.user_id == leaving_user.id,
            models.RoomAdmin.room_id == room_id,
        ).delete()
        db.commit()

    # Promote the next user in join order
    successor = manager.get_admin_successor(room_id)
    if successor:
        successor_user = db.query(models.User).filter(models.User.username == successor).first()
        if successor_user and not is_admin_in_room(successor, room_id, db):
            db.add(models.RoomAdmin(user_id=successor_user.id, room_id=room_id))
            db.commit()
            await manager.broadcast(room_id, {
                "type": "new_admin",
                "username": successor,
                "room_id": room_id,
            })
```

### 2.3 Write `routers/websocket.py`

Replaces the socket handling loop in `chatServer.py` (`ManageMessages`, `_decryptReceivedMessage`). Instead of a custom binary protocol with struct pack/unpack, messages are plain JSON.

```python
# routers/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from ws_manager import manager
from auth import verify_password
from jose import jwt, JWTError
from config import SECRET_KEY, ALGORITHM
from services import room_service
import models

router = APIRouter(tags=["websocket"])


def get_user_from_token(token: str, db: Session) -> models.User | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        return db.query(models.User).filter(models.User.id == user_id).first()
    except JWTError:
        return None


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    # Authenticate
    user = get_user_from_token(token, db)
    if not user:
        await websocket.close(code=4001)
        return

    # Check room exists and is active
    room = db.query(models.Room).filter(models.Room.id == room_id, models.Room.is_active == True).first()
    if not room:
        await websocket.close(code=4004)
        return

    # Prevent same user joining the same room twice — old: '_CantBeInRoomTwice'
    if manager.is_user_in_room(user.username, room_id):
        await websocket.close(code=4003)
        return

    await manager.connect(websocket, room_id, user.username)

    # Make the first user in a room the admin automatically
    # Old: 'מנהל - משתמש הנכנס ראשון לחדר'
    if len(manager.get_users_in_room(room_id)) == 1:
        if not room_service.is_admin_in_room(user.username, room_id, db):
            db.add(models.RoomAdmin(user_id=user.id, room_id=room_id))
            db.commit()

    # Announce join to the room
    await manager.broadcast(room_id, {
        "type": "user_join",
        "username": user.username,
        "users": manager.get_users_in_room(room_id),
        "room_id": room_id,
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            # --- Chat message ---
            if msg_type == "message":
                # Check mute — old: server checked _usersToMute before broadcasting
                if room_service.is_muted_in_room(user.username, room_id, db):
                    await websocket.send_json({"type": "error", "detail": "You are muted in this room"})
                    continue
                await manager.broadcast(room_id, {
                    "type": "message",
                    "from": user.username,
                    "text": data.get("text", ""),
                    "room_id": room_id,
                }, exclude=websocket)

            # --- Private message ---
            elif msg_type == "private_message":
                target = data.get("to")
                if not target or target == user.username:
                    continue
                await manager.send_personal(target, {
                    "type": "private_message",
                    "from": user.username,
                    "text": data.get("text", ""),
                })

            # --- Admin: kick ---
            elif msg_type == "kick":
                target = data.get("target")
                if not target or target == user.username:
                    await websocket.send_json({"type": "error", "detail": "Cannot kick yourself"})
                    continue
                if not room_service.is_admin_in_room(user.username, room_id, db):
                    await websocket.send_json({"type": "error", "detail": "Not an admin"})
                    continue
                if room_service.is_admin_in_room(target, room_id, db):
                    await websocket.send_json({"type": "error", "detail": "Cannot kick another admin"})
                    continue
                # Disconnect the target
                target_ws = manager.user_to_socket.get(target)
                if target_ws:
                    await target_ws.send_json({"type": "kicked", "room_id": room_id})
                    await target_ws.close()
                await manager.broadcast(room_id, {"type": "user_left", "username": target, "room_id": room_id, "reason": "kicked"})

            # --- Admin: mute ---
            elif msg_type == "mute":
                target = data.get("target")
                try:
                    room_service.mute_user(user.username, target, room_id, db)
                    await manager.broadcast(room_id, {"type": "muted", "username": target, "room_id": room_id})
                except Exception as e:
                    await websocket.send_json({"type": "error", "detail": str(e)})

            # --- Admin: unmute ---
            elif msg_type == "unmute":
                target = data.get("target")
                try:
                    room_service.unmute_user(user.username, target, room_id, db)
                    await manager.broadcast(room_id, {"type": "unmuted", "username": target, "room_id": room_id})
                except Exception as e:
                    await websocket.send_json({"type": "error", "detail": str(e)})

            # --- Admin: promote ---
            elif msg_type == "promote":
                target = data.get("target")
                try:
                    room_service.promote_to_admin(user.username, target, room_id, db)
                    await manager.broadcast(room_id, {"type": "new_admin", "username": target, "room_id": room_id})
                except Exception as e:
                    await websocket.send_json({"type": "error", "detail": str(e)})

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        was_admin = room_service.is_admin_in_room(user.username, room_id, db)
        if was_admin:
            await room_service.handle_admin_succession(room_id, user.username, db, manager)
        await manager.broadcast(room_id, {
            "type": "user_left",
            "username": user.username,
            "users": manager.get_users_in_room(room_id),
            "room_id": room_id,
        })
```

### 2.4 Phase 2 Verification

Install `wscat`: `npm install -g wscat`

```bash
# Terminal 1 — start server
uvicorn main:app --reload

# Terminal 2 — login and get token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"secret123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Connect to room 1
wscat -c "ws://localhost:8000/ws/1?token=$TOKEN"

# In the wscat prompt, send a message:
{"type":"message","text":"hello from wscat"}

# Terminal 3 — connect a second user and verify they receive the message
```

✅ Phase 2 complete when two wscat sessions in the same room exchange messages, and mute/kick/promote commands trigger the correct broadcast events.

---

## Phase 3 — React Frontend

**Goal:** A working browser UI connected to the Phase 2 backend. Users can log in, join rooms, and chat.

### 3.1 Scaffold the React app

```bash
npm create vite@latest chatbox-client -- --template react
cd chatbox-client
npm install
npm install axios react-router-dom
```

### 3.2 Project structure to create

```
src/
  api/
    http.js          ← Axios instance
    websocket.js     ← WebSocket wrapper
  context/
    AuthContext.jsx  ← user + token state
    ChatContext.jsx  ← rooms + messages + online users
  pages/
    LoginPage.jsx    ← replaces loginWindow.py
    ChatPage.jsx     ← replaces chatWindow.py
    AdminPage.jsx    ← replaces tornadoWeb.py templates
  components/
    RoomList.jsx       ← replaces chooseRoomWindow.py
    MessageList.jsx
    MessageInput.jsx
    UserList.jsx
    ContextMenu.jsx    ← right-click admin menu
    FileProgress.jsx   ← upload/download progress bar
  App.jsx
  main.jsx
```

### 3.3 Write `src/api/http.js`

```javascript
// src/api/http.js
import axios from 'axios';

const http = axios.create({ baseURL: 'http://localhost:8000' });

// Attach JWT to every request automatically
http.interceptors.request.use(config => {
  const token = sessionStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export default http;
```

### 3.4 Write `src/api/websocket.js`

Replaces `chatClient._decryptReceivedMessage()` and the binary struct protocol. Each room gets one WebSocket connection.

```javascript
// src/api/websocket.js
const sockets = {}; // room_id -> WebSocket

export function connectToRoom(roomId, token, onMessage) {
  if (sockets[roomId]) return; // already connected

  const ws = new WebSocket(`ws://localhost:8000/ws/${roomId}?token=${token}`);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    onMessage(data);
  };

  ws.onclose = () => {
    delete sockets[roomId];
    onMessage({ type: 'disconnected', room_id: roomId });
  };

  sockets[roomId] = ws;
}

export function sendMessage(roomId, payload) {
  const ws = sockets[roomId];
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }
}

export function disconnectFromRoom(roomId) {
  if (sockets[roomId]) {
    sockets[roomId].close();
    delete sockets[roomId];
  }
}
```

### 3.5 Write `src/context/AuthContext.jsx`

```jsx
// src/context/AuthContext.jsx
import { createContext, useContext, useState } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);   // { username, is_global_admin }
  const [token, setToken] = useState(null);

  function login(tokenStr, userData) {
    setToken(tokenStr);
    setUser(userData);
    sessionStorage.setItem('token', tokenStr); // Use sessionStorage, NOT localStorage
  }

  function logout() {
    setToken(null);
    setUser(null);
    sessionStorage.removeItem('token');
  }

  return (
    <AuthContext.Provider value={{ user, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

### 3.6 Write `src/context/ChatContext.jsx`

```jsx
// src/context/ChatContext.jsx
import { createContext, useContext, useReducer } from 'react';

const ChatContext = createContext(null);

const initialState = {
  rooms: [],          // list of { id, name }
  activeRoomId: null,
  messages: {},       // { room_id: [{ from, text, timestamp }] }
  onlineUsers: {},    // { room_id: [username] }
  admins: {},         // { room_id: [username] }
  mutedUsers: {},     // { room_id: [username] }
};

function chatReducer(state, action) {
  switch (action.type) {
    case 'SET_ROOMS':
      return { ...state, rooms: action.rooms };
    case 'SET_ACTIVE_ROOM':
      return { ...state, activeRoomId: action.roomId };
    case 'ADD_MESSAGE': {
      const roomMsgs = state.messages[action.roomId] || [];
      return {
        ...state,
        messages: { ...state.messages, [action.roomId]: [...roomMsgs, action.message] },
      };
    }
    case 'SET_USERS':
      return { ...state, onlineUsers: { ...state.onlineUsers, [action.roomId]: action.users } };
    case 'SET_ADMIN':
      return {
        ...state,
        admins: {
          ...state.admins,
          [action.roomId]: [...(state.admins[action.roomId] || []), action.username],
        },
      };
    case 'ADD_MUTED':
      return {
        ...state,
        mutedUsers: {
          ...state.mutedUsers,
          [action.roomId]: [...(state.mutedUsers[action.roomId] || []), action.username],
        },
      };
    case 'REMOVE_MUTED':
      return {
        ...state,
        mutedUsers: {
          ...state.mutedUsers,
          [action.roomId]: (state.mutedUsers[action.roomId] || []).filter(u => u !== action.username),
        },
      };
    default:
      return state;
  }
}

export function ChatProvider({ children }) {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  return (
    <ChatContext.Provider value={{ state, dispatch }}>
      {children}
    </ChatContext.Provider>
  );
}

export const useChat = () => useContext(ChatContext);
```

### 3.7 Write `src/pages/LoginPage.jsx`

Replaces `loginWindow.py`. Uses a form with two tabs (Login / Register).

```jsx
// src/pages/LoginPage.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import http from '../api/http';

export default function LoginPage() {
  const [mode, setMode] = useState('login');   // 'login' | 'register'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    try {
      if (mode === 'register') {
        await http.post('/auth/register', { username, password });
        setMode('login');
        setError('Registered! Now log in.');
      } else {
        const res = await http.post('/auth/login', { username, password });
        login(res.data.access_token, {
          username: res.data.username,
          is_global_admin: res.data.is_global_admin,
        });
        navigate('/chat');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong');
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: '100px auto', padding: 24, border: '1px solid #ccc', borderRadius: 8 }}>
      <h2>cHATBOX</h2>
      <div style={{ marginBottom: 16 }}>
        <button onClick={() => setMode('login')} disabled={mode === 'login'}>Login</button>
        <button onClick={() => setMode('register')} disabled={mode === 'register'} style={{ marginLeft: 8 }}>Register</button>
      </div>
      <form onSubmit={handleSubmit}>
        <input placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} required style={{ display: 'block', width: '100%', marginBottom: 8 }} />
        <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required style={{ display: 'block', width: '100%', marginBottom: 8 }} />
        {error && <p style={{ color: mode === 'login' ? 'red' : 'green' }}>{error}</p>}
        <button type="submit" style={{ width: '100%' }}>{mode === 'login' ? 'Login' : 'Register'}</button>
      </form>
    </div>
  );
}
```

### 3.8 Write `src/App.jsx`

```jsx
// src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ChatProvider } from './context/ChatContext';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import AdminPage from './pages/AdminPage';

function ProtectedRoute({ children, adminOnly = false }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" />;
  if (adminOnly && !user.is_global_admin) return <Navigate to="/chat" />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <ChatProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
            <Route path="/admin" element={<ProtectedRoute adminOnly><AdminPage /></ProtectedRoute>} />
            <Route path="*" element={<Navigate to="/login" />} />
          </Routes>
        </BrowserRouter>
      </ChatProvider>
    </AuthProvider>
  );
}
```

### 3.9 Wire up ChatPage (skeleton)

`ChatPage.jsx` is the main component. At minimum it should:
1. On mount: call `GET /rooms`, store rooms in ChatContext
2. When user selects a room: call `connectToRoom(roomId, token, dispatchEvent)`
3. `dispatchEvent` handles all WS message types (see table below)
4. Render `<RoomList>`, `<MessageList>`, `<UserList>`, `<MessageInput>`

**WebSocket message dispatch table** (what the client receives):

| `type` value | Action |
|---|---|
| `user_join` | dispatch SET_USERS with updated users list |
| `user_left` | dispatch SET_USERS with updated users list |
| `message` | dispatch ADD_MESSAGE |
| `private_message` | dispatch ADD_MESSAGE with `isPrivate: true` |
| `kicked` | disconnect from room, show notification |
| `muted` | dispatch ADD_MUTED |
| `unmuted` | dispatch REMOVE_MUTED |
| `new_admin` | dispatch SET_ADMIN |
| `error` | show toast/alert to current user only |
| `disconnected` | show reconnect option |

### 3.10 Phase 3 Verification

```bash
# Start backend
cd chatbox-server && uvicorn main:app --reload

# Start frontend
cd chatbox-client && npm run dev
```

Open http://localhost:5173 in two different browser tabs.

- [ ] Tab 1: Register as `alice`, login, see room list
- [ ] Tab 2: Register as `bob`, login, join same room
- [ ] Tab 1: Send a message — Tab 2 should receive it instantly
- [ ] Tab 2: Verify alice appears in the user list
- [ ] Tab 1 (alice, first to join = admin): right-click bob → mute
- [ ] Tab 2: bob tries to send a message → receives "You are muted" error

✅ Phase 3 complete when all checklist items pass.

---

## Phase 4 — File Transfer & Polish

**Goal:** File upload/download with progress bar. End-to-end production-ready.

### 4.1 Write `services/file_service.py`

Replaces `File.py`, `Files.py`, and the file handling in `chatServer.py` (`_sendFile`, `_serverSendFile`). The old code sent files as raw binary chunks over the socket with a custom protocol. The new approach uses standard HTTP multipart upload.

```python
# services/file_service.py
import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from config import UPLOAD_DIR, MAX_FILE_SIZE_BYTES
import models


async def save_file(file: UploadFile, sender_id: int, room_id: int, db: Session) -> models.File:
    # Check file size — old: chatServer checked size before sending, rejected if > 150MB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(413, f"File exceeds maximum size of 150 MB")

    # Store with a unique name to prevent collisions — old: chatServer used _fileCount integer
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest = UPLOAD_DIR / safe_name
    dest.write_bytes(content)

    file_record = models.File(
        original_name=file.filename,
        stored_path=str(dest),
        file_size=len(content),
        sender_id=sender_id,
        room_id=room_id,
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)
    return file_record
```

### 4.2 Write `routers/files.py`

```python
# routers/files.py
from fastapi import APIRouter, Depends, UploadFile, File as FastAPIFile, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from auth import get_current_user
from services.file_service import save_file
from ws_manager import manager
import models, schemas

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=schemas.FileResponse)
async def upload_file(
    room_id: int,
    file: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    file_record = await save_file(file, current_user.id, room_id, db)

    # Notify all users in the room that a file is available — old: server sent 'filename:' message
    await manager.broadcast(room_id, {
        "type": "file_shared",
        "file_id": file_record.id,
        "filename": file_record.original_name,
        "size": file_record.file_size,
        "from": current_user.username,
        "room_id": room_id,
    })

    return schemas.FileResponse(
        id=file_record.id,
        original_name=file_record.original_name,
        file_size=file_record.file_size,
        sender=current_user.username,
        room_id=room_id,
        uploaded_at=file_record.uploaded_at,
    )


@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    # Old: chatServer._serverSendFile() sent raw bytes over socket
    record = db.query(models.File).filter(models.File.id == file_id).first()
    if not record:
        raise HTTPException(404, "File not found")
    return FileResponse(
        path=record.stored_path,
        filename=record.original_name,
        media_type="application/octet-stream",
    )


@router.get("/room/{room_id}", response_model=List[schemas.FileResponse])
def list_room_files(room_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    files = db.query(models.File).filter(models.File.room_id == room_id).all()
    return [
        schemas.FileResponse(
            id=f.id,
            original_name=f.original_name,
            file_size=f.file_size,
            sender=f.sender.username,
            room_id=f.room_id,
            uploaded_at=f.uploaded_at,
        ) for f in files
    ]
```

### 4.3 Write `routers/admin.py`

Replaces `tornadoWeb.py` (the Tornado template handlers: `BlockHandler`, `OpenHandler`, `DatabaseHandler`, `UsersHandler`, `RoomsHandler`, `addAdminHandler`, `addRoomHandler`).

```python
# routers/admin.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from auth import require_admin
from ws_manager import manager
import models
from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def get_connected_users(_=Depends(require_admin)):
    """Old: tornadoWeb UsersHandler — polled every 5 seconds. Now: on-demand."""
    all_users = {}
    for room_id, sockets in manager.rooms.items():
        all_users[room_id] = manager.get_users_in_room(room_id)
    return all_users


@router.get("/rooms")
def get_rooms(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(models.Room).all()


@router.post("/chat/close")
async def close_chat(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Old: tornadoWeb BlockHandler — kick all users and block new connections."""
    for room in db.query(models.Room).all():
        room.is_active = False
        # Kick all connected users from this room
        await manager.broadcast(room.id, {"type": "chat_closed", "detail": "Admin has closed the chat"})
    db.commit()
    # Close all active WebSocket connections
    for room_id, sockets in list(manager.rooms.items()):
        for ws in list(sockets):
            await ws.close()
    return {"message": "Chat closed"}


@router.post("/chat/open")
def open_chat(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Old: tornadoWeb OpenHandler."""
    for room in db.query(models.Room).all():
        room.is_active = True
    db.commit()
    return {"message": "Chat opened"}


@router.delete("/db")
def reset_database(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Old: tornadoWeb DatabaseHandler — wipe users so they must re-register.
    Admin user is recreated immediately after the wipe."""
    db.query(models.RoomAdmin).delete()
    db.query(models.MutedUser).delete()
    db.query(models.User).delete()
    db.commit()
    # Re-create admin user
    db.add(models.User(
        username=ADMIN_USERNAME,
        password_hash=hash_password(ADMIN_PASSWORD),
        is_global_admin=True,
    ))
    db.commit()
    return {"message": "Database reset. Admin user restored."}


@router.post("/promote")
def promote_user(username: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Old: tornadoWeb addAdminHandler — promote user to admin in ALL rooms."""
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        return {"error": "User not found"}
    for room in db.query(models.Room).all():
        exists = db.query(models.RoomAdmin).filter(
            models.RoomAdmin.user_id == user.id,
            models.RoomAdmin.room_id == room.id,
        ).first()
        if not exists:
            db.add(models.RoomAdmin(user_id=user.id, room_id=room.id))
    db.commit()
    return {"message": f"{username} promoted to admin in all rooms"}
```

### 4.4 File progress in React (`src/components/FileProgress.jsx`)

```jsx
// src/components/FileProgress.jsx
import { useState } from 'react';
import http from '../api/http';

export default function FileUpload({ roomId }) {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);

  async function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    setUploading(true);
    setProgress(0);

    try {
      await http.post(`/files/upload?room_id=${roomId}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100));
        },
      });
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }

  return (
    <div>
      <input type="file" onChange={handleFileChange} disabled={uploading} />
      {uploading && (
        <div style={{ marginTop: 8 }}>
          <div style={{ width: '100%', background: '#eee', borderRadius: 4 }}>
            <div style={{ width: `${progress}%`, background: '#4a9eed', height: 8, borderRadius: 4, transition: 'width 0.2s' }} />
          </div>
          <small>{progress}%</small>
        </div>
      )}
    </div>
  );
}
```

### 4.5 Phase 4 Verification

```bash
# Upload a file via curl
TOKEN="<your jwt token>"
curl -X POST "http://localhost:8000/files/upload?room_id=1" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/any/small/file.txt"
# Expected: {"id":1,"original_name":"file.txt","file_size":...}

# Download it back
curl -OJ "http://localhost:8000/files/download/1" \
  -H "Authorization: Bearer $TOKEN"
# Expected: file downloaded with original name

# Admin: close chat
curl -X POST http://localhost:8000/admin/chat/close \
  -H "Authorization: Bearer $ADMIN_TOKEN"
# Expected: {"message":"Chat closed"}

# Admin: open chat again
curl -X POST http://localhost:8000/admin/chat/open \
  -H "Authorization: Bearer $ADMIN_TOKEN"
# Expected: {"message":"Chat opened"}
```

✅ Phase 4 complete when file upload/download work in browser with progress bar visible, and admin close/open chat disconnects and re-allows users.

---

## Migration: Existing Users from Old shelve Database

If you want to keep users from the 2015 deployment (not start fresh), run this **one-time script** before starting the new server:

```python
# migrate_users.py  — run ONCE then delete
import shelve, sys
from pathlib import Path

# Adjust this path to your old 'database' folder
OLD_DB_PATH = str(Path(__file__).parent / "database" / "DB")

from database import engine, SessionLocal
from models import Base, User
from auth import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()

try:
    old = shelve.open(OLD_DB_PATH)
    for username, old_hash in old.items():
        if db.query(User).filter(User.username == username).first():
            print(f"  skip {username} (already exists)")
            continue
        # The old hash is MD5/SHA — we cannot re-use it with Argon2.
        # Force a password reset by setting a placeholder. Users must re-register.
        db.add(User(
            username=username,
            password_hash=hash_password("RESET_REQUIRED_" + username),
            is_global_admin=False,
        ))
        print(f"  imported {username} (password reset required)")
    old.close()
    db.commit()
    print("Migration complete. All imported users must reset their passwords.")
finally:
    db.close()
```

> **Note:** The old password hashes (`hashlib` + salt from a local text file) cannot be verified by Argon2id. Imported users need to re-register or use a password-reset flow.

---

## Production Checklist

Before deploying beyond localhost:

- [ ] Set `SECRET_KEY` via environment variable (do not use the default)
- [ ] Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` via environment variables
- [ ] Enable HTTPS/WSS (use a reverse proxy like nginx with Let's Encrypt, or run behind a platform like Railway/Render)
- [ ] In `main.py`, update CORS `allow_origins` from `localhost:3000` to your actual domain
- [ ] In `src/api/http.js` and `src/api/websocket.js`, replace `localhost:8000` with your server URL
- [ ] Change `ws://` to `wss://` in `websocket.js` for production
- [ ] Set `UPLOAD_DIR` to a persistent volume (files are lost if the container restarts without one)
- [ ] Add rate limiting to `/auth/register` and `/auth/login` to prevent brute force

---

## Quick Reference: WebSocket Message Types

All messages are JSON. The `type` field routes the message.

**Client → Server:**

| type | fields | description |
|---|---|---|
| `message` | `text` | Send chat message to room |
| `private_message` | `to`, `text` | Send private message to a user |
| `kick` | `target` | Admin: kick user from room |
| `mute` | `target` | Admin: mute user in room |
| `unmute` | `target` | Admin: unmute user in room |
| `promote` | `target` | Admin: promote user to room admin |

**Server → Client:**

| type | fields | description |
|---|---|---|
| `user_join` | `username`, `users`, `room_id` | User joined the room |
| `user_left` | `username`, `users`, `room_id`, `reason` | User left or was kicked |
| `message` | `from`, `text`, `room_id` | Incoming chat message |
| `private_message` | `from`, `text` | Incoming private message |
| `kicked` | `room_id` | You were kicked from this room |
| `muted` | `username`, `room_id` | A user was muted |
| `unmuted` | `username`, `room_id` | A user was unmuted |
| `new_admin` | `username`, `room_id` | A user was promoted to admin |
| `file_shared` | `file_id`, `filename`, `size`, `from`, `room_id` | A file was uploaded |
| `chat_closed` | `detail` | Admin closed the chat |
| `error` | `detail` | Server-side error for your last action |
