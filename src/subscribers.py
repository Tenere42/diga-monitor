"""Public newsletter signup via Brevo's native double opt-in.

Brevo is the sole system of record for subscriber status. This module
holds no subscriber database of its own -- it only ever makes one
outbound call per signup attempt, to Brevo's
``/v3/contacts/doubleOptinConfirmation`` endpoint, and returns a
German-language, user-facing result. No email address is logged,
persisted, or written to disk by this module.

Deliberately separate from ``src/notifications.py`` (existing admin
change-notification path) and from ``src/subscriber_alerts.py`` (the
alert-campaign dispatch triggered by change detection): a bug here
cannot affect either of those.

NOTE for whoever wires this up against a real Brevo account: the exact
duplicate-signup error shape (``code``/``message`` on a 400 response)
below is based on Brevo's publicly documented contact-API error
conventions at the time this was written, and has **not** been verified
against a live call (making that call would itself send a real email --
disallowed without explicit approval). Verify the exact error `code`
Brevo returns for an already-confirmed or already-pending contact
against a real account before relying on this classification in
production, and adjust ``_classify_duplicate`` if it differs.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BREVO_DOI_API_URL = "https://api.brevo.com/v3/contacts/doubleOptinConfirmation"

# Deliberately simple: good enough to reject obvious typos client-side
# without pretending to be a full RFC 5322 validator. Brevo performs the
# authoritative validation server-side.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

REQUIRED_SIGNUP_ENV_VARS = [
    "BREVO_API_KEY",
    "BREVO_NEWSLETTER_LIST_ID",
    "BREVO_DOI_TEMPLATE_ID",
    "BREVO_DOI_REDIRECT_URL",
]

# Brevo error codes/messages that indicate "this address is already a
# pending or confirmed contact" rather than a real failure. See the
# module docstring: verify against a live account before production use.
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
    return bool(EMAIL_PATTERN.match(value.strip()))


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
    """Trigger Brevo's native double opt-in flow for ``email``.

    Never raises. Every failure mode -- invalid input, missing config,
    network/API error -- is translated into a safe, honest German
    message and returned, never surfaced as a stack trace to a visitor.
    """
    candidate = (email or "").strip()
    if not is_valid_email(candidate):
        return SignupResult(
            SignupOutcome.INVALID_EMAIL,
            "Bitte gib eine gueltige E-Mail-Adresse ein.",
        )

    try:
        config = load_signup_config()
    except MissingSignupConfig:
        return SignupResult(
            SignupOutcome.CONFIG_MISSING,
            "Die Anmeldung ist aktuell nicht verfuegbar. Bitte versuche es spaeter erneut.",
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
        # exc.read() and the duplicate-error classification below are
        # wrapped in their own try/except: a broken/reset connection
        # while streaming Brevo's error response body can make
        # exc.read() itself raise, and an exception raised inside this
        # except-block is a *sibling* of -- not caught by -- the
        # `except Exception:` clause further down. Without this inner
        # guard, that would break request_double_optin's "never raises"
        # contract and surface a raw traceback to the visitor.
        try:
            body = exc.read()
            if _is_duplicate_signup_error(exc.code, body):
                return SignupResult(
                    SignupOutcome.ALREADY_PENDING_OR_CONFIRMED,
                    "Diese E-Mail-Adresse ist bereits angemeldet. Falls du noch keine "
                    "Bestaetigungs-E-Mail erhalten hast, pruefe bitte deinen Spam-Ordner.",
                )
        except Exception:
            pass
        return SignupResult(
            SignupOutcome.ERROR,
            "Die Anmeldung konnte nicht verarbeitet werden. Bitte versuche es spaeter erneut.",
        )
    except Exception:
        return SignupResult(
            SignupOutcome.ERROR,
            "Die Anmeldung konnte nicht verarbeitet werden. Bitte versuche es spaeter erneut.",
        )

    return SignupResult(
        SignupOutcome.CONFIRMATION_SENT,
        "Fast geschafft: Wir haben dir eine Bestaetigungs-E-Mail geschickt. "
        "Bitte bestaetige deine Anmeldung ueber den Link darin.",
    )


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
