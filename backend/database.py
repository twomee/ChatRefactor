# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import DATABASE_URL

# SQLite requires check_same_thread=False for async FastAPI usage
connect_args = {}
engine_kwargs = {"pool_pre_ping": True}

if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    # PostgreSQL connection pool settings
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)
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
