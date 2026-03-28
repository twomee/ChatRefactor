# app/core/database.py — SQLAlchemy engine, session factory, and Base
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import DATABASE_URL

_engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL and not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(pool_size=10, max_overflow=20, pool_timeout=5, pool_recycle=1800)
engine = create_engine(DATABASE_URL, **_engine_kwargs)
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
