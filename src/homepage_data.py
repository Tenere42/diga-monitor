"""Read-only market-summary adapter; no monitoring, storage writes or API calls."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.snapshot import calculate_directory_metrics


# Already committed by the monitoring workflow and available in Railway's checkout.
# Never infer current listing status from historical change events.
MARKET_SNAPSHOT_PATH = Path("data/baseline/current_snapshot.json")


@dataclass(frozen=True)
class MarketSnapshot:
    active: int
    permanent: int
    provisional: int
    unknown: int
    as_of: str


def load_market_snapshot(path: Path = MARKET_SNAPSHOT_PATH) -> MarketSnapshot | None:
    """Validate stored aggregates against the existing snapshot status rules.

    Active = permanent + provisional; removed/unknown listings are excluded.
    Counts describe this snapshot's timestamp, not a live BfArM query. A missing
    or inconsistent snapshot is unavailable, never zero or a historical estimate.
    Only the small result is returned to the presentation cache.
    """
    try:
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        entries = payload["entries"]
        metrics = payload["directory_metrics"]
        timestamp = payload["created_at"]
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None or not isinstance(entries, list):
            return None
        if not all(isinstance(entry, dict) for entry in entries):
            return None
        if metrics["source"] != "snapshot_entries.status" or metrics["calculated_at"] != timestamp:
            return None
        expected = calculate_directory_metrics(entries, calculated_at=timestamp)
        counts = metrics["status_counts"]
        values = [metrics["active_count"], metrics["total_count"], *counts.values()]
        if not all(type(value) is int and value >= 0 for value in values):
            return None
        if any(metrics[key] != expected[key] for key in ("active_count", "total_count", "status_counts")):
            return None
        return MarketSnapshot(metrics["active_count"], counts["permanent"],
                              counts["provisional"], counts["unknown"], timestamp)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
