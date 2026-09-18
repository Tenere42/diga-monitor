"""Concise shared email presentation. No transport, credentials or subscriber data."""
from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
from string import Template

from src.change_links import PUBLIC_URL, change_url, diga_key, local_event_date, page_url, safe_web_url
from src.change_events import (has_semantic_price_change,
    is_misclassified_steckbrief_evidence_change, is_reclassified_evidence_description_change)
from src.public_changes import is_public

HEADLINE = "Es gibt Updates im DiGA Verzeichnis"
UNSUBSCRIBE = "{{ unsubscribe }}"
TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "change-notification.html"


@dataclass(frozen=True)
class EmailItem:
    name: str
    label: str
    url: str


def public_name(value) -> str:
    # Prevent provider template expressions as well as newlines in text output.
    return " ".join(str(value or "Unbekannte DiGA").split()).replace("{", "｛").replace("}", "｝")


def event_label(event: dict) -> str:
    kind = event.get("change_type")
    before = event.get("previous_value", event.get("before_value"))
    after = event.get("new_value", event.get("after_value"))
    if kind == "status_change":
        if before == "removed" and after in ("provisional", "permanent", "listed"):
            return "Wieder aufgenommen"
        if after in ("permanent", "listed"):
            return "Dauerhaft aufgenommen"
        if after == "removed":
            return "Aus dem Verzeichnis entfernt"
        return "Statusänderung"
    return {"new_diga": "Neue DiGA", "removed_diga": "Aus dem Verzeichnis entfernt",
            "price_change": "Preisänderung"}.get(kind, "Aktualisierung")


def email_items(events: list[dict], base: str = PUBLIC_URL) -> list[EmailItem]:
    groups = {}
    for event in events:
        # Aggregate-only diagnostics have no individual DiGA destination.
        if event.get("directory_metric") or event.get("change_type") == "directory_metric_change":
            continue
        if not event.get("diga_id") and not event.get("diga_name"):
            continue
        if event.get('diga_id') and not is_public({**event, 'change_type': 'other_field_change'}):
            continue
        field = str(event.get('changed_field') or event.get('field_name') or '').lower()
        if (event.get('source_kind') != 'visible_directory'
                and re.search(r'\bdescriptive_texts\.questionnaire\.\d+\b', field)):
            continue
        if field.startswith(('source_update_notice', 'raw_public_fhir')) or any(
                term in field for term in ('last_updated', 'updated_at', 'timestamp', 'checked_sources')):
            continue
        before = event.get('previous_value', event.get('before_value'))
        after = event.get('new_value', event.get('after_value'))
        if is_misclassified_steckbrief_evidence_change(field, before, after) or is_reclassified_evidence_description_change(
                field, before, after, event.get('snapshot_context') or {}):
            continue
        if display_value(before) == display_value(after):
            continue
        if event.get('change_type') == 'price_change' and not has_semantic_price_change(before, after):
            continue
        day = local_event_date(event)
        if day is None:
            continue  # No public daily record can be addressed reliably.
        key = (diga_key(event), day)
        groups.setdefault(key, []).append(event)
    items = []
    for rows in groups.values():
        labels = {event_label(row) for row in rows}
        # Mixed lifecycle directions must never imply a single invented outcome.
        label = next(iter(labels)) if len(labels) == 1 else "Aktualisierung"
        items.append(EmailItem(public_name(rows[0].get("diga_name")), label, change_url(rows[0], base)))
    return items


def display_value(value) -> str:
    """Match the dashboard's order-insensitive display comparison."""
    if isinstance(value, list):
        return '\n'.join(sorted(display_value(item) for item in value))
    if isinstance(value, dict):
        return '\n'.join(f'{key}:{display_value(item)}' for key,item in sorted(value.items()) if item is not None)
    return ' '.join(str(value).split())


def intro(count: int) -> str:
    change = "1 Änderung" if count == 1 else f"{count} Änderungen"
    return f"Wir haben {change} erkannt. Sieh dir die Updates direkt im DiGA Tracker an."


def render_html(events: list[dict], base: str = PUBLIC_URL, *, unsubscribe: bool = False,
                impressum_url: str = "", test_mode: bool = False) -> str:
    items = email_items(events, base)
    cards = []
    for item in items:
        cards.append(f'''<tr><td style="padding:28px 0;border-top:1px solid #e5e5e5;word-wrap:break-word;overflow-wrap:anywhere;">
<h2 style="margin:0 0 8px;font-size:21px;line-height:29px;color:#111111;">{escape(item.name)}</h2>
<p style="margin:0 0 20px;font-size:15px;line-height:23px;color:#555555;">{escape(item.label)}</p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>
<td align="center" bgcolor="#111111" style="background-color:#111111;border-radius:5px;mso-padding-alt:16px 20px;">
<a href="{escape(item.url, quote=True)}" style="display:block;padding:16px 20px;border:1px solid #111111;border-radius:5px;font-size:16px;line-height:24px;font-weight:bold;text-decoration:none;color:#ffffff;"><span style="color:#ffffff;">Änderung ansehen →</span></a>
</td></tr></table></td></tr>''')
    legal = ''
    if impressum_url:
        legal += f'<a href="{escape(safe_web_url(impressum_url), quote=True)}" style="color:#555555;">Impressum</a> &nbsp;·&nbsp; '
    elif unsubscribe:
        raise ValueError("Subscriber email requires a configured Impressum URL")
    legal += f'<a href="{escape(page_url(base, view="datenschutz"), quote=True)}" style="color:#555555;">Datenschutz</a>'
    if unsubscribe:
        legal += f'<br><br><a href="{UNSUBSCRIBE}" style="color:#555555;">Abmelden</a>'
    return Template(TEMPLATE.read_text(encoding="utf-8")).substitute(
        headline=HEADLINE, intro=intro(len(items)), cards="".join(cards), legal=legal,
        home=escape(page_url(base), quote=True),
        test_notice='<p style="font-weight:bold;">TEST / SIMULATION — Keine echte BfArM-Änderung.</p>' if test_mode else '')


def render_text(events: list[dict], base: str = PUBLIC_URL, *, unsubscribe: bool = False,
                impressum_url: str = "", test_mode: bool = False) -> str:
    items = email_items(events, base)
    lines = [HEADLINE, "", intro(len(items)), ""]
    if test_mode:
        lines[0:0] = ["TEST / SIMULATION — Keine echte BfArM-Änderung.", ""]
    for item in items:
        lines.extend([item.name, item.label, f"Änderung ansehen → {item.url}", ""])
    lines.extend(["DiGA Tracker", "www.diga-tracker.de"])
    if impressum_url:
        lines.append("Impressum: " + safe_web_url(impressum_url))
    elif unsubscribe:
        raise ValueError("Subscriber email requires a configured Impressum URL")
    lines.append("Datenschutz: " + page_url(base, view="datenschutz"))
    if unsubscribe:
        lines.append("Abmelden: " + UNSUBSCRIBE)
    return "\n".join(lines)
