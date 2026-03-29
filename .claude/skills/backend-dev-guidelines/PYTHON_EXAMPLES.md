# Python/FastAPI Backend Examples

## Table of Contents

- [Project Structure](#project-structure)
- [Dependency Injection](#dependency-injection)
- [Route Handler](#route-handler)
- [Service](#service)
- [Repository](#repository)
- [Error Handling](#error-handling)
- [Validation](#validation)
- [Middleware](#middleware)
- [Structured Logging](#structured-logging)
- [Configuration](#configuration)
- [Health Checks](#health-checks)
- [Graceful Shutdown](#graceful-shutdown)
- [Dockerfile](#dockerfile)

---

## Project Structure

```
auth-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # Entrypoint — app factory, startup, shutdown
│   ├── routes/
│   │   └── user_routes.py   # Route handlers
│   ├── services/
│   │   └── user_service.py  # Business logic
│   ├── repositories/
│   │   └── user_repo.py     # Database access
│   ├── models/
│   │   └── user.py          # Domain types, Pydantic schemas
│   ├── middleware/
│   │   └── auth.py          # Middleware
│   └── config.py            # Configuration
├── tests/
├── requirements.txt
└── pyproject.toml
```

---

## Dependency Injection

```python
# app/main.py
from fastapi import FastAPI
from app.config import Settings
from app.repositories.user_repo import UserRepository
from app.services.user_service import UserService
from app.routes.user_routes import create_user_router

def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI()

    # Build dependency chain: repo → service → router
    db = create_db_session(settings.database_url)
    user_repo = UserRepository(db)
    user_service = UserService(user_repo)

    app.include_router(create_user_router(user_service))

    return app

# Alternative: FastAPI's Depends() system
# app/dependencies.py
from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()

def get_db(settings: Settings = Depends(get_settings)):
    db = SessionLocal(settings.database_url)
    try:
        yield db
    finally:
        db.close()

def get_user_repo(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)

def get_user_service(repo: UserRepository = Depends(get_user_repo)) -> UserService:
    return UserService(repo)
```

---

## Route Handler

```python
# app/routes/user_routes.py
from fastapi import APIRouter, HTTPException, status

def create_user_router(user_service: UserService) -> APIRouter:
    router = APIRouter(prefix="/users", tags=["users"])

    @router.post("/", status_code=status.HTTP_201_CREATED)
    async def create_user(request: CreateUserRequest):
        # 1. Input already validated by Pydantic (format-level)
        # 2. Call service (no business logic here)
        try:
            user = await user_service.create_user(request.email, request.name)
        except UserAlreadyExistsError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "RESOURCE_ALREADY_EXISTS", "message": "Email already registered"},
            )
        # 3. Return response
        return UserResponse.model_validate(user)

    @router.get("/{user_id}")
    async def get_user(user_id: str):
        user = await user_service.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RESOURCE_NOT_FOUND", "message": "User not found"},
            )
        return UserResponse.model_validate(user)

    return router
```

---

## Service

```python
# app/services/user_service.py
from typing import Protocol

# Interface — defined by the consumer
class UserRepositoryProtocol(Protocol):
    async def create(self, user: User) -> None: ...
    async def find_by_id(self, user_id: str) -> User | None: ...
    async def find_by_email(self, email: str) -> User | None: ...

class UserService:
    def __init__(self, user_repo: UserRepositoryProtocol):
        self.user_repo = user_repo

    async def create_user(self, email: str, name: str) -> User:
        # Business validation
        existing = await self.user_repo.find_by_email(email)
        if existing:
            raise UserAlreadyExistsError(f"User with email {email} already exists")

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
        )

        await self.user_repo.create(user)
        return user

    async def get_user(self, user_id: str) -> User | None:
        return await self.user_repo.find_by_id(user_id)
```

---

## Repository

```python
# app/repositories/user_repo.py
from sqlalchemy.ext.asyncio import AsyncSession

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_email(self, email: str) -> User | None:
        # Always use parameterized queries
        result = await self.db.execute(
            select(UserModel).where(UserModel.email == email)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return User(id=row.id, email=row.email, name=row.name)

    async def create(self, user: User) -> None:
        db_user = UserModel(id=user.id, email=user.email, name=user.name)
        self.db.add(db_user)
        await self.db.commit()

    async def find_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return User(id=row.id, email=row.email, name=row.name)
```

---

## Error Handling

```python
# app/services/exceptions.py
class ServiceError(Exception):
    """Base exception for service-layer errors."""

class UserAlreadyExistsError(ServiceError):
    pass

class UserNotFoundError(ServiceError):
    pass

# app/routes/error_handlers.py
from fastapi import Request
from fastapi.responses import JSONResponse

async def service_error_handler(request: Request, exc: ServiceError):
    error_map = {
        UserNotFoundError: (404, "RESOURCE_NOT_FOUND"),
        UserAlreadyExistsError: (409, "RESOURCE_ALREADY_EXISTS"),
    }

    status_code, code = error_map.get(type(exc), (500, "INTERNAL_ERROR"))
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": str(exc)}},
    )

# Register in main.py
app.add_exception_handler(ServiceError, service_error_handler)
```

---

## Validation

```python
# app/models/user.py — Pydantic handles format validation
from pydantic import BaseModel, EmailStr, Field

class CreateUserRequest(BaseModel):
    email: EmailStr                          # validates email format
    name: str = Field(..., min_length=1, max_length=100)  # validates length

# Service handles business validation
class UserService:
    async def create_user(self, email: str, name: str) -> User:
        # Business rule: email must be unique
        existing = await self.user_repo.find_by_email(email)
        if existing:
            raise UserAlreadyExistsError(f"Email {email} already registered")
```

---

## Middleware

```python
# app/middleware/request_id.py
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

# app/middleware/logging.py
import time

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        logger.info("request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
            request_id=getattr(request.state, "request_id", "unknown"),
        )
        return response

# Register in main.py (order: last added = outermost)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
```

---

## Structured Logging

```python
# Use structlog
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger()

# Usage
logger.info("user_created", user_id=user.id, email=user.email)
logger.error("failed_to_create_user", error=str(err), email=email)

# Never do this:
logger.info(f"User {user.id} created with email {user.email}")
```

---

## Configuration

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    port: int = 8000
    database_url: str                    # required — no default means fail if missing
    redis_url: str                       # required
    secret_key: str                      # required
    log_level: str = "info"

    model_config = {
        "env_file": ".env",             # load from .env for local dev
        "env_file_encoding": "utf-8",
    }

# Usage — fails at startup if required vars are missing
settings = Settings()
```

---

## Health Checks

```python
@router.get("/healthz")
async def liveness():
    """Liveness — is the process running?"""
    return {"status": "ok"}

@router.get("/readyz")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Readiness — can it serve traffic?"""
    checks = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "failed"
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks},
        )

    return {"status": "ready", "checks": checks}
```

---

## Graceful Shutdown

```python
# app/main.py
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("server_starting", port=settings.port)
    db_engine = create_async_engine(settings.database_url)
    app.state.db_engine = db_engine

    yield  # App runs here

    # Shutdown
    logger.info("shutting_down")
    await db_engine.dispose()
    logger.info("shutdown_complete")

app = FastAPI(lifespan=lifespan)
```

---

## Dockerfile

```dockerfile
# Build stage
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Production stage
FROM python:3.12-slim
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1001 appuser
USER appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
