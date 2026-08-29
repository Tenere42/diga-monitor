"""Brevo Transactional Email API notifications for DiGA change events."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_NOTIFICATION_LOG_PATH = Path("outputs/notification_log.json")
BREVO_EMAIL_API_URL = "https://api.brevo.com/v3/smtp/email"

CHANGE_LABELS = {
    "new_diga": "Neue DiGA",
    "removed_diga": "Nicht mehr gefunden",
    "status_change": "Statusänderung",
    "text_change": "Textänderung",
    "price_change": "Preisänderung",
    "directory_metric_change": "Verzeichnis-Zähler geändert",
    "visible_diff_unresolved": "Änderung erkannt",
    "other_field_change": "Sonstige Feldänderung",
}

FIELD_LABELS = {
    "directory_metrics": "DiGA-Verzeichnis > Statusübersicht",
    "directory_metrics.total_count": "Gesamtzahl DiGA",
    "directory_metrics.active_count": "Aktive DiGA",
    "directory_metrics.status_counts.provisional": "Vorläufig aufgenommen",
    "directory_metrics.status_counts.permanent": "Dauerhaft aufgenommen",
    "directory_metrics.status_counts.removed": "Gestrichen",
    "directory_metrics.status_counts.unknown": "Status unbekannt",
    "evidence_summary_text": "Bewertungsentscheidung des BfArM",
    "descriptive_texts": "Beschreibung der DiGA",
    "pricing_information": "Vergütung / Preisangaben",
    "source_update_notice": "Aktualisierungshinweis im DiGA-Verzeichnis",
    "status": "Aufnahmestatus",
    "indication": "Anwendungsgebiet / Indikation",
    "manufacturer": "Hersteller",
}


@dataclass(frozen=True)
class BrevoConfig:
    api_key: str
    email_from: str
    email_from_name: str


@dataclass(frozen=True)
class NotificationSettings:
    brevo: BrevoConfig
    recipients: tuple[str, ...]
    dashboard_url: str


class MissingNotificationConfig(ValueError):
    """Raised when email notification configuration is incomplete."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"Missing email configuration: {', '.join(missing)}")


def notify_changes(
    events: list[dict[str, Any]],
    dry_run: bool = False,
    include_simulated: bool = False,
    test_mode: bool = False,
) -> bool:
    real_events = [
        event
        for event in events
        if is_notifiable_event(event, include_simulated=include_simulated)
    ]
    recipients = configured_recipients()
    recipient = format_recipients(recipients)

    if not real_events:
        log_notification(
            recipient=recipient,
            number_of_changes=0,
            subject="DiGA Watch: 0 Änderung(en) erkannt",
            status="skipped",
            error_message="Keine echten Änderungen erkannt.",
        )
        print_notification_status("Notification skipped: no real changes detected.")
        return False

    subject_prefix = "[TEST / SIMULATION] " if test_mode else ""
    subject = f"{subject_prefix}DiGA Watch: {len(real_events)} Änderung(en) erkannt"
    if dry_run:
        body = build_email_body(real_events, os.getenv("DASHBOARD_URL", ""), test_mode=test_mode)
        print("Dry-run: email would be sent with this content:")
        print()
        print(f"To: {recipient or '(DIGA_MONITOR_EMAIL_TO nicht gesetzt)'}")
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
        print_notification_status("Notification dry-run: email content printed; no API email sent.")
        return False

    try:
        settings = load_notification_settings()
        print_notification_status("Notification configuration complete.")
        message = build_email_message(
            settings.brevo.email_from,
            settings.brevo.email_from_name,
            settings.recipients,
            subject,
            build_email_body(real_events, settings.dashboard_url, test_mode=test_mode),
        )
        message_id = send_email(settings.brevo, message)
    except MissingNotificationConfig as exc:
        message = f"Notification configuration incomplete. Missing: {', '.join(exc.missing)}"
        log_notification(
            recipient=recipient,
            number_of_changes=len(real_events),
            subject=subject,
            status="skipped",
            error_message=message,
        )
        print_notification_status(message)
        return False
    except Exception as exc:
        message = f"Notification failed: {exc}"
        log_notification(
            recipient=recipient,
            number_of_changes=len(real_events),
            subject=subject,
            status="failed",
            error_message=message,
        )
        print_notification_status(message, level="warning")
        return False

    log_notification(
        recipient=format_recipients(settings.recipients),
        number_of_changes=len(real_events),
        subject=subject,
        status="sent",
    )
    print_notification_status(f"Brevo API accepted notification: {message_id}")
    print_notification_status(f"Notification sent to {len(settings.recipients)} recipient(s).")
    return True


def send_test_notification(dry_run: bool = False) -> bool:
    now = datetime.now(timezone.utc)
    event = {
        "detected_at": now.isoformat(),
        "diga_id": "TEST-DIGA-NOTIFICATION",
        "diga_name": "Test DiGA",
        "manufacturer": "Test Hersteller",
        "change_type": "price_change",
        "changed_field": "pricing_information",
        "previous_value": "499,00 €",
        "new_value": "529,00 €",
        "previous_snapshot_timestamp": now.isoformat(),
        "current_snapshot_timestamp": now.isoformat(),
        "simulated": True,
        "simulation_category": "E-Mail End-to-End-Test",
        "summary_de": "Simulierte Preisänderung von 499,00 € auf 529,00 €.",
    }
    sent = notify_changes(
        [event],
        dry_run=dry_run,
        include_simulated=True,
        test_mode=True,
    )
    return dry_run or sent


def required_notification_env_vars() -> list[str]:
    return [
        "BREVO_API_KEY",
        "DIGA_MONITOR_EMAIL_FROM",
        "DIGA_MONITOR_EMAIL_FROM_NAME",
        "DIGA_MONITOR_EMAIL_TO",
    ]


def load_notification_settings() -> NotificationSettings:
    recipients = configured_recipients()
    missing = [
        name
        for name in required_notification_env_vars()
        if not os.getenv(name) or (name == "DIGA_MONITOR_EMAIL_TO" and not recipients)
    ]
    if missing:
        raise MissingNotificationConfig(missing)

    return NotificationSettings(
        brevo=BrevoConfig(
            api_key=os.environ["BREVO_API_KEY"],
            email_from=os.environ["DIGA_MONITOR_EMAIL_FROM"],
            email_from_name=os.environ["DIGA_MONITOR_EMAIL_FROM_NAME"],
        ),
        recipients=recipients,
        dashboard_url=os.getenv("DASHBOARD_URL", ""),
    )


def configured_recipients() -> tuple[str, ...]:
    raw = os.getenv("DIGA_MONITOR_EMAIL_TO", "")
    recipients = []
    seen = set()
    for candidate in raw.replace(";", ",").split(","):
        recipient = candidate.strip()
        normalized = recipient.casefold()
        if recipient and normalized not in seen:
            recipients.append(recipient)
            seen.add(normalized)
    return tuple(recipients)


def format_recipients(recipients: tuple[str, ...]) -> str:
    return ", ".join(recipients)


def build_email_message(
    email_from: str,
    email_from_name: str,
    recipients: tuple[str, ...],
    subject: str,
    body: str,
) -> dict[str, Any]:
    return {
        "sender": {"email": email_from, "name": email_from_name},
        "to": [{"email": recipient} for recipient in recipients],
        "subject": subject,
        "textContent": body,
    }


def send_email(config: BrevoConfig, message: dict[str, Any]) -> str:
    request = Request(
        BREVO_EMAIL_API_URL,
        data=json.dumps(message, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "accept": "application/json",
            "api-key": config.api_key,
            "content-type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            status_code = response.status
            response_body = response.read()
    except HTTPError as exc:
        response_body = exc.read()
        raise RuntimeError(format_brevo_error(exc.code, response_body, config.api_key)) from exc

    if not 200 <= status_code < 300:
        raise RuntimeError(format_brevo_error(status_code, response_body, config.api_key))

    try:
        message_id = json.loads(response_body)["messageId"]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError(
            f"Brevo API returned HTTP {status_code} without a messageId."
        ) from exc
    return str(message_id)


def format_brevo_error(status_code: int, response_body: bytes, api_key: str) -> str:
    detail = ""
    try:
        payload = json.loads(response_body)
        if isinstance(payload, dict):
            detail = str(payload.get("message") or payload.get("code") or "")
    except (ValueError, UnicodeDecodeError):
        pass
    if api_key:
        detail = detail.replace(api_key, "[redacted]")
    suffix = f": {detail[:300]}" if detail else ""
    return f"Brevo API request failed with HTTP {status_code}{suffix}"


def print_notification_status(message: str, level: str = "notice") -> None:
    if os.getenv("GITHUB_ACTIONS"):
        annotation = "warning" if level == "warning" else "notice"
        print(f"::{annotation}::{message}")
        return
    print(message)


def build_email_body(
    events: list[dict[str, Any]],
    dashboard_url: str,
    test_mode: bool = False,
) -> str:
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

    lines = []
    if test_mode:
        lines.extend(
            [
                "TEST / SIMULATION",
                "Keine echte BfArM-Änderung. Diese Nachricht prüft ausschließlich den Benachrichtigungspfad.",
                "",
            ]
        )

    lines.extend([
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
    ])

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

    if event.get("manufacturer"):
        lines.append(f"   Hersteller: {event['manufacturer']}")

    if event.get("change_type") == "price_change":
        lines.extend(
            [
                f"   Vorher: {event.get('previous_value', '-')}",
                f"   Nachher: {event.get('new_value', '-')}",
            ]
        )

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
        if event.get("lifecycle_event_type") == "diga_reactivated":
            return "Die DiGA wurde wieder im Verzeichnis aufgenommen."
        return "Der Aufnahmestatus wurde geändert."
    if change_type == "price_change":
        return "Preisangaben wurden geändert."
    if change_type == "directory_metric_change":
        label = event.get("directory_metric_label") or "Verzeichnis-Zähler"
        before = event.get("directory_metric_before", event_previous_value(event))
        after = event.get("directory_metric_after", event_new_value(event))
        return f"Der Verzeichnis-Zähler '{label}' wurde von {before} auf {after} geändert."
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
    if event.get("lifecycle_event_type") == "diga_reactivated":
        return "DiGA wieder aufgenommen"
    if event.get("change_type") == "directory_metric_change":
        return "Verzeichnis-Zähler geändert"
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


def event_new_value(event: dict[str, Any]) -> Any:
    return event.get("new_value", event.get("after_value"))


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
