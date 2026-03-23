#!/usr/bin/env python3
"""
Load test orchestrator — runs all scenarios sequentially.

Levels:
  smoke:  Quick validation (10 users, 2 min) — use in CI
  load:   Standard load test (100 users, 10 min)
  stress: Find breaking points (300 users, 15 min)

Usage:
  python scripts/run_all.py --level smoke
  python scripts/run_all.py --level load --env config/environments/staging.env
  python scripts/run_all.py --level stress
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

LOADTESTS_DIR = Path(__file__).parent.parent
REPORTS_DIR = LOADTESTS_DIR / "reports"
SCENARIOS_DIR = LOADTESTS_DIR / "scenarios"
SCRIPTS_DIR = LOADTESTS_DIR / "scripts"


@dataclass
class TestLevel:
    users: int
    spawn_rate: int
    duration: str
    ws_connections: int
    ws_duration: int


LEVELS = {
    "smoke": TestLevel(users=10, spawn_rate=5, duration="2m", ws_connections=20, ws_duration=60),
    "load": TestLevel(users=100, spawn_rate=10, duration="10m", ws_connections=100, ws_duration=300),
    "stress": TestLevel(users=300, spawn_rate=20, duration="15m", ws_connections=300, ws_duration=600),
}


def run_command(cmd: list[str], label: str) -> tuple[int, float]:
    """Run a command, print output, return (exit_code, duration_seconds)."""
    print(f"\n{'=' * 60}")
    print(f"RUNNING: {label}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 60}\n")

    start = time.monotonic()
    result = subprocess.run(cmd, cwd=str(LOADTESTS_DIR))
    duration = time.monotonic() - start

    status = "PASSED" if result.returncode == 0 else "FAILED"
    print(f"\n[{status}] {label} (took {duration:.1f}s)")

    return result.returncode, duration


def wait_for_server(host: str, timeout: int = 60) -> bool:
    """Wait for Kong and the chat-service to be ready."""
    import requests  # noqa: local import

    print(f"Waiting for server at {host}/rooms ...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{host}/rooms", timeout=5)
            # 200 = up and authenticated, 401 = Kong + chat-service is up
            if resp.status_code in (200, 401):
                print("Server is ready!")
                return True
        except Exception:
            pass
        time.sleep(2)

    print(f"Server not ready after {timeout}s")
    return False


def main():
    parser = argparse.ArgumentParser(description="Run all load test scenarios")
    parser.add_argument(
        "--level",
        choices=["smoke", "load", "stress"],
        default="smoke",
        help="Test intensity level (default: smoke)",
    )
    parser.add_argument("--env", type=str, help="Path to .env file")
    parser.add_argument(
        "--host",
        type=str,
        default="http://localhost",
        help="Target host (default: http://localhost)",
    )
    parser.add_argument(
        "--skip-provision", action="store_true",
        help="Skip user provisioning (if already done)",
    )
    parser.add_argument(
        "--skip-ws", action="store_true",
        help="Skip WebSocket stress test",
    )
    args = parser.parse_args()

    level = LEVELS[args.level]
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    prefix = f"{args.level}_{timestamp}"

    # Set environment
    env_vars = os.environ.copy()
    if args.env:
        env_vars["LOADTEST_ENV_FILE"] = args.env

    results = []

    # ── Step 0: Check server readiness ──
    if not wait_for_server(args.host):
        print("ABORT: Server is not available")
        sys.exit(1)

    # ── Step 1: Provision users ──
    if not args.skip_provision:
        num_users = max(level.users, level.ws_connections) + 50  # Buffer
        rc, dur = run_command(
            [
                sys.executable, "-m", "utils.user_pool",
                "--provision", str(num_users),
            ],
            f"Provision {num_users} users",
        )
        results.append({"name": "provision", "exit_code": rc, "duration": dur})
        if rc != 0:
            print("ABORT: User provisioning failed")
            sys.exit(1)

    # ── Step 2: HTTP endpoint load test ──
    http_csv = str(REPORTS_DIR / f"{prefix}_http")
    http_html = str(REPORTS_DIR / f"{prefix}_http.html")
    rc, dur = run_command(
        [
            sys.executable, "-m", "locust",
            "-f", str(SCENARIOS_DIR / "http_endpoints.py"),
            "--headless",
            "--users", str(level.users),
            "--spawn-rate", str(level.spawn_rate),
            "--run-time", level.duration,
            "--host", args.host,
            "--csv", http_csv,
            "--html", http_html,
        ],
        f"HTTP Endpoint Load Test ({level.users} users, {level.duration})",
    )
    results.append({"name": "http_endpoints", "exit_code": rc, "duration": dur})

    # ── Step 3: User journey test ──
    journey_csv = str(REPORTS_DIR / f"{prefix}_journey")
    journey_html = str(REPORTS_DIR / f"{prefix}_journey.html")
    journey_users = max(level.users // 5, 5)  # Fewer users for journey (heavier)
    rc, dur = run_command(
        [
            sys.executable, "-m", "locust",
            "-f", str(SCENARIOS_DIR / "user_journey.py"),
            "--headless",
            "--users", str(journey_users),
            "--spawn-rate", str(max(level.spawn_rate // 2, 1)),
            "--run-time", level.duration,
            "--host", args.host,
            "--csv", journey_csv,
            "--html", journey_html,
        ],
        f"User Journey Test ({journey_users} users, {level.duration})",
    )
    results.append({"name": "user_journey", "exit_code": rc, "duration": dur})

    # ── Step 4: WebSocket stress test ──
    if not args.skip_ws:
        ws_output = str(REPORTS_DIR / f"{prefix}_ws_stress.json")
        ws_base = args.host.replace("http://", "ws://").replace("https://", "wss://")
        rc, dur = run_command(
            [
                sys.executable, str(SCRIPTS_DIR / "ws_stress.py"),
                "--connections", str(level.ws_connections),
                "--duration", str(level.ws_duration),
                "--rooms", "3",
                "--output", ws_output,
            ],
            f"WebSocket Stress Test ({level.ws_connections} connections, {level.ws_duration}s)",
        )
        results.append({"name": "ws_stress", "exit_code": rc, "duration": dur})

    # ── Step 5: Check criteria on HTTP results ──
    http_stats_csv = f"{http_csv}_stats.csv"
    criteria_output = str(REPORTS_DIR / f"{prefix}_criteria.json")
    rc, dur = run_command(
        [
            sys.executable, str(SCRIPTS_DIR / "check_criteria.py"),
            "--stats", http_stats_csv,
            "--max-error-rate", "1.0",
            "--max-p95", "500" if args.level == "smoke" else "200",
            "--max-p99", "1000" if args.level == "smoke" else "500",
            "--output", criteria_output,
        ],
        "Check Pass/Fail Criteria",
    )
    results.append({"name": "criteria_check", "exit_code": rc, "duration": dur})

    # ── Summary ──
    print("\n" + "=" * 60)
    print(f"ALL TESTS COMPLETE — Level: {args.level}")
    print("=" * 60)

    all_passed = True
    for r in results:
        status = "PASS" if r["exit_code"] == 0 else "FAIL"
        if r["exit_code"] != 0:
            all_passed = False
        print(f"  [{status}] {r['name']} ({r['duration']:.1f}s)")

    print(f"\nReports directory: {REPORTS_DIR}")
    print(f"Generated files: {prefix}_*")

    # Save summary
    summary_path = str(REPORTS_DIR / f"{prefix}_summary.json")
    with open(summary_path, "w") as f:
        json.dump(
            {
                "level": args.level,
                "host": args.host,
                "timestamp": timestamp,
                "results": results,
                "all_passed": all_passed,
            },
            f,
            indent=2,
        )

    print(f"\nOVERALL VERDICT: {'PASS' if all_passed else 'FAIL'}")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
