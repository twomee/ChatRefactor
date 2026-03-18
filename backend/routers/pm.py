# routers/pm.py — Thin controller for HTTP-based private messaging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from ws_manager import manager
import models

router = APIRouter(prefix="/pm", tags=["pm"])


class PMSendRequest(BaseModel):
    to: str
    text: str


@router.post("/send")
async def send_pm(
    body: PMSendRequest,
    current_user: models.User = Depends(get_current_user),
):
    if not body.text.strip():
        raise HTTPException(400, "Cannot send empty message")
    if body.to == current_user.username:
        raise HTTPException(400, "Cannot send a private message to yourself")
    if not manager.is_user_online(body.to):
        raise HTTPException(404, "User is not online")

    msg_id = str(uuid.uuid4())
    await manager.send_personal(body.to, {
        "type": "private_message",
        "from": current_user.username,
        "to": body.to,
        "text": body.text,
        "msg_id": msg_id,
    })
    return {"msg_id": msg_id, "from": current_user.username, "to": body.to, "text": body.text}
