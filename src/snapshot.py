"""Create, store, and load local DiGA snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SNAPSHOT_DIR = Path("data/snapshots")


@dataclass(frozen=True)
class Snapshot:
    path: Path
    created_at: str
    entries: list[dict[str, Any]]


def ensure_snapshot_dir(snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return snapshot_dir


def create_snapshot_payload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(entries),
        "entries": entries,
    }


def save_snapshot(
    entries: list[dict[str, Any]],
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
) -> Path:
    ensure_snapshot_dir(snapshot_dir)
    payload = create_snapshot_payload(entries)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_path = snapshot_dir / f"diga_snapshot_{timestamp}.json"

    with snapshot_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")

    return snapshot_path


def load_snapshot(path: Path) -> Snapshot:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError(f"Snapshot has invalid entries field: {path}")

    return Snapshot(
        path=path,
        created_at=str(payload.get("created_at", "unknown")),
        entries=entries,
    )


def list_snapshot_paths(snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR) -> list[Path]:
    if not snapshot_dir.exists():
        return []
    return sorted(snapshot_dir.glob("diga_snapshot_*.json"))


def latest_snapshot_paths(
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    limit: int = 2,
) -> list[Path]:
    return list_snapshot_paths(snapshot_dir)[-limit:]
