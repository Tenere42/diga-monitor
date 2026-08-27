"""Backfill legacy contexts and perform an idempotent verified R2 migration."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from src.legacy_history import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_RETENTION_REPORT_PATH,
    backfill_event_contexts,
    build_retention_report,
    execute_r2_migration,
    git_snapshot_sources,
    migration_sources,
    restore_baseline_integration,
    verify_manifest_objects,
    write_retention_report,
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
    parser.add_argument("--retention-report", type=Path, default=DEFAULT_RETENTION_REPORT_PATH)
    parser.add_argument("--verify-existing-manifest", action="store_true")
    args = parser.parse_args()

    if args.verify_existing_manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        bucket = os.environ.get("R2_BUCKET_NAME", "diga-monitor").strip()
        print(json.dumps(verify_manifest_objects(r2_client(), bucket, manifest), sort_keys=True))
        return 0

    sources = git_snapshot_sources()
    result = backfill_event_contexts(Path("outputs/changes"), sources, write=args.backfill)
    if result["unmatched_events"]:
        raise RuntimeError(f"Unmatched events: {json.dumps(result['unmatched_events'], ensure_ascii=False)}")
    retention = build_retention_report(sources)
    write_retention_report(retention, args.retention_report)
    plan = migration_sources(sources, result["selected_sources"], unique_state_sources=retention["unique_state_representatives"])
    summary = {"backfill": result, "retention": {key: retention[key] for key in ("snapshot_count", "unique_monitored_state_count", "redundant_snapshot_count", "all_snapshots_classified", "all_unique_states_have_representative")}, "planned_r2_objects": len(plan)}

    if args.execute_r2:
        bucket = os.environ.get("R2_BUCKET_NAME", "diga-monitor").strip()
        client = r2_client()
        manifest = execute_r2_migration(client, bucket, plan, args.manifest)
        baseline_entry = next(entry for entry in manifest["objects"] if "current-baseline" in entry["roles"])
        with tempfile.TemporaryDirectory() as directory:
            restored = restore_baseline_integration(client, bucket, baseline_entry, Path(directory))
        summary["verified_r2_objects"] = manifest["object_count"]
        summary["restore"] = {**restored, "isolated": True, "successful": True}

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
