from __future__ import annotations

import unittest

from scripts.r2_connectivity_check import R2ConnectivityError, run_connectivity_check
from src.snapshot_storage import R2SnapshotArchive


class S3Error(Exception):
    def __init__(self, status: int, code: str, secret: str = "") -> None:
        super().__init__(f"{code}: {secret}")
        self.response = {
            "ResponseMetadata": {"HTTPStatusCode": status},
            "Error": {"Code": code},
        }


class DiagnosticS3Client:
    def __init__(self, fail_at: str | None = None) -> None:
        self.fail_at = fail_at
        self.objects: dict[str, bytes] = {}
        self.calls: list[str] = []

    def list_objects_v2(self, **_kwargs: object) -> dict[str, object]:
        self.calls.append("list")
        if self.fail_at == "list":
            raise S3Error(403, "AccessDenied", "never-print-this-secret")
        return {"Contents": []}

    def head_object(self, **kwargs: object) -> dict[str, object]:
        self.calls.append("head")
        if self.fail_at == "head-after" and str(kwargs["Key"]) in self.objects:
            raise S3Error(403, "AccessDenied", "never-print-this-secret")
        if str(kwargs["Key"]) not in self.objects:
            raise S3Error(404, "NoSuchKey")
        return {}

    def put_object(self, **kwargs: object) -> None:
        self.calls.append("put")
        self.objects[str(kwargs["Key"])] = bytes(kwargs["Body"])

    def delete_object(self, **kwargs: object) -> None:
        self.calls.append("delete")
        self.objects.pop(str(kwargs["Key"]), None)


class R2ConnectivityCheckTests(unittest.TestCase):
    def test_check_verifies_access_and_removes_temporary_object(self) -> None:
        client = DiagnosticS3Client()
        archive = R2SnapshotArchive(client=client, bucket="diga-monitor")

        run_connectivity_check(archive, "diagnostics/test-key.txt")

        self.assertEqual(client.calls, ["list", "head", "put", "head", "delete"])
        self.assertEqual(client.objects, {})

    def test_check_cleans_up_after_post_upload_failure_without_leaking_details(self) -> None:
        client = DiagnosticS3Client(fail_at="head-after")
        archive = R2SnapshotArchive(client=client, bucket="diga-monitor")

        with self.assertRaises(R2ConnectivityError) as raised:
            run_connectivity_check(archive, "diagnostics/test-key.txt")

        message = str(raised.exception)
        self.assertIn("HeadObject-after-upload", message)
        self.assertIn("status=403 code=AccessDenied", message)
        self.assertNotIn("never-print-this-secret", message)
        self.assertEqual(client.objects, {})
        self.assertEqual(client.calls[-1], "delete")

    def test_auth_failure_reports_only_safe_metadata(self) -> None:
        client = DiagnosticS3Client(fail_at="list")
        archive = R2SnapshotArchive(client=client, bucket="diga-monitor")

        with self.assertRaises(R2ConnectivityError) as raised:
            run_connectivity_check(archive, "diagnostics/test-key.txt")

        message = str(raised.exception)
        self.assertEqual(
            message,
            "R2 connectivity check failed at ListBucket: status=403 code=AccessDenied",
        )
        self.assertNotIn("never-print-this-secret", message)


if __name__ == "__main__":
    unittest.main()
