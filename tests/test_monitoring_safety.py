from __future__ import annotations

import json
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts import monitoring_health_check
import app
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


def named_section(path: list[str], stable_key: str, content: str, content_type: str = "section") -> dict[str, object]:
    return {
        "path": path,
        "display_path": " > ".join(path),
        "stable_key": stable_key,
        "content": content,
        "content_type": content_type,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class MonitoringSafetyTests(unittest.TestCase):
    def test_dashboard_prefers_embedded_snapshot_context(self) -> None:
        context = {"id": "12345", "name": "Test DiGA", "descriptive_texts": {"field": "value"}}
        with mock.patch.object(app, "SNAPSHOT_DIR") as snapshot_dir:
            self.assertEqual(app.current_snapshot_entry({"snapshot_context": context}), context)
            self.assertIsNone(app.current_snapshot_entry({"current_snapshot_timestamp": "2026-01-01T00:00:00+00:00"}))
            snapshot_dir.glob.assert_not_called()

    def test_all_historical_events_have_embedded_context(self) -> None:
        events = []
        for path in sorted(Path("outputs/changes").glob("changes_*.json")):
            events.extend(json.loads(path.read_text(encoding="utf-8")).get("events", []))
        self.assertEqual(len(events), 369)
        self.assertTrue(all(isinstance(event.get("snapshot_context"), dict) for event in events))

    def test_dashboard_scan_status_prefers_scan_history_over_legacy_snapshots(self) -> None:
        history = [{"scan_timestamp": "2026-08-23T15:00:00+00:00"}]
        with mock.patch.object(app, "latest_snapshot_timestamp", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc)):
            self.assertIn("23.08.2026", app.latest_scan_timestamp(history))

    def test_normal_scan_without_changes_replaces_only_operational_baseline(self) -> None:
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
            self.assertEqual(len(list(snapshot_dir.glob("diga_snapshot_*.json"))), 1)
            self.assertTrue((root / "baseline" / "current_snapshot.json").exists())
            self.assertFalse(list((root / "work_snapshots").glob("diga_snapshot_*.json")))
            self.assertEqual(len(load_scan_history(history_path)), 1)

    def test_scan_with_change_updates_baseline_and_persists_event(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            snapshot_dir = root / "snapshots"
            history_path = root / "scan_history.json"
            save_snapshot([sample_entry()], snapshot_dir)
            changed_entry = {**sample_entry(), "manufacturer": "Changed GmbH"}

            def append_local_history(**kwargs: object) -> None:
                append_scan_history(path=history_path, **kwargs)

            with (
                mock.patch.object(main, "fetch_diga_entries", return_value=[changed_entry]),
                mock.patch.object(main, "append_scan_history", side_effect=append_local_history),
                mock.patch.object(main, "save_change_events") as save_events,
                mock.patch.object(main, "notify_changes"),
            ):
                result = main.run_monitor(snapshot_dir=snapshot_dir, notify=False)

            self.assertEqual(result, 0)
            self.assertTrue(save_events.called)
            baseline = json.loads((root / "baseline" / "current_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(baseline["entries"][0]["manufacturer"], "Changed GmbH")
            self.assertEqual(load_scan_history(history_path)[0]["changes_detected"], 1)

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
                            "changed_field": "descriptive_texts.field",
                            "previous_value": "old text",
                            "new_value": "new text",
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

    def test_render_success_preserves_exactly_one_event_per_fhir_content_change(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            baseline_path = latest / "12345_test-diga_structure.json"
            old_payload = {
                "diga_id": "12345",
                "content_sections": [
                    named_section(["Beschreibung", "Zweck"], "zweck", "alter Zweck"),
                    named_section(["Beschreibung", "Technik"], "technik", "alte Technik"),
                ],
            }
            new_payload = {
                "diga_id": "12345",
                "content_sections": [
                    named_section(["Beschreibung", "Zweck"], "zweck", "neuer Zweck"),
                    named_section(["Beschreibung", "Technik"], "technik", "neue Technik"),
                ],
            }
            write_json(baseline_path, old_payload)

            with mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.zweck",
                            "display_path": "Beschreibung > Zweck",
                            "previous_value": "alter Zweck",
                            "new_value": "neuer Zweck",
                        },
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.technik",
                            "display_path": "Beschreibung > Technik",
                            "previous_value": "alte Technik",
                            "new_value": "neue Technik",
                        },
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": new_payload["content_sections"],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(len(events), 2)
            self.assertEqual(len(updates), 1)
            self.assertEqual(
                [event.get("original_changed_field") for event in events],
                ["descriptive_texts.zweck", "descriptive_texts.technik"],
            )

    def test_ambiguous_visible_candidates_preserve_fhir_event_as_unresolved(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            write_json(
                latest / "12345_test-diga_structure.json",
                {
                    "diga_id": "12345",
                    "content_sections": [
                        named_section(["Beschreibung", "A"], "a", "alter Text A"),
                        named_section(["Beschreibung", "B"], "b", "alter Text B"),
                    ],
                },
            )

            with mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.unknown",
                            "display_path": "Beschreibung",
                            "previous_value": "FHIR alter Inhalt",
                            "new_value": "FHIR neuer Inhalt",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": [
                                named_section(["Beschreibung", "A"], "a", "neuer Text A"),
                                named_section(["Beschreibung", "B"], "b", "neuer Text B"),
                            ],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(updates, [])
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["change_type"], "visible_diff_unresolved")
            self.assertIn("ambiguous visible section match", events[0]["fallback_reason"])

    def test_clear_visible_candidate_is_selected(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            write_json(
                latest / "12345_test-diga_structure.json",
                {
                    "diga_id": "12345",
                    "content_sections": [
                        named_section(["Beschreibung", "Zweck"], "zweck", "alter Zweck"),
                        named_section(["Beschreibung", "Technik"], "technik", "alte Technik"),
                    ],
                },
            )

            with mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.zweck",
                            "display_path": "Beschreibung > Zweck",
                            "previous_value": "alter Zweck",
                            "new_value": "neuer Zweck",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": [
                                named_section(["Beschreibung", "Zweck"], "zweck", "neuer Zweck"),
                                named_section(["Beschreibung", "Technik"], "technik", "neue Technik"),
                            ],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(len(events), 1)
            self.assertEqual(len(updates), 1)
            self.assertEqual(events[0]["change_type"], "text_change")
            self.assertEqual(events[0]["display_path"], "Beschreibung > Zweck")
            self.assertEqual(events[0]["visible_match_count"], 1)

    def test_single_weak_visible_candidate_is_not_auto_assigned(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            write_json(
                latest / "12345_test-diga_structure.json",
                {
                    "diga_id": "12345",
                    "content_sections": [named_section(["Beschreibung", "A"], "a", "vollig anderer alter Text")],
                },
            )

            with mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.zielgruppe",
                            "previous_value": "Patientengruppe Erwachsene",
                            "new_value": "Patientengruppe Jugendliche",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": [
                                named_section(["Beschreibung", "A"], "a", "vollig anderer neuer Text")
                            ],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(updates, [])
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["change_type"], "visible_diff_unresolved")
            self.assertIn("below threshold", events[0]["fallback_reason"])

    def test_one_fhir_trigger_can_preserve_multiple_visible_details(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            write_json(
                latest / "12345_test-diga_structure.json",
                {
                    "diga_id": "12345",
                    "content_sections": [
                        named_section(["Beschreibung", "Ziel"], "ziel", "alter Zieltext"),
                        named_section(["Beschreibung", "Nutzen"], "nutzen", "alter Nutzentext"),
                    ],
                },
            )

            with mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.combined",
                            "previous_value": "alter Zieltext alter Nutzentext",
                            "new_value": "neuer Zieltext neuer Nutzentext",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": [
                                named_section(["Beschreibung", "Ziel"], "ziel", "neuer Zieltext"),
                                named_section(["Beschreibung", "Nutzen"], "nutzen", "neuer Nutzentext"),
                            ],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(len(events), 1)
            self.assertEqual(len(updates), 1)
            self.assertEqual(events[0]["original_changed_field"], "descriptive_texts.combined")
            self.assertEqual(events[0]["visible_match_count"], 2)
            self.assertCountEqual(
                [detail["display_path"] for detail in events[0]["visible_changes"]],
                ["Beschreibung > Ziel", "Beschreibung > Nutzen"],
            )

    def test_one_fhir_trigger_with_multiple_ambiguous_sections_is_unresolved(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            write_json(
                latest / "12345_test-diga_structure.json",
                {
                    "diga_id": "12345",
                    "content_sections": [
                        named_section(["Beschreibung", "A"], "a", "alter Abschnitt A"),
                        named_section(["Beschreibung", "B"], "b", "alter Abschnitt B"),
                    ],
                },
            )

            with mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.combined",
                            "display_path": "Beschreibung",
                            "previous_value": "nicht lokalisierter alter Inhalt",
                            "new_value": "nicht lokalisierter neuer Inhalt",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": [
                                named_section(["Beschreibung", "A"], "a", "neuer Abschnitt A"),
                                named_section(["Beschreibung", "B"], "b", "neuer Abschnitt B"),
                            ],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(updates, [])
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["change_type"], "visible_diff_unresolved")
            self.assertNotIn("visible_changes", events[0])

    def test_multiple_digas_preserve_one_event_per_fhir_content_change(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            write_json(
                latest / "12345_test-diga_structure.json",
                {"diga_id": "12345", "content_sections": [named_section(["Beschreibung", "A"], "a", "alt A")]},
            )
            write_json(
                latest / "67890_second-diga_structure.json",
                {"diga_id": "67890", "content_sections": [named_section(["Beschreibung", "B"], "b", "alt B")]},
            )

            with mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.a",
                            "display_path": "Beschreibung > A",
                            "previous_value": "alt A",
                            "new_value": "neu A",
                        },
                        {
                            "diga_id": "67890",
                            "diga_name": "Second DiGA",
                            "change_type": "text_change",
                            "changed_field": "descriptive_texts.b",
                            "display_path": "Beschreibung > B",
                            "previous_value": "alt B",
                            "new_value": "neu B",
                        },
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test/1",
                            "content_sections": [named_section(["Beschreibung", "A"], "a", "neu A")],
                        },
                        "67890": {
                            "name": "Second DiGA",
                            "url": "https://example.test/2",
                            "content_sections": [named_section(["Beschreibung", "B"], "b", "neu B")],
                        },
                    },
                    entries=[sample_entry(), {**sample_entry(), "id": "67890", "name": "Second DiGA"}],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(len(events), 2)
            self.assertEqual(len(updates), 2)
            self.assertEqual({event.get("diga_id") for event in events}, {"12345", "67890"})

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

    def test_metadata_only_trigger_does_not_update_visible_baseline(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            latest = root / "latest"
            baseline_path = latest / "12345_test-diga_structure.json"
            write_json(
                baseline_path,
                {"diga_id": "12345", "content_sections": [named_section(["Beschreibung", "A"], "a", "alt A")]},
            )

            with mock.patch.object(main, "VISIBLE_BASELINE_DIR", latest):
                events, updates = main.build_visible_change_events_from_rendered_baselines(
                    trigger_events=[
                        {
                            "diga_id": "12345",
                            "diga_name": "Test DiGA",
                            "change_type": "text_change",
                            "changed_field": "source_update_notice.last_updated_at",
                            "previous_value": "2026-01-01",
                            "new_value": "2026-01-02",
                        }
                    ],
                    rendered_entries={
                        "12345": {
                            "name": "Test DiGA",
                            "url": "https://example.test",
                            "content_sections": [named_section(["Beschreibung", "A"], "a", "neu A")],
                        }
                    },
                    entries=[sample_entry()],
                    detected_at="2026-01-01T01:00:00+00:00",
                )

            self.assertEqual(events, [])
            self.assertEqual(updates, [])

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

    def test_repeated_identical_snapshots_are_idempotent(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            snapshot_dir = root / "snapshots"
            first = save_snapshot([sample_entry()], snapshot_dir)
            second = save_snapshot([sample_entry()], snapshot_dir)
            from src.diff import diff_snapshots
            from src.change_events import build_change_events
            from src.snapshot import load_snapshot

            report = diff_snapshots(load_snapshot(first), load_snapshot(second))
            self.assertFalse(report.has_changes)
            self.assertEqual(build_change_events(report, load_snapshot(first), load_snapshot(second)), [])

    def test_dashboard_dedup_keeps_same_phrase_in_different_fields(self) -> None:
        event_a = {
            "change_type": "text_change",
            "changed_field": "visible_directory.1",
            "original_changed_field": "descriptive_texts.a",
            "display_path": "Beschreibung > A",
            "previous_value": "alter Text",
            "new_value": "neuer Text",
            "word_diff": [{"op": "insert", "text": "neu"}],
        }
        event_b = {
            "change_type": "text_change",
            "changed_field": "visible_directory.2",
            "original_changed_field": "descriptive_texts.b",
            "display_path": "Beschreibung > B",
            "previous_value": "alter Text",
            "new_value": "neuer Text",
            "word_diff": [{"op": "insert", "text": "neu"}],
        }

        self.assertEqual(len(app.deduplicate_events([event_a, event_b])), 2)

    def test_health_check_detects_missing_current_run_history(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            baseline_path = root / "data" / "baseline" / "current_snapshot.json"
            history_path = root / "outputs" / "scan_history.json"
            write_json(baseline_path, {"created_at": "2026-01-01T00:00:00+00:00", "entries": []})
            append_scan_history(
                "2026-01-01T03:00:00+00:00",
                number_of_diga=1,
                changes_detected=0,
                scan_duration_seconds=1.0,
                path=history_path,
            )
            with (
                mock.patch.object(monitoring_health_check, "BASELINE_PATH", baseline_path),
                mock.patch.object(monitoring_health_check, "SCAN_HISTORY_PATH", history_path),
            ):
                self.assertNotEqual(
                    monitoring_health_check.main_with_args(["--require-current-run"]),
                    0,
                )

    def test_health_check_warns_for_stale_baseline(self) -> None:
        stale = datetime.now(timezone.utc) - timedelta(hours=7)
        with temporary_directory() as temp:
            root = Path(temp)
            baseline_path = root / "data" / "baseline" / "current_snapshot.json"
            history_path = root / "outputs" / "scan_history.json"
            write_json(baseline_path, {"created_at": stale.isoformat(), "entries": []})
            append_scan_history(
                stale.isoformat(),
                number_of_diga=1,
                changes_detected=0,
                scan_duration_seconds=1.0,
                path=history_path,
            )
            with (
                mock.patch.object(monitoring_health_check, "BASELINE_PATH", baseline_path),
                mock.patch.object(monitoring_health_check, "SCAN_HISTORY_PATH", history_path),
            ):
                self.assertEqual(monitoring_health_check.main_with_args(["--max-snapshot-age-hours", "6"]), 0)


if __name__ == "__main__":
    unittest.main()
