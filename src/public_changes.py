"""Public presentation semantics only; callers retain existing eligibility/dedup rules."""
from __future__ import annotations
import re
from typing import Any

CATEGORIES = {"new_diga": "NEU", "removed_diga": "ENTFERNT",
              "status_change": "AKTUALISIERT", "price_change": "AKTUALISIERT",
              "text_change": "AKTUALISIERT", "other_field_change": "AKTUALISIERT",
              "visible_diff_unresolved": "AKTUALISIERT"}
SUBJECTS = ("STATUS", "PREIS", "EVIDENZ", "ANWENDUNG", "TECHNIK", "DATENSCHUTZ", "HERSTELLER", "ANGABEN")

def normalized(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").casefold())

def is_public(event: dict) -> bool:
    identity = str(event.get("diga_id") or "").strip()
    name = str(event.get("diga_name") or "").strip()
    sentinels = {"directory", "digaverzeichnis", "unknown", "unbekanntediga", "unnamedentry"}
    return bool(normalized(identity) and normalized(name) and normalized(identity) not in sentinels
                and normalized(name) not in sentinels
                and event.get("change_type") in CATEGORIES
                and not event.get("directory_metric"))

def category(event: dict) -> str:
    return CATEGORIES[event["change_type"]]

def subject(event: dict) -> str:
    field = str(event.get("original_changed_field") or event.get("changed_field") or event.get("field_name") or "").casefold()
    kind = event.get("original_change_type") or event.get("change_type")
    # Explicit fields outrank incidental words in section headings.
    if field == "status": return "STATUS"
    if field.startswith("pricing_information") or kind == "price_change": return "PREIS"
    if field == "evidence_summary_text": return "EVIDENZ"
    if field == "indication": return "ANWENDUNG"
    if field.startswith("manufacturer"): return "HERSTELLER"
    if field in {"name", "title", "bfarm_directory_url"}: return "ANGABEN"
    context = " ".join(str(event.get(k) or "") for k in
                       ("display_path", "main_section", "section_title", "question_label", "subsection_title", "user_facing_field_label"))
    if str(event.get("localization_confidence", "")).lower() in {"low", "legacy_fallback"}:
        context = ""  # Keep trusted original fields, not speculative localization.
    manufacturer = (event.get("snapshot_context") or {}).get("manufacturer") or event.get("manufacturer")
    if context.strip() and (context.strip().casefold() == "hersteller" or
                            normalized(context) == normalized(manufacturer)):
        return "HERSTELLER"
    text = field + " " + context.casefold()
    rules = (
        ("STATUS", ("status der listung", "aufnahmestatus", "erstmalige aufnahme")),
        ("PREIS", ("preis", "kosten", "price", "vergütung", "zuschlag")),
        ("EVIDENZ", ("evidence", "bewertungsentscheidung", "studie", "studi", "versorgungseffekt", "evalu", "erprobung", "vorläufigen aufnahme", "medizinischen nutzen")),
        ("ANWENDUNG", ("indikation", "zweckbestimmung", "kontraindikation", "ausschluss", "sichere anwendung", "höchstdauer", "mindestdauer", "nutzungsdauer")),
        ("DATENSCHUTZ", ("datenschutz", "datensicherheit", "datenverarbeitung")),
        ("TECHNIK", ("version", "kompatibil", "plattform", "interoperabil", "datenimport", "datenexport", "datenportabil", "unterstützte geräte")),
        ("HERSTELLER", ("herstelleradresse", "herstellerkontakt", "herstellerwebsite", "hersteller >", "herstelleridentität")),
    )
    return next((label for label, terms in rules if any(term in text for term in terms)), "ANGABEN")

def labels(events: list[dict]) -> list[str]:
    # Daily groups may span lifecycle transitions; retain each category explicitly.
    categories = list(dict.fromkeys(category(e) for e in events))
    subjects = {subject(e) for e in events if category(e) == "AKTUALISIERT"}
    return categories + [s for s in SUBJECTS if s in subjects]

def matches(event: dict, selected: str, query: str) -> bool:
    return (selected == "Alle" or category(event).casefold() == selected.casefold()) and (
        not query.strip() or query.strip().casefold() in
        (str(event.get("diga_name", "")) + " " + str(event.get("manufacturer", ""))).casefold())
