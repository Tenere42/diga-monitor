"""Backfill legacy contexts and perform an idempotent verified R2 migration."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from src.legacy_history import (
    DEFAULT_MANIFEST_PATH,
    backfill_event_contexts,
    execute_r2_migration,
    git_snapshot_sources,
    migration_sources,
    restore_object,
)


def r2_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"].strip(),
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--execute-r2", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()

    sources = git_snapshot_sources()
    result = backfill_event_contexts(Path("outputs/changes"), sources, write=args.backfill)
    if result["unmatched_events"]:
        raise RuntimeError(f"Unmatched events: {json.dumps(result['unmatched_events'], ensure_ascii=False)}")
    plan = migration_sources(sources, result["selected_sources"])
    summary = {"backfill": result, "planned_r2_objects": len(plan)}

    if args.execute_r2:
        bucket = os.environ.get("R2_BUCKET_NAME", "diga-monitor").strip()
        client = r2_client()
        manifest = execute_r2_migration(client, bucket, plan, args.manifest)
        historical = next(entry for entry in manifest["objects"] if "event-context" in entry["roles"])
        with tempfile.TemporaryDirectory() as directory:
            restored = restore_object(client, bucket, historical, Path(directory) / "restored_snapshot.json")
            if not Path(restored["target"]).is_file():
                raise RuntimeError("Isolated restore did not create a snapshot")
        summary["verified_r2_objects"] = manifest["object_count"]
        summary["restore"] = {**restored, "isolated": True, "successful": True}

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
