"""Stable public daily-group identifiers shared by dashboard and email."""
from datetime import datetime, timezone
import hashlib
from urllib.parse import urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

PUBLIC_URL = "https://www.diga-tracker.de"


def diga_key(event: dict) -> str:
    return str(event.get("diga_id") or event.get("diga_name") or
               event.get("bfarm_directory_url") or "unknown").lower()


def local_event_date(event: dict):
    value = event.get("detected_at")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo("Europe/Berlin")).date()


def group_anchor(identity: str, day) -> str:
    return "change-" + hashlib.sha256(f"{identity}|{day}".encode("utf-8")).hexdigest()[:16]


def safe_web_url(value: str) -> str:
    """Validate configured links; never reflect executable schemes or credentials."""
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or any(c.isspace() or ord(c) < 32 for c in value)
            or any(c in value for c in '{}<>"\\')):
        raise ValueError("A valid HTTPS URL is required")
    return value


def page_url(base: str, **query: str) -> str:
    parts = urlsplit(safe_web_url(base or PUBLIC_URL))
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(query), ""))


def change_url(event: dict, base: str = PUBLIC_URL) -> str:
    return page_url(base, view="changes", detail=group_anchor(diga_key(event), local_event_date(event)))
