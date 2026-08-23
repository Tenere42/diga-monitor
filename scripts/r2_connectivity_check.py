"""Safely verify the R2 credentials used by the snapshot archive.

This diagnostic never prints configuration values. It lists the configured
bucket, probes a unique key, uploads a small object, verifies it, and removes
it again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from src.snapshot_storage import R2SnapshotArchive, SnapshotArchiveError


class R2ConnectivityError(RuntimeError):
    """Raised when a connectivity-check stage fails."""


@dataclass(frozen=True)
class OperationResult:
    operation: str
    passed: bool
    status: str
    code: str
    message: str


def safe_error_metadata(exc: Exception) -> tuple[str, str]:
    """Return status and error code only, never an exception message."""
    response = getattr(exc, "response", {})
    if not isinstance(response, dict):
        return "unknown", "unknown"
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode", "unknown")
    code = response.get("Error", {}).get("Code", "unknown")
    return str(status), str(code)


def is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    if not isinstance(response, dict):
        return False
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    code = response.get("Error", {}).get("Code")
    return status == 404 or str(code) in {"404", "NoSuchKey", "NotFound"}


def _call(operation_name: str, operation: Any, **kwargs: Any) -> OperationResult:
    try:
        operation(**kwargs)
    except Exception as exc:
        status, code = safe_error_metadata(exc)
        return OperationResult(
            operation_name, False, status, code, "request rejected"
        )
    return OperationResult(operation_name, True, "success", "success", "request succeeded")


def run_connectivity_check(
    archive: R2SnapshotArchive,
    key: str | None = None,
) -> list[OperationResult]:
    """Test each R2 operation independently and always attempt cleanup."""
    key = key or f"diagnostics/connectivity-{uuid.uuid4().hex}.txt"
    client = archive.client
    bucket = archive.bucket
    results: list[OperationResult] = []

    try:
        client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        status, code = safe_error_metadata(exc)
        if is_not_found(exc):
            results.append(
                OperationResult(
                    "HeadObject nonexistent", True, status, code, "expected object-not-found response"
                )
            )
        else:
            results.append(
                OperationResult("HeadObject nonexistent", False, status, code, "request rejected")
            )
    else:
        results.append(
            OperationResult(
                "HeadObject nonexistent",
                False,
                "success",
                "UnexpectedExistingObject",
                "diagnostic key unexpectedly exists; it was not modified",
            )
        )
        results.append(
            _call("ListObjectsV2", client.list_objects_v2, Bucket=bucket, MaxKeys=1)
        )
        return results

    results.append(
        _call(
            "PutObject",
            client.put_object,
            Bucket=bucket,
            Key=key,
            Body=b"DiGA Monitor R2 connectivity check\n",
            ContentType="text/plain",
        )
    )
    results.append(
        _call("HeadObject uploaded", client.head_object, Bucket=bucket, Key=key)
    )
    results.append(
        _call("DeleteObject cleanup", client.delete_object, Bucket=bucket, Key=key)
    )
    results.append(
        _call("ListObjectsV2", client.list_objects_v2, Bucket=bucket, MaxKeys=1)
    )
    return results


def main() -> int:
    try:
        archive = R2SnapshotArchive.from_env()
        if archive is None:
            raise R2ConnectivityError("R2 configuration is not present")
        results = run_connectivity_check(archive)
    except (SnapshotArchiveError, R2ConnectivityError) as exc:
        print(str(exc))
        return 1
    for result in results:
        outcome = "PASS" if result.passed else "FAIL"
        print(
            f"{outcome} {result.operation}: status={result.status} "
            f"code={result.code} message={result.message}"
        )
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
