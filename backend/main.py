# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from auth import hash_password
from config import ADMIN_USERNAME, ADMIN_PASSWORD
from dal import user_dal, room_dal
from database import engine, Base
from routers import auth, rooms, files, admin, websocket, pm

app = FastAPI(title="cHATBOX API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
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
    """Create all tables and seed the default rooms + admin user."""
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        for room_name in ["politics", "sports", "movies"]:
            if not room_dal.get_by_name(db, room_name):
                room_dal.create(db, room_name)

        admin_user = user_dal.get_by_username(db, ADMIN_USERNAME)
        if not admin_user:
            user_dal.create(db, ADMIN_USERNAME, hash_password(ADMIN_PASSWORD), is_global_admin=True)
        elif not admin_user.is_global_admin:
            admin_user.is_global_admin = True
            db.commit()
