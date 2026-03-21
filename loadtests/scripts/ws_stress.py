#!/usr/bin/env python3
"""
Standalone WebSocket stress test using pure asyncio.

Opens N concurrent WebSocket connections, each sending messages at intervals.
Measures connection time, message round-trip, and failure rates.
Produces a JSON report for CI integration.

Why standalone (not Locust)?
  Locust uses threads for WebSocket. For maximum concurrent connections,
  asyncio is more efficient — one event loop handles thousands of connections.

Usage:
  python scripts/ws_stress.py --connections 100 --duration 60 --rooms 3
  python scripts/ws_stress.py --connections 300 --duration 300 --msg-interval 2
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config
from utils.user_pool import UserPool
from utils.ws_client import AsyncWSClient, WSMetrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ws_stress")


@dataclass
class StressTestResult:
    """Aggregate results from all connections."""

    total_connections: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    total_messages_sent: int = 0
    total_messages_received: int = 0
    unexpected_disconnects: int = 0
    connect_times_ms: list[float] = field(default_factory=list)
    round_trip_times_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def summary(self) -> dict:
        ct = sorted(self.connect_times_ms) if self.connect_times_ms else [0]
        rt = sorted(self.round_trip_times_ms) if self.round_trip_times_ms else [0]

        def pct(arr, p):
            idx = min(int(len(arr) * p / 100), len(arr) - 1)
            return round(arr[idx], 2)

        return {
            "total_connections": self.total_connections,
            "successful_connections": self.successful_connections,
            "failed_connections": self.failed_connections,
            "connection_success_rate": round(
                self.successful_connections / max(self.total_connections, 1) * 100, 1
            ),
            "unexpected_disconnects": self.unexpected_disconnects,
            "total_messages_sent": self.total_messages_sent,
            "total_messages_received": self.total_messages_received,
            "connect_time": {
                "avg_ms": round(sum(ct) / max(len(ct), 1), 2),
                "p50_ms": pct(ct, 50),
                "p95_ms": pct(ct, 95),
                "p99_ms": pct(ct, 99),
                "max_ms": round(ct[-1], 2),
            },
            "round_trip": {
                "avg_ms": round(sum(rt) / max(len(rt), 1), 2),
                "p50_ms": pct(rt, 50),
                "p95_ms": pct(rt, 95),
                "p99_ms": pct(rt, 99),
                "max_ms": round(rt[-1], 2),
            },
            "throughput": {
                "messages_per_second": round(
                    self.total_messages_sent / max(self.duration_seconds, 1), 1
                ),
            },
            "errors": self.errors[:20],  # First 20 errors
            "duration_seconds": round(self.duration_seconds, 1),
        }


async def run_single_client(
    creds: dict,
    room_id: int,
    duration: float,
    msg_interval: float,
    result: StressTestResult,
    semaphore: asyncio.Semaphore,
):
    """Run a single WebSocket client for `duration` seconds."""
    async with semaphore:
        client = AsyncWSClient(config.ws_base, creds["token"], room_id)
        result.total_connections += 1

        try:
            connect_time = await client.connect(timeout=15.0)
            result.successful_connections += 1
            result.connect_times_ms.append(connect_time)
        except Exception as e:
            result.failed_connections += 1
            result.errors.append(f"connect({creds['username']}): {e}")
            return

        try:
            end_time = time.monotonic() + duration
            while time.monotonic() < end_time:
                msg_text = f"stress_{uuid.uuid4().hex[:8]}"
                try:
                    rt = await client.send_and_wait_echo(msg_text, timeout=10.0)
                    result.round_trip_times_ms.append(rt)
                except asyncio.TimeoutError:
                    result.errors.append(
                        f"timeout({creds['username']}): no echo for '{msg_text}'"
                    )
                except Exception as e:
                    result.errors.append(f"send({creds['username']}): {e}")
                    break

                await asyncio.sleep(msg_interval)

            result.total_messages_sent += client.metrics.messages_sent
            result.total_messages_received += client.metrics.messages_received

            if client.metrics.disconnected_unexpectedly:
                result.unexpected_disconnects += 1

        finally:
            await client.close()


async def run_stress_test(
    num_connections: int,
    duration: float,
    num_rooms: int,
    msg_interval: float,
    max_concurrent_connects: int = 50,
) -> StressTestResult:
    """
    Run the full stress test:
      1. Provision users
      2. Open N connections across rooms
      3. Each sends messages for `duration` seconds
      4. Collect and aggregate metrics
    """
    result = StressTestResult()

    # Provision users
    pool = UserPool()
    logger.info(f"Provisioning {num_connections} users ...")
    pool.provision(num_connections)

    if pool.total_provisioned < num_connections:
        logger.warning(
            f"Only provisioned {pool.total_provisioned}/{num_connections} users"
        )

    room_ids = pool.room_ids[:num_rooms]
    if not room_ids:
        logger.error("No rooms available. Aborting.")
        return result

    all_creds = pool.get_all()
    creds_to_use = all_creds[:num_connections]

    # Limit concurrent connection establishment to avoid thundering herd
    semaphore = asyncio.Semaphore(max_concurrent_connects)

    logger.info(
        f"Starting stress test: {len(creds_to_use)} connections, "
        f"{num_rooms} rooms, {duration}s duration, "
        f"{msg_interval}s between messages"
    )

    start_time = time.monotonic()

    # Launch all clients concurrently
    tasks = []
    for i, creds in enumerate(creds_to_use):
        room_id = room_ids[i % len(room_ids)]
        tasks.append(
            run_single_client(
                creds, room_id, duration, msg_interval, result, semaphore
            )
        )

    await asyncio.gather(*tasks, return_exceptions=True)

    result.duration_seconds = time.monotonic() - start_time
    return result


def main():
    parser = argparse.ArgumentParser(
        description="WebSocket stress test for cHATBOX"
    )
    parser.add_argument(
        "--connections", type=int, default=100,
        help="Number of concurrent WebSocket connections (default: 100)",
    )
    parser.add_argument(
        "--duration", type=int, default=60,
        help="Test duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--rooms", type=int, default=3,
        help="Number of rooms to distribute connections across (default: 3)",
    )
    parser.add_argument(
        "--msg-interval", type=float, default=2.0,
        help="Seconds between messages per client (default: 2.0)",
    )
    parser.add_argument(
        "--max-concurrent-connects", type=int, default=50,
        help="Max simultaneous connection attempts (default: 50)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output JSON file path (default: reports/ws_stress_TIMESTAMP.json)",
    )
    args = parser.parse_args()

    # Run the test
    result = asyncio.run(
        run_stress_test(
            num_connections=args.connections,
            duration=args.duration,
            num_rooms=args.rooms,
            msg_interval=args.msg_interval,
            max_concurrent_connects=args.max_concurrent_connects,
        )
    )

    summary = result.summary()

    # Output
    output_path = args.output
    if not output_path:
        reports_dir = Path(__file__).parent.parent / "reports"
        reports_dir.mkdir(exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        output_path = str(reports_dir / f"ws_stress_{ts}.json")

    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("WEBSOCKET STRESS TEST RESULTS")
    print("=" * 60)
    print(f"Connections: {summary['successful_connections']}/{summary['total_connections']} "
          f"({summary['connection_success_rate']}% success)")
    print(f"Unexpected disconnects: {summary['unexpected_disconnects']}")
    print(f"Messages sent: {summary['total_messages_sent']}")
    print(f"Throughput: {summary['throughput']['messages_per_second']} msg/s")
    print(f"\nConnect time:")
    ct = summary["connect_time"]
    print(f"  avg={ct['avg_ms']}ms  p50={ct['p50_ms']}ms  "
          f"p95={ct['p95_ms']}ms  p99={ct['p99_ms']}ms  max={ct['max_ms']}ms")
    print(f"\nMessage round-trip:")
    rt = summary["round_trip"]
    print(f"  avg={rt['avg_ms']}ms  p50={rt['p50_ms']}ms  "
          f"p95={rt['p95_ms']}ms  p99={rt['p99_ms']}ms  max={rt['max_ms']}ms")
    print(f"\nDuration: {summary['duration_seconds']}s")
    if summary["errors"]:
        print(f"\nFirst {len(summary['errors'])} errors:")
        for err in summary["errors"][:5]:
            print(f"  - {err}")
    print(f"\nReport saved to: {output_path}")

    # Exit code for CI
    fail = (
        summary["connection_success_rate"] < 95
        or summary["round_trip"]["p95_ms"] > 500
    )
    if fail:
        print("\nVERDICT: FAIL")
        sys.exit(1)
    else:
        print("\nVERDICT: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
