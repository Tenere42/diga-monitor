from __future__ import annotations

import io
import json
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.legacy_history import (
    SnapshotSource,
    backfill_event_contexts,
    build_retention_report,
    closest_snapshot,
    execute_r2_migration,
    migration_sources,
    restore_object,
    restore_baseline_integration,
    verify_manifest_objects,
)


class MissingObject(Exception):
    def __init__(self) -> None:
        self.response = {"ResponseMetadata": {"HTTPStatusCode": 404}, "Error": {"Code": "NoSuchKey"}}


class FakeR2:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.uploads = 0

    def head_object(self, Bucket: str, Key: str):
        if Key not in self.objects:
            raise MissingObject()
        body, metadata = self.objects[Key]
        return {"ContentLength": len(body), "Metadata": metadata}

    def put_object(self, Bucket: str, Key: str, Body: bytes, Metadata: dict[str, str], **_kwargs):
        self.objects[Key] = (Body, Metadata)
        self.uploads += 1

    def get_object(self, Bucket: str, Key: str):
        body, metadata = self.objects[Key]
        return {"Body": io.BytesIO(body), "Metadata": metadata}


class LegacyHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_root = Path("work/test-temp")
        cls.temp_root.mkdir(parents=True, exist_ok=True)

    def source(self, path: str, timestamp: str, size: int = 10) -> SnapshotSource:
        return SnapshotSource(path, datetime.fromisoformat(timestamp).astimezone(timezone.utc), size)

    def temp_directory(self) -> Path:
        path = self.temp_root / uuid.uuid4().hex
        path.mkdir()
        return path

    def test_closest_snapshot_matches_dashboard_distance_rule(self) -> None:
        sources = [
            self.source("data/snapshots/diga_snapshot_20260601T000000000000Z.json", "2026-06-01T00:00:00+00:00"),
            self.source("data/snapshots/diga_snapshot_20260601T010000000000Z.json", "2026-06-01T01:00:00+00:00"),
        ]
        selected = closest_snapshot(sources, "2026-06-01T00:50:00+00:00")
        self.assertEqual(selected.path, sources[1].path)

    def test_backfill_is_semantically_complete_and_idempotent(self) -> None:
        source = self.source(
            "data/snapshots/diga_snapshot_20260601T000000000000Z.json",
            "2026-06-01T00:00:00+00:00",
        )
        snapshot = {
            "created_at": "2026-06-01T00:00:00+00:00",
            "entries": [{"id": "123", "name": "Test", "descriptive_texts": {"a": "b"}}],
        }
        payload = {
            "events": [
                {"diga_id": "123", "current_snapshot_timestamp": "2026-06-01T00:00:01+00:00"},
                {"diga_id": "__directory__", "current_snapshot_timestamp": "2026-06-01T00:00:01+00:00"},
            ]
        }
        changes = self.temp_directory()
        path = changes / "changes_test.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        reader = lambda _path: json.dumps(snapshot).encode()
        first = backfill_event_contexts(changes, [source], reader)
        first_bytes = path.read_bytes()
        second = backfill_event_contexts(changes, [source], reader)
        self.assertEqual(first["backfilled_events"], 2)
        self.assertEqual(first["unmatched_events"], [])
        self.assertEqual(second["backfilled_events"], 0)
        self.assertEqual(path.read_bytes(), first_bytes)

    def test_r2_manifest_hash_restore_and_upload_idempotence(self) -> None:
        payload = json.dumps({"created_at": "2026-06-01T00:00:00+00:00", "entries": []}).encode()
        plan = [{"source_path": "legacy.json", "object_key": "full-snapshots/legacy/legacy.json.gz", "roles": ["event-context"], "source_size": len(payload)}]
        client = FakeR2()
        root = self.temp_directory().resolve()
        (root / "legacy.json").write_bytes(payload)
        manifest_path = root / "manifest.json"
        original_cwd = Path.cwd()
        try:
            import os
            os.chdir(root)
            first = execute_r2_migration(client, "bucket", plan, manifest_path)
            manifest_bytes = manifest_path.read_bytes()
            second = execute_r2_migration(client, "bucket", plan, manifest_path)
            restored = restore_object(client, "bucket", first["objects"][0], root / "restore" / "snapshot.json")
        finally:
            os.chdir(original_cwd)
        self.assertEqual(client.uploads, 1)
        self.assertEqual(first, second)
        self.assertEqual(manifest_path.read_bytes(), manifest_bytes)
        self.assertEqual(Path(restored["target"]).read_bytes(), payload)
        self.assertTrue(first["objects"][0]["verified"])
        integrated = restore_baseline_integration(client, "bucket", first["objects"][0], root / "integration")
        self.assertTrue(integrated["load_path_verified"])
        self.assertEqual(integrated["entry_count"], 0)
        self.assertEqual(verify_manifest_objects(client, "bucket", first)["verified_r2_objects"], 1)

    def test_retention_report_classifies_every_snapshot_and_keeps_every_unique_state(self) -> None:
        sources = [
            self.source("data/snapshots/diga_snapshot_20260601T000000000000Z.json", "2026-06-01T00:00:00+00:00"),
            self.source("data/snapshots/diga_snapshot_20260601T010000000000Z.json", "2026-06-01T01:00:00+00:00"),
            self.source("data/snapshots/diga_snapshot_20260601T020000000000Z.json", "2026-06-01T02:00:00+00:00"),
        ]
        payloads = {
            sources[0].path: {"created_at": "a", "entries": [{"id": "1", "name": "A", "raw_public_fhir": {"version": 1}}]},
            sources[1].path: {"created_at": "b", "entries": [{"id": "1", "name": "A", "raw_public_fhir": {"version": 2}}]},
            sources[2].path: {"created_at": "c", "entries": [{"id": "1", "name": "B", "raw_public_fhir": {"version": 2}}]},
        }
        report = build_retention_report(sources, lambda path: json.dumps(payloads[path]).encode())
        self.assertEqual(report["snapshot_count"], 3)
        self.assertEqual(report["unique_monitored_state_count"], 2)
        self.assertEqual(report["redundant_snapshot_count"], 1)
        self.assertTrue(report["all_snapshots_classified"])
        self.assertTrue(report["all_unique_states_have_representative"])

    def test_plan_includes_event_weekly_edges_and_baseline(self) -> None:
        sources = [
            self.source("data/snapshots/diga_snapshot_20260601T000000000000Z.json", "2026-06-01T00:00:00+00:00"),
            self.source("data/snapshots/diga_snapshot_20260608T000000000000Z.json", "2026-06-08T00:00:00+00:00"),
            self.source("data/snapshots/diga_snapshot_20260609T000000000000Z.json", "2026-06-09T00:00:00+00:00"),
        ]
        baseline = self.temp_directory() / "baseline.json"
        baseline.write_text(json.dumps({"created_at": "2026-06-10T00:00:00+00:00"}), encoding="utf-8")
        plan = migration_sources(sources, [sources[2].path], baseline)
        roles = {item["source_path"]: set(item["roles"]) for item in plan}
        self.assertIn("earliest", roles[sources[0].path])
        self.assertIn("weekly-checkpoint", roles[sources[1].path])
        self.assertIn("event-context", roles[sources[2].path])
        self.assertIn("last-legacy", roles[sources[2].path])
        self.assertTrue(any("current-baseline" in item["roles"] for item in plan))


if __name__ == "__main__":
    unittest.main()
