"""SMTP email notifications for DiGA change events."""

from __future__ import annotations

import json
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any


DEFAULT_NOTIFICATION_LOG_PATH = Path("outputs/notification_log.json")

CHANGE_LABELS = {
    "new_diga": "Neue DiGA",
    "removed_diga": "Nicht mehr gefunden",
    "status_change": "Statusänderung",
    "text_change": "Textänderung",
    "price_change": "Preisänderung",
    "other_field_change": "Sonstige Feldänderung",
}

FIELD_LABELS = {
    "evidence_summary_text": "Bewertungsentscheidung des BfArM",
    "descriptive_texts": "Beschreibung der DiGA",
    "pricing_information": "Vergütung / Preisangaben",
    "source_update_notice": "Aktualisierungshinweis im DiGA-Verzeichnis",
    "status": "Aufnahmestatus",
    "indication": "Anwendungsgebiet / Indikation",
    "manufacturer": "Hersteller",
}


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    email_from: str
    email_to: str
    dashboard_url: str


def notify_changes(
    events: list[dict[str, Any]],
    dry_run: bool = False,
    include_simulated: bool = False,
) -> bool:
    real_events = [
        event
        for event in events
        if is_notifiable_event(event, include_simulated=include_simulated)
    ]
    recipient = os.getenv("EMAIL_TO", "")

    if not real_events:
        log_notification(
            recipient=recipient,
            number_of_changes=0,
            subject="DiGA Watch: 0 Änderung(en) erkannt",
            status="skipped",
            error_message="Keine echten Änderungen erkannt.",
        )
        print("No real changes detected. Email notification skipped.")
        return False

    subject = f"DiGA Watch: {len(real_events)} Änderung(en) erkannt"
    body = build_email_body(real_events, os.getenv("DASHBOARD_URL", ""))

    if dry_run:
        print("Dry-run: email would be sent with this content:")
        print()
        print(f"To: {recipient or '(EMAIL_TO nicht gesetzt)'}")
        print(f"Subject: {subject}")
        print()
        print(body)
        log_notification(
            recipient=recipient,
            number_of_changes=len(real_events),
            subject=subject,
            status="skipped",
            error_message="Dry-run: email not sent.",
        )
        return False

    try:
        config = load_smtp_config()
        send_email(config, subject, body)
    except Exception as exc:
        log_notification(
            recipient=recipient,
            number_of_changes=len(real_events),
            subject=subject,
            status="failed",
            error_message=str(exc),
        )
        print(f"Email notification failed: {exc}")
        return False

    log_notification(
        recipient=config.email_to,
        number_of_changes=len(real_events),
        subject=subject,
        status="sent",
    )
    print(f"Email notification sent to {config.email_to}.")
    return True


def load_smtp_config() -> SmtpConfig:
    required = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "EMAIL_FROM",
        "EMAIL_TO",
        "DASHBOARD_URL",
    ]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ValueError(f"Missing email configuration: {', '.join(missing)}")

    try:
        port = int(os.environ["SMTP_PORT"])
    except ValueError as exc:
        raise ValueError("SMTP_PORT must be a number.") from exc

    return SmtpConfig(
        host=os.environ["SMTP_HOST"],
        port=port,
        username=os.environ["SMTP_USERNAME"],
        password=os.environ["SMTP_PASSWORD"],
        email_from=os.environ["EMAIL_FROM"],
        email_to=os.environ["EMAIL_TO"],
        dashboard_url=os.environ["DASHBOARD_URL"],
    )


def send_email(config: SmtpConfig, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.email_from
    message["To"] = config.email_to
    message.set_content(body)

    with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(config.username, config.password)
        smtp.send_message(message)


def build_email_body(events: list[dict[str, Any]], dashboard_url: str) -> str:
    visible_events = events[:10]
    previous_times = [
        parsed
        for event in events
        if (parsed := parse_datetime(event.get("previous_snapshot_timestamp")))
    ]
    current_times = [
        parsed
        for event in events
        if (parsed := parse_datetime(event.get("current_snapshot_timestamp") or event.get("detected_at")))
    ]
    previous_label = format_datetime(min(previous_times)) if previous_times else "-"
    current_label = format_datetime(max(current_times)) if current_times else "-"

    lines = [
        "Hallo,",
        "",
        f"DiGA Watch hat {len(events)} Änderung(en) im BfArM DiGA-Verzeichnis erkannt.",
        "",
        "Zeitraum:",
        f"Letzter bekannter Zustand: {previous_label}",
        f"Neuer Zustand: {current_label}",
        "",
        "Änderungen:",
        "",
    ]

    for index, event in enumerate(visible_events, start=1):
        lines.extend(render_event_summary(index, event))
        lines.append("")

    if len(events) > len(visible_events):
        lines.append("Weitere simulierte Änderungen im Dashboard.")
        lines.append("")

    lines.extend(
        [
            "Dashboard:",
            dashboard_url or "(DASHBOARD_URL nicht gesetzt)",
            "",
            "Viele Grüße",
            "DiGA Watch",
        ]
    )
    return "\n".join(lines)


def render_event_summary(index: int, event: dict[str, Any]) -> list[str]:
    lines = [
        f"{index}. {event.get('diga_name', 'Unbekannte DiGA')}",
        f"   Änderungstyp: {change_label(event)}",
        f"   Geändert in: {field_label(event)}",
        f"   Kurzbeschreibung: {event.get('summary_de') or short_description(event)}",
    ]

    if event.get("change_type") == "text_change":
        text_summary = text_change_summary(event)
        if text_summary:
            lines.extend([f"   {line}" for line in text_summary])

    return lines


def text_change_summary(event: dict[str, Any]) -> list[str]:
    tokens = event.get("word_diff")
    if not isinstance(tokens, list):
        return []

    removed = first_changed_phrase(tokens, "delete")
    added = first_changed_phrase(tokens, "insert")
    kind = event.get("text_change_kind")
    lines = []
    if removed and kind != "text_added":
        lines.extend(["Entfernt:", f'"{removed}"'])
    if added and kind != "text_removed":
        lines.extend(["Hinzugefügt:", f'"{added}"'])
    return lines


def first_changed_phrase(tokens: list[dict[str, Any]], op: str) -> str:
    words = []
    collecting = False
    for token in tokens:
        if token.get("op") == op:
            words.append(str(token.get("text", "")))
            collecting = True
        elif collecting:
            break
    phrase = " ".join(word for word in words if word).strip()
    if len(phrase) > 240:
        return phrase[:237].rstrip() + "..."
    return phrase


def short_description(event: dict[str, Any]) -> str:
    change_type = event.get("change_type")
    if change_type == "text_change":
        kind = event.get("text_change_kind")
        if kind == "text_removed":
            return "Ein Textabschnitt wurde entfernt."
        if kind == "text_added":
            return "Der Text wurde ergänzt."
        if kind in {"text_modified", "text_replaced"}:
            return "Die Formulierung wurde angepasst."
        return "Text wurde geändert."
    if change_type == "new_diga":
        return "Eine neue DiGA wurde aufgenommen."
    if change_type == "removed_diga":
        return "Eine DiGA wurde gestrichen."
    if change_type == "status_change":
        return "Der Aufnahmestatus wurde geändert."
    if change_type == "price_change":
        return "Preisangaben wurden geändert."
    return "Ein Feld wurde geändert."


def is_notifiable_event(event: dict[str, Any], include_simulated: bool = False) -> bool:
    if event.get("simulated") and not include_simulated:
        return False
    if event.get("development") or event.get("is_development") or event.get("baseline_cleanup"):
        return False

    field_name = event_field_name(event).lower()
    previous_value = event_previous_value(event)
    if previous_value is None and field_name == "source_update_notice":
        return False
    if previous_value is None and "checked_sources" in field_name:
        return False
    return True


def log_notification(
    recipient: str,
    number_of_changes: int,
    subject: str,
    status: str,
    error_message: str | None = None,
    path: Path = DEFAULT_NOTIFICATION_LOG_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    log_entries = load_notification_log(path)
    entry = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient,
        "number_of_changes": number_of_changes,
        "subject": subject,
        "status": status,
    }
    if error_message:
        entry["error_message"] = error_message
    log_entries.append(entry)
    with path.open("w", encoding="utf-8") as file:
        json.dump(log_entries, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def load_notification_log(path: Path = DEFAULT_NOTIFICATION_LOG_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def change_label(event: dict[str, Any]) -> str:
    return CHANGE_LABELS.get(str(event.get("change_type")), str(event.get("change_type") or "Unbekannt"))


def field_label(event_or_field_name: dict[str, Any] | str) -> str:
    if isinstance(event_or_field_name, dict):
        if event_or_field_name.get("user_facing_field_label"):
            return str(event_or_field_name["user_facing_field_label"])
        field_name = event_field_name(event_or_field_name)
    else:
        field_name = event_or_field_name
    root = field_name.split(".", 1)[0]
    return FIELD_LABELS.get(field_name) or FIELD_LABELS.get(root) or root or "Unbekannter Bereich"


def event_field_name(event: dict[str, Any]) -> str:
    return str(event.get("changed_field") or event.get("field_name") or "")


def event_previous_value(event: dict[str, Any]) -> Any:
    return event.get("previous_value", event.get("before_value"))


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_datetime(value: datetime) -> str:
    return value.astimezone().strftime("%d.%m.%Y %H:%M")
