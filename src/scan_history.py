"""Append-only scan history for the DiGA monitor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SCAN_HISTORY_PATH = Path("outputs/scan_history.json")


def append_scan_history(
    scan_timestamp: str,
    number_of_diga: int,
    changes_detected: int,
    scan_duration_seconds: float,
    path: Path = DEFAULT_SCAN_HISTORY_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    history = load_scan_history(path)
    history.append(
        {
            "scan_timestamp": scan_timestamp,
            "number_of_diga": number_of_diga,
            "changes_detected": changes_detected,
            "scan_duration_seconds": round(scan_duration_seconds, 3),
        }
    )
    with path.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def load_scan_history(path: Path = DEFAULT_SCAN_HISTORY_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []
