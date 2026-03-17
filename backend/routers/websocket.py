# routers/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from ws_manager import manager
from jose import jwt, JWTError
from config import SECRET_KEY, ALGORITHM
from services import room_service
import models

router = APIRouter(tags=["websocket"])


def get_user_from_token(token: str, db: Session) -> models.User | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return None
        user_id = int(sub)
        return db.query(models.User).filter(models.User.id == user_id).first()
    except (JWTError, ValueError):
        return None


def _get_room_admins(room_id: int, db: Session, users_in_room: list) -> list:
    """Return list of usernames who are admins in this room (among currently connected users)."""
    return [u for u in users_in_room if room_service.is_admin_in_room(u, room_id, db)]


def _get_room_muted(room_id: int, db: Session, users_in_room: list) -> list:
    """Return list of muted usernames in this room (among currently connected users)."""
    return [u for u in users_in_room if room_service.is_muted_in_room(u, room_id, db)]


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
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        await websocket.close(code=4004)
        return
    if not room.is_active:
        await websocket.close(code=4002)
        return

    # Prevent same user joining the same room twice
    if manager.is_user_in_room(user.username, room_id):
        await websocket.close(code=4003)
        return

    await manager.connect(websocket, room_id, user.username)

    # Make the first user in a room the admin automatically
    became_admin = False
    users_now = manager.get_users_in_room(room_id)
    if len(users_now) == 1:
        if not room_service.is_admin_in_room(user.username, room_id, db):
            db.add(models.RoomAdmin(user_id=user.id, room_id=room_id))
            db.commit()
            became_admin = True

    # Send message history to the joining user (last 50 non-private messages)
    recent_msgs = (
        db.query(models.Message)
        .filter(models.Message.room_id == room_id, models.Message.is_private == False)
        .order_by(models.Message.sent_at.desc())
        .limit(50)
        .all()
    )
    recent_msgs.reverse()
    await websocket.send_json({
        "type": "history",
        "messages": [
            {
                "from": m.sender.username,
                "text": m.content,
                "timestamp": m.sent_at.isoformat(),
            }
            for m in recent_msgs
        ],
        "room_id": room_id,
    })

    # Announce join to everyone — include admins + muted lists so frontend state is authoritative
    admins_now = _get_room_admins(room_id, db, users_now)
    muted_now = _get_room_muted(room_id, db, users_now)
    await manager.broadcast(room_id, {
        "type": "user_join",
        "username": user.username,
        "users": users_now,
        "admins": admins_now,
        "muted": muted_now,
        "room_id": room_id,
    })
    await manager.broadcast(room_id, {
        "type": "system",
        "text": f"{user.username} has joined the room",
        "room_id": room_id,
    })
    if became_admin:
        await manager.broadcast(room_id, {
            "type": "system",
            "text": f"{user.username} has become admin automatically",
            "room_id": room_id,
        })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            # Re-check room is still active (admin may have closed it)
            db.refresh(room)
            if not room.is_active:
                await websocket.send_json({"type": "error", "detail": "Room is closed"})
                continue

            # --- Chat message ---
            if msg_type == "message":
                if room_service.is_muted_in_room(user.username, room_id, db):
                    await websocket.send_json({"type": "error", "detail": "You are muted in this room"})
                    continue
                text = data.get("text", "")
                # Persist to DB
                db.add(models.Message(sender_id=user.id, room_id=room_id, content=text))
                db.commit()
                # Broadcast to ALL users including sender
                await manager.broadcast(room_id, {
                    "type": "message",
                    "from": user.username,
                    "text": text,
                    "room_id": room_id,
                })

            # --- Private message ---
            elif msg_type == "private_message":
                target = data.get("to")
                if not target or target == user.username:
                    await websocket.send_json({"type": "error", "detail": "Invalid private message target"})
                    continue
                text = data.get("text", "")
                if not text.strip():
                    await websocket.send_json({"type": "error", "detail": "Cannot send empty private message"})
                    continue
                # Send to target
                await manager.send_personal(target, {
                    "type": "private_message",
                    "from": user.username,
                    "to": target,
                    "text": text,
                })
                # Echo to sender so they see sent message
                await websocket.send_json({
                    "type": "private_message",
                    "from": user.username,
                    "to": target,
                    "text": text,
                    "self": True,
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
                # Mark as kicked before closing so disconnect handler skips "has left" message
                manager.kicked_users.add(target)
                target_sockets = list(manager.user_to_socket.get(target, set()))
                for target_ws in target_sockets:
                    try:
                        await target_ws.send_json({"type": "kicked", "room_id": room_id})
                        await target_ws.close()
                    except Exception:
                        pass
                await manager.broadcast(room_id, {
                    "type": "system",
                    "text": f"{target} was kicked by {user.username}",
                    "room_id": room_id,
                })

            # --- Admin: mute ---
            elif msg_type == "mute":
                target = data.get("target")
                try:
                    room_service.mute_user(user.username, target, room_id, db)
                    await manager.broadcast(room_id, {"type": "muted", "username": target, "room_id": room_id})
                    await manager.broadcast(room_id, {
                        "type": "system",
                        "text": f"{target} has been muted by {user.username}",
                        "room_id": room_id,
                    })
                except Exception as e:
                    detail = e.detail if hasattr(e, "detail") else str(e)
                    await websocket.send_json({"type": "error", "detail": detail})

            # --- Admin: unmute ---
            elif msg_type == "unmute":
                target = data.get("target")
                try:
                    room_service.unmute_user(user.username, target, room_id, db)
                    await manager.broadcast(room_id, {"type": "unmuted", "username": target, "room_id": room_id})
                    await manager.broadcast(room_id, {
                        "type": "system",
                        "text": f"{target} has been unmuted by {user.username}",
                        "room_id": room_id,
                    })
                except Exception as e:
                    detail = e.detail if hasattr(e, "detail") else str(e)
                    await websocket.send_json({"type": "error", "detail": detail})

            # --- Admin: promote ---
            elif msg_type == "promote":
                target = data.get("target")
                try:
                    room_service.promote_to_admin(user.username, target, room_id, db)
                    await manager.broadcast(room_id, {"type": "new_admin", "username": target, "room_id": room_id})
                    await manager.broadcast(room_id, {
                        "type": "system",
                        "text": f"{target} has become admin by {user.username}",
                        "room_id": room_id,
                    })
                except Exception as e:
                    detail = e.detail if hasattr(e, "detail") else str(e)
                    await websocket.send_json({"type": "error", "detail": detail})

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)

        # Clear mute if user was muted in this room (user left → mute reset)
        mute_record = db.query(models.MutedUser).filter(
            models.MutedUser.user_id == user.id,
            models.MutedUser.room_id == room_id,
        ).first()
        if mute_record:
            db.delete(mute_record)
            db.commit()
            await manager.broadcast(room_id, {"type": "unmuted", "username": user.username, "room_id": room_id})

        was_admin = room_service.is_admin_in_room(user.username, room_id, db)
        if was_admin:
            await room_service.handle_admin_succession(room_id, user.username, db, manager)

        # Broadcast updated user list with authoritative admins + muted state
        remaining = manager.get_users_in_room(room_id)
        await manager.broadcast(room_id, {
            "type": "user_left",
            "username": user.username,
            "users": remaining,
            "admins": _get_room_admins(room_id, db, remaining),
            "muted": _get_room_muted(room_id, db, remaining),
            "room_id": room_id,
        })

        # Only broadcast "has left" if user wasn't kicked (avoid duplicate system message)
        if user.username not in manager.kicked_users:
            await manager.broadcast(room_id, {
                "type": "system",
                "text": f"{user.username} has left the room",
                "room_id": room_id,
            })
        else:
            manager.kicked_users.discard(user.username)
