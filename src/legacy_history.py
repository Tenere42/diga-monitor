"""Legacy snapshot reconciliation, R2 migration, and restore verification."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from src.change_events import normalize_monitor_text, removed_text_candidates, strip_leading_section_label
from src.diff import IGNORED_FIELD_PATHS, IGNORED_FIELD_PREFIXES, normalize_entry_for_diff
from src.snapshot import load_directory_metrics, load_snapshot


SNAPSHOT_PREFIX = "data/snapshots/diga_snapshot_"
SNAPSHOT_SUFFIX = "Z.json"
DEFAULT_MANIFEST_PATH = Path("data/audit/legacy_history_manifest.json")
DEFAULT_RETENTION_REPORT_PATH = Path("data/audit/legacy_retention_report.json")


@dataclass(frozen=True)
class SnapshotSource:
    path: str
    timestamp: datetime
    size: int


def parse_snapshot_timestamp(path: str) -> datetime:
    name = Path(path).name
    raw = name.removeprefix("diga_snapshot_").removesuffix("Z.json")
    return datetime.strptime(raw, "%Y%m%dT%H%M%S%f").replace(tzinfo=timezone.utc)


def git_snapshot_sources(ref: str = "HEAD") -> list[SnapshotSource]:
    output = subprocess.check_output(
        ["git", "ls-tree", "-r", "--long", ref, "--", "data/snapshots"],
        text=True,
        encoding="utf-8",
    )
    sources = []
    for line in output.splitlines():
        metadata, _, path = line.partition("\t")
        if not path.startswith(SNAPSHOT_PREFIX) or not path.endswith(SNAPSHOT_SUFFIX):
            continue
        size = int(metadata.split()[-1])
        sources.append(SnapshotSource(path, parse_snapshot_timestamp(path), size))
    return sorted(sources, key=lambda item: (item.timestamp, item.path))


def git_bytes(path: str, ref: str = "HEAD") -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"])


def monitored_state_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return precisely the state considered by the production snapshot diff."""
    entries = []
    for entry in snapshot.get("entries", []):
        if isinstance(entry, dict):
            entries.append(_without_ignored_fields(normalize_entry_for_diff(entry)))
    entries.sort(key=lambda item: str(item.get("id") or item.get("identifier") or item.get("url") or item.get("name") or item.get("title") or ""))
    metrics = load_directory_metrics(snapshot, entries)
    status_counts = metrics.get("status_counts") if isinstance(metrics.get("status_counts"), dict) else {}
    return {
        "entries": entries,
        "directory_metrics": {
            "total_count": metrics.get("total_count", len(entries)),
            "status_counts": {
                name: status_counts.get(name)
                for name in ("provisional", "permanent", "removed", "unknown")
            },
        },
    }


def _without_ignored_fields(value: Any, path: str = "") -> Any:
    if path in IGNORED_FIELD_PATHS or any(path == prefix or path.startswith(f"{prefix}.") for prefix in IGNORED_FIELD_PREFIXES):
        return None
    if isinstance(value, dict):
        return {
            key: cleaned
            for key in sorted(value)
            if (cleaned := _without_ignored_fields(value[key], f"{path}.{key}".lstrip("."))) is not None
        }
    if isinstance(value, list):
        return [_without_ignored_fields(item, path) for item in value]
    return value


def monitored_state_sha256(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(monitored_state_payload(snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_retention_report(
    sources: list[SnapshotSource],
    read_source: Callable[[str], bytes] = git_bytes,
) -> dict[str, Any]:
    """Classify every legacy snapshot and retain one representative per monitored state."""
    representatives: dict[str, str] = {}
    snapshots = []
    for source in sources:
        payload = json.loads(read_source(source.path))
        state_sha = monitored_state_sha256(payload)
        representative = representatives.setdefault(state_sha, source.path)
        snapshots.append(
            {
                "source_path": source.path,
                "created_at": payload.get("created_at"),
                "source_size": source.size,
                "monitored_state_sha256": state_sha,
                "retained_representative": representative,
                "redundant": source.path != representative,
            }
        )
    unique_paths = sorted(representatives.values())
    return {
        "schema_version": 1,
        "comparison_semantics": "src.diff monitored fields; ignored raw_public_fhir and diagnostic/render metadata",
        "snapshot_count": len(snapshots),
        "unique_monitored_state_count": len(unique_paths),
        "redundant_snapshot_count": len(snapshots) - len(unique_paths),
        "all_snapshots_classified": len(snapshots) == len(sources),
        "all_unique_states_have_representative": len(representatives) == len(unique_paths),
        "unique_state_representatives": unique_paths,
        "snapshots": snapshots,
    }


def write_retention_report(report: dict[str, Any], path: Path = DEFAULT_RETENTION_REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def closest_snapshot(sources: Iterable[SnapshotSource], value: str) -> SnapshotSource:
    target = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return min(sources, key=lambda item: (abs((item.timestamp - target).total_seconds()), item.path))


def matching_entry(snapshot: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        str(event.get("diga_id") or "").lower(),
        str(event.get("diga_name") or "").lower(),
        str(event.get("bfarm_directory_url") or "").lower(),
    ]
    for entry in snapshot.get("entries", []):
        if not isinstance(entry, dict):
            continue
        entry_keys = {
            str(entry.get("id") or "").lower(),
            str(entry.get("identifier") or "").lower(),
            str(entry.get("name") or "").lower(),
            str(entry.get("bfarm_directory_url") or "").lower(),
        }
        if any(candidate and candidate in entry_keys for candidate in candidates):
            return entry
    return None


def historical_snapshot_context(entry: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Keep only context consumed by the historical dashboard, not the full entry."""
    identity_keys = ("id", "identifier", "name", "manufacturer", "bfarm_directory_url")
    context = {key: entry[key] for key in identity_keys if entry.get(key) is not None}
    field_name = str(event.get("changed_field") or event.get("field_name") or "")
    descriptive = entry.get("descriptive_texts")
    selected_texts: dict[str, Any] = {}
    if isinstance(descriptive, dict) and field_name.startswith("descriptive_texts."):
        key = field_name.removeprefix("descriptive_texts.")
        if key in descriptive:
            selected_texts[key] = descriptive[key]
    if isinstance(descriptive, dict) and field_name == "evidence_summary_text":
        before = event.get("previous_value", event.get("before_value"))
        after = event.get("new_value", event.get("after_value"))
        if isinstance(before, str) and isinstance(after, str):
            candidates = [
                normalize_monitor_text(strip_leading_section_label(value))
                for value in removed_text_candidates(before, after)
            ]
            for key, value in descriptive.items():
                normalized = normalize_monitor_text(str(value))
                if any(len(candidate.split()) >= 20 and (candidate in normalized or candidate[:240] in normalized) for candidate in candidates):
                    selected_texts[key] = value
    if selected_texts:
        context["descriptive_texts"] = selected_texts

    sections = entry.get("structured_text_sections")
    if isinstance(sections, list):
        matching_sections = [
            section for section in sections
            if isinstance(section, dict) and section.get("field_path") == field_name
        ]
        if matching_sections:
            context["structured_text_sections"] = matching_sections
    return context


def load_change_payloads(changes_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(changes_dir.glob("changes_*.json"))
    ]


def backfill_event_contexts(
    changes_dir: Path,
    sources: list[SnapshotSource],
    read_source: Callable[[str], bytes] = git_bytes,
    write: bool = True,
) -> dict[str, Any]:
    cache: dict[str, dict[str, Any]] = {}
    selected: set[str] = set()
    changed_files = 0
    backfilled = 0
    unmatched = []

    for path, payload in load_change_payloads(changes_dir):
        changed = False
        for index, event in enumerate(payload.get("events", [])):
            timestamp = event.get("current_snapshot_timestamp")
            source = None
            if timestamp:
                parsed_timestamp = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if parsed_timestamp <= sources[-1].timestamp + timedelta(minutes=10):
                    source = closest_snapshot(sources, str(timestamp))
                    selected.add(source.path)
            if isinstance(event.get("snapshot_context"), dict):
                continue
            if not timestamp:
                unmatched.append({"file": str(path), "event_index": index, "reason": "missing timestamp"})
                continue
            if source is None:
                unmatched.append({"file": str(path), "event_index": index, "reason": "no legacy source"})
                continue
            snapshot = cache.setdefault(source.path, json.loads(read_source(source.path)))
            entry = matching_entry(snapshot, event)
            # Directory-level events historically resolved to no entry. An empty mapping
            # preserves that behavior while making the context explicit and self-contained.
            if entry is None and event.get("diga_id") != "__directory__":
                unmatched.append({"file": str(path), "event_index": index, "source": source.path})
                continue
            event["snapshot_context"] = historical_snapshot_context(entry, event) if entry is not None else {}
            changed = True
            backfilled += 1
        if changed:
            changed_files += 1
            if write:
                path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

    return {
        "backfilled_events": backfilled,
        "changed_files": changed_files,
        "selected_sources": sorted(selected),
        "unmatched_events": unmatched,
    }


def migration_sources(
    all_sources: list[SnapshotSource],
    event_sources: Iterable[str],
    baseline_path: Path = Path("data/baseline/current_snapshot.json"),
    unique_state_sources: Iterable[str] = (),
) -> list[dict[str, Any]]:
    roles: dict[str, set[str]] = {path: {"event-context"} for path in event_sources}
    for path in unique_state_sources:
        roles.setdefault(path, set()).add("unique-monitored-state")
    roles.setdefault(all_sources[0].path, set()).add("earliest")
    roles.setdefault(all_sources[-1].path, set()).add("last-legacy")
    seen_weeks: set[tuple[int, int]] = set()
    for source in all_sources:
        year, week, _ = source.timestamp.isocalendar()
        if (year, week) not in seen_weeks:
            roles.setdefault(source.path, set()).add("weekly-checkpoint")
            seen_weeks.add((year, week))

    result = [
        {
            "source_path": source.path,
            "object_key": f"full-snapshots/legacy/{Path(source.path).name}.gz",
            "roles": sorted(roles[source.path]),
            "source_size": source.size,
        }
        for source in all_sources
        if source.path in roles
    ]
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    stamp = datetime.fromisoformat(str(baseline["created_at"]).replace("Z", "+00:00")).strftime("%Y%m%dT%H%M%S%fZ")
    result.append(
        {
            "source_path": baseline_path.as_posix(),
            "object_key": f"full-snapshots/baseline/current_snapshot_{stamp}.json.gz",
            "roles": ["current-baseline"],
            "source_size": baseline_path.stat().st_size,
        }
    )
    return result


def verify_or_upload_object(client: Any, bucket: str, item: dict[str, Any], raw: bytes) -> dict[str, Any]:
    expected_sha = hashlib.sha256(raw).hexdigest()
    key = item["object_key"]
    try:
        head = client.head_object(Bucket=bucket, Key=key)
        stored_sha = str(head.get("Metadata", {}).get("sha256") or "")
        if stored_sha != expected_sha:
            raise ValueError(f"Existing R2 object has a different SHA-256: {key}")
    except Exception as exc:
        response = getattr(exc, "response", {})
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode") if isinstance(response, dict) else None
        code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
        if status != 404 and str(code) not in {"404", "NoSuchKey", "NotFound"}:
            raise
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=compressed,
            ContentType="application/json",
            ContentEncoding="gzip",
            Metadata={
                "archive-kind": "legacy-history",
                "sha256": expected_sha,
            },
        )
        head = client.head_object(Bucket=bucket, Key=key)

    response = client.get_object(Bucket=bucket, Key=key)
    compressed = response["Body"].read()
    restored = gzip.decompress(compressed)
    payload = json.loads(restored)
    calculated_sha = hashlib.sha256(restored).hexdigest()
    stored_sha = str(response.get("Metadata", {}).get("sha256") or head.get("Metadata", {}).get("sha256") or "")
    return {
        "key": key,
        "archive_kind": str(response.get("Metadata", {}).get("archive-kind") or "legacy-history"),
        "timestamp": payload.get("created_at"),
        "compressed_size": len(compressed),
        "uncompressed_size": len(restored),
        "stored_sha256": stored_sha,
        "calculated_sha256": calculated_sha,
        "json_parse": True,
        "internal_created_at": payload.get("created_at"),
        "legacy_source_path": item["source_path"],
        "legacy_source_match": restored == raw,
        "roles": item["roles"],
        "verified": stored_sha == calculated_sha == expected_sha and restored == raw,
    }


def execute_r2_migration(
    client: Any,
    bucket: str,
    plan: list[dict[str, Any]],
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    ref: str = "HEAD",
) -> dict[str, Any]:
    entries = []
    for item in plan:
        path = item["source_path"]
        raw = Path(path).read_bytes() if Path(path).exists() else git_bytes(path, ref)
        entries.append(verify_or_upload_object(client, bucket, item, raw))
    if not all(entry["verified"] for entry in entries):
        raise ValueError("At least one R2 object failed verification")

    manifest = {
        "schema_version": 1,
        "bucket": bucket,
        "object_count": len(entries),
        "all_verified": True,
        "objects": sorted(entries, key=lambda entry: entry["key"]),
    }
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old == manifest:
            return manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_manifest_objects(client: Any, bucket: str, manifest: dict[str, Any]) -> dict[str, Any]:
    """Reverify retained R2 objects without requiring any legacy source files."""
    verified = []
    for entry in manifest.get("objects", []):
        response = client.get_object(Bucket=bucket, Key=entry["key"])
        compressed = response["Body"].read()
        raw = gzip.decompress(compressed)
        json.loads(raw)
        calculated = hashlib.sha256(raw).hexdigest()
        stored = str(response.get("Metadata", {}).get("sha256") or "")
        expected = str(entry.get("calculated_sha256") or entry.get("stored_sha256") or "")
        if calculated != stored or calculated != expected:
            raise ValueError(f"R2 manifest verification failed: {entry['key']}")
        verified.append(entry["key"])
    if len(verified) != int(manifest.get("object_count", -1)):
        raise ValueError("R2 manifest object count does not match verified objects")
    return {"verified_r2_objects": len(verified), "all_verified": True, "source_files_required": False}


def restore_object(client: Any, bucket: str, entry: dict[str, Any], target: Path) -> dict[str, Any]:
    response = client.get_object(Bucket=bucket, Key=entry["key"])
    raw = gzip.decompress(response["Body"].read())
    payload = json.loads(raw)
    calculated = hashlib.sha256(raw).hexdigest()
    if calculated != entry["stored_sha256"]:
        raise ValueError(f"Restore SHA-256 mismatch: {entry['key']}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {"key": entry["key"], "target": str(target), "created_at": payload.get("created_at"), "sha256": calculated}


def restore_baseline_integration(client: Any, bucket: str, entry: dict[str, Any], root: Path) -> dict[str, Any]:
    """Restore an R2 object as an isolated operational baseline and load it through production code."""
    baseline = root / "data" / "baseline" / "current_snapshot.json"
    restored = restore_object(client, bucket, entry, baseline)
    loaded = load_snapshot(baseline)
    if loaded.created_at != restored["created_at"] or not isinstance(loaded.entries, list):
        raise ValueError("Restored baseline cannot be loaded by the production snapshot path")
    return {
        **restored,
        "baseline_path": str(baseline),
        "entry_count": len(loaded.entries),
        "load_path_verified": True,
        "isolated": True,
        "successful": True,
    }
