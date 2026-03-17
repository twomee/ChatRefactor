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
