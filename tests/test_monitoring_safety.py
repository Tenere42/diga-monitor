from __future__ import annotations

import json
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts import monitoring_health_check
from src import main
from src.scan_history import append_scan_history, load_scan_history
from src.snapshot import save_snapshot


TEST_TMP = Path("work/test_tmp")


@contextmanager
def temporary_directory():
    TEST_TMP.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP / uuid.uuid4().hex
    path.mkdir()
    yield str(path)


def sample_entry(status: str = "permanent") -> dict[str, object]:
    return {
        "id": "12345",
        "name": "Test DiGA",
        "manufacturer": "Test GmbH",
        "status": status,
        "status_source": "catalog_entry.status",
        "bfarm_directory_url": "https://diga.bfarm.de/de/verzeichnis/12345",
        "descriptive_texts": {"field": "value"},
        "pricing_information": [],
        "change_history": [],
    }


def section(content: str) -> dict[str, object]:
    return {
        "path": ["Beschreibung", "Kurztext"],
        "stable_key": "beschreibung-kurztext",
        "content": content,
        "content_type": "section",
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class MonitoringSafetyTests(unittest.TestCase):
    def test_normal_scan_without_changes_persists_snapshot_and_history(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            snapshot_dir = root / "snapshots"
            history_path = root / "scan_history.json"
            save_snapshot([sample_entry()], snapshot_dir)

            def append_local_history(**kwargs: object) -> None:
                append_scan_history(path=history_path, **kwargs)

            with (
                mock.patch.object(main, "fetch_diga_entries", return_value=[sample_entry()]),
                mock.patch.object(main, "append_scan_history", side_effect=append_local_history),
                mock.patch.object(main, "notify_changes"),
            ):
                result = main.run_monitor(snapshot_dir=snapshot_dir, notify=False)

            self.assertEqual(result, 0)
            self.assertEqual(len(list(snapshot_dir.glob("diga_snapshot_*.json"))), 2)
            self.assertEqual(len(load_scan_history(history_path)), 1)

    def test_visible_baseline_is_replaced_only_after_successful_diff_and_apply(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            runs = root / "runs"
            history = root / "history"
            baseline_path = latest / "12345_test-diga_structure.json"
            old_payload = {"diga_id": "12345", "content_sections": [section("old text")]}
            new_payload = {"diga_id": "12345", "content_sections": [section("new text")]}
            rendered_path = root / "rendered.json"
            write_json(baseline_path, old_payload)
            write_json(rendered_path, new_payload)

            with (
                mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest),
                mock.patch.object(main, "VISIBLE_RUN_DIR", runs),
                mock.patch.object(main, "VISIBLE_HISTORY_DIR", history),
            ):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "previous_snapshot_timestamp": "2026-01-01T00:00:00+00:00",
                            "current_snapshot_timestamp": "2026-01-01T01:00:00+00:00",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "structure_path": str(rendered_path),
                            "content_sections": [section("new text")],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

                self.assertEqual(json.loads(baseline_path.read_text(encoding="utf-8")), old_payload)
                self.assertEqual(len(events), 1)
                self.assertEqual(len(updates), 1)
                main.apply_visible_baseline_updates(updates)

            self.assertEqual(json.loads(baseline_path.read_text(encoding="utf-8")), new_payload)
            self.assertTrue(list((history / "12345").glob("*_structure.json")))

    def test_fhir_change_without_visible_diff_is_preserved_as_unresolved(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            runs = root / "runs"
            baseline_path = latest / "12345_test-diga_structure.json"
            payload = {"diga_id": "12345", "content_sections": [section("same visible text")]}
            write_json(baseline_path, payload)

            with (
                mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest),
                mock.patch.object(main, "VISIBLE_RUN_DIR", runs),
            ):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.visible_field",
                            "previous_value": "old FHIR text",
                            "new_value": "new FHIR text",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": [section("same visible text")],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(updates, [])
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["change_type"], "visible_diff_unresolved")
            self.assertEqual(events[0]["original_change_type"], "text_change")

    def test_render_failure_preserves_fhir_content_change_as_unresolved(self) -> None:
        events, updates = main.build_visible_change_events_from_rendered_baselines(
            trigger_events=[
                {
                    "diga_id": "12345",
                    "diga_name": "Test DiGA",
                    "change_type": "text_change",
                    "changed_field": "descriptive_texts.visible_field",
                    "previous_value": "old FHIR text",
                    "new_value": "new FHIR text",
                }
            ],
            rendered_entries={},
            entries=[sample_entry()],
            detected_at="2026-01-01T01:00:00+00:00",
        )

        self.assertEqual(updates, [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["change_type"], "visible_diff_unresolved")
        self.assertIn("render-on-change did not produce", events[0]["fallback_reason"])

    def test_missing_visible_baseline_preserves_fhir_content_change_as_unresolved(self) -> None:
        with temporary_directory() as temp:
            latest = Path(temp) / "latest"
            with mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.visible_field",
                            "previous_value": "old FHIR text",
                            "new_value": "new FHIR text",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": [section("new visible text")],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

        self.assertEqual(updates, [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["change_type"], "visible_diff_unresolved")

    def test_pure_metadata_change_is_not_preserved_as_unresolved(self) -> None:
        events = main.legacy_fallback_events(
            [
                {
                    "diga_id": "12345",
                    "diga_name": "Test DiGA",
                    "change_type": "text_change",
                    "changed_field": "source_update_notice.last_updated_at",
                    "previous_value": "2026-01-01",
                    "new_value": "2026-01-02",
                }
            ],
            "visible baseline diff found no visible content_section changes",
        )

        self.assertEqual(events, [])

    def test_visible_baseline_diff_failure_leaves_latest_unchanged(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            baseline_path = latest / "12345_test-diga_structure.json"
            old_payload = {"diga_id": "12345", "content_sections": [section("old text")]}
            write_json(baseline_path, old_payload)

            with (
                mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest),
                mock.patch.object(main, "diff_content_section_lists", side_effect=RuntimeError("boom")),
            ):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.visible_field",
                            "previous_value": "old FHIR text",
                            "new_value": "new FHIR text",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": [section("new text")],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(json.loads(baseline_path.read_text(encoding="utf-8")), old_payload)
            self.assertEqual(updates, [])
            self.assertTrue(events)
            self.assertTrue(all(event.get("change_type") == "visible_diff_unresolved" for event in events))

    def test_lifecycle_event_is_preserved(self) -> None:
        event = {"change_type": "status_change"}
        self.assertTrue(main.is_lifecycle_event(event))

    def test_health_check_detects_missing_current_run_history(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            snapshot_dir = root / "data" / "snapshots"
            history_path = root / "outputs" / "scan_history.json"
            snapshot_dir.mkdir(parents=True)
            (snapshot_dir / "diga_snapshot_20260101T000000000000Z.json").write_text("{}", encoding="utf-8")
            append_scan_history(
                "2026-01-01T03:00:00+00:00",
                number_of_diga=1,
                changes_detected=0,
                scan_duration_seconds=1.0,
                path=history_path,
            )
            with (
                mock.patch.object(monitoring_health_check, "SNAPSHOT_DIR", snapshot_dir),
                mock.patch.object(monitoring_health_check, "SCAN_HISTORY_PATH", history_path),
            ):
                self.assertNotEqual(
                    monitoring_health_check.main_with_args(["--require-current-run"]),
                    0,
                )

    def test_health_check_warns_for_stale_snapshot(self) -> None:
        stale = datetime.now(timezone.utc) - timedelta(hours=7)
        with temporary_directory() as temp:
            root = Path(temp)
            snapshot_dir = root / "data" / "snapshots"
            history_path = root / "outputs" / "scan_history.json"
            snapshot_dir.mkdir(parents=True)
            timestamp = stale.strftime("%Y%m%dT%H%M%S%fZ")
            (snapshot_dir / f"diga_snapshot_{timestamp}.json").write_text("{}", encoding="utf-8")
            append_scan_history(
                stale.isoformat(),
                number_of_diga=1,
                changes_detected=0,
                scan_duration_seconds=1.0,
                path=history_path,
            )
            with (
                mock.patch.object(monitoring_health_check, "SNAPSHOT_DIR", snapshot_dir),
                mock.patch.object(monitoring_health_check, "SCAN_HISTORY_PATH", history_path),
            ):
                self.assertEqual(monitoring_health_check.main_with_args(["--max-snapshot-age-hours", "6"]), 0)


if __name__ == "__main__":
    unittest.main()
