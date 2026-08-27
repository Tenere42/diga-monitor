from __future__ import annotations

import hashlib
import json
import sys
import types
import unittest
from pathlib import Path

try:
    import streamlit  # noqa: F401
except ModuleNotFoundError:
    sys.modules["streamlit"] = types.ModuleType("streamlit")

import app

EXPECTED_PATH = Path("data/audit/historical_dashboard_expected.json")


def events_from_repository() -> list[dict]:
    events = []
    for path in sorted(Path("outputs/changes").glob("changes_*.json")):
        events.extend(json.loads(path.read_text(encoding="utf-8")).get("events", []))
    return events


def without_storage_context(value):
    if isinstance(value, dict):
        return {key: without_storage_context(item) for key, item in value.items() if key != "snapshot_context"}
    if isinstance(value, list):
        return [without_storage_context(item) for item in value]
    return value


class HistoricalDashboardEquivalenceTests(unittest.TestCase):
    def test_all_historical_dashboard_output_matches_committed_legacy_projection(self) -> None:
        expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        events = events_from_repository()
        groups = without_storage_context(app.group_events_by_diga(events))
        classification = [
            (app.is_metadata_event(event), app.has_user_visible_change(event), app.is_reclassified_evidence_description_event(event))
            for event in events
        ]
        projection = json.dumps(
            {"groups": groups, "classification": classification},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        self.assertEqual(len(events), expected["event_count"])
        self.assertEqual(len(groups), expected["group_count"])
        self.assertEqual(hashlib.sha256(projection).hexdigest(), expected["dashboard_projection_sha256"])
        self.assertTrue(all(isinstance(event.get("snapshot_context"), dict) for event in events))


if __name__ == "__main__":
    unittest.main()
