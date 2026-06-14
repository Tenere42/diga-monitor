"""Diff DiGA snapshots and render readable reports."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from typing import Any

from src.snapshot import Snapshot


IDENTITY_KEYS = ("id", "identifier", "url", "name", "title")
IGNORED_FIELD_PATHS = {"structured_text_sections", "content_sections", "rendered_structure_metadata"}
IGNORED_FIELD_PREFIXES = ("raw_public_fhir",)


@dataclass
class ChangedField:
    field_path: str
    before: Any
    after: Any
    text_diff: list[str] = field(default_factory=list)


@dataclass
class ChangedEntry:
    entry_id: str
    before_name: str
    after_name: str
    fields: list[ChangedField]


@dataclass
class DiffReport:
    old_snapshot: str
    new_snapshot: str
    added: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    changed: list[ChangedEntry]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def diff_snapshots(old_snapshot: Snapshot, new_snapshot: Snapshot) -> DiffReport:
    old_entries = index_entries(old_snapshot.entries)
    new_entries = index_entries(new_snapshot.entries)

    added_ids = sorted(set(new_entries) - set(old_entries))
    removed_ids = sorted(set(old_entries) - set(new_entries))
    common_ids = sorted(set(old_entries) & set(new_entries))

    changed = []
    for entry_id in common_ids:
        changed_fields = diff_values(old_entries[entry_id], new_entries[entry_id])
        if changed_fields:
            changed.append(
                ChangedEntry(
                    entry_id=entry_id,
                    before_name=display_name(old_entries[entry_id]),
                    after_name=display_name(new_entries[entry_id]),
                    fields=changed_fields,
                )
            )

    return DiffReport(
        old_snapshot=str(old_snapshot.path),
        new_snapshot=str(new_snapshot.path),
        added=[new_entries[entry_id] for entry_id in added_ids],
        removed=[old_entries[entry_id] for entry_id in removed_ids],
        changed=changed,
    )


def index_entries(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed = {}
    for position, entry in enumerate(entries):
        entry_id = entry_identity(entry, fallback=f"position-{position}")
        indexed[entry_id] = entry
    return indexed


def entry_identity(entry: dict[str, Any], fallback: str) -> str:
    for key in IDENTITY_KEYS:
        value = entry.get(key)
        if value:
            return str(value)
    return fallback


def display_name(entry: dict[str, Any]) -> str:
    for key in ("name", "title", "id", "identifier"):
        value = entry.get(key)
        if value:
            return str(value)
    return "Unnamed entry"


def diff_values(before: Any, after: Any, path: str = "") -> list[ChangedField]:
    if is_ignored_field_path(path):
        return []

    if before == after:
        return []

    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(set(before) | set(after)):
            child_path = join_path(path, key)
            if is_ignored_field_path(child_path):
                continue
            if key not in before:
                changes.append(ChangedField(child_path, None, after[key]))
            elif key not in after:
                changes.append(ChangedField(child_path, before[key], None))
            else:
                changes.extend(diff_values(before[key], after[key], child_path))
        return changes

    if isinstance(before, list) and isinstance(after, list):
        if before == after:
            return []
        return [
            ChangedField(
                field_path=path or "<root>",
                before=before,
                after=after,
                text_diff=unified_json_diff(before, after),
            )
        ]

    text_diff = []
    if isinstance(before, str) and isinstance(after, str):
        text_diff = unified_text_diff(before, after)

    return [ChangedField(path or "<root>", before, after, text_diff)]


def is_ignored_field_path(path: str) -> bool:
    if path in IGNORED_FIELD_PATHS:
        return True
    return any(path == prefix or path.startswith(f"{prefix}.") for prefix in IGNORED_FIELD_PREFIXES)


def join_path(parent: str, child: str) -> str:
    if not parent:
        return child
    return f"{parent}.{child}"


def unified_text_diff(before: str, after: str) -> list[str]:
    before_lines = before.splitlines() or [before]
    after_lines = after.splitlines() or [after]
    line_diff = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )
    if max(len(before), len(after)) < 120:
        return line_diff

    word_diff = list(difflib.ndiff(before.split(), after.split()))
    changed_words = [
        line for line in word_diff if line.startswith("- ") or line.startswith("+ ")
    ]
    if not changed_words:
        return line_diff

    return line_diff + ["", "Word-level text changes:"] + changed_words


def unified_json_diff(before: Any, after: Any) -> list[str]:
    before_lines = json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    after_lines = json.dumps(after, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    return list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )


def render_report(report: DiffReport) -> str:
    lines = [
        "DiGA directory diff report",
        f"Old snapshot: {report.old_snapshot}",
        f"New snapshot: {report.new_snapshot}",
        "",
    ]

    if not report.has_changes:
        lines.append("No changes detected.")
        return "\n".join(lines)

    lines.extend(render_added(report.added))
    lines.extend(render_removed(report.removed))
    lines.extend(render_changed(report.changed))
    return "\n".join(lines).rstrip()


def render_added(entries: list[dict[str, Any]]) -> list[str]:
    if not entries:
        return []
    lines = [f"New entries ({len(entries)}):"]
    for entry in entries:
        lines.append(f"  + {display_name(entry)} [{entry_identity(entry, 'unknown')}]")
    lines.append("")
    return lines


def render_removed(entries: list[dict[str, Any]]) -> list[str]:
    if not entries:
        return []
    lines = [f"Removed entries ({len(entries)}):"]
    for entry in entries:
        lines.append(f"  - {display_name(entry)} [{entry_identity(entry, 'unknown')}]")
    lines.append("")
    return lines


def render_changed(entries: list[ChangedEntry]) -> list[str]:
    if not entries:
        return []

    lines = [f"Changed entries ({len(entries)}):"]
    for entry in entries:
        name = (
            entry.after_name
            if entry.after_name == entry.before_name
            else f"{entry.before_name} -> {entry.after_name}"
        )
        lines.append(f"  * {name} [{entry.entry_id}]")
        for field_change in entry.fields:
            lines.append(f"    Field: {field_change.field_path}")
            if field_change.text_diff:
                for diff_line in field_change.text_diff:
                    lines.append(f"      {diff_line}")
            else:
                lines.append(f"      Before: {format_value(field_change.before)}")
                lines.append(f"      After:  {format_value(field_change.after)}")
        lines.append("")
    return lines


def format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return repr(value)
