"""Validate that a DiGA monitor workflow run produced persistable outputs."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASELINE_PATH = Path("data/baseline/current_snapshot.json")
SCAN_HISTORY_PATH = Path("outputs/scan_history.json")


def main_with_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-snapshot-age-hours", type=float, default=6.0)
    parser.add_argument("--require-current-run", action="store_true")
    parser.add_argument("--verify-head", action="store_true")
    args = parser.parse_args(argv)

    if not BASELINE_PATH.exists():
        print("::error::No operational baseline exists at data/baseline/current_snapshot.json.")
        return 1

    baseline_time = load_baseline_timestamp()
    if baseline_time is None:
        print(f"::error::Operational baseline has no parseable created_at: {BASELINE_PATH}")
        return 1

    history = load_scan_history()
    if not history:
        print("::error::outputs/scan_history.json is missing or empty.")
        return 1
    latest_history_time = parse_datetime(history[-1].get("scan_timestamp"))
    if latest_history_time is None:
        print("::error::Latest scan_history entry has no parseable scan_timestamp.")
        return 1

    if args.require_current_run:
        if abs((latest_history_time - baseline_time).total_seconds()) > 15 * 60:
            print(
                "::error::Latest scan_history entry does not match the operational baseline. "
                f"baseline={baseline_time.isoformat()} scan_history={latest_history_time.isoformat()}"
            )
            return 1

    age_hours = (datetime.now(timezone.utc) - baseline_time).total_seconds() / 3600
    if age_hours > args.max_snapshot_age_hours:
        print(
            "::warning::Operational baseline is stale: "
            f"{BASELINE_PATH} is {age_hours:.1f} hours old."
        )

    if args.verify_head:
        head_files = git_head_files()
        if BASELINE_PATH.as_posix() not in head_files:
            print(f"::error::Operational baseline is not present in HEAD: {BASELINE_PATH}")
            return 1
        if SCAN_HISTORY_PATH.as_posix() not in head_files:
            print(f"::error::Scan history is not present in HEAD: {SCAN_HISTORY_PATH}")
            return 1

    print(f"::notice::Monitoring outputs healthy. operational_baseline={BASELINE_PATH}")
    return 0


def main() -> int:
    return main_with_args()


def load_baseline_timestamp() -> datetime | None:
    try:
        with BASELINE_PATH.open(encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None
    return parse_datetime(payload.get("created_at")) if isinstance(payload, dict) else None


def load_scan_history() -> list[dict[str, Any]]:
    if not SCAN_HISTORY_PATH.exists():
        return []
    with SCAN_HISTORY_PATH.open(encoding="utf-8") as file:
        payload = json.load(file)
    return payload if isinstance(payload, list) else []


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def git_head_files() -> set[str]:
    output = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "HEAD"], text=True)
    return {line.strip() for line in output.splitlines() if line.strip()}


if __name__ == "__main__":
    raise SystemExit(main())
