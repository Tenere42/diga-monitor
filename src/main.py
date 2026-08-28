"""CLI entry point for the DiGA directory change monitor."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src.change_events import build_change_events, save_change_events, snapshot_context, word_level_diff
from src.diff import diff_snapshots, render_report
from src.fetch_diga import fetch_diga_entries
from src.notifications import is_notifiable_event, notify_changes, send_test_notification
from src.render_directory import (
    diff_content_section_files,
    diff_content_section_lists,
    inspect_rendered_structure_file,
    render_diga_content_sections,
    render_diga_entry,
)
from src.scan_history import append_scan_history
from src.simulations import run_simulation
from src.snapshot import (
    DEFAULT_SNAPSHOT_DIR,
    Snapshot,
    calculate_directory_metrics,
    latest_snapshot_paths,
    load_snapshot,
    save_snapshot,
)
from src.snapshot_storage import finalize_snapshot_storage, operational_baseline_path


DEFAULT_SIMULATION_DIR = Path("data/simulations")
VISIBLE_BASELINE_DIR = Path("data/rendered_structure/latest")
VISIBLE_HISTORY_DIR = Path("data/rendered_structure/history")
VISIBLE_RUN_DIR = Path("outputs/rendered_structure/runs")
PRESERVED_CHANGE_TYPES = {"new_diga", "removed_diga", "status_change", "directory_metric_change"}
ORTHOPY_REMOVED_SENTENCE = "Für die DiGA konnte kein positiver Versorgungseffekt nachgewiesen werden."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor changes in the BfArM DiGA directory.")
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=DEFAULT_SNAPSHOT_DIR,
        help="Directory where JSON snapshots are stored.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Fetch, save a snapshot, and compare it with the previous snapshot.")
    run_parser.add_argument("--notify", action="store_true", help="Send an email when real changes are detected.")
    run_parser.add_argument("--dry-run", action="store_true", help="Print the notification email without sending it.")
    run_parser.add_argument(
        "--with-rendered-structure",
        action="store_true",
        help="Optionally render DiGA pages and store visible content_sections in the snapshot.",
    )
    run_parser.add_argument(
        "--render-changed-entries",
        action="store_true",
        help="Render only DiGA entries with real detected changes after the normal scan.",
    )
    run_parser.add_argument("--archive-rendered-pages", action="store_true", help="Also save PDF/PNG rendered page archives.")
    run_parser.add_argument("--limit", type=int, help="Limit fetched entries for local rendered-structure tests.")
    notify_test_parser = subparsers.add_parser(
        "notify-test",
        help="Send or preview a test notification email without running a DiGA scan.",
    )
    notify_test_parser.add_argument("--dry-run", action="store_true", help="Print the test email without sending it.")
    subparsers.add_parser("fetch", help="Fetch entries and print them without saving a snapshot.")
    render_parser = subparsers.add_parser(
        "render-entry",
        help="Render one public BfArM DiGA detail page as optional PDF/PNG audit archive.",
    )
    render_parser.add_argument("--url", required=True, help="Official BfArM DiGA detail page URL.")
    render_parser.add_argument("--diga-id", required=True, help="DiGA directory identifier used in output filenames.")
    render_parser.add_argument("--slug", help="Optional human-readable filename slug, for example somnio.")
    render_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/rendered_pages"),
        help="Directory where rendered page archives are stored.",
    )
    render_parser.add_argument("--no-pdf", action="store_true", help="Do not write a PDF file.")
    render_parser.add_argument("--no-png", action="store_true", help="Do not write a full-page PNG screenshot.")
    baseline_parser = subparsers.add_parser(
        "build-rendered-baseline",
        help="Render all known DiGA entries and store visible structure baselines.",
    )
    baseline_parser.add_argument("--limit", type=int, help="Limit rendered entries for local tests.")
    baseline_parser.add_argument(
        "--archive-rendered-pages",
        action="store_true",
        help="Also save PDF/PNG rendered page archives while building the baseline.",
    )
    for command_name in ("inspect-structure", "inspect-rendered-structure"):
        inspect_parser = subparsers.add_parser(
            command_name,
            help="Inspect extracted content_sections from a rendered DiGA structure JSON file.",
        )
        inspect_parser.add_argument("--file", required=True, type=Path, help="Path to a *_structure.json file.")
        inspect_parser.add_argument("--out", type=Path, help="Optional Markdown output path.")
    content_diff_parser = subparsers.add_parser(
        "diff-content-sections",
        help="Dry-run diff for two rendered DiGA structure JSON files based on content_sections.",
    )
    content_diff_parser.add_argument("--before", required=True, type=Path, help="Previous *_structure.json file.")
    content_diff_parser.add_argument("--after", required=True, type=Path, help="Current *_structure.json file.")
    content_diff_parser.add_argument("--out", type=Path, help="Optional Markdown output path.")
    simulate_suite_parser = subparsers.add_parser("simulate", help="Generate safe simulated change events.")
    simulate_suite_parser.add_argument(
        "scenario",
        choices=[
            "all",
            "text-change",
            "price-change",
            "status-change",
            "new-diga",
            "removed-diga",
            "study-evidence",
            "all-page-fields",
        ],
        help="Simulation scenario to generate.",
    )
    simulate_suite_parser.add_argument("--notify", action="store_true", help="Print a dry-run email for simulated events.")
    simulate_suite_parser.add_argument("--dry-run", action="store_true", help="Required with --notify; never sends email.")
    simulate_parser = subparsers.add_parser(
        "simulate-orthopy-change",
        help="Create a temporary Orthopy text-change simulation event.",
    )
    simulate_parser.add_argument("--notify", action="store_true", help="Print a dry-run email for the simulated event.")
    simulate_parser.add_argument("--dry-run", action="store_true", help="Required with --notify; never sends email.")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = build_parser().parse_args()

    if args.command == "fetch":
        entries = fetch_diga_entries()
        print(json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "run":
        return run_monitor(
            args.snapshot_dir,
            notify=args.notify,
            dry_run=args.dry_run,
            with_rendered_structure=args.with_rendered_structure or env_flag("DIGA_RENDER_STRUCTURE"),
            render_changed_entries=args.render_changed_entries or env_flag("DIGA_RENDER_CHANGED_ENTRIES"),
            archive_rendered_pages=args.archive_rendered_pages,
            limit=args.limit,
        )

    if args.command == "notify-test":
        return run_notify_test(dry_run=args.dry_run)

    if args.command == "render-entry":
        return render_entry_command(args)

    if args.command == "build-rendered-baseline":
        return build_rendered_baseline_command(
            limit=args.limit,
            archive_rendered_pages=args.archive_rendered_pages,
        )

    if args.command in {"inspect-structure", "inspect-rendered-structure"}:
        return inspect_structure_command(args)

    if args.command == "diff-content-sections":
        return diff_content_sections_command(args)

    if args.command == "simulate":
        return run_simulation_command(args.snapshot_dir, args.scenario, notify=args.notify, dry_run=args.dry_run)

    if args.command == "simulate-orthopy-change":
        return simulate_orthopy_change(args.snapshot_dir, notify=args.notify, dry_run=args.dry_run)

    raise ValueError(f"Unsupported command: {args.command}")


def run_monitor(
    snapshot_dir: Path,
    notify: bool = False,
    dry_run: bool = False,
    with_rendered_structure: bool = False,
    render_changed_entries: bool = False,
    archive_rendered_pages: bool = False,
    limit: int | None = None,
) -> int:
    started = time.perf_counter()
    if render_changed_entries:
        print("Render-on-change active: FHIR changes trigger rendering; visible content_sections drive user-facing events.")
    else:
        print("Render-on-change inactive.")
    baseline_path = operational_baseline_path(snapshot_dir)
    previous_paths = [baseline_path] if baseline_path.exists() else []
    if not previous_paths and snapshot_dir != DEFAULT_SNAPSHOT_DIR:
        previous_paths = latest_snapshot_paths(snapshot_dir, limit=1)
    entries = fetch_diga_entries()
    if limit is not None:
        entries = entries[: max(limit, 0)]
        print(f"Limited scan to {len(entries)} DiGA entries.")
    if with_rendered_structure:
        enrich_entries_with_rendered_structure(entries, archive_rendered_pages=archive_rendered_pages)
    candidate_dir = snapshot_dir if snapshot_dir == DEFAULT_SNAPSHOT_DIR else snapshot_dir.parent / "work_snapshots"
    new_snapshot_path = save_snapshot(entries, candidate_dir)
    detected_at = datetime.now(timezone.utc).isoformat()
    print(f"Prepared candidate snapshot: {new_snapshot_path}")

    if not previous_paths:
        if with_rendered_structure:
            baseline_stats = save_visible_baselines_from_entries(entries, detected_at)
            print(
                "Visible rendered baselines: "
                f"{baseline_stats['created']} created, "
                f"{baseline_stats['updated']} updated, "
                f"{baseline_stats['existing']} already present, "
                f"{baseline_stats['skipped']} skipped."
            )
        baseline_path = finalize_snapshot_storage(
            previous=None,
            candidate=new_snapshot_path,
            detected_at=datetime.fromisoformat(detected_at),
            has_changes=False,
            baseline=baseline_path,
        )
        print(f"Operational baseline updated: {baseline_path}")
        append_scan_history(
            scan_timestamp=detected_at,
            number_of_diga=len(entries),
            changes_detected=0,
            scan_duration_seconds=time.perf_counter() - started,
        )
        if notify:
            notify_changes([], dry_run=dry_run)
        print("No previous snapshot found. Baseline created.")
        return 0

    old_snapshot = load_snapshot(previous_paths[0])
    new_snapshot = load_snapshot(new_snapshot_path)
    if with_rendered_structure:
        dry_run_report_path = save_content_section_scan_dry_run_report(old_snapshot.entries, new_snapshot.entries, detected_at)
        if dry_run_report_path:
            print(f"Saved content_sections dry-run report: {dry_run_report_path}")
    if limit is not None:
        append_scan_history(
            scan_timestamp=detected_at,
            number_of_diga=len(entries),
            changes_detected=0,
            scan_duration_seconds=time.perf_counter() - started,
        )
        if notify:
            notify_changes([], dry_run=dry_run)
        new_snapshot_path.unlink(missing_ok=True)
        print("Limited test scan: skipped production snapshot diff and normal change event generation.")
        return 0
    report = diff_snapshots(old_snapshot, new_snapshot)
    events = []
    if report.has_changes:
        trigger_events = build_change_events(report, old_snapshot, new_snapshot, detected_at)
        events = trigger_events
        pending_baseline_updates: list[dict[str, object]] = []
        if render_changed_entries:
            lifecycle_events = [event for event in trigger_events if is_lifecycle_event(event)]
            content_trigger_events = [event for event in trigger_events if not is_lifecycle_event(event)]
            rendered_entries = render_changed_entry_archives(
                events=trigger_events,
                entries=new_snapshot.entries,
                detected_at=detected_at,
                archive_rendered_pages=archive_rendered_pages,
            )
            content_rendered_entries = {
                diga_id: rendered
                for diga_id, rendered in rendered_entries.items()
                if diga_id in event_diga_ids(content_trigger_events)
            }
            visible_events = []
            if content_trigger_events:
                visible_events, visible_baseline_updates = build_visible_change_events_from_rendered_baselines(
                    trigger_events=content_trigger_events,
                    rendered_entries=content_rendered_entries,
                    entries=new_snapshot.entries,
                    detected_at=detected_at,
                )
                pending_baseline_updates.extend(visible_baseline_updates)
            events = lifecycle_events + visible_events
            print(f"Rendered changed DiGA entries: {len(rendered_entries)}")
            print(f"Lifecycle change events preserved: {len(lifecycle_events)}")
            print(f"Visible content_section change events: {len(visible_events)}")
        if events:
            changes_path = save_change_events(events, detected_at=detected_at)
            if changes_path:
                print(f"Saved change events: {changes_path}")
            if render_changed_entries and pending_baseline_updates:
                apply_visible_baseline_updates(pending_baseline_updates)
        elif render_changed_entries:
            print("No visible content_section changes detected. FHIR changes were used as trigger only.")
    print(f"Detected change events: {len(events)}")
    warn_for_unmatched_directory_metric_changes(events)
    baseline_path = finalize_snapshot_storage(
        previous=old_snapshot.path,
        candidate=new_snapshot.path,
        detected_at=datetime.fromisoformat(detected_at),
        has_changes=report.has_changes,
        baseline=baseline_path,
    )
    print(f"Operational baseline updated: {baseline_path}")
    append_scan_history(
        scan_timestamp=detected_at,
        number_of_diga=len(entries),
        changes_detected=len(events),
        scan_duration_seconds=time.perf_counter() - started,
    )
    if notify:
        notify_changes(events, dry_run=dry_run)
    print()
    print(render_report(report))
    return 0


def run_notify_test(dry_run: bool = False) -> int:
    print("Running Brevo API notification configuration and delivery test.")
    return 0 if send_test_notification(dry_run=dry_run) else 1


def render_entry_command(args: argparse.Namespace) -> int:
    try:
        result = render_diga_entry(
            url=args.url,
            diga_id=args.diga_id,
            output_root=args.output_dir,
            slug=args.slug,
            save_pdf=not args.no_pdf,
            save_png=not args.no_png,
        )
    except RuntimeError as exc:
        print(exc)
        return 1

    print("Rendered DiGA entry archive:")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print()
    print(f"Opened accordions: {result.get('accordions_opened', 0)}")
    print(f"Extracted content sections: {result.get('content_section_count', 0)}")
    print(f"Extracted field/value pairs: {result.get('field_value_count', 0)}")
    example_paths = result.get("example_paths") or []
    if example_paths:
        print("Example paths:")
        for path in example_paths[:10]:
            print(f"- {path}")
    return 0


def build_rendered_baseline_command(limit: int | None = None, archive_rendered_pages: bool = False) -> int:
    started = time.perf_counter()
    detected_at = datetime.now(timezone.utc).isoformat()
    entries = fetch_diga_entries()
    total_available = len(entries)
    if limit is not None:
        entries = entries[: max(limit, 0)]
        print(f"Limited rendered baseline build to {len(entries)} of {total_available} DiGA entries.")

    print(f"Building visible rendered baselines in {VISIBLE_BASELINE_DIR}")
    success_paths: list[Path] = []
    failures: list[dict[str, str]] = []
    for index, entry in enumerate(entries, start=1):
        diga_id = str(entry.get("id") or "")
        name = str(entry.get("name") or diga_id)
        url = str(entry.get("bfarm_directory_url") or "")
        if not diga_id or not url:
            failures.append({"diga_id": diga_id, "name": name, "error": "missing id or BfArM URL"})
            print(f"[{index}/{len(entries)}] Skipping {name}: missing id or BfArM URL")
            continue
        print(f"[{index}/{len(entries)}] Rendering baseline for {name} ({diga_id})")
        try:
            payload = render_visible_structure_payload(
                entry=entry,
                detected_at=detected_at,
                archive_rendered_pages=archive_rendered_pages,
            )
        except Exception as exc:
            failures.append({"diga_id": diga_id, "name": name, "error": str(exc)})
            print(f"    failed: {exc}")
            continue

        baseline_path = visible_baseline_path(diga_id, name)
        replace_visible_baseline(
            payload=payload,
            path=baseline_path,
            diga_id=diga_id,
            detected_at=detected_at,
            archive_existing=True,
        )
        success_paths.append(baseline_path)
        print(
            "    saved: "
            f"{baseline_path} "
            f"({len(payload.get('content_sections') or [])} content_sections)"
        )

    duration = time.perf_counter() - started
    print()
    print("Rendered baseline build complete.")
    print(f"DiGA total available: {total_available}")
    print(f"DiGA processed: {len(entries)}")
    print(f"Successfully rendered: {len(success_paths)}")
    print(f"Failed: {len(failures)}")
    print(f"Duration seconds: {duration:.1f}")
    if success_paths:
        print("Generated baseline files:")
        for path in success_paths:
            print(f"- {path}")
    if failures:
        print("Failures:")
        for failure in failures:
            print(f"- {failure['name']} ({failure['diga_id']}): {failure['error']}")
        return 1
    return 0


def env_flag(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def render_visible_structure_payload(
    entry: dict[str, object],
    detected_at: str,
    archive_rendered_pages: bool = False,
) -> dict[str, object]:
    diga_id = str(entry.get("id") or "")
    name = str(entry.get("name") or diga_id)
    url = str(entry.get("bfarm_directory_url") or "")
    if not diga_id or not url:
        raise ValueError("missing DiGA id or BfArM directory URL")

    if archive_rendered_pages:
        rendered = render_diga_entry(
            url=url,
            diga_id=diga_id,
            output_root=Path("data/rendered_pages"),
            slug=name,
            timestamp=scan_timestamp_for_path(detected_at),
            save_pdf=True,
            save_png=True,
        )
        structure_path = Path(str(rendered["structure_path"]))
        with structure_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        payload["name"] = name
        payload["source_kind"] = "visible_directory"
        payload["rendered_structure_metadata"] = {
            "source_kind": "visible_directory",
            "rendered_at": rendered.get("timestamp"),
            "accordions_opened": rendered.get("accordions_opened"),
            "content_section_count": rendered.get("content_section_count"),
            "field_value_count": rendered.get("field_value_count"),
            "archive": {
                "pdf_path": rendered.get("pdf_path"),
                "png_path": rendered.get("png_path"),
                "structure_path": rendered.get("structure_path"),
            },
        }
        return payload

    rendered = render_diga_content_sections(url=url, diga_id=diga_id)
    return {
        "diga_id": diga_id,
        "name": name,
        "url": url,
        "timestamp": scan_timestamp_for_path(detected_at),
        "source_kind": "visible_directory",
        "content_sections": rendered["content_sections"],
        "rendered_structure_metadata": {
            key: value for key, value in rendered.items() if key != "content_sections"
        },
    }


def enrich_entries_with_rendered_structure(
    entries: list[dict[str, object]],
    archive_rendered_pages: bool = False,
) -> None:
    total = len(entries)
    for index, entry in enumerate(entries, start=1):
        diga_id = str(entry.get("id") or "")
        url = str(entry.get("bfarm_directory_url") or "")
        name = str(entry.get("name") or diga_id)
        if not diga_id or not url:
            print(f"[{index}/{total}] Skipping rendered structure: missing id or URL for {name}")
            continue
        print(f"[{index}/{total}] Rendering visible structure for {name} ({diga_id})")
        try:
            if archive_rendered_pages:
                rendered = render_diga_entry(url=url, diga_id=diga_id, slug=name, save_pdf=True, save_png=True)
                structure_path = Path(str(rendered["structure_path"]))
                with structure_path.open("r", encoding="utf-8") as file:
                    payload = json.load(file)
                content_sections = payload.get("content_sections", [])
                entry["rendered_structure_metadata"] = {
                    "source_kind": "visible_directory",
                    "rendered_at": rendered.get("timestamp"),
                    "accordions_opened": rendered.get("accordions_opened"),
                    "content_section_count": len(content_sections),
                    "field_value_count": sum(
                        1 for section in content_sections if isinstance(section, dict) and section.get("content_type") == "field_value"
                    ),
                    "archive": {
                        "pdf_path": rendered.get("pdf_path"),
                        "png_path": rendered.get("png_path"),
                        "structure_path": rendered.get("structure_path"),
                    },
                }
                entry["content_sections"] = content_sections
            else:
                rendered = render_diga_content_sections(url=url, diga_id=diga_id)
                entry["content_sections"] = rendered["content_sections"]
                entry["rendered_structure_metadata"] = {
                    key: value for key, value in rendered.items() if key != "content_sections"
                }
            print(
                "    content_sections: "
                f"{len(entry.get('content_sections') or [])}, "
                f"field/value pairs: {entry.get('rendered_structure_metadata', {}).get('field_value_count', 0)}"
            )
        except Exception as exc:
            entry["content_sections"] = []
            entry["rendered_structure_metadata"] = {
                "source_kind": "visible_directory",
                "error": str(exc),
            }
            print(f"    rendered structure failed: {exc}")


def render_changed_entry_archives(
    events: list[dict[str, object]],
    entries: list[dict[str, object]],
    detected_at: str,
    archive_rendered_pages: bool = False,
) -> dict[str, dict[str, object]]:
    entries_by_id = {str(entry.get("id")): entry for entry in entries if entry.get("id")}
    targets: dict[str, dict[str, object]] = {}
    for event in events:
        if not isinstance(event, dict) or not is_notifiable_event(event):
            continue
        diga_id = str(event.get("diga_id") or "")
        if not diga_id:
            continue
        entry = entries_by_id.get(diga_id, {})
        url = str(event.get("bfarm_directory_url") or entry.get("bfarm_directory_url") or "")
        name = str(event.get("diga_name") or entry.get("name") or diga_id)
        if not url:
            print(f"Skipping render-on-change for {name}: missing BfArM URL")
            continue
        targets[diga_id] = {"id": diga_id, "name": name, "url": url}

    if not targets:
        print("Render-on-change: no real changed DiGA entries to render.")
        return {}

    timestamp = scan_timestamp_for_path(detected_at)
    rendered_entries: dict[str, dict[str, object]] = {}
    for index, target in enumerate(targets.values(), start=1):
        diga_id = str(target["id"])
        name = str(target["name"])
        url = str(target["url"])
        print(f"[{index}/{len(targets)}] Render-on-change for {name} ({diga_id})")
        try:
            result = render_diga_entry(
                url=url,
                diga_id=diga_id,
                output_root=Path("data/rendered_pages") if archive_rendered_pages else VISIBLE_RUN_DIR,
                slug=name,
                timestamp=timestamp,
                save_pdf=archive_rendered_pages,
                save_png=archive_rendered_pages,
            )
        except Exception as exc:
            print(f"    render-on-change failed: {exc}")
            continue
        structure_path = result.get("structure_path")
        content_sections = []
        if structure_path:
            structure_file = Path(str(structure_path))
            try:
                with structure_file.open("r", encoding="utf-8") as file:
                    structure_payload = json.load(file)
                loaded_sections = structure_payload.get("content_sections")
                if isinstance(loaded_sections, list):
                    content_sections = loaded_sections
            except (OSError, json.JSONDecodeError) as exc:
                print(f"    could not read rendered structure for enrichment: {exc}")
            rendered_entries[diga_id] = {
                "name": name,
                "url": url,
                "structure_path": str(structure_path),
                "content_sections": content_sections,
            }
        print(f"    structure: {structure_path}")
        if archive_rendered_pages:
            print(f"    pdf: {result.get('pdf_path')}")
            print(f"    png: {result.get('png_path')}")
    return rendered_entries


def is_lifecycle_event(event: dict[str, object]) -> bool:
    return str(event.get("change_type") or "") in PRESERVED_CHANGE_TYPES


def warn_for_unmatched_directory_metric_changes(events: list[dict[str, object]]) -> None:
    if not any(event.get("change_type") == "directory_metric_change" for event in events):
        return
    has_lifecycle_event = any(
        str(event.get("change_type") or "") in {"new_diga", "removed_diga", "status_change"}
        for event in events
    )
    if not has_lifecycle_event:
        print("Directory metric changed but no matching DiGA-level lifecycle event found.")


def event_diga_ids(events: list[dict[str, object]]) -> set[str]:
    return {str(event.get("diga_id") or "") for event in events if event.get("diga_id")}


def visible_baseline_update(
    payload: dict[str, object],
    path: Path,
    diga_id: str,
    name: str,
    detected_at: str,
    archive_existing: bool,
) -> dict[str, object]:
    return {
        "payload": payload,
        "path": path,
        "diga_id": diga_id,
        "name": name,
        "detected_at": detected_at,
        "archive_existing": archive_existing,
    }


def apply_visible_baseline_updates(updates: list[dict[str, object]]) -> None:
    for update in updates:
        payload = update.get("payload")
        path = update.get("path")
        if not isinstance(payload, dict) or not isinstance(path, Path):
            continue
        diga_id = str(update.get("diga_id") or payload.get("diga_id") or "")
        detected_at = str(update.get("detected_at") or payload.get("timestamp") or "")
        archive_existing = bool(update.get("archive_existing"))
        replace_visible_baseline(
            payload=payload,
            path=path,
            diga_id=diga_id,
            detected_at=detected_at,
            archive_existing=archive_existing,
        )
        print(f"Visible baseline latest updated: {path}")


def replace_visible_baseline(
    payload: dict[str, object],
    path: Path,
    diga_id: str,
    detected_at: str,
    archive_existing: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if archive_existing and path.exists():
        archive_visible_baseline(path, diga_id=diga_id, detected_at=detected_at)
    save_visible_baseline(payload, path)


def archive_visible_baseline(path: Path, diga_id: str, detected_at: str) -> Path | None:
    if not path.exists():
        return None
    timestamp = scan_timestamp_for_path(detected_at)
    archive_dir = VISIBLE_HISTORY_DIR / safe_key(diga_id or path.stem)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{timestamp}_structure.json"
    if archive_path.exists():
        archive_path = archive_dir / f"{timestamp}_{int(time.time() * 1000)}_structure.json"
    shutil.copy2(path, archive_path)
    print(f"Archived previous visible baseline: {archive_path}")
    return archive_path


def baseline_updates_from_rendered_entries(
    rendered_entries: dict[str, dict[str, object]],
    entries: list[dict[str, object]],
    detected_at: str,
    archive_existing: bool,
) -> list[dict[str, object]]:
    entries_by_id = {str(entry.get("id")): entry for entry in entries if entry.get("id")}
    updates: list[dict[str, object]] = []
    for diga_id, rendered in rendered_entries.items():
        entry = entries_by_id.get(diga_id, {})
        name = str(rendered.get("name") or entry.get("name") or diga_id)
        content_sections = rendered.get("content_sections")
        if not isinstance(content_sections, list):
            print(f"Lifecycle baseline skipped for {name} ({diga_id}): no rendered content_sections.")
            continue
        payload = load_rendered_structure_payload(rendered)
        if not payload:
            payload = {
                "diga_id": diga_id,
                "name": name,
                "url": rendered.get("url") or entry.get("bfarm_directory_url"),
                "timestamp": scan_timestamp_for_path(detected_at),
                "source_kind": "visible_directory",
                "content_sections": content_sections,
            }
        save_visible_baseline(payload, visible_run_structure_path(diga_id, name, detected_at))
        updates.append(
            visible_baseline_update(
                payload=payload,
                path=visible_baseline_path(diga_id, name),
                diga_id=diga_id,
                name=name,
                detected_at=detected_at,
                archive_existing=archive_existing,
            )
        )
    return updates


def build_visible_change_events_from_rendered_baselines(
    trigger_events: list[dict[str, object]],
    rendered_entries: dict[str, dict[str, object]],
    entries: list[dict[str, object]],
    detected_at: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    entries_by_id = {str(entry.get("id")): entry for entry in entries if entry.get("id")}
    trigger_events_by_id: dict[str, list[dict[str, object]]] = {}
    for event in trigger_events:
        diga_id = str(event.get("diga_id") or "")
        if diga_id:
            trigger_events_by_id.setdefault(diga_id, []).append(event)

    visible_events: list[dict[str, object]] = []
    baseline_updates: list[dict[str, object]] = []
    rendered_ids: set[str] = set()
    for diga_id, rendered in rendered_entries.items():
        rendered_ids.add(diga_id)
        content_sections = rendered.get("content_sections")
        if not isinstance(content_sections, list):
            print(f"Visible baseline skipped for {diga_id}: rendered structure has no content_sections.")
            visible_events.extend(
                legacy_fallback_events(
                    trigger_events_by_id.get(diga_id, []),
                    "rendered structure has no content_sections",
                )
            )
            continue

        entry = entries_by_id.get(diga_id, {})
        trigger_group = trigger_events_by_id.get(diga_id, [])
        name = str(rendered.get("name") or entry.get("name") or diga_id)
        baseline_path = visible_baseline_path(diga_id, name)
        current_payload = load_rendered_structure_payload(rendered)
        if not current_payload:
            current_payload = {
                "diga_id": diga_id,
                "url": rendered.get("url") or entry.get("bfarm_directory_url"),
                "timestamp": scan_timestamp_for_path(detected_at),
                "content_sections": content_sections,
            }

        previous_payload = load_json_file(baseline_path)
        save_visible_baseline(current_payload, visible_run_structure_path(diga_id, name, detected_at))
        if not previous_payload:
            print(f"Visible baseline missing for {name} ({diga_id}); preserving FHIR fallback without updating latest baseline.")
            if has_trigger_change_type(trigger_group, "new_diga"):
                visible_events.append(new_diga_baseline_event(trigger_group, entry, rendered, detected_at))
            else:
                visible_events.extend(
                    legacy_fallback_events(
                        trigger_group,
                        "visible baseline did not exist before this scan",
                    )
                )
            continue

        try:
            section_changes = diff_content_section_lists(
                previous_payload.get("content_sections", []),
                current_payload.get("content_sections", []),
            )
        except Exception as exc:
            print(f"Visible baseline diff failed for {name} ({diga_id}): {exc}")
            visible_events.extend(legacy_fallback_events(trigger_group, f"visible baseline diff failed: {exc}"))
            continue

        if not section_changes:
            print(f"Visible baseline diff for {name} ({diga_id}): no visible changes.")
            visible_events.extend(
                legacy_fallback_events(
                    trigger_group,
                    "visible baseline diff found no visible content_section changes",
                )
            )
            continue

        previous_snapshot_timestamp = timestamp_value(trigger_group, "previous_snapshot_timestamp", latest=False)
        current_snapshot_timestamp = timestamp_value(trigger_group, "current_snapshot_timestamp", latest=True)
        new_visible_events = visible_events_for_trigger_group(
            trigger_group=trigger_group,
            section_changes=section_changes,
            detected_at=detected_at,
            diga_id=diga_id,
            entry=entry,
            rendered=rendered,
            previous_snapshot_timestamp=previous_snapshot_timestamp,
            current_snapshot_timestamp=current_snapshot_timestamp,
        )
        visible_events.extend(new_visible_events)
        has_resolved_visible_event = any(
            str(event.get("change_type") or "") != "visible_diff_unresolved"
            for event in new_visible_events
        )
        if not has_resolved_visible_event:
            print(f"Visible baseline diff for {name} ({diga_id}) produced no preservable content events.")
            continue
        baseline_updates.append(
            visible_baseline_update(
                payload=current_payload,
                path=baseline_path,
                diga_id=diga_id,
                name=name,
                detected_at=detected_at,
                archive_existing=True,
            )
        )
        print(f"Visible baseline diff for {name} ({diga_id}): {len(section_changes)} visible change(s).")

    for diga_id, trigger_group in trigger_events_by_id.items():
        if diga_id in rendered_ids:
            continue
        visible_events.extend(
            legacy_fallback_events(
                trigger_group,
                "render-on-change did not produce a rendered structure",
            )
        )

    return visible_events, baseline_updates


def visible_events_for_trigger_group(
    trigger_group: list[dict[str, object]],
    section_changes: list[dict[str, object]],
    detected_at: str,
    diga_id: str,
    entry: dict[str, object],
    rendered: dict[str, object],
    previous_snapshot_timestamp: str,
    current_snapshot_timestamp: str,
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    content_triggers = [event for event in trigger_group if should_preserve_unresolved_content_event(event)]
    for index, trigger_event in enumerate(content_triggers, start=1):
        matches, match_reason = confident_section_changes_for_trigger(trigger_event, section_changes)
        if not matches:
            events.extend(
                legacy_fallback_events(
                    [trigger_event],
                    f"visible baseline diff did not match this FHIR content change: {match_reason}",
                )
            )
            continue
        event = visible_section_change_event(
            change=matches[0][2],
            index=index,
            detected_at=detected_at,
            diga_id=diga_id,
            entry=entry,
            rendered=rendered,
            previous_snapshot_timestamp=previous_snapshot_timestamp,
            current_snapshot_timestamp=current_snapshot_timestamp,
        )
        event["original_change_type"] = trigger_event.get("change_type")
        event["original_changed_field"] = trigger_event.get("changed_field") or trigger_event.get("field_name")
        event["trigger_previous_value"] = trigger_event.get("previous_value", trigger_event.get("before_value"))
        event["trigger_new_value"] = trigger_event.get("new_value", trigger_event.get("after_value"))
        event["visible_changes"] = [
            visible_change_detail(change, score)
            for score, _candidate_index, change in matches
        ]
        event["visible_match_reason"] = match_reason
        event["visible_match_count"] = len(matches)
        events.append(event)
    return events


VISIBLE_MATCH_MIN_SCORE = 0.18
VISIBLE_MATCH_CLEAR_MARGIN = 0.15
VISIBLE_MATCH_STRONG_SCORE = 0.85


def confident_section_changes_for_trigger(
    trigger_event: dict[str, object],
    section_changes: list[dict[str, object]],
) -> tuple[list[tuple[float, int, dict[str, object]]], str]:
    ranked = ranked_section_changes_for_trigger(trigger_event, section_changes)
    if not ranked:
        return [], "no visible section changes were available"

    candidates = [candidate for candidate in ranked if candidate[0] >= VISIBLE_MATCH_MIN_SCORE]
    if not candidates:
        return [], f"best score below threshold {VISIBLE_MATCH_MIN_SCORE:.2f}"

    strong_candidates = [candidate for candidate in candidates if candidate[0] >= VISIBLE_MATCH_STRONG_SCORE]
    if strong_candidates:
        return strong_candidates, (
            f"{len(strong_candidates)} visible section change(s) matched with direct content evidence"
        )

    best = candidates[0]
    if len(candidates) == 1:
        return [best], "single visible section change passed the minimum score threshold"

    second = candidates[1]
    separation = best[0] - second[0]
    # Conservative ambiguity rule:
    # A non-strong match is accepted only when the best score clears the minimum
    # threshold and is at least 0.15 higher than the second-best candidate.
    # Otherwise the visible location is treated as ambiguous and the original
    # FHIR event is preserved as visible_diff_unresolved.
    if separation >= VISIBLE_MATCH_CLEAR_MARGIN:
        return [best], (
            f"best visible section separated from second-best by {separation:.2f}"
        )
    return [], (
        "ambiguous visible section match "
        f"(best={best[0]:.2f}, second={second[0]:.2f}, required_margin={VISIBLE_MATCH_CLEAR_MARGIN:.2f})"
    )


def ranked_section_changes_for_trigger(
    trigger_event: dict[str, object],
    section_changes: list[dict[str, object]],
) -> list[tuple[float, int, dict[str, object]]]:
    ranked = [
        (score_section_change_for_trigger(trigger_event, change), index, change)
        for index, change in enumerate(section_changes)
    ]
    return sorted(ranked, key=lambda item: (-item[0], item[1]))


def best_section_change_for_trigger(
    trigger_event: dict[str, object],
    section_changes: list[dict[str, object]],
) -> dict[str, object] | None:
    matches, _reason = confident_section_changes_for_trigger(trigger_event, section_changes)
    return matches[0][2] if matches else None


def score_section_change_for_trigger(
    trigger_event: dict[str, object],
    section_change: dict[str, object],
) -> float:
    display_path = normalize_match_text(section_change.get("display_path") or "")
    change_text = normalize_match_text(
        " ".join(
            str(section_change.get(key) or "")
            for key in ("before", "after", "diff_excerpt", "display_path")
        )
    )
    trigger_text = normalize_match_text(
        " ".join(
            str(trigger_event.get(key) or "")
            for key in ("previous_value", "before_value", "new_value", "after_value")
        )
    )
    field_context = normalize_match_text(
        " ".join(
            str(trigger_event.get(key) or "")
            for key in ("display_path", "user_facing_field_label", "changed_field", "field_name")
        )
    )
    score = 0.0
    if field_context and display_path and (field_context in display_path or display_path in field_context):
        score = max(score, 0.75)

    change_type = str(trigger_event.get("change_type") or "")
    if change_type == "price_change" and any(marker in display_path for marker in ("preis", "kosten", "vergütung")):
        score = max(score, 0.8)

    for key in ("before", "after"):
        value = section_change.get(key)
        if not isinstance(value, str):
            continue
        normalized_section_value = normalize_match_text(value)
        if normalized_section_value and normalized_section_value in trigger_text:
            score = max(score, 0.9)

    for key in ("previous_value", "before_value", "new_value", "after_value"):
        value = trigger_event.get(key)
        if not isinstance(value, str):
            continue
        for snippet in split_match_windows(value):
            normalized = normalize_match_text(snippet)
            if normalized and normalized in change_text:
                score = max(score, 0.9)
            else:
                score = max(score, token_overlap(normalized, change_text))
    return score


def visible_section_change_event(
    change: dict[str, object],
    index: int,
    detected_at: str,
    diga_id: str,
    entry: dict[str, object],
    rendered: dict[str, object],
    previous_snapshot_timestamp: str,
    current_snapshot_timestamp: str,
) -> dict[str, object]:
    before = str(change.get("before") or "")
    after = str(change.get("after") or "")
    display_path = str(change.get("display_path") or "Nicht eindeutig zugeordneter Eintrag")
    content_type = str(change.get("content_type") or "")
    raw_change_type = str(change.get("change_type") or "")
    is_textual = content_type != "field_value"
    event: dict[str, object] = {
        "detected_at": detected_at,
        "diga_id": diga_id,
        "diga_name": rendered.get("name") or entry.get("name") or diga_id,
        "manufacturer": entry.get("manufacturer"),
        "bfarm_directory_url": rendered.get("url") or entry.get("bfarm_directory_url"),
        "change_type": "text_change" if is_textual else "other_field_change",
        "changed_field": f"visible_directory.{safe_key(diga_id)}.{index}",
        "field_name": f"visible_directory.{safe_key(diga_id)}.{index}",
        "previous_value": before or None,
        "new_value": after or None,
        "previous_snapshot_timestamp": previous_snapshot_timestamp,
        "current_snapshot_timestamp": current_snapshot_timestamp,
        "user_facing_field_label": display_path,
        "display_path": display_path,
        "source_kind": "visible_directory",
        "confidence": "high",
        "localization_confidence": "high",
        "content_section_change_type": raw_change_type,
        "content_section_content_type": content_type,
        "summary_de": visible_change_summary(raw_change_type, display_path),
        "snapshot_context": snapshot_context(entry),
    }
    if is_textual:
        event["word_diff"] = word_level_diff(before, after)
        event["text_change_kind"] = visible_text_change_kind(raw_change_type, before, after)
    return event


def visible_change_detail(change: dict[str, object], match_score: float) -> dict[str, object]:
    display_path = str(change.get("display_path") or "Nicht eindeutig zugeordneter Eintrag")
    return {
        "display_path": display_path,
        "field_label": str(change.get("field_label") or change.get("subsection_title") or display_path),
        "section": str(change.get("section") or change.get("section_title") or ""),
        "content_type": str(change.get("content_type") or ""),
        "change_type": str(change.get("change_type") or ""),
        "before": change.get("before"),
        "after": change.get("after"),
        "match_score": round(match_score, 3),
    }


def has_trigger_change_type(events: list[dict[str, object]], change_type: str) -> bool:
    return any(str(event.get("change_type") or "") == change_type for event in events)


def new_diga_baseline_event(
    trigger_events: list[dict[str, object]],
    entry: dict[str, object],
    rendered: dict[str, object],
    detected_at: str,
) -> dict[str, object]:
    source = next((event for event in trigger_events if event.get("change_type") == "new_diga"), {})
    event = dict(source)
    event.update(
        {
            "detected_at": detected_at,
            "diga_id": source.get("diga_id") or entry.get("id"),
            "diga_name": source.get("diga_name") or rendered.get("name") or entry.get("name"),
            "manufacturer": source.get("manufacturer") or entry.get("manufacturer"),
            "bfarm_directory_url": source.get("bfarm_directory_url")
            or rendered.get("url")
            or entry.get("bfarm_directory_url"),
            "change_type": "new_diga",
            "changed_field": "visible_directory.new_diga",
            "field_name": "visible_directory.new_diga",
            "previous_value": None,
            "new_value": "Neu im DiGA-Verzeichnis aufgenommen",
            "user_facing_field_label": "Neue DiGA im Verzeichnis",
            "display_path": "Neue DiGA im Verzeichnis",
            "source_kind": "visible_directory",
            "confidence": "high",
            "localization_confidence": "high",
            "summary_de": "Neue DiGA im Verzeichnis.",
        }
    )
    return event


def legacy_fallback_events(events: list[dict[str, object]], reason: str) -> list[dict[str, object]]:
    fallback_events = []
    for event in events:
        if not should_preserve_unresolved_content_event(event):
            continue
        fallback = dict(event)
        fallback["original_change_type"] = fallback.get("change_type")
        fallback["original_changed_field"] = fallback.get("changed_field") or fallback.get("field_name")
        fallback["change_type"] = "visible_diff_unresolved"
        fallback["source_kind"] = "visible_diff_unresolved"
        fallback["confidence"] = "visible_diff_unresolved"
        fallback["localization_confidence"] = "visible_diff_unresolved"
        fallback["display_path"] = "Änderung erkannt, sichtbarer Abschnitt nicht eindeutig zugeordnet"
        fallback["user_facing_field_label"] = "Änderung erkannt, sichtbarer Abschnitt nicht eindeutig zugeordnet"
        fallback["summary_de"] = (
            "Eine fachliche Änderung wurde erkannt, der sichtbare Abschnitt konnte aber "
            "nicht eindeutig zugeordnet werden."
        )
        fallback["fallback_reason"] = reason
        fallback_events.append(fallback)
    if fallback_events:
        diga_name = fallback_events[0].get("diga_name") or fallback_events[0].get("diga_id")
        print(f"Using legacy fallback for {diga_name}: {reason}")
    return fallback_events


def should_preserve_unresolved_content_event(event: dict[str, object]) -> bool:
    change_type = str(event.get("change_type") or "")
    if change_type in PRESERVED_CHANGE_TYPES:
        return False

    field_name = str(event.get("changed_field") or event.get("field_name") or "").lower()
    if not field_name:
        return False
    if field_name in {"change_history", "structured_text_sections", "content_sections", "rendered_structure_metadata"}:
        return False
    if field_name.startswith(("change_history.", "structured_text_sections.", "content_sections.", "rendered_structure_metadata.")):
        return False
    if field_name == "raw_public_fhir" or field_name.startswith("raw_public_fhir."):
        return False
    if field_name == "source_update_notice" or field_name.startswith("source_update_notice."):
        return False
    if any(marker in field_name for marker in ("last_updated", "updated_at", "timestamp", "checked_sources")):
        return False

    return change_type in {"text_change", "price_change", "other_field_change"}


def visible_text_change_kind(raw_change_type: str, before: str, after: str) -> str:
    if raw_change_type == "removed_section" or (before and not after):
        return "text_removed"
    if raw_change_type == "added_section" or (after and not before):
        return "text_added"
    return "text_modified"


def visible_change_summary(raw_change_type: str, display_path: str) -> str:
    if raw_change_type == "added_section":
        return f"Im Abschnitt '{display_path}' wurde sichtbarer Inhalt ergänzt."
    if raw_change_type == "removed_section":
        return f"Im Abschnitt '{display_path}' wurde sichtbarer Inhalt entfernt."
    if raw_change_type == "changed_field_value":
        return f"Im Abschnitt '{display_path}' wurde ein sichtbarer Wert geändert."
    return f"Im Abschnitt '{display_path}' wurde sichtbarer Text geändert."


def visible_baseline_path(diga_id: str, name: str) -> Path:
    return VISIBLE_BASELINE_DIR / f"{safe_key(diga_id)}_{safe_key(name)}_structure.json"


def visible_run_structure_path(diga_id: str, name: str, detected_at: str) -> Path:
    return VISIBLE_RUN_DIR / scan_timestamp_for_path(detected_at) / f"{safe_key(diga_id)}_{safe_key(name)}_structure.json"


def load_rendered_structure_payload(rendered: dict[str, object]) -> dict[str, object] | None:
    structure_path = rendered.get("structure_path")
    if not structure_path:
        return None
    return load_json_file(Path(str(structure_path)))


def load_json_file(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read JSON file {path}: {exc}")
        return None
    return payload if isinstance(payload, dict) else None


def save_visible_baseline(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    temp_path.replace(path)


def save_visible_baselines_from_entries(
    entries: list[dict[str, object]],
    detected_at: str,
    overwrite_existing: bool = False,
) -> dict[str, int]:
    stats = {"created": 0, "updated": 0, "existing": 0, "skipped": 0}
    for entry in entries:
        diga_id = str(entry.get("id") or "")
        name = str(entry.get("name") or diga_id)
        sections = entry.get("content_sections")
        if not diga_id or not isinstance(sections, list) or not sections:
            stats["skipped"] += 1
            continue

        payload: dict[str, object] = {
            "diga_id": diga_id,
            "name": name,
            "url": entry.get("bfarm_directory_url"),
            "timestamp": scan_timestamp_for_path(detected_at),
            "source_kind": "visible_directory",
            "content_sections": sections,
            "rendered_structure_metadata": entry.get("rendered_structure_metadata", {}),
        }
        run_path = visible_run_structure_path(diga_id, name, detected_at)
        baseline_path = visible_baseline_path(diga_id, name)
        save_visible_baseline(payload, run_path)
        if baseline_path.exists():
            if overwrite_existing:
                save_visible_baseline(payload, baseline_path)
                stats["updated"] += 1
                continue
            stats["existing"] += 1
            continue
        save_visible_baseline(payload, baseline_path)
        stats["created"] += 1
    return stats


def timestamp_value(events: list[dict[str, object]], key: str, latest: bool) -> str:
    values = [str(event.get(key) or "") for event in events if event.get(key)]
    if not values:
        return ""
    return max(values) if latest else min(values)


def safe_key(value: object) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").lower()).strip("-")
    return normalized or "diga"


def enrich_text_events_from_rendered_sections(
    events: list[dict[str, object]],
    rendered_entries: dict[str, dict[str, object]],
) -> int:
    enriched_count = 0
    for event in events:
        if not isinstance(event, dict) or event.get("change_type") != "text_change":
            continue
        diga_id = str(event.get("diga_id") or "")
        rendered = rendered_entries.get(diga_id) or {}
        sections = rendered.get("content_sections")
        if not isinstance(sections, list) or not sections:
            mark_legacy_fallback(event)
            continue
        match = find_best_visible_section_for_text_change(event, sections)
        if not match:
            mark_legacy_fallback(event)
            continue

        display_path = visible_section_display_path(match)
        if not display_path:
            mark_legacy_fallback(event)
            continue

        if event.get("display_path"):
            event.setdefault("legacy_display_path", event.get("display_path"))
        if event.get("user_facing_field_label"):
            event.setdefault("legacy_user_facing_field_label", event.get("user_facing_field_label"))
        event["display_path"] = display_path
        event["user_facing_field_label"] = display_path
        event["source_kind"] = "visible_directory"
        event["confidence"] = "high"
        event["localization_confidence"] = "high"
        event["content_section_stable_key"] = match.get("stable_key")
        event["content_section_title"] = match.get("title")
        event["content_section_type"] = match.get("content_type")
        enriched_count += 1
    return enriched_count


def mark_legacy_fallback(event: dict[str, object]) -> None:
    if not event.get("source_kind"):
        event["source_kind"] = "legacy_fallback"
    event["confidence"] = "legacy_fallback"
    event["localization_confidence"] = "legacy_fallback"


def find_best_visible_section_for_text_change(
    event: dict[str, object],
    sections: list[object],
) -> dict[str, object] | None:
    candidates = [section for section in sections if is_visible_content_section(section)]
    if not candidates:
        return None

    before = event_text(event, "previous_value")
    after = event_text(event, "new_value")
    snippets = event_match_snippets(event, before, after)
    if not snippets:
        return None

    best_section: dict[str, object] | None = None
    best_score = 0.0
    for section in candidates:
        score = score_visible_section(section, snippets, before, after)
        if score > best_score:
            best_score = score
            best_section = section

    return best_section if best_score >= 0.32 else None


def is_visible_content_section(section: object) -> bool:
    if not isinstance(section, dict):
        return False
    content = normalize_match_text(section.get("content") or section.get("value") or "")
    if not content:
        return False
    path = section.get("path")
    if not isinstance(path, list) or not path:
        return False
    first = str(path[0]).strip().lower()
    if first.startswith("www.") or "gebrauchsanweisung" in first or "seiteninhalt" in first:
        return False
    return True


def event_text(event: dict[str, object], key: str) -> str:
    value = event.get(key)
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def event_match_snippets(event: dict[str, object], before: str, after: str) -> list[str]:
    snippets: list[str] = []
    for token in event.get("word_diff") or []:
        if not isinstance(token, dict):
            continue
        if token.get("op") not in {"equal", "insert"}:
            continue
        text = str(token.get("text") or "").strip()
        if len(text) >= 12:
            snippets.append(text)
    if after.strip():
        snippets.extend(split_match_windows(after))
    if before.strip():
        snippets.extend(split_match_windows(before))
    unique: list[str] = []
    seen = set()
    for snippet in snippets:
        normalized = normalize_match_text(snippet)
        if len(normalized) < 12 or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(snippet)
    return unique[:12]


def split_match_windows(text: str) -> list[str]:
    normalized = " ".join(str(text).split())
    if not normalized:
        return []
    if len(normalized) <= 240:
        return [normalized]
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    windows = [sentence for sentence in sentences if len(sentence) >= 40]
    if windows:
        return windows[:6]
    return [normalized[:240], normalized[-240:]]


def score_visible_section(
    section: dict[str, object],
    snippets: list[str],
    before: str,
    after: str,
) -> float:
    section_text = normalize_match_text(section.get("content") or section.get("value") or "")
    if not section_text:
        return 0.0

    score = 0.0
    for snippet in snippets:
        normalized_snippet = normalize_match_text(snippet)
        if not normalized_snippet:
            continue
        if normalized_snippet in section_text:
            score = max(score, min(1.0, 0.72 + len(normalized_snippet) / 1000))
            continue
        overlap = token_overlap(normalized_snippet, section_text)
        score = max(score, overlap)

    after_tokens = token_overlap(normalize_match_text(after), section_text)
    before_tokens = token_overlap(normalize_match_text(before), section_text)
    score = max(score, after_tokens * 0.95, before_tokens * 0.75)
    return score


def token_overlap(left: str, right: str) -> float:
    left_tokens = meaningful_tokens(left)
    if not left_tokens:
        return 0.0
    right_tokens = meaningful_tokens(right)
    if not right_tokens:
        return 0.0
    matches = left_tokens & right_tokens
    return len(matches) / len(left_tokens)


def meaningful_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[\wäöüÄÖÜß]{4,}", text.lower()) if token}


def normalize_match_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def visible_section_display_path(section: dict[str, object]) -> str:
    path = section.get("path")
    if isinstance(path, list):
        parts = [str(part).strip() for part in path if str(part).strip()]
    else:
        parts = []
    if not parts and section.get("display_path"):
        parts = [str(section["display_path"]).strip()]
    return " > ".join(parts)


def scan_timestamp_for_path(detected_at: str) -> str:
    try:
        parsed = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_content_section_scan_dry_run_report(
    old_entries: list[dict[str, object]],
    new_entries: list[dict[str, object]],
    detected_at: str,
) -> Path | None:
    old_by_id = {str(entry.get("id")): entry for entry in old_entries if entry.get("id")}
    rows = []
    comparable_entries = 0
    for entry in new_entries:
        diga_id = str(entry.get("id") or "")
        if not diga_id:
            continue
        old_entry = old_by_id.get(diga_id)
        if not old_entry:
            continue
        old_sections = old_entry.get("content_sections")
        new_sections = entry.get("content_sections")
        if not isinstance(old_sections, list) or not isinstance(new_sections, list):
            continue
        comparable_entries += 1
        changes = diff_content_section_lists(old_sections, new_sections)
        if not changes:
            continue
        rows.append(
            {
                "diga_id": diga_id,
                "diga_name": entry.get("name"),
                "change_count": len(changes),
                "change_types": sorted({str(change.get("change_type")) for change in changes}),
                "display_paths": [str(change.get("display_path")) for change in changes],
            }
        )

    if comparable_entries == 0:
        print("No content_sections dry-run report created because previous snapshot has no content_sections.")
        return None

    output_dir = Path("outputs/content_section_dry_run")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = output_dir / f"content_section_dry_run_{timestamp}.json"
    payload = {
        "detected_at": detected_at,
        "compared_diga": comparable_entries,
        "diga_with_changes": len(rows),
        "total_content_section_changes": sum(int(row["change_count"]) for row in rows),
        "entries": rows,
    }
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    return output_path


def inspect_structure_command(args: argparse.Namespace) -> int:
    report = inspect_rendered_structure_file(args.file, output_path=args.out)
    print(report, end="")
    if args.out:
        print()
        print(f"Markdown preview written to: {args.out}")
    return 0


def diff_content_sections_command(args: argparse.Namespace) -> int:
    report = diff_content_section_files(args.before, args.after, output_path=args.out)
    print(report, end="")
    if args.out:
        print()
        print(f"Markdown diff written to: {args.out}")
    return 0


def run_simulation_command(snapshot_dir: Path, scenario: str, notify: bool = False, dry_run: bool = False) -> int:
    if notify and not dry_run:
        print("Simulation notifications are dry-run only. Add --dry-run to print the email body.")
        return 1
    try:
        events, output_path = run_simulation(scenario, notify=notify, dry_run=dry_run, snapshot_dir=snapshot_dir)
    except ValueError as exc:
        print(exc)
        return 1

    print(f"Generated simulated events: {len(events)}")
    if output_path:
        print(f"Saved simulated change events: {output_path}")
    print("Simulation report: outputs/simulation_report.md")
    return 0


def simulate_orthopy_change(snapshot_dir: Path, notify: bool = False, dry_run: bool = False) -> int:
    if notify and not dry_run:
        print("Simulation notifications are dry-run only. Add --dry-run to print the email body.")
        return 1

    baseline_path = operational_baseline_path(snapshot_dir)
    if not baseline_path.exists():
        print("No operational baseline found. Run `py -m src.main run` first.")
        return 1

    latest_real_snapshot = load_snapshot(baseline_path)
    previous_known_timestamp = latest_real_snapshot.created_at
    simulated_entries = copy.deepcopy(latest_real_snapshot.entries)
    orthopy_entry = find_orthopy_entry(simulated_entries)
    if orthopy_entry is None:
        print("Orthopy record not found in latest snapshot.")
        return 1

    field_name = choose_orthopy_simulation_field(orthopy_entry)
    original_value = str(get_nested_value(orthopy_entry, field_name) or "")
    if ORTHOPY_REMOVED_SENTENCE in original_value:
        print("Latest real Orthopy snapshot already contains the simulation sentence.")
        return 1

    set_nested_value(orthopy_entry, field_name, f"{ORTHOPY_REMOVED_SENTENCE} {original_value}".strip())
    simulated_snapshot_path = save_simulated_snapshot(
        simulated_entries,
        latest_real_snapshot.path,
        created_at=previous_known_timestamp,
    )
    simulated_snapshot = Snapshot(
        path=simulated_snapshot_path,
        created_at=previous_known_timestamp,
        entries=simulated_entries,
        directory_metrics=calculate_directory_metrics(simulated_entries, calculated_at=previous_known_timestamp),
    )

    detected_at = datetime.now(timezone.utc).isoformat()
    report = diff_snapshots(simulated_snapshot, latest_real_snapshot)
    events = build_change_events(report, simulated_snapshot, latest_real_snapshot, detected_at)
    events = [
        event
        for event in events
        if "orthopy" in str(event.get("diga_name", "")).lower()
        and event.get("field_name") == field_name
    ]
    for event in events:
        event["simulated"] = True
        event["simulation_name"] = "orthopy_removed_bfarm_assessment_sentence"
        event["change_type"] = "text_change"

    changes_path = save_change_events(events, detected_at=detected_at)
    print(f"Simulated old snapshot: {simulated_snapshot_path}")
    if changes_path:
        print(f"Saved simulated change event: {changes_path}")
    if notify:
        print()
        notify_changes(events, dry_run=True, include_simulated=True)
    print()
    print(render_report(report))
    return 0


def find_orthopy_entry(entries: list[dict[str, object]]) -> dict[str, object] | None:
    for entry in entries:
        if "orthopy" in str(entry.get("name", "")).lower():
            return entry
    return None


def choose_orthopy_simulation_field(entry: dict[str, object]) -> str:
    if isinstance(entry.get("evidence_summary_text"), str):
        return "evidence_summary_text"
    descriptive_texts = entry.get("descriptive_texts")
    if isinstance(descriptive_texts, dict):
        for key in descriptive_texts:
            if "bewertungsentscheidung" in str(key).lower():
                return f"descriptive_texts.{key}"
    return "evidence_summary_text"


def get_nested_value(entry: dict[str, object], field_path: str) -> object:
    current: object = entry
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def set_nested_value(entry: dict[str, object], field_path: str, value: object) -> None:
    parts = field_path.split(".")
    current: dict[str, object] = entry
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def save_simulated_snapshot(
    entries: list[dict[str, object]],
    real_snapshot_path: Path,
    created_at: str,
) -> Path:
    DEFAULT_SIMULATION_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = DEFAULT_SIMULATION_DIR / f"orthopy_simulated_old_{timestamp}.json"
    payload = {
        "created_at": created_at,
        "entry_count": len(entries),
        "directory_metrics": calculate_directory_metrics(entries, calculated_at=created_at),
        "simulation": True,
        "simulation_source_snapshot": str(real_snapshot_path),
        "entries": entries,
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
