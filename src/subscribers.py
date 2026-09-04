"""Public newsletter signup via Brevo's native double opt-in.

Brevo is the sole system of record for subscriber status. This module
holds no subscriber database of its own. No email address is logged,
persisted, or written to disk by this module.

The signup flow also handles an explicit re-subscription after a previous
unsubscribe. Brevo keeps such contacts as ``emailBlacklisted=true``. Before
starting a new DOI flow we therefore check the existing contact. If it is
blocklisted, we atomically remove it from the confirmed subscriber list and
clear the marketing blocklist, then start a fresh DOI flow. This keeps the
contact outside the alert audience until the new DOI is completed.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


BREVO_DOI_API_URL = "https://api.brevo.com/v3/contacts/doubleOptinConfirmation"
BREVO_CONTACTS_API_URL = "https://api.brevo.com/v3/contacts"

EMAIL_PATTERN = re.compile(r"^[^@\s\x00-\x1f]+@[^@\s\x00-\x1f]+\.[^@\s\x00-\x1f]+$")
MAX_EMAIL_LENGTH = 254

REQUIRED_SIGNUP_ENV_VARS = [
    "BREVO_API_KEY",
    "BREVO_NEWSLETTER_LIST_ID",
    "BREVO_DOI_TEMPLATE_ID",
    "BREVO_DOI_REDIRECT_URL",
]

_DUPLICATE_ERROR_CODES = {"duplicate_parameter", "contact_already_exist"}
_DUPLICATE_MESSAGE_MARKERS = ("already exist", "already subscribed", "duplicate")


class SignupOutcome:
    CONFIRMATION_SENT = "confirmation_sent"
    ALREADY_PENDING_OR_CONFIRMED = "already_pending_or_confirmed"
    INVALID_EMAIL = "invalid_email"
    CONFIG_MISSING = "config_missing"
    ERROR = "error"


@dataclass(frozen=True)
class SignupResult:
    outcome: str
    message_de: str


class MissingSignupConfig(ValueError):
    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"Missing newsletter signup configuration: {', '.join(missing)}")


@dataclass(frozen=True)
class SignupConfig:
    api_key: str
    list_id: int
    template_id: int
    redirect_url: str


def is_valid_email(value: str) -> bool:
    if not value:
        return False
    candidate = value.strip()
    return len(candidate) <= MAX_EMAIL_LENGTH and bool(EMAIL_PATTERN.match(candidate))


def load_signup_config() -> SignupConfig:
    missing = [name for name in REQUIRED_SIGNUP_ENV_VARS if not os.getenv(name, "").strip()]
    if missing:
        raise MissingSignupConfig(missing)
    try:
        list_id = int(os.environ["BREVO_NEWSLETTER_LIST_ID"])
        template_id = int(os.environ["BREVO_DOI_TEMPLATE_ID"])
    except ValueError as exc:
        raise MissingSignupConfig(
            ["BREVO_NEWSLETTER_LIST_ID/BREVO_DOI_TEMPLATE_ID (must be numeric)"]
        ) from exc
    return SignupConfig(
        api_key=os.environ["BREVO_API_KEY"],
        list_id=list_id,
        template_id=template_id,
        redirect_url=os.environ["BREVO_DOI_REDIRECT_URL"],
    )


def request_double_optin(email: str) -> SignupResult:
    """Trigger Brevo's DOI flow and safely support explicit re-subscription."""
    candidate = (email or "").strip()
    if len(candidate) > MAX_EMAIL_LENGTH:
        return SignupResult(
            SignupOutcome.INVALID_EMAIL,
            "Die E-Mail-Adresse darf maximal 254 Zeichen lang sein.",
        )
    if not is_valid_email(candidate):
        return SignupResult(
            SignupOutcome.INVALID_EMAIL,
            "Bitte gib eine gültige E-Mail-Adresse ein.",
        )

    try:
        config = load_signup_config()
    except MissingSignupConfig:
        return SignupResult(
            SignupOutcome.CONFIG_MISSING,
            "Die Anmeldung ist aktuell nicht verfügbar. Bitte versuche es später erneut.",
        )

    try:
        blocked = _is_marketing_blocklisted(config.api_key, candidate)
        if blocked:
            _prepare_resubscribe(config.api_key, candidate, config.list_id)
    except Exception:
        return SignupResult(
            SignupOutcome.ERROR,
            "Die erneute Anmeldung konnte nicht vorbereitet werden. Bitte versuche es später erneut.",
        )

    payload = {
        "email": candidate,
        "includeListIds": [config.list_id],
        "templateId": config.template_id,
        "redirectionUrl": config.redirect_url,
    }

    try:
        _post_brevo(config.api_key, payload)
    except HTTPError as exc:
        try:
            body = exc.read()
            if _is_duplicate_signup_error(exc.code, body):
                return SignupResult(
                    SignupOutcome.ALREADY_PENDING_OR_CONFIRMED,
                    "Diese E-Mail-Adresse ist bereits angemeldet. Falls du noch keine "
                    "Bestätigungs-E-Mail erhalten hast, prüfe bitte deinen Spam-Ordner.",
                )
        except Exception:
            pass
        return SignupResult(
            SignupOutcome.ERROR,
            "Die Anmeldung konnte nicht verarbeitet werden. Bitte versuche es später erneut.",
        )
    except Exception:
        return SignupResult(
            SignupOutcome.ERROR,
            "Die Anmeldung konnte nicht verarbeitet werden. Bitte versuche es später erneut.",
        )

    return SignupResult(
        SignupOutcome.CONFIRMATION_SENT,
        "Fast geschafft: Wir haben dir eine Bestätigungs-E-Mail geschickt. "
        "Bitte bestätige deine Anmeldung über den Link darin.",
    )


def _contact_url(email: str) -> str:
    return f"{BREVO_CONTACTS_API_URL}/{quote(email, safe='')}"


def _is_marketing_blocklisted(api_key: str, email: str) -> bool:
    request = Request(
        _contact_url(email),
        method="GET",
        headers={"accept": "application/json", "api-key": api_key},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return False
        raise
    return bool(payload.get("emailBlacklisted")) if isinstance(payload, dict) else False


def _prepare_resubscribe(api_key: str, email: str, list_id: int) -> None:
    """Remove a previously unsubscribed contact from the final list and unblock it.

    Both fields are updated in one Brevo request. The subsequent DOI request is
    what may add the contact back to the confirmed list, so subscriber alerts
    remain fail-closed until confirmation.
    """
    payload = {
        "emailBlacklisted": False,
        "unlinkListIds": [list_id],
    }
    request = Request(
        _contact_url(email),
        data=json.dumps(payload).encode("utf-8"),
        method="PUT",
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        status_code = response.status
    if not 200 <= status_code < 300:
        raise RuntimeError(f"Brevo contact update failed with HTTP {status_code}")


def _is_duplicate_signup_error(status_code: int, response_body: bytes) -> bool:
    if status_code != 400:
        return False
    try:
        payload = json.loads(response_body)
    except (ValueError, UnicodeDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    code = str(payload.get("code") or "").strip()
    message = str(payload.get("message") or "").lower()
    if code in _DUPLICATE_ERROR_CODES:
        return True
    return any(marker in message for marker in _DUPLICATE_MESSAGE_MARKERS)


def _post_brevo(api_key: str, payload: dict[str, Any]) -> None:
    request = Request(
        BREVO_DOI_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        status_code = response.status
    if not 200 <= status_code < 300:
        raise RuntimeError(f"Brevo API request failed with HTTP {status_code}")
