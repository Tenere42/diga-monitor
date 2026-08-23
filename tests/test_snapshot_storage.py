from __future__ import annotations

import gzip
import json
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from src.snapshot_storage import R2SnapshotArchive, SnapshotArchiveError, finalize_snapshot_storage


@contextmanager
def temporary_directory():
    root = Path("work/test_tmp")
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield str(path)
    finally:
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            else:
                child.rmdir()
        path.rmdir()


class NotFoundError(Exception):
    response = {"ResponseMetadata": {"HTTPStatusCode": 404}, "Error": {"Code": "NoSuchKey"}}


class FakeS3Client:
    def __init__(self, fail_upload: bool = False) -> None:
        self.objects: dict[str, dict[str, object]] = {}
        self.fail_upload = fail_upload

    def head_object(self, Bucket: str, Key: str) -> dict[str, object]:
        if Key not in self.objects:
            raise NotFoundError(Key)
        return {}

    def put_object(self, **kwargs: object) -> None:
        if self.fail_upload:
            raise RuntimeError("upload unavailable")
        self.objects[str(kwargs["Key"])] = kwargs


def write_snapshot(path: Path, created_at: str, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"created_at": created_at, "entries": [{"id": "1", "name": name}]}) + "\n",
        encoding="utf-8",
    )


class SnapshotStorageTests(unittest.TestCase):
    def test_unchanged_scan_keeps_one_baseline_without_change_archive(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            previous = root / "baseline.json"
            candidate = root / "candidate.json"
            write_snapshot(previous, "2026-08-17T06:00:00+00:00", "same")
            write_snapshot(candidate, "2026-08-17T09:00:00+00:00", "same")
            client = FakeS3Client()
            archive = R2SnapshotArchive(client, "diga-monitor")

            finalize_snapshot_storage(previous, candidate, datetime(2026, 8, 17, 9, tzinfo=timezone.utc), False, previous, archive)

            self.assertFalse(candidate.exists())
            self.assertEqual(json.loads(previous.read_text(encoding="utf-8"))["created_at"], "2026-08-17T09:00:00+00:00")
            self.assertEqual(list(client.objects), ["full-snapshots/checkpoints/2026-W34.json.gz"])

    def test_changed_scan_uploads_compressed_before_and_after(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            before = root / "before.json"
            after = root / "after.json"
            baseline = root / "baseline.json"
            write_snapshot(before, "2026-08-17T06:00:00+00:00", "before")
            write_snapshot(after, "2026-08-17T09:00:00+00:00", "after")
            client = FakeS3Client()
            archive = R2SnapshotArchive(client, "diga-monitor")

            finalize_snapshot_storage(before, after, datetime(2026, 8, 17, 9, tzinfo=timezone.utc), True, baseline, archive)

            change_keys = [key for key in client.objects if "/changes/" in key]
            self.assertEqual(len(change_keys), 2)
            uploaded = client.objects[change_keys[1]]
            self.assertEqual(uploaded["ContentEncoding"], "gzip")
            self.assertEqual(json.loads(gzip.decompress(uploaded["Body"])), json.loads(baseline.read_bytes()))

    def test_weekly_checkpoint_is_uploaded_only_once(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            client = FakeS3Client()
            archive = R2SnapshotArchive(client, "diga-monitor")
            for hour in (6, 9):
                candidate = root / f"candidate-{hour}.json"
                write_snapshot(candidate, f"2026-08-18T{hour:02d}:00:00+00:00", "same")
                finalize_snapshot_storage(None, candidate, datetime(2026, 8, 18, hour, tzinfo=timezone.utc), False, root / "baseline.json", archive)
            self.assertEqual(list(client.objects), ["full-snapshots/checkpoints/2026-W34.json.gz"])

    def test_upload_failure_preserves_existing_baseline(self) -> None:
        with temporary_directory() as temp:
            root = Path(temp)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            write_snapshot(baseline, "2026-08-17T06:00:00+00:00", "before")
            write_snapshot(candidate, "2026-08-17T09:00:00+00:00", "after")
            archive = R2SnapshotArchive(FakeS3Client(fail_upload=True), "diga-monitor")

            with self.assertRaises(SnapshotArchiveError):
                finalize_snapshot_storage(baseline, candidate, datetime(2026, 8, 17, 9, tzinfo=timezone.utc), True, baseline, archive)

            self.assertEqual(json.loads(baseline.read_text(encoding="utf-8"))["entries"][0]["name"], "before")


if __name__ == "__main__":
    unittest.main()
