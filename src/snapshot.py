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
    directory_metrics: dict[str, Any]


def ensure_snapshot_dir(snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    return snapshot_dir


def create_snapshot_payload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    return {
        "created_at": created_at,
        "entry_count": len(entries),
        "directory_metrics": calculate_directory_metrics(entries, calculated_at=created_at),
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
        directory_metrics=load_directory_metrics(payload, entries),
    )


def load_directory_metrics(payload: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = payload.get("directory_metrics")
    if isinstance(metrics, dict):
        return metrics
    return calculate_directory_metrics(entries, calculated_at=str(payload.get("created_at", "unknown")))


def calculate_directory_metrics(
    entries: list[dict[str, Any]],
    calculated_at: str | None = None,
) -> dict[str, Any]:
    status_counts = {
        "provisional": 0,
        "permanent": 0,
        "removed": 0,
        "unknown": 0,
    }
    for entry in entries:
        status = effective_entry_status(entry)
        status_counts[status] += 1
    active_count = status_counts["provisional"] + status_counts["permanent"]
    return {
        "total_count": len(entries),
        "status_counts": status_counts,
        "active_count": active_count,
        "source": "snapshot_entries.status",
        "calculated_at": calculated_at or datetime.now(timezone.utc).isoformat(),
    }


def normalize_status_value(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"draft", "preliminary", "provisional"}:
        return "provisional"
    if text in {"active", "final", "permanent", "listed"}:
        return "permanent"
    if text in {"retired", "removed", "revoked", "inactive"}:
        return "removed"
    return "unknown"


def effective_entry_status(entry: dict[str, Any]) -> str:
    status_source = str(entry.get("status_source") or "").strip()
    status = normalize_status_value(entry.get("status"))
    if status_source and status != "unknown":
        return status

    history_status = status_from_change_history(entry.get("change_history"))
    if history_status != "unknown":
        return history_status

    return status


def status_from_change_history(history: Any) -> str:
    if not isinstance(history, list):
        return "unknown"
    status_entries = []
    for item in history:
        if not isinstance(item, dict):
            continue
        status = status_from_history_entry(item)
        if status != "unknown":
            status_entries.append((str(item.get("date") or ""), status))
    if not status_entries:
        return "unknown"
    return max(status_entries, key=lambda item: item[0])[1]


def status_from_history_entry(entry: dict[str, Any]) -> str:
    code = str(entry.get("type") or "").lower()
    display = " ".join(
        str(entry.get(key) or "").lower()
        for key in ("type_display", "title")
    )
    if "retired" in code or "gestrichen" in display:
        return "removed"
    if "draft" in code or "provisional" in code or "vorl" in display:
        return "provisional"
    if "permanent" in code or "listed" in code or "dauerhaft" in display:
        return "permanent"
    return "unknown"


def list_snapshot_paths(snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR) -> list[Path]:
    if not snapshot_dir.exists():
        return []
    return sorted(snapshot_dir.glob("diga_snapshot_*.json"))


def latest_snapshot_paths(
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    limit: int = 2,
) -> list[Path]:
    return list_snapshot_paths(snapshot_dir)[-limit:]
