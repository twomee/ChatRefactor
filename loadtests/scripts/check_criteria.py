#!/usr/bin/env python3
"""
CI gate: check Locust CSV results against pass/fail criteria.

Reads Locust's _stats.csv output and checks:
  - Overall error rate < threshold
  - p95 response time < threshold
  - p99 response time < threshold
  - No endpoints with 100% failure rate

Exit code 0 = PASS, 1 = FAIL.

Usage:
  python scripts/check_criteria.py --stats reports/http_stats.csv
  python scripts/check_criteria.py --stats reports/http_stats.csv \
    --max-error-rate 1.0 --max-p95 200 --max-p99 500
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def load_locust_stats(csv_path: str) -> list[dict]:
    """Parse Locust's _stats.csv file."""
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def check_criteria(
    stats: list[dict],
    max_error_rate: float = 1.0,
    max_p95_ms: float = 200.0,
    max_p99_ms: float = 500.0,
) -> dict:
    """
    Check pass/fail criteria against Locust stats.

    Returns a dict with:
      - passed: bool
      - checks: list of individual check results
      - summary: overall stats
    """
    checks = []
    overall_passed = True

    # Find the "Aggregated" row (Locust puts this as the last row)
    aggregated = None
    endpoint_rows = []

    for row in stats:
        name = row.get("Name", "")
        if name == "Aggregated":
            aggregated = row
        elif name:
            endpoint_rows.append(row)

    if not aggregated:
        return {
            "passed": False,
            "checks": [{"name": "stats_file", "passed": False,
                         "detail": "No Aggregated row found in CSV"}],
            "summary": {},
        }

    # Parse aggregated values
    total_requests = int(aggregated.get("Request Count", 0))
    total_failures = int(aggregated.get("Failure Count", 0))
    error_rate = (total_failures / max(total_requests, 1)) * 100
    p95 = float(aggregated.get("95%", 0))
    p99 = float(aggregated.get("99%", 0))
    avg_response = float(aggregated.get("Average Response Time", 0))
    rps = float(aggregated.get("Requests/s", 0))

    # Check 1: Error rate
    error_check = error_rate <= max_error_rate
    checks.append({
        "name": "error_rate",
        "passed": error_check,
        "detail": f"{error_rate:.2f}% (threshold: {max_error_rate}%)",
        "value": round(error_rate, 2),
        "threshold": max_error_rate,
    })
    if not error_check:
        overall_passed = False

    # Check 2: p95 response time
    p95_check = p95 <= max_p95_ms
    checks.append({
        "name": "p95_response_time",
        "passed": p95_check,
        "detail": f"{p95:.0f}ms (threshold: {max_p95_ms:.0f}ms)",
        "value": p95,
        "threshold": max_p95_ms,
    })
    if not p95_check:
        overall_passed = False

    # Check 3: p99 response time
    p99_check = p99 <= max_p99_ms
    checks.append({
        "name": "p99_response_time",
        "passed": p99_check,
        "detail": f"{p99:.0f}ms (threshold: {max_p99_ms:.0f}ms)",
        "value": p99,
        "threshold": max_p99_ms,
    })
    if not p99_check:
        overall_passed = False

    # Check 4: No endpoint with 100% failure
    for row in endpoint_rows:
        name = row.get("Name", "unknown")
        req_count = int(row.get("Request Count", 0))
        fail_count = int(row.get("Failure Count", 0))

        if req_count > 0 and fail_count == req_count:
            checks.append({
                "name": f"endpoint_{name}",
                "passed": False,
                "detail": f"100% failure rate ({fail_count}/{req_count})",
            })
            overall_passed = False

    # Check 5: Minimum throughput (at least some requests were made)
    if total_requests < 10:
        checks.append({
            "name": "minimum_requests",
            "passed": False,
            "detail": f"Only {total_requests} requests (minimum: 10)",
        })
        overall_passed = False

    return {
        "passed": overall_passed,
        "checks": checks,
        "summary": {
            "total_requests": total_requests,
            "total_failures": total_failures,
            "error_rate_percent": round(error_rate, 2),
            "avg_response_ms": round(avg_response, 1),
            "p95_ms": p95,
            "p99_ms": p99,
            "requests_per_second": round(rps, 1),
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check load test results against pass/fail criteria"
    )
    parser.add_argument(
        "--stats", required=True,
        help="Path to Locust _stats.csv file",
    )
    parser.add_argument(
        "--max-error-rate", type=float, default=1.0,
        help="Max acceptable error rate in percent (default: 1.0)",
    )
    parser.add_argument(
        "--max-p95", type=float, default=200.0,
        help="Max acceptable p95 response time in ms (default: 200)",
    )
    parser.add_argument(
        "--max-p99", type=float, default=500.0,
        help="Max acceptable p99 response time in ms (default: 500)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write JSON report to file",
    )
    args = parser.parse_args()

    stats = load_locust_stats(args.stats)
    result = check_criteria(
        stats,
        max_error_rate=args.max_error_rate,
        max_p95_ms=args.max_p95,
        max_p99_ms=args.max_p99,
    )

    # Print report
    print("\n" + "=" * 60)
    print("LOAD TEST CRITERIA CHECK")
    print("=" * 60)

    for check in result["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"  [{status}] {check['name']}: {check['detail']}")

    summary = result["summary"]
    if summary:
        print(f"\n  Total requests: {summary.get('total_requests', 'N/A')}")
        print(f"  Requests/sec:   {summary.get('requests_per_second', 'N/A')}")
        print(f"  Avg response:   {summary.get('avg_response_ms', 'N/A')}ms")

    verdict = "PASS" if result["passed"] else "FAIL"
    print(f"\n  VERDICT: {verdict}")
    print("=" * 60)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nReport saved to: {args.output}")

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
