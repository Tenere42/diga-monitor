"""CLI entry point for the DiGA directory change monitor."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src.change_events import build_change_events, save_change_events
from src.diff import diff_snapshots, render_report
from src.fetch_diga import fetch_diga_entries
from src.notifications import notify_changes
from src.render_directory import diff_content_section_files, inspect_rendered_structure_file, render_diga_entry
from src.scan_history import append_scan_history
from src.simulations import run_simulation
from src.snapshot import DEFAULT_SNAPSHOT_DIR, Snapshot, latest_snapshot_paths, list_snapshot_paths, load_snapshot, save_snapshot


DEFAULT_SIMULATION_DIR = Path("data/simulations")
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
    notify_test_parser = subparsers.add_parser(
        "notify-test",
        help="Send or preview a test notification email without running a DiGA scan.",
    )
    notify_test_parser.add_argument("--dry-run", action="store_true", help="Print the test email without sending it.")
    subparsers.add_parser("fetch", help="Fetch entries and print them without saving a snapshot.")
    subparsers.add_parser("diff", help="Compare the latest two saved snapshots.")
    subparsers.add_parser("snapshots", help="List saved snapshots.")
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

    if args.command == "snapshots":
        paths = list_snapshot_paths(args.snapshot_dir)
        if not paths:
            print("No snapshots found.")
            return 0
        for path in paths:
            print(path)
        return 0

    if args.command == "diff":
        return diff_latest(args.snapshot_dir)

    if args.command == "run":
        return run_monitor(args.snapshot_dir, notify=args.notify, dry_run=args.dry_run)

    if args.command == "notify-test":
        return run_notify_test(dry_run=args.dry_run)

    if args.command == "render-entry":
        return render_entry_command(args)

    if args.command in {"inspect-structure", "inspect-rendered-structure"}:
        return inspect_structure_command(args)

    if args.command == "diff-content-sections":
        return diff_content_sections_command(args)

    if args.command == "simulate":
        return run_simulation_command(args.snapshot_dir, args.scenario, notify=args.notify, dry_run=args.dry_run)

    if args.command == "simulate-orthopy-change":
        return simulate_orthopy_change(args.snapshot_dir, notify=args.notify, dry_run=args.dry_run)

    raise ValueError(f"Unsupported command: {args.command}")


def run_monitor(snapshot_dir: Path, notify: bool = False, dry_run: bool = False) -> int:
    started = time.perf_counter()
    previous_paths = latest_snapshot_paths(snapshot_dir, limit=1)
    entries = fetch_diga_entries()
    new_snapshot_path = save_snapshot(entries, snapshot_dir)
    detected_at = datetime.now(timezone.utc).isoformat()
    print(f"Saved snapshot: {new_snapshot_path}")

    if not previous_paths:
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
    report = diff_snapshots(old_snapshot, new_snapshot)
    events = []
    if report.has_changes:
        events = build_change_events(report, old_snapshot, new_snapshot, detected_at)
        changes_path = save_change_events(events, detected_at=detected_at)
        if changes_path:
            print(f"Saved change events: {changes_path}")
    print(f"Detected change events: {len(events)}")
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
    now = datetime.now(timezone.utc).isoformat()
    event = {
        "detected_at": now,
        "diga_id": "notification-test",
        "diga_name": "Test-DiGA Benachrichtigung",
        "manufacturer": "DiGA Watch Test",
        "bfarm_directory_url": "https://diga.bfarm.de/de",
        "change_type": "text_change",
        "changed_field": "evidence_summary_text",
        "field_name": "evidence_summary_text",
        "previous_value": "Bisheriger Bewertungstext mit einem entfernten Satz.",
        "new_value": "Bisheriger Bewertungstext.",
        "previous_snapshot_timestamp": now,
        "current_snapshot_timestamp": now,
        "user_facing_field_label": "Bewertungsentscheidung des BfArM",
        "summary_de": "Test: Im Abschnitt 'Bewertungsentscheidung des BfArM' wurde ein Textabschnitt entfernt.",
        "text_change_kind": "text_removed",
        "word_diff": [
            {"op": "equal", "text": "Bisheriger Bewertungstext"},
            {"op": "delete", "text": "mit einem entfernten Satz"},
            {"op": "equal", "text": "."},
        ],
    }
    print("Running notification test with one synthetic real change event.")
    notify_changes([event], dry_run=dry_run)
    return 0


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


def diff_latest(snapshot_dir: Path) -> int:
    paths = latest_snapshot_paths(snapshot_dir, limit=2)
    if len(paths) < 2:
        print("Need at least two snapshots to produce a diff report.")
        return 1

    old_snapshot = load_snapshot(paths[0])
    new_snapshot = load_snapshot(paths[1])
    print(render_report(diff_snapshots(old_snapshot, new_snapshot)))
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

    paths = latest_snapshot_paths(snapshot_dir, limit=2)
    if not paths:
        print("No real snapshot found. Run `py -m src.main run` first.")
        return 1

    latest_real_snapshot = load_snapshot(paths[-1])
    previous_known_timestamp = (
        load_snapshot(paths[-2]).created_at
        if len(paths) > 1
        else latest_real_snapshot.created_at
    )
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
