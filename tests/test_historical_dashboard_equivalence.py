from __future__ import annotations

import copy
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

try:
    import streamlit  # noqa: F401
except ModuleNotFoundError:
    sys.modules["streamlit"] = types.ModuleType("streamlit")

import app
from src.legacy_history import closest_snapshot, git_bytes, git_snapshot_sources, matching_entry


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
    def test_all_historical_dashboard_output_matches_without_legacy_directory(self) -> None:
        current_events = events_from_repository()
        self.assertEqual(len(current_events), 369)
        legacy_events = copy.deepcopy(current_events)
        for event in legacy_events:
            event.pop("snapshot_context", None)

        sources = git_snapshot_sources()
        cache = {}

        def legacy_entry(event):
            timestamp = event.get("current_snapshot_timestamp")
            if not timestamp:
                return None
            source = closest_snapshot(sources, str(timestamp))
            snapshot = cache.setdefault(source.path, json.loads(git_bytes(source.path)))
            return matching_entry(snapshot, event)

        with mock.patch.object(app, "current_snapshot_entry", side_effect=legacy_entry):
            legacy_groups = app.group_events_by_diga(legacy_events)
            legacy_classification = [
                (app.is_metadata_event(event), app.has_user_visible_change(event), app.is_reclassified_evidence_description_event(event))
                for event in legacy_events
            ]

        current_groups = app.group_events_by_diga(current_events)
        current_classification = [
            (app.is_metadata_event(event), app.has_user_visible_change(event), app.is_reclassified_evidence_description_event(event))
            for event in current_events
        ]
        self.assertEqual(len(current_groups), 22)
        self.assertEqual(without_storage_context(current_groups), without_storage_context(legacy_groups))
        self.assertEqual(current_classification, legacy_classification)
        self.assertTrue(all(isinstance(event.get("snapshot_context"), dict) for event in current_events))


if __name__ == "__main__":
    unittest.main()
