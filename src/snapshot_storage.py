"""Operational baseline and compressed R2 snapshot archives."""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_PATH = Path("data/baseline/current_snapshot.json")


class SnapshotArchiveError(RuntimeError):
    """Raised when durable snapshot archival cannot be completed."""


def normalized_env_value(name: str) -> str | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    value = raw_value.strip()
    if "\r" in value or "\n" in value:
        raise SnapshotArchiveError(f"Malformed R2 configuration: {name} contains an embedded newline")
    return value


@dataclass
class R2SnapshotArchive:
    client: Any
    bucket: str
    prefix: str = "full-snapshots"

    @classmethod
    def from_env(cls) -> "R2SnapshotArchive | None":
        values = {
            "endpoint_url": normalized_env_value("R2_ENDPOINT"),
            "bucket": normalized_env_value("R2_BUCKET_NAME"),
            "aws_access_key_id": normalized_env_value("R2_ACCESS_KEY_ID"),
            "aws_secret_access_key": normalized_env_value("R2_SECRET_ACCESS_KEY"),
        }
        configured = [bool(value) for value in values.values()]
        required = os.getenv("R2_ARCHIVE_REQUIRED", "").strip().lower() in {"1", "true", "yes", "on"}
        if not any(configured):
            if required:
                raise SnapshotArchiveError("R2 archive is required but no R2 configuration is present")
            return None
        if not all(configured):
            missing = ", ".join(name for name, value in values.items() if not value)
            raise SnapshotArchiveError(f"Incomplete R2 configuration: {missing}")

        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=values["endpoint_url"],
            aws_access_key_id=values["aws_access_key_id"],
            aws_secret_access_key=values["aws_secret_access_key"],
            region_name="auto",
        )
        return cls(client=client, bucket=str(values["bucket"]))

    def archive_change_pair(self, before: Path, after: Path, detected_at: datetime) -> list[str]:
        stamp = archive_timestamp(detected_at)
        base = f"{self.prefix}/changes/{stamp}"
        return [
            self.upload_snapshot(before, f"{base}/before.json.gz", "change-before"),
            self.upload_snapshot(after, f"{base}/after.json.gz", "change-after"),
        ]

    def archive_weekly_checkpoint(self, snapshot: Path, detected_at: datetime) -> str | None:
        iso_year, iso_week, _weekday = detected_at.isocalendar()
        key = f"{self.prefix}/checkpoints/{iso_year}-W{iso_week:02d}.json.gz"
        if self.object_exists(key):
            return None
        return self.upload_snapshot(snapshot, key, "weekly-checkpoint")

    def object_exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            response = getattr(exc, "response", {})
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode") if isinstance(response, dict) else None
            code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
            if status == 404 or str(code) in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise SnapshotArchiveError(f"R2 head_object failed for {key}: {exc}") from exc

    def upload_snapshot(self, path: Path, key: str, archive_kind: str) -> str:
        raw = path.read_bytes()
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=compressed,
                ContentType="application/json",
                ContentEncoding="gzip",
                Metadata={
                    "archive-kind": archive_kind,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
            )
        except Exception as exc:
            raise SnapshotArchiveError(f"R2 upload failed for {key}: {exc}") from exc
        return key


def archive_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def replace_operational_baseline(candidate: Path, baseline: Path = DEFAULT_BASELINE_PATH) -> Path:
    baseline.parent.mkdir(parents=True, exist_ok=True)
    temporary = baseline.with_suffix(".tmp")
    shutil.copyfile(candidate, temporary)
    temporary.replace(baseline)
    if candidate.resolve() != baseline.resolve():
        candidate.unlink(missing_ok=True)
    return baseline


def operational_baseline_path(snapshot_dir: Path) -> Path:
    from src.snapshot import DEFAULT_SNAPSHOT_DIR

    if snapshot_dir == DEFAULT_SNAPSHOT_DIR:
        return DEFAULT_BASELINE_PATH
    return snapshot_dir.parent / "baseline" / "current_snapshot.json"


def finalize_snapshot_storage(
    previous: Path | None,
    candidate: Path,
    detected_at: datetime,
    has_changes: bool,
    baseline: Path = DEFAULT_BASELINE_PATH,
    archive: R2SnapshotArchive | None = None,
) -> Path:
    archive = archive if archive is not None else R2SnapshotArchive.from_env()
    if archive is not None:
        if has_changes and previous is not None:
            archive.archive_change_pair(previous, candidate, detected_at)
        archive.archive_weekly_checkpoint(candidate, detected_at)
    return replace_operational_baseline(candidate, baseline)
