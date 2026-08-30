"""Brevo campaign dispatch of DiGA Tracker Alerts to confirmed subscribers.

Triggered once per scan, right after (never instead of) the existing
admin change-notification in ``src/notifications.py``. This module is
deliberately separate from that one:

- it never persists subscriber email addresses -- Brevo remains the sole
  system of record for subscriber status (confirmed vs. pending vs.
  unsubscribed);
- it sends via Brevo's Email Campaign API against a confirmed-only list,
  so this codebase never assembles or sees individual recipient
  addresses, and Brevo delivers each recipient an individually addressed
  message (no cross-recipient visibility);
- it is fully fault-isolated: ``dispatch_subscriber_alerts`` never
  raises. Any failure (missing config, network error, Brevo API error)
  is caught here and logged as a non-fatal warning, so the calling scan
  pipeline (change detection, baseline update, R2 archival, admin
  notification) is completely unaffected regardless of what happens in
  this module.

NOTE for whoever wires this up against a real Brevo account: verify the
exact Email Campaign API request/response shape against Brevo's current
docs before the first live send -- this was written against Brevo's
publicly documented v3 Email Campaigns API without a live call (a real
call here would send a real campaign, which requires explicit approval
first).
"""

from __future__ import annotations

import html
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.notifications import (
    format_brevo_error,
    is_notifiable_event,
    print_notification_status,
    resolve_dashboard_url,
)


DEFAULT_SUBSCRIBER_ALERT_LOG_PATH = Path("outputs/subscriber_alert_log.json")
BREVO_CAMPAIGNS_API_URL = "https://api.brevo.com/v3/emailCampaigns"

# Brevo's merge tag that renders a personalized, working unsubscribe link
# in a classic email campaign. Kept as an explicit constant (rather than
# relying on account-level auto-injection) so its presence is directly
# testable and does not depend on Brevo dashboard settings.
BREVO_UNSUBSCRIBE_MERGE_TAG = "{{ unsubscribe }}"

REQUIRED_SUBSCRIBER_ALERT_ENV_VARS = [
    "BREVO_API_KEY",
    "DIGA_MONITOR_EMAIL_FROM",
    "DIGA_MONITOR_EMAIL_FROM_NAME",
    "BREVO_NEWSLETTER_LIST_ID",
]
# Reviewed trade-off (raised in adversarial review, refined after a
# second review pass): this list shares three variable *names* with
# src/notifications.py's admin-path config (BREVO_API_KEY,
# DIGA_MONITOR_EMAIL_FROM, DIGA_MONITOR_EMAIL_FROM_NAME). That is
# deliberate, not accidental coupling: both paths legitimately send as
# the same verified "DiGA Tracker" Brevo sender identity, and each
# module reads os.environ independently via its own config-loading
# function (load_subscriber_alert_settings() here vs.
# src.notifications.load_notification_settings()) -- neither shares
# mutable state or a config-loading function with the other. This
# module does import four *pure, stateless* helpers from
# src/notifications.py (format_brevo_error, is_notifiable_event,
# print_notification_status, resolve_dashboard_url) -- none of them
# touch audience/recipient selection, so a bug in one cannot corrupt
# *who* receives which message. The setting that actually defines that
# is fully independent: BREVO_NEWSLETTER_LIST_ID (confirmed
# subscribers) vs. DIGA_MONITOR_EMAIL_TO (admin recipients) never
# overlap.


class MissingSubscriberAlertConfig(ValueError):
    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"Missing subscriber alert configuration: {', '.join(missing)}")


@dataclass(frozen=True)
class SubscriberAlertSettings:
    api_key: str
    email_from: str
    email_from_name: str
    list_id: int
    dashboard_url: str


def dispatch_subscriber_alerts(
    events: list[dict[str, Any]],
    dry_run: bool = False,
    include_simulated: bool = False,
) -> bool:
    """Best-effort dispatch of a DiGA Tracker Alert campaign to confirmed
    subscribers. Never raises -- see module docstring.
    """
    try:
        return _dispatch_subscriber_alerts(
            events, dry_run=dry_run, include_simulated=include_simulated
        )
    except Exception as exc:  # noqa: BLE001 - deliberate fault-isolation boundary
        # Deliberately `Exception`, not `BaseException`: KeyboardInterrupt/
        # SystemExit must keep propagating so Ctrl+C and sys.exit() still
        # work. This does not weaken the fault-isolation guarantee for the
        # scan pipeline -- by the time this function is called, change
        # detection, baseline finalization, R2 archival, and the admin
        # notification have already run and persisted (see call order in
        # src/main.py); nothing here can un-do or corrupt that.
        # The fallback logging/reporting below must itself never raise --
        # e.g. a disk-full or read-only-filesystem error while writing the
        # log would otherwise escape this function a second time. This
        # function's "never raises" contract must hold on its own, not
        # only via the caller's own defense-in-depth wrapper.
        try:
            _log_subscriber_alert(
                status="failed",
                number_of_changes=len(events),
                error_message=f"Unerwarteter Fehler im Subscriber-Alert-Pfad: {exc}",
            )
        except Exception:  # noqa: BLE001 - logging must never break isolation
            pass
        try:
            print_notification_status(
                f"Subscriber alert dispatch failed (isolated, scan pipeline unaffected): {exc}",
                level="warning",
            )
        except Exception:  # noqa: BLE001 - reporting must never break isolation
            pass
        return False


def _dispatch_subscriber_alerts(
    events: list[dict[str, Any]],
    dry_run: bool,
    include_simulated: bool,
) -> bool:
    real_events = [
        event
        for event in events
        if is_notifiable_event(event, include_simulated=include_simulated)
    ]

    if not real_events:
        _log_subscriber_alert(
            status="skipped",
            number_of_changes=0,
            error_message="Keine echten Aenderungen erkannt.",
        )
        print_notification_status("Subscriber alert skipped: no real changes detected.")
        return False

    subject = f"DiGA Tracker Alert: {len(real_events)} Aenderung(en) erkannt"

    if dry_run:
        print("Dry-run: subscriber alert campaign would be created with this content:")
        print(f"Subject: {subject}")
        print("Audience: confirmed Brevo list (BREVO_NEWSLETTER_LIST_ID) -- individually addressed by Brevo")
        _log_subscriber_alert(
            status="skipped",
            number_of_changes=len(real_events),
            subject=subject,
            error_message="Dry-run: campaign not created.",
        )
        return False

    try:
        settings = load_subscriber_alert_settings()
    except MissingSubscriberAlertConfig as exc:
        message = f"Subscriber alert configuration incomplete. Missing: {', '.join(exc.missing)}"
        _log_subscriber_alert(
            status="skipped",
            number_of_changes=len(real_events),
            subject=subject,
            error_message=message,
        )
        print_notification_status(message)
        return False

    html_body = build_alert_html_body(real_events, settings.dashboard_url)
    campaign_id = create_campaign(settings, subject, html_body)
    send_campaign_now(settings, campaign_id)

    _log_subscriber_alert(
        status="sent",
        number_of_changes=len(real_events),
        subject=subject,
        campaign_id=campaign_id,
    )
    print_notification_status(
        f"Subscriber alert campaign {campaign_id} sent to confirmed list {settings.list_id}."
    )
    return True


def load_subscriber_alert_settings() -> SubscriberAlertSettings:
    missing = [
        name for name in REQUIRED_SUBSCRIBER_ALERT_ENV_VARS if not os.getenv(name, "").strip()
    ]
    if missing:
        raise MissingSubscriberAlertConfig(missing)
    try:
        list_id = int(os.environ["BREVO_NEWSLETTER_LIST_ID"])
    except ValueError as exc:
        raise MissingSubscriberAlertConfig(["BREVO_NEWSLETTER_LIST_ID (must be numeric)"]) from exc
    return SubscriberAlertSettings(
        api_key=os.environ["BREVO_API_KEY"],
        email_from=os.environ["DIGA_MONITOR_EMAIL_FROM"],
        email_from_name=os.environ["DIGA_MONITOR_EMAIL_FROM_NAME"],
        list_id=list_id,
        dashboard_url=resolve_dashboard_url(),
    )


def build_alert_html_body(events: list[dict[str, Any]], dashboard_url: str) -> str:
    visible_events = events[:10]
    items = "".join(
        f"<li>{_escape(event.get('diga_name', 'Unbekannte DiGA'))}: "
        f"{_escape(event.get('summary_de') or 'Aenderung erkannt.')}</li>"
        for event in visible_events
    )
    more_note = (
        "<p>Weitere Aenderungen im Dashboard.</p>" if len(events) > len(visible_events) else ""
    )
    dashboard_link = dashboard_url or "https://www.diga-tracker.de"
    return (
        "<html><body>"
        f"<p>DiGA Tracker hat {len(events)} Aenderung(en) im BfArM DiGA-Verzeichnis erkannt.</p>"
        f"<ul>{items}</ul>"
        f"{more_note}"
        f'<p>Dashboard: <a href="{dashboard_link}">{dashboard_link}</a></p>'
        "<p>Viele Gruesse<br>DiGA Tracker</p>"
        f'<p style="font-size:12px;color:#6b7280;">'
        f'Du erhaeltst diese E-Mail, weil du DiGA Tracker Alerts abonniert hast. '
        f'<a href="{BREVO_UNSUBSCRIBE_MERGE_TAG}">Abmelden</a></p>'
        "</body></html>"
    )


def create_campaign(settings: SubscriberAlertSettings, subject: str, html_content: str) -> int:
    payload = {
        "name": f"DiGA Tracker Alert - {datetime.now(timezone.utc).isoformat()}",
        "subject": subject,
        "sender": {"name": settings.email_from_name, "email": settings.email_from},
        "type": "classic",
        "htmlContent": html_content,
        "recipients": {"listIds": [settings.list_id]},
    }
    status_code, response_body = _brevo_request(
        "POST", BREVO_CAMPAIGNS_API_URL, settings.api_key, payload
    )
    if not 200 <= status_code < 300:
        raise RuntimeError(format_brevo_error(status_code, response_body, settings.api_key))
    try:
        return int(json.loads(response_body)["id"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError(
            f"Brevo API returned HTTP {status_code} without a campaign id."
        ) from exc


def send_campaign_now(settings: SubscriberAlertSettings, campaign_id: int) -> None:
    url = f"{BREVO_CAMPAIGNS_API_URL}/{campaign_id}/sendNow"
    status_code, response_body = _brevo_request("POST", url, settings.api_key, None)
    if not 200 <= status_code < 300:
        raise RuntimeError(format_brevo_error(status_code, response_body, settings.api_key))


def _brevo_request(
    method: str, url: str, api_key: str, payload: dict[str, Any] | None
) -> tuple[int, bytes]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def _log_subscriber_alert(
    status: str,
    number_of_changes: int,
    subject: str | None = None,
    campaign_id: int | None = None,
    error_message: str | None = None,
    path: Path | None = None,
) -> None:
    # Resolved at call time (not bound as a default parameter value) so
    # that tests can redirect DEFAULT_SUBSCRIBER_ALERT_LOG_PATH via
    # mock.patch without ever touching this repository's real outputs/.
    path = path if path is not None else DEFAULT_SUBSCRIBER_ALERT_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    log_entries = _load_subscriber_alert_log(path)
    entry: dict[str, Any] = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "number_of_changes": number_of_changes,
        "status": status,
    }
    if subject:
        entry["subject"] = subject
    if campaign_id is not None:
        entry["campaign_id"] = campaign_id
    if error_message:
        entry["error_message"] = error_message
    log_entries.append(entry)
    with path.open("w", encoding="utf-8") as file:
        json.dump(log_entries, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def _load_subscriber_alert_log(path: Path | None = None) -> list[dict[str, Any]]:
    path = path if path is not None else DEFAULT_SUBSCRIBER_ALERT_LOG_PATH
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _escape(value: Any) -> str:
    return html.escape(str(value))
