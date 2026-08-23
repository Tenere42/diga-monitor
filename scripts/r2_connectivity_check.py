"""Safely verify the R2 credentials used by the snapshot archive.

This diagnostic never prints configuration values. It lists the configured
bucket, probes a unique key, uploads a small object, verifies it, and removes
it again.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.snapshot_storage import R2SnapshotArchive, SnapshotArchiveError


class R2ConnectivityError(RuntimeError):
    """Raised when a connectivity-check stage fails."""


def safe_error_metadata(exc: Exception) -> str:
    """Return status and error code only, never an exception message."""
    response = getattr(exc, "response", {})
    if not isinstance(response, dict):
        return "status=unknown code=unknown"
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode", "unknown")
    code = response.get("Error", {}).get("Code", "unknown")
    return f"status={status} code={code}"


def is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    if not isinstance(response, dict):
        return False
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    code = response.get("Error", {}).get("Code")
    return status == 404 or str(code) in {"404", "NoSuchKey", "NotFound"}


def _call(stage: str, operation: Any, **kwargs: Any) -> Any:
    try:
        return operation(**kwargs)
    except Exception as exc:
        raise R2ConnectivityError(
            f"R2 connectivity check failed at {stage}: {safe_error_metadata(exc)}"
        ) from None


def run_connectivity_check(archive: R2SnapshotArchive, key: str | None = None) -> None:
    """Verify list, head, put, and delete access without touching archive data."""
    key = key or f"diagnostics/connectivity-{uuid.uuid4().hex}.txt"
    client = archive.client
    bucket = archive.bucket
    uploaded = False

    _call("ListBucket", client.list_objects_v2, Bucket=bucket, MaxKeys=1)

    try:
        client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if not is_not_found(exc):
            raise R2ConnectivityError(
                "R2 connectivity check failed at HeadObject-before-upload: "
                f"{safe_error_metadata(exc)}"
            ) from None
    else:
        raise R2ConnectivityError("R2 connectivity check generated a non-unique temporary key")

    try:
        _call(
            "PutObject",
            client.put_object,
            Bucket=bucket,
            Key=key,
            Body=b"DiGA Monitor R2 connectivity check\n",
            ContentType="text/plain",
        )
        uploaded = True
        _call("HeadObject-after-upload", client.head_object, Bucket=bucket, Key=key)
    finally:
        if uploaded:
            _call("DeleteObject", client.delete_object, Bucket=bucket, Key=key)


def main() -> int:
    try:
        archive = R2SnapshotArchive.from_env()
        if archive is None:
            raise R2ConnectivityError("R2 configuration is not present")
        run_connectivity_check(archive)
    except (SnapshotArchiveError, R2ConnectivityError) as exc:
        print(str(exc))
        return 1
    print("R2 connectivity check passed: ListBucket, HeadObject, PutObject, and DeleteObject")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
