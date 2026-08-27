from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path

import app

from src.change_events import save_change_events, snapshot_context
from src.dashboard_cache import change_files_signature, scan_history_signature


TEST_TMP = Path("work/test_tmp")


class DashboardCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = TEST_TMP / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        for path in sorted(self.root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.root.rmdir()

    def test_change_signature_changes_with_same_size_content(self) -> None:
        changes = self.root / "changes"
        changes.mkdir()
        path = changes / "changes_test.json"
        path.write_text('{"value":"one"}', encoding="utf-8")
        before = change_files_signature(changes)
        path.write_text('{"value":"two"}', encoding="utf-8")
        self.assertNotEqual(before, change_files_signature(changes))

    def test_scan_history_signature_tracks_missing_and_changed_file(self) -> None:
        path = self.root / "scan_history.json"
        missing = scan_history_signature(path)
        path.write_text("[]", encoding="utf-8")
        self.assertNotEqual(missing, scan_history_signature(path))

    def test_change_signature_changes_when_new_change_file_is_added(self) -> None:
        changes = self.root / "changes"
        changes.mkdir()
        (changes / "changes_first.json").write_text("{}", encoding="utf-8")
        before = change_files_signature(changes)
        (changes / "changes_second.json").write_text("{}", encoding="utf-8")
        self.assertNotEqual(before, change_files_signature(changes))

    def test_future_snapshot_context_does_not_duplicate_full_entry_text(self) -> None:
        entry = {
            "id": "12345",
            "name": "Test DiGA",
            "manufacturer": "Test GmbH",
            "descriptive_texts": {"description": "large text"},
            "structured_text_sections": [{"text": "large section"}],
        }
        context = snapshot_context(entry)
        self.assertEqual(context["id"], "12345")
        self.assertNotIn("descriptive_texts", context)
        self.assertNotIn("structured_text_sections", context)

    def test_saved_change_file_is_compact_and_loadable(self) -> None:
        event = {"detected_at": "2026-08-27T12:00:00+00:00", "value": "ä"}
        path = save_change_events([event], self.root)
        self.assertIsNotNone(path)
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn("\n  ", raw)
        self.assertEqual(json.loads(raw)["events"], [event])

    def test_cached_dashboard_loader_refreshes_when_signature_changes(self) -> None:
        changes = self.root / "changes"
        changes.mkdir()
        history_path = self.root / "scan_history.json"
        history_path.write_text('[{"scan_timestamp":"2026-08-27T12:00:00+00:00"}]', encoding="utf-8")
        change_path = changes / "changes_test.json"

        def write_event(name: str) -> None:
            payload = {
                "events": [
                    {
                        "detected_at": "2026-08-27T12:00:00+00:00",
                        "diga_id": "12345",
                        "diga_name": name,
                        "changed_field": "manufacturer",
                        "previous_value": "Before",
                        "new_value": "After",
                    }
                ]
            }
            change_path.write_text(json.dumps(payload), encoding="utf-8")

        write_event("First Name")
        app.load_dashboard_data.clear()
        first, history = app.load_dashboard_data(
            str(changes),
            change_files_signature(changes),
            str(history_path),
            scan_history_signature(history_path),
        )
        write_event("Other Name")
        second, _history = app.load_dashboard_data(
            str(changes),
            change_files_signature(changes),
            str(history_path),
            scan_history_signature(history_path),
        )

        self.assertEqual(first[0]["diga_name"], "First Name")
        self.assertEqual(second[0]["diga_name"], "Other Name")
        self.assertEqual(len(history), 1)


if __name__ == "__main__":
    unittest.main()
