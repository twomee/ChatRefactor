# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import auth, rooms, files, admin, websocket, pm
from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD
import models
from sqlalchemy.orm import Session

app = FastAPI(title="cHATBOX API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(files.router)
app.include_router(admin.router)
app.include_router(websocket.router)
app.include_router(pm.router)


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
