"""Load test configuration — reads from environment or .env files."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).parent


@dataclass
class LoadTestConfig:
    api_base: str = "http://localhost"
    ws_base: str = "ws://localhost"

    # User provisioning
    num_users: int = 200
    user_prefix: str = "loadtest_user"
    user_password: str = "loadtest_pass_123"

    # Admin credentials (for room creation, etc.)
    admin_username: str = "ido"
    admin_password: str = "changeme"

    # Rooms to use in load tests
    room_names: list[str] = field(
        default_factory=lambda: ["politics", "sports", "movies"]
    )

    # Default scenario parameters
    default_users: int = 50
    default_spawn_rate: int = 10
    default_duration: str = "5m"

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "LoadTestConfig":
        if env_file:
            load_dotenv(env_file, override=True)

        rooms_str = os.getenv("LOADTEST_ROOMS", "politics,sports,movies")
        return cls(
            api_base=os.getenv("LOADTEST_API_BASE", "http://localhost"),
            ws_base=os.getenv("LOADTEST_WS_BASE", "ws://localhost"),
            num_users=int(os.getenv("LOADTEST_NUM_USERS", "200")),
            user_prefix=os.getenv("LOADTEST_USER_PREFIX", "loadtest_user"),
            user_password=os.getenv("LOADTEST_USER_PASSWORD", "loadtest_pass_123"),
            admin_username=os.getenv("ADMIN_USERNAME", "ido"),
            admin_password=os.getenv("ADMIN_PASSWORD", "changeme"),
            room_names=[r.strip() for r in rooms_str.split(",") if r.strip()],
            default_users=int(os.getenv("LOADTEST_DEFAULT_USERS", "50")),
            default_spawn_rate=int(os.getenv("LOADTEST_SPAWN_RATE", "10")),
            default_duration=os.getenv("LOADTEST_DEFAULT_DURATION", "5m"),
        )


# Singleton — imported by scenarios and utilities
config = LoadTestConfig.from_env(
    env_file=os.getenv("LOADTEST_ENV_FILE")
)
