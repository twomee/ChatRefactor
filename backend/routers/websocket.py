# routers/websocket.py — WebSocket controller for real-time chat
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.orm import Session

from auth import decode_token
from dal import room_dal
from database import get_db
from services import room_service, message_service
from ws_manager import manager

router = APIRouter(tags=["websocket"])


def _extract_error_detail(exc: Exception) -> str:
    return exc.detail if hasattr(exc, "detail") else str(exc)


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    # ── Authenticate ──────────────────────────────────────────────────
    user = decode_token(token, db)
    if not user:
        await websocket.close(code=4001)
        return

    # ── Validate room ─────────────────────────────────────────────────
    room = room_dal.get_by_id(db, room_id)
    if not room:
        await websocket.close(code=4004)
        return
    if not room.is_active:
        await websocket.close(code=4002)
        return
    if manager.is_user_in_room(user.username, room_id):
        await websocket.close(code=4003)
        return

    # ── Connect ───────────────────────────────────────────────────────
    await manager.connect(websocket, room_id, user.username)

    # Auto-promote first user in room to admin
    became_admin = False
    users_now = manager.get_users_in_room(room_id)
    if len(users_now) == 1:
        became_admin = room_service.auto_promote_first_user(user, room_id, db)

    # Send message history
    history = message_service.get_room_history(db, room_id)
    await websocket.send_json({"type": "history", "messages": history, "room_id": room_id})

    # Announce join with authoritative admin/muted state
    admins_now = room_service.get_admins_in_room(room_id, db, users_now)
    muted_now = room_service.get_muted_in_room(room_id, db, users_now)
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

    # ── Message loop ──────────────────────────────────────────────────
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            db.refresh(room)
            if not room.is_active:
                await websocket.send_json({"type": "error", "detail": "Room is closed"})
                continue

            if msg_type == "message":
                await _handle_chat_message(websocket, user, room_id, data, db)

            elif msg_type == "private_message":
                await _handle_private_message(websocket, user, data)

            elif msg_type == "kick":
                await _handle_kick(websocket, user, room_id, data, db)

            elif msg_type == "mute":
                await _handle_mute(user, room_id, data, db, websocket)

            elif msg_type == "unmute":
                await _handle_unmute(user, room_id, data, db, websocket)

            elif msg_type == "promote":
                await _handle_promote(user, room_id, data, db, websocket)

    except WebSocketDisconnect:
        await _handle_disconnect(websocket, user, room_id, db)


# ── Message handlers ──────────────────────────────────────────────────

async def _handle_chat_message(websocket, user, room_id, data, db):
    if room_service.is_muted_in_room(user.username, room_id, db):
        await websocket.send_json({"type": "error", "detail": "You are muted in this room"})
        return
    text = data.get("text", "")
    message_service.save_message(db, user.id, room_id, text)
    await manager.broadcast(room_id, {
        "type": "message",
        "from": user.username,
        "text": text,
        "room_id": room_id,
    })


async def _handle_private_message(websocket, user, data):
    target = data.get("to")
    if not target or target == user.username:
        await websocket.send_json({"type": "error", "detail": "Invalid private message target"})
        return
    text = data.get("text", "")
    if not text.strip():
        await websocket.send_json({"type": "error", "detail": "Cannot send empty private message"})
        return
    pm_payload = {"type": "private_message", "from": user.username, "to": target, "text": text}
    await manager.send_personal(target, pm_payload)
    await websocket.send_json({**pm_payload, "self": True})


async def _handle_kick(websocket, user, room_id, data, db):
    target = data.get("target")
    if not target or target == user.username:
        await websocket.send_json({"type": "error", "detail": "Cannot kick yourself"})
        return
    if not room_service.is_admin_in_room(user.username, room_id, db):
        await websocket.send_json({"type": "error", "detail": "Not an admin"})
        return
    if room_service.is_admin_in_room(target, room_id, db):
        await websocket.send_json({"type": "error", "detail": "Cannot kick another admin"})
        return
    manager.kicked_users.add(target)
    for target_ws in list(manager.user_to_socket.get(target, set())):
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


async def _handle_mute(user, room_id, data, db, websocket):
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
        await websocket.send_json({"type": "error", "detail": _extract_error_detail(e)})


async def _handle_unmute(user, room_id, data, db, websocket):
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
        await websocket.send_json({"type": "error", "detail": _extract_error_detail(e)})


async def _handle_promote(user, room_id, data, db, websocket):
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
        await websocket.send_json({"type": "error", "detail": _extract_error_detail(e)})


async def _handle_disconnect(websocket, user, room_id, db):
    manager.disconnect(websocket, room_id)

    # Clear mute on leave
    was_muted = room_service.clear_user_mute_on_leave(user, room_id, db)
    if was_muted:
        await manager.broadcast(room_id, {"type": "unmuted", "username": user.username, "room_id": room_id})

    # Admin succession
    if room_service.is_admin_in_room(user.username, room_id, db):
        await room_service.handle_admin_succession(room_id, user.username, db, manager)

    # Broadcast updated user list
    remaining = manager.get_users_in_room(room_id)
    await manager.broadcast(room_id, {
        "type": "user_left",
        "username": user.username,
        "users": remaining,
        "admins": room_service.get_admins_in_room(room_id, db, remaining),
        "muted": room_service.get_muted_in_room(room_id, db, remaining),
        "room_id": room_id,
    })

    if user.username not in manager.kicked_users:
        await manager.broadcast(room_id, {
            "type": "system",
            "text": f"{user.username} has left the room",
            "room_id": room_id,
        })
    else:
        manager.kicked_users.discard(user.username)
