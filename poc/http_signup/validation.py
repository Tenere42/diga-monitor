"""Pure request validation and outcome-to-response mapping.

Deliberately free of I/O, ASGI, and the Brevo call itself, so it can be
unit tested directly (see tests/test_validation.py) without an ASGI app,
a running event loop, or network mocking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from src.subscribers import SignupOutcome


class SignupResponseStatus:
    """Structured, client-facing status codes for this HTTP endpoint.

    Deliberately distinct from ``src.subscribers.SignupOutcome``: that
    enum describes the *Brevo request's* result. This one describes the
    *HTTP endpoint's* result, which also covers request-shape problems
    (malformed JSON, missing consent) that never reach
    ``request_double_optin()`` at all, plus this endpoint's own
    rate-limit response -- none of which src.subscribers needs to know
    about.
    """

    SUCCESS: Final = "success"
    ALREADY_SUBSCRIBED: Final = "already_subscribed"
    VALIDATION_ERROR: Final = "validation_error"
    CONFIG_ERROR: Final = "config_error"
    API_ERROR: Final = "api_error"
    RATE_LIMITED: Final = "rate_limited"


@dataclass(frozen=True)
class ParsedSignupRequest:
    """A request body that passed shape validation."""

    email: str
    consent: bool


@dataclass(frozen=True)
class ValidationFailure:
    field: str
    message: str


def is_acceptable_content_type(content_type: str) -> bool:
    """True only for an exact (parameter-stripped) ``application/json``.

    This is a security control, not just a parsing nicety -- see
    README.md's CORS section. A browser will only attach the
    application/json content type to a cross-origin fetch() if it also
    runs a CORS preflight first (OPTIONS request); the three
    CORS-"safelisted" content types
    (application/x-www-form-urlencoded, multipart/form-data, text/plain)
    skip that preflight entirely, so a page on any other origin could
    otherwise trigger this endpoint (and thus a real DOI email) without
    ever being subject to this service's CORS policy. Rejecting anything
    but application/json means CORS configuration actually has teeth:
    without it, `POC_HTTP_SIGNUP_ALLOWED_ORIGINS` would give a false
    sense of restricting who can *trigger* this endpoint from a browser,
    when it would really only restrict who can *read the response*.

    This does nothing against a non-browser caller (curl, a script) --
    nothing can, since CORS and content-type sniffing are both purely
    browser-enforced conventions. That residual risk is the "mail-bombing
    arbitrary addresses" abuse vector already covered by the rate
    limiter, not something content-type checking addresses.
    """
    # Strip any ``; charset=...`` parameter before comparing.
    return content_type.split(";", 1)[0].strip().lower() == "application/json"


def validate_request_body(payload: Any) -> ParsedSignupRequest | ValidationFailure:
    """Validate the *shape* of a decoded JSON request body.

    Deliberately minimal: this checks that an ``email`` string and an
    explicit ``consent: true`` are present -- it does NOT re-validate
    email *format*. ``src.subscribers.request_double_optin()`` already
    does that (and is the single source of truth for what counts as a
    valid address), so re-implementing it here would risk the two
    diverging over time. A malformed email is caught one call later, as
    ``SignupOutcome.INVALID_EMAIL`` from that function, and mapped to
    the same ``validation_error`` status by
    ``response_body_for_signup_result`` below.
    """
    if not isinstance(payload, dict):
        return ValidationFailure("body", "Der Request-Body muss ein JSON-Objekt sein.")

    email = payload.get("email")
    if not isinstance(email, str) or not email.strip():
        return ValidationFailure("email", "E-Mail-Adresse ist erforderlich.")

    # Consent must be explicit and affirmative -- missing, false, "true"
    # (string), 1, etc. are all rejected. This mirrors the existing
    # Streamlit flow's own rule (app.py: "if not consent: ...") applied
    # to a JSON boolean instead of a checkbox widget value.
    consent = payload.get("consent")
    if consent is not True:
        return ValidationFailure(
            "consent",
            "Zustimmung zur Datenschutzerklärung ist erforderlich (consent: true).",
        )

    return ParsedSignupRequest(email=email.strip(), consent=True)


_STATUS_HTTP_CODE: Final[dict[str, int]] = {
    SignupResponseStatus.SUCCESS: 201,
    SignupResponseStatus.ALREADY_SUBSCRIBED: 200,
    SignupResponseStatus.VALIDATION_ERROR: 400,
    SignupResponseStatus.CONFIG_ERROR: 503,
    SignupResponseStatus.API_ERROR: 502,
    SignupResponseStatus.RATE_LIMITED: 429,
}


def http_status_for(status: str) -> int:
    """The HTTP status code for a given ``SignupResponseStatus`` value.

    Falls back to 500 for an unrecognized status rather than raising --
    this is only ever used to pick a response code, so a wrong-but-safe
    5xx is preferable to a crash mid-request.
    """
    return _STATUS_HTTP_CODE.get(status, 500)


_OUTCOME_TO_STATUS: Final[dict[str, str]] = {
    SignupOutcome.CONFIRMATION_SENT: SignupResponseStatus.SUCCESS,
    SignupOutcome.ALREADY_PENDING_OR_CONFIRMED: SignupResponseStatus.ALREADY_SUBSCRIBED,
    SignupOutcome.INVALID_EMAIL: SignupResponseStatus.VALIDATION_ERROR,
    SignupOutcome.CONFIG_MISSING: SignupResponseStatus.CONFIG_ERROR,
    SignupOutcome.ERROR: SignupResponseStatus.API_ERROR,
}


_UNKNOWN_OUTCOME_MESSAGE: Final = (
    "Bei der Anmeldung ist ein unerwarteter Fehler aufgetreten. Bitte versuche es später erneut."
)


def response_body_for_signup_result(outcome: str, message_de: str) -> dict[str, Any]:
    """Map a ``request_double_optin()`` result onto this endpoint's JSON
    response shape.

    For a *recognized* outcome, reuses the existing German, user-facing
    ``message_de`` from ``src.subscribers`` as-is -- that module is the
    single source of truth for signup copy, including which outcomes are
    safe to show a caller (it never includes the email address, an API
    key, or any other secret; see src/subscribers.py's own tests). This
    function only adds a stable, machine-readable ``status`` field for
    API consumers who should not need to parse German prose to know what
    happened.

    Falls back to ``api_error`` for an outcome code this PoC doesn't
    recognize, rather than raising -- see
    ``test_unrecognized_outcome_falls_back_to_api_error``. In that case
    the accompanying ``message_de`` is *not* passed through either
    (unlike the recognized-outcome path): an outcome this mapping
    doesn't know about is, by definition, one whose accompanying message
    hasn't been vetted as safe to expose either, so a fixed generic
    message is used instead -- see
    ``test_unrecognized_outcome_uses_a_fixed_message_not_the_provided_one``.
    """
    status = _OUTCOME_TO_STATUS.get(outcome)
    if status is None:
        return {"status": SignupResponseStatus.API_ERROR, "message": _UNKNOWN_OUTCOME_MESSAGE}
    return {"status": status, "message": message_de}
