"""Validate that a DiGA monitor workflow run produced persistable outputs."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SNAPSHOT_DIR = Path("data/snapshots")
SCAN_HISTORY_PATH = Path("outputs/scan_history.json")


def main_with_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-snapshot-age-hours", type=float, default=6.0)
    parser.add_argument("--require-current-run", action="store_true")
    parser.add_argument("--verify-head", action="store_true")
    args = parser.parse_args(argv)

    latest_snapshot = latest_snapshot_path()
    if latest_snapshot is None:
        print("::error::No committed snapshot file exists under data/snapshots.")
        return 1

    latest_snapshot_time = parse_snapshot_timestamp(latest_snapshot)
    if latest_snapshot_time is None:
        print(f"::error::Could not parse latest snapshot timestamp: {latest_snapshot}")
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
        if abs((latest_history_time - latest_snapshot_time).total_seconds()) > 15 * 60:
            print(
                "::error::Latest scan_history entry does not match the latest snapshot. "
                f"snapshot={latest_snapshot_time.isoformat()} scan_history={latest_history_time.isoformat()}"
            )
            return 1

    age_hours = (datetime.now(timezone.utc) - latest_snapshot_time).total_seconds() / 3600
    if age_hours > args.max_snapshot_age_hours:
        print(
            "::warning::Latest committed snapshot is stale: "
            f"{latest_snapshot.name} is {age_hours:.1f} hours old."
        )

    if args.verify_head:
        head_files = git_head_files()
        if latest_snapshot.as_posix() not in head_files:
            print(f"::error::Latest snapshot is not present in HEAD: {latest_snapshot}")
            return 1
        if SCAN_HISTORY_PATH.as_posix() not in head_files:
            print(f"::error::Scan history is not present in HEAD: {SCAN_HISTORY_PATH}")
            return 1

    print(f"::notice::Monitoring outputs healthy. latest_snapshot={latest_snapshot}")
    return 0


def main() -> int:
    return main_with_args()


def latest_snapshot_path() -> Path | None:
    snapshots = sorted(SNAPSHOT_DIR.glob("diga_snapshot_*.json"))
    return snapshots[-1] if snapshots else None


def parse_snapshot_timestamp(path: Path) -> datetime | None:
    raw = path.name.removeprefix("diga_snapshot_").removesuffix(".json")
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


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
