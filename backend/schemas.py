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
