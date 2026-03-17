# cHATBOX

A real-time chat application built with **FastAPI** (backend) and **React + Vite** (frontend).

---

## Requirements

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

---

## Project Structure

```
Chat-Project-Final/
├── backend/          # FastAPI server
│   ├── main.py
│   ├── models.py
│   ├── routers/
│   ├── services/
│   ├── tests/
│   └── uploads/
└── frontend/         # React + Vite app
    ├── src/
    └── package.json
```

---

## Setup & Running

### 1. Backend

```bash
cd backend

# Install dependencies (first time only)
pip install fastapi uvicorn[standard] sqlalchemy argon2-cffi \
    "python-jose[cryptography]" python-multipart aiofiles httpx pytest pytest-asyncio websockets

# Start the server
uvicorn main:app --reload --port 8000
```

The API will be available at **http://localhost:8000**
Interactive docs: **http://localhost:8000/docs**

### 2. Frontend

```bash
cd frontend

# Install dependencies (first time only)
npm install

# Start the dev server
npm run dev
```

The app will be available at **http://localhost:5173**

> **Note:** Both backend and frontend must be running at the same time.

---

## Default Credentials

| Username | Password | Role |
|----------|----------|------|
| `ido` | `ido123` | Global Admin |

You can register additional accounts from the login page.

---

## Features

- **Authentication** — Register/Login with JWT tokens
- **Chat rooms** — Three default rooms: Politics, Sports, Movies
- **Real-time messaging** — WebSocket-based live chat
- **Private messages** — Send direct messages to users in the same room
- **File sharing** — Upload and download files within rooms
- **Admin controls** (room admin):
  - Kick users from the room
  - Mute / Unmute users
  - Promote users to room admin
  - Admin succession: when admin leaves, the next user in join order automatically becomes admin
- **Global Admin Panel** (accessible via "Admin Panel" button):
  - View all rooms with users and status
  - Open / Close individual rooms or all rooms at once
  - View all currently connected users
  - Browse and download files per room
  - Add new rooms
  - Promote users to room admin across all rooms
  - Reset the database

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

All tests should pass.

---

## Build for Production

```bash
cd frontend
npm run build
```

Compiled output will be in `frontend/dist/`.
