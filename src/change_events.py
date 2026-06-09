"""Convert snapshot diffs into structured change-feed events."""

from __future__ import annotations

import difflib
import json
import re
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
            if change_type == "price_change" and not has_semantic_price_change(field.before, field.after):
                continue
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
    if isinstance(entry.get("structured_text_sections"), list):
        context = context_from_sections(entry["structured_text_sections"], field_name)
        if context:
            for key in ("source_area_label", "section_title", "subsection_title"):
                if context.get(key):
                    event[key] = context[key]
            event["user_facing_field_label"] = format_text_context_label(context)
    enrich_event(event)
    return event


def enrich_event(event: dict[str, Any]) -> None:
    apply_text_context(event)
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


def has_semantic_price_change(before_value: Any, after_value: Any) -> bool:
    before_periods = normalized_price_periods(extract_price_periods(before_value))
    after_periods = normalized_price_periods(extract_price_periods(after_value))
    if before_periods or after_periods:
        return before_periods != after_periods
    return normalize_json_value(before_value) != normalize_json_value(after_value)


def extract_price_periods(value: Any) -> list[dict[str, str | None]]:
    periods = []
    for item in ensure_list(value):
        if not isinstance(item, dict):
            continue
        period = find_period(item) or {}
        amount = first_present_value(find_price_amounts(item) + find_amounts_in_text(item))
        amount_number, currency = split_price_amount(amount)
        periods.append(
            {
                "amount_number": amount_number,
                "currency": currency,
                "start": normalize_date_sort_key(period.get("start")),
                "end": normalize_date_sort_key(period.get("end")),
            }
        )
    return periods


def normalized_price_periods(periods: list[dict[str, str | None]]) -> list[tuple[str, str, str, str]]:
    return sorted(
        (
            str(period.get("amount_number") or ""),
            str(period.get("start") or ""),
            str(period.get("end") or ""),
            str(period.get("currency") or ""),
        )
        for period in periods
    )


def ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def find_period(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for key in ("effective_period", "effectivePeriod", "period"):
            item = value.get(key)
            if isinstance(item, dict) and (item.get("start") or item.get("end")):
                return item
        for item in value.values():
            found = find_period(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_period(item)
            if found:
                return found
    return None


def find_price_amounts(value: Any) -> list[str]:
    amounts = []
    if isinstance(value, dict):
        currency = value.get("currency")
        amount = value.get("value")
        if currency and isinstance(amount, (int, float, str)) and not isinstance(amount, bool):
            amounts.append(f"{normalize_amount_for_display(amount)} {currency}")
        for item in value.values():
            amounts.extend(find_price_amounts(item))
    elif isinstance(value, list):
        for item in value:
            amounts.extend(find_price_amounts(item))
    return unique_values(amounts)


def find_amounts_in_text(value: Any) -> list[str]:
    text_values = []
    if isinstance(value, dict):
        for item in value.values():
            text_values.extend(find_amounts_in_text(item))
    elif isinstance(value, list):
        for item in value:
            text_values.extend(find_amounts_in_text(item))
    elif isinstance(value, str):
        for amount, currency in re.findall(r"(\d+(?:[.,]\d{1,2})?)\s*(€|EUR)", value, flags=re.IGNORECASE):
            text_values.append(f"{normalize_amount_for_display(amount)} {'EUR' if currency.upper() == 'EUR' else currency}")
    return unique_values(text_values)


def split_price_amount(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*([A-Z]{3}|€)", value, flags=re.IGNORECASE)
    if not match:
        return normalize_amount_for_sort(value), None
    amount, currency = match.groups()
    normalized_currency = "EUR" if currency == "€" or currency.upper() == "EUR" else currency.upper()
    return normalize_amount_for_sort(amount), normalized_currency


def normalize_amount_for_display(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0"):
        return text[:-2]
    return text.replace(",", ".")


def normalize_amount_for_sort(value: Any) -> str:
    text = str(value).strip().replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return text.lower()
    return f"{number:.6f}"


def normalize_date_sort_key(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else text


def first_present_value(values: list[str]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def unique_values(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def normalize_json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def apply_text_context(event: dict[str, Any]) -> None:
    field_name = str(event.get("changed_field") or event.get("field_name") or "")
    if not field_name.startswith("descriptive_texts."):
        return

    context = find_structured_text_context(event, field_name) or infer_text_context_from_field(field_name)
    if not context:
        return

    for key in ("source_area_label", "section_title", "subsection_title"):
        if context.get(key):
            event[key] = context[key]
    event["user_facing_field_label"] = format_text_context_label(context)


def find_structured_text_context(event: dict[str, Any], field_name: str) -> dict[str, str] | None:
    for value_key in ("new_value", "after_value", "previous_value", "before_value"):
        value = event.get(value_key)
        if isinstance(value, dict) and isinstance(value.get("structured_text_sections"), list):
            context = context_from_sections(value["structured_text_sections"], field_name)
            if context:
                return context
    return None


def context_from_sections(sections: list[Any], field_name: str) -> dict[str, str] | None:
    for section in sections:
        if isinstance(section, dict) and section.get("field_path") == field_name:
            return {key: str(section[key]) for key in ("source_area_label", "section_title", "subsection_title") if section.get(key)}
    return None


def infer_text_context_from_field(field_name: str) -> dict[str, str] | None:
    if not field_name.startswith("descriptive_texts."):
        return None
    raw_label = field_name.removeprefix("descriptive_texts.")
    if raw_label.startswith("questionnaire."):
        raw_label = raw_label.removeprefix("questionnaire.")
    label = raw_label.split(".", 1)[-1].replace("_", " ")
    section_title = infer_section_title(label)
    return {
        "source_area_label": section_title,
        "section_title": section_title,
        "subsection_title": label,
    }


def infer_section_title(label: str) -> str:
    normalized = label.lower()
    if any(
        marker in normalized
        for marker in (
            "versorgungseffekt",
            "nachweis",
            "pico",
            "studie",
            "studiendesign",
            "erprobungszeitraum",
            "medizinischer nutzen",
            "patientenrelevante struktur",
        )
    ):
        return "Informationen zum positiven Versorgungseffekt"
    if any(marker in normalized for marker in ("datenschutz", "datensicherheit", "datenverarbeitung")):
        return "Informationen zu Datenschutz und Datensicherheit"
    if any(marker in normalized for marker in ("zweckbestimmung", "zielsetzung", "wirkungsweise", "inhalt", "nutzung")):
        return "Weitere Informationen zur digitalen Gesundheitsanwendung"
    if any(marker in normalized for marker in ("preis", "kosten", "vergütung")):
        return "Weitere Informationen"
    return "Beschreibung der DiGA"


def format_text_context_label(context: dict[str, str]) -> str:
    parts = []
    section_title = context.get("section_title") or context.get("source_area_label")
    subsection_title = context.get("subsection_title")
    if section_title:
        parts.append(section_title)
    if subsection_title and subsection_title not in parts:
        parts.append(subsection_title)
    return " > ".join(parts) if parts else "Beschreibung der DiGA"


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
