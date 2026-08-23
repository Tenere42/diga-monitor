from __future__ import annotations

import unittest

from scripts.r2_connectivity_check import run_connectivity_check
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
        if self.fail_at == "put":
            raise S3Error(403, "AccessDenied", "never-print-this-secret")
        self.objects[str(kwargs["Key"])] = bytes(kwargs["Body"])

    def delete_object(self, **kwargs: object) -> None:
        self.calls.append("delete")
        self.objects.pop(str(kwargs["Key"]), None)


class R2ConnectivityCheckTests(unittest.TestCase):
    def test_check_verifies_access_and_removes_temporary_object(self) -> None:
        client = DiagnosticS3Client()
        archive = R2SnapshotArchive(client=client, bucket="diga-monitor")

        run_connectivity_check(archive, "diagnostics/test-key.txt")

        self.assertEqual(client.calls, ["head", "put", "head", "delete", "list"])
        self.assertEqual(client.objects, {})

    def test_check_reports_each_operation_and_cleans_up_after_failure(self) -> None:
        client = DiagnosticS3Client(fail_at="head-after")
        archive = R2SnapshotArchive(client=client, bucket="diga-monitor")

        results = run_connectivity_check(archive, "diagnostics/test-key.txt")

        self.assertEqual(len(results), 5)
        failed = [result for result in results if not result.passed]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].operation, "HeadObject uploaded")
        self.assertEqual((failed[0].status, failed[0].code), ("403", "AccessDenied"))
        self.assertNotIn("never-print-this-secret", repr(results))
        self.assertEqual(client.objects, {})
        self.assertIn("delete", client.calls)
        self.assertEqual(client.calls[-1], "list")

    def test_list_failure_does_not_block_production_operations(self) -> None:
        client = DiagnosticS3Client(fail_at="list")
        archive = R2SnapshotArchive(client=client, bucket="diga-monitor")

        results = run_connectivity_check(archive, "diagnostics/test-key.txt")

        self.assertTrue(all(result.passed for result in results[:-1]))
        self.assertEqual(results[-1].operation, "ListObjectsV2")
        self.assertFalse(results[-1].passed)
        self.assertEqual((results[-1].status, results[-1].code), ("403", "AccessDenied"))
        self.assertNotIn("never-print-this-secret", repr(results))

    def test_cleanup_is_attempted_even_when_put_fails(self) -> None:
        client = DiagnosticS3Client(fail_at="put")
        archive = R2SnapshotArchive(client=client, bucket="diga-monitor")

        results = run_connectivity_check(archive, "diagnostics/test-key.txt")

        self.assertEqual(len(results), 5)
        self.assertIn("delete", client.calls)
        self.assertEqual(client.objects, {})


if __name__ == "__main__":
    unittest.main()
