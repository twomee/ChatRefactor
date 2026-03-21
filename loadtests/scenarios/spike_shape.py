"""
Spike and soak test shapes using Locust's LoadTestShape.

Spike test: sudden traffic burst, then recovery observation.
Soak test: steady moderate load for hours to detect memory leaks.

These shapes control the user count over time — pair them with any
User class (ChatHttpUser, WebSocketChatUser, UserJourneyUser).

Usage:
  # Spike test with HTTP users
  locust -f scenarios/spike_shape.py,scenarios/http_endpoints.py \
    --host http://localhost:8000 --headless --csv reports/spike

  # Soak test with WS users
  locust -f scenarios/spike_shape.py,scenarios/websocket_chat.py \
    --host ws://localhost:8000 --headless --csv reports/soak
"""

import os
import sys
from pathlib import Path

from locust import LoadTestShape

sys.path.insert(0, str(Path(__file__).parent.parent))


class SpikeShape(LoadTestShape):
    """
    Simulates a sudden traffic spike with recovery.

    Timeline:
      0–60s:    Baseline at 10 users (warm-up)
      60–75s:   Ramp UP to 200 users (spike!)
      75–195s:  Hold at 200 users (sustained pressure)
      195–210s: Ramp DOWN to 10 users
      210–330s: Hold at 10 users (recovery observation)

    What you learn:
      - Does the system recover after a spike?
      - Do WebSocket connections get dropped during scale-up?
      - Are there memory leaks from connections that weren't cleaned up?
      - Does Redis pub/sub lag during high broadcast volume?
    """

    stages = [
        {"duration": 60, "users": 10, "spawn_rate": 5},
        {"duration": 75, "users": 200, "spawn_rate": 20},
        {"duration": 195, "users": 200, "spawn_rate": 1},
        {"duration": 210, "users": 10, "spawn_rate": 20},
        {"duration": 330, "users": 10, "spawn_rate": 1},
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < stage["duration"]:
                tick_data = (stage["users"], stage["spawn_rate"])
                return tick_data

        return None


class SoakShape(LoadTestShape):
    """
    Long-duration stability test at moderate load.

    Timeline:
      0–60s:      Ramp to 50 users
      60s–2h:     Hold at 50 users
      2h–2h10s:   Ramp down

    What you learn:
      - Memory leaks (RSS growth over time)
      - Connection leaks (DB connections, file descriptors)
      - Kafka consumer lag accumulation
      - WebSocket connection manager dict growth
        (rooms, socket_to_user, user_to_socket)
    """

    # Duration in seconds — default 2 hours, override via env
    SOAK_DURATION = int(os.getenv("LOADTEST_SOAK_DURATION", str(2 * 3600)))
    SOAK_USERS = int(os.getenv("LOADTEST_SOAK_USERS", "50"))

    def tick(self):
        run_time = self.get_run_time()

        # Phase 1: Ramp up (60s)
        if run_time < 60:
            return (int(self.SOAK_USERS * run_time / 60), 5)

        # Phase 2: Steady state
        if run_time < self.SOAK_DURATION:
            return (self.SOAK_USERS, 1)

        # Phase 3: Ramp down (60s)
        ramp_down_elapsed = run_time - self.SOAK_DURATION
        if ramp_down_elapsed < 60:
            remaining = int(self.SOAK_USERS * (1 - ramp_down_elapsed / 60))
            return (max(remaining, 0), 5)

        return None


class SteppedShape(LoadTestShape):
    """
    Step-function load test for finding breaking points.

    Increases users in steps, holds each step to measure steady-state.
    Useful for capacity planning — find exactly where latency degrades.

    Timeline:
      0–120s:   50 users
      120–240s: 100 users
      240–360s: 150 users
      360–480s: 200 users
      480–600s: 300 users
    """

    steps = [
        {"duration": 120, "users": 50},
        {"duration": 240, "users": 100},
        {"duration": 360, "users": 150},
        {"duration": 480, "users": 200},
        {"duration": 600, "users": 300},
    ]

    def tick(self):
        run_time = self.get_run_time()

        for step in self.steps:
            if run_time < step["duration"]:
                return (step["users"], 10)

        return None
