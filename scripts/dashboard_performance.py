"""Reproducible dashboard data-path benchmark (no Streamlit server required)."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Callable

import app
from src.change_events import DEFAULT_CHANGES_DIR, load_change_events
from src.dashboard_cache import change_files_signature, scan_history_signature
from src.scan_history import DEFAULT_SCAN_HISTORY_PATH, load_scan_history


SIZE_KEYS = ("snapshot_context", "structured_text_sections", "descriptive_texts", "word_diff")


def elapsed_ms(call: Callable[[], Any], repeats: int) -> tuple[Any, list[float]]:
    timings = []
    value = None
    for _ in range(repeats):
        started = time.perf_counter()
        value = call()
        timings.append((time.perf_counter() - started) * 1000)
    return value, timings


def median(timings: list[float]) -> float:
    return round(statistics.median(timings), 3)


def encoded_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def nested_key_sizes(value: Any, totals: dict[str, int]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in totals:
                totals[key] += encoded_size(item)
            nested_key_sizes(item, totals)
    elif isinstance(value, list):
        for item in value:
            nested_key_sizes(item, totals)


def largest_files(paths: list[Path]) -> list[dict[str, Any]]:
    result = []
    for path in sorted(paths, key=lambda item: item.stat().st_size, reverse=True)[:10]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        totals = {key: 0 for key in SIZE_KEYS}
        nested_key_sizes(payload, totals)
        result.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "events": len(payload.get("events", [])),
                **totals,
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    files = sorted(DEFAULT_CHANGES_DIR.glob("changes_*.json"))

    events, load_times = elapsed_ms(lambda: load_change_events(DEFAULT_CHANGES_DIR), args.repeats)
    history, history_times = elapsed_ms(lambda: load_scan_history(DEFAULT_SCAN_HISTORY_PATH), args.repeats)

    def prepare() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        ordered = sorted(events, key=lambda event: event.get("detected_at", ""), reverse=True)
        return ordered, [event for event in ordered if app.is_real_change_event(event)]

    (_ordered, real_events), transform_times = elapsed_ms(prepare, args.repeats)
    groups, group_times = elapsed_ms(lambda: app.group_events_by_diga(real_events), args.repeats)

    def uncached_rerun() -> list[dict[str, Any]]:
        loaded = load_change_events(DEFAULT_CHANGES_DIR)
        ordered = sorted(loaded, key=lambda event: event.get("detected_at", ""), reverse=True)
        prepared = [event for event in ordered if app.is_real_change_event(event)]
        load_scan_history(DEFAULT_SCAN_HISTORY_PATH)
        return app.group_events_by_diga(prepared)

    _uncached_groups, uncached_rerun_times = elapsed_ms(uncached_rerun, args.repeats)
    signatures, signature_times = elapsed_ms(
        lambda: (
            change_files_signature(DEFAULT_CHANGES_DIR),
            scan_history_signature(DEFAULT_SCAN_HISTORY_PATH),
        ),
        args.repeats,
    )

    app.load_dashboard_data.clear()
    cold_started = time.perf_counter()
    app.load_dashboard_data(
        str(DEFAULT_CHANGES_DIR), signatures[0], str(DEFAULT_SCAN_HISTORY_PATH), signatures[1]
    )
    cached_cold_ms = (time.perf_counter() - cold_started) * 1000
    _cached, cache_hit_times = elapsed_ms(
        lambda: app.load_dashboard_data(
            str(DEFAULT_CHANGES_DIR), signatures[0], str(DEFAULT_SCAN_HISTORY_PATH), signatures[1]
        ),
        args.repeats,
    )

    def cached_rerun() -> list[dict[str, Any]]:
        change_signature = change_files_signature(DEFAULT_CHANGES_DIR)
        history_signature = scan_history_signature(DEFAULT_SCAN_HISTORY_PATH)
        prepared_events, _history = app.load_dashboard_data(
            str(DEFAULT_CHANGES_DIR),
            change_signature,
            str(DEFAULT_SCAN_HISTORY_PATH),
            history_signature,
        )
        return app.group_events_by_diga(prepared_events)

    _rerun_groups, cached_rerun_times = elapsed_ms(cached_rerun, args.repeats)

    print(
        json.dumps(
            {
                "change_files": len(files),
                "change_bytes": sum(path.stat().st_size for path in files),
                "events": len(events),
                "real_events": len(real_events),
                "groups": len(groups),
                "render_events": sum(len(group["events"]) for group in groups),
                "scan_history_entries": len(history),
                "median_ms": {
                    "load_change_events": median(load_times),
                    "load_scan_history": median(history_times),
                    "sort_and_real_filter": median(transform_times),
                    "group_events_by_diga": median(group_times),
                    "uncached_rerun_end_to_end": median(uncached_rerun_times),
                    "content_signatures": median(signature_times),
                    "cached_prepare_cold": round(cached_cold_ms, 3),
                    "cached_prepare_hit": median(cache_hit_times),
                    "cached_rerun_end_to_end": median(cached_rerun_times),
                },
                "largest_files": largest_files(files),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
