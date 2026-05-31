"""Convert snapshot diffs into structured change-feed events."""

from __future__ import annotations

import difflib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.diff import DiffReport, display_name, entry_identity, index_entries
from src.snapshot import Snapshot


DEFAULT_CHANGES_DIR = Path("outputs/changes")

FIELD_LABELS = {
    "evidence_summary_text": "Bewertungsentscheidung des BfArM",
    "descriptive_texts": "Beschreibung der DiGA",
    "pricing_information": "Vergütung / Preisangaben",
    "source_update_notice": "Aktualisierungshinweis im DiGA-Verzeichnis",
    "status": "Aufnahmestatus",
    "indication": "Anwendungsgebiet / Indikation",
    "manufacturer": "Hersteller",
    "name": "Name der DiGA",
    "bfarm_directory_url": "BfArM-Verzeichniseintrag",
}


def build_change_events(
    report: DiffReport,
    old_snapshot: Snapshot,
    new_snapshot: Snapshot,
    detected_at: str | None = None,
) -> list[dict[str, Any]]:
    detected_at = detected_at or datetime.now(timezone.utc).isoformat()
    previous_snapshot_timestamp = old_snapshot.created_at
    current_snapshot_timestamp = new_snapshot.created_at
    old_entries = index_entries(old_snapshot.entries)
    new_entries = index_entries(new_snapshot.entries)
    events = []

    for entry in report.added:
        events.append(
            base_event(
                detected_at=detected_at,
                change_type="new_diga",
                field_name="<entry>",
                before_value=None,
                after_value=entry_summary(entry),
                entry=entry,
                previous_snapshot_timestamp=previous_snapshot_timestamp,
                current_snapshot_timestamp=current_snapshot_timestamp,
            )
        )

    for entry in report.removed:
        events.append(
            base_event(
                detected_at=detected_at,
                change_type="removed_diga",
                field_name="<entry>",
                before_value=entry_summary(entry),
                after_value=None,
                entry=entry,
                previous_snapshot_timestamp=previous_snapshot_timestamp,
                current_snapshot_timestamp=current_snapshot_timestamp,
            )
        )

    for changed_entry in report.changed:
        entry = new_entries.get(changed_entry.entry_id) or old_entries.get(changed_entry.entry_id) or {}
        for field in changed_entry.fields:
            change_type = classify_change(field.field_path, field.before, field.after)
            event = base_event(
                detected_at=detected_at,
                change_type=change_type,
                field_name=field.field_path,
                before_value=field.before,
                after_value=field.after,
                entry=entry,
                previous_snapshot_timestamp=previous_snapshot_timestamp,
                current_snapshot_timestamp=current_snapshot_timestamp,
            )
            if change_type == "text_change" and isinstance(field.before, str) and isinstance(field.after, str):
                event["word_diff"] = word_level_diff(field.before, field.after)
            enrich_event(event)
            events.append(event)

    return events


def base_event(
    detected_at: str,
    change_type: str,
    field_name: str,
    before_value: Any,
    after_value: Any,
    entry: dict[str, Any],
    previous_snapshot_timestamp: str,
    current_snapshot_timestamp: str,
) -> dict[str, Any]:
    event = {
        "detected_at": detected_at,
        "diga_id": entry_identity(entry, "unknown"),
        "diga_name": display_name(entry),
        "manufacturer": entry.get("manufacturer"),
        "bfarm_directory_url": entry.get("bfarm_directory_url"),
        "change_type": change_type,
        "changed_field": field_name,
        "previous_value": before_value,
        "new_value": after_value,
        "previous_snapshot_timestamp": previous_snapshot_timestamp,
        "current_snapshot_timestamp": current_snapshot_timestamp,
        "field_name": field_name,
        "before_value": before_value,
        "after_value": after_value,
    }
    enrich_event(event)
    return event


def enrich_event(event: dict[str, Any]) -> None:
    event["user_facing_field_label"] = event.get("user_facing_field_label") or field_label(str(event.get("changed_field") or event.get("field_name") or ""))
    if event.get("change_type") == "text_change":
        event["text_change_kind"] = classify_text_change(event.get("word_diff") or [])
    event["summary_de"] = build_summary(event)


def entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry_identity(entry, "unknown"),
        "name": display_name(entry),
        "manufacturer": entry.get("manufacturer"),
        "status": entry.get("status"),
        "bfarm_directory_url": entry.get("bfarm_directory_url"),
    }


def classify_change(field_name: str, before_value: Any, after_value: Any) -> str:
    field_lower = field_name.lower()
    if field_name == "status":
        return "status_change"
    if "price" in field_lower or "pricing_information" in field_lower or "preis" in field_lower:
        return "price_change"
    if isinstance(before_value, str) and isinstance(after_value, str):
        return "text_change"
    return "other_field_change"


def classify_text_change(tokens: list[dict[str, str]]) -> str:
    deleted = [token for token in tokens if token.get("op") == "delete"]
    inserted = [token for token in tokens if token.get("op") == "insert"]
    if deleted and not inserted:
        return "text_removed"
    if inserted and not deleted:
        return "text_added"
    if deleted and inserted:
        delete_groups = count_change_groups(tokens, "delete")
        insert_groups = count_change_groups(tokens, "insert")
        if delete_groups == 1 and insert_groups == 1:
            deleted_text = normalize_changed_text(deleted)
            inserted_text = normalize_changed_text(inserted)
            if deleted_text and inserted_text:
                if deleted_text in inserted_text:
                    return "text_added"
                if inserted_text in deleted_text:
                    return "text_removed"
            return "text_replaced" if looks_like_sentence(deleted) and looks_like_sentence(inserted) else "text_modified"
        return "mixed_text_change"
    return "text_modified"


def count_change_groups(tokens: list[dict[str, str]], op: str) -> int:
    groups = 0
    previous = None
    for token in tokens:
        current = token.get("op")
        if current == op and previous != op:
            groups += 1
        previous = current
    return groups


def looks_like_sentence(tokens: list[dict[str, str]]) -> bool:
    text = " ".join(token.get("text", "") for token in tokens).strip()
    return len(text.split()) >= 4 and text.endswith((".", "!", "?"))


def normalize_changed_text(tokens: list[dict[str, str]]) -> str:
    text = " ".join(token.get("text", "") for token in tokens).strip().lower()
    return text.replace(".", "").replace(",", "").replace(";", "").replace(":", "")


def build_summary(event: dict[str, Any]) -> str:
    label = str(event.get("user_facing_field_label") or "Unbekannter Bereich")
    change_type = event.get("change_type")
    before = event.get("previous_value", event.get("before_value"))
    after = event.get("new_value", event.get("after_value"))
    if change_type == "text_change":
        kind = event.get("text_change_kind")
        if kind == "text_removed":
            return f"Im Abschnitt '{label}' wurde ein Textabschnitt entfernt."
        if kind == "text_added":
            return f"Im Abschnitt '{label}' wurde Text ergänzt."
        if kind == "text_replaced":
            return f"Die Formulierung im Abschnitt '{label}' wurde angepasst."
        if kind == "text_modified":
            return f"Die Formulierung im Abschnitt '{label}' wurde angepasst."
        return f"Im Abschnitt '{label}' wurde Text geändert."
    if change_type == "price_change":
        return f"Die Preisangabe wurde von {format_summary_value(before)} auf {format_summary_value(after)} geändert."
    if change_type == "status_change":
        return f"Der Aufnahmestatus wurde von '{format_summary_value(before)}' auf '{format_summary_value(after)}' geändert."
    if change_type == "new_diga":
        return "Eine neue DiGA wurde in das Verzeichnis aufgenommen."
    if change_type == "removed_diga":
        return "Eine DiGA ist im aktuellen Verzeichnis nicht mehr vorhanden."
    return f"Im Abschnitt '{label}' wurde ein Wert geändert."


def format_summary_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def field_label(field_name: str) -> str:
    root = field_name.split(".", 1)[0]
    return FIELD_LABELS.get(field_name) or FIELD_LABELS.get(root) or root or "Unbekannter Bereich"


def word_level_diff(before: str, after: str) -> list[dict[str, str]]:
    diff = difflib.ndiff(before.split(), after.split())
    tokens = []
    for token in diff:
        marker = token[:2]
        text = token[2:]
        if marker == "  ":
            tokens.append({"op": "equal", "text": text})
        elif marker == "- ":
            tokens.append({"op": "delete", "text": text})
        elif marker == "+ ":
            tokens.append({"op": "insert", "text": text})
    return tokens


def save_change_events(
    events: list[dict[str, Any]],
    changes_dir: Path = DEFAULT_CHANGES_DIR,
    detected_at: str | None = None,
) -> Path | None:
    if not events:
        return None

    changes_dir.mkdir(parents=True, exist_ok=True)
    detected_at = detected_at or events[0]["detected_at"]
    timestamp = safe_timestamp(detected_at)
    output_path = changes_dir / f"changes_{timestamp}.json"
    payload = {
        "created_at": detected_at,
        "event_count": len(events),
        "events": events,
    }
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    return output_path


def safe_timestamp(value: str) -> str:
    return (
        value.replace(":", "")
        .replace("-", "")
        .replace(".", "")
        .replace("+", "")
        .replace("Z", "")
    )


def load_change_events(changes_dir: Path = DEFAULT_CHANGES_DIR) -> list[dict[str, Any]]:
    events = []
    if not changes_dir.exists():
        return events
    for path in sorted(changes_dir.glob("changes_*.json")):
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        for event in payload.get("events", []):
            if isinstance(event, dict):
                event["_source_file"] = str(path)
                events.append(event)
    return events
