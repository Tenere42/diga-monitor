"""The actual ``POST /api/newsletter/subscribe`` route handler.

Deliberately thin: request parsing, rate limiting, and response shaping
only. All decision logic lives in ``validation.py`` (pure, unit-tested)
and ``src.subscribers`` (the existing, already-reviewed Brevo DOI
logic -- reused here via ``request_double_optin``, never duplicated).
"""

from __future__ import annotations

import logging
import traceback

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.subscribers import SignupOutcome, request_double_optin

from .rate_limit import InMemoryRateLimiter
from .validation import (
    SignupResponseStatus,
    ValidationFailure,
    http_status_for,
    is_acceptable_content_type,
    response_body_for_signup_result,
    validate_request_body,
)

logger = logging.getLogger(__name__)

# PoC-grade limit -- see README.md's rate-limiting analysis for why this
# is not sufficient on its own for a real deployment (in-memory,
# per-process; does not coordinate across replicas or survive a restart).
_RATE_LIMIT_MAX_REQUESTS = 5
_RATE_LIMIT_WINDOW_SECONDS = 600.0
_rate_limiter = InMemoryRateLimiter(_RATE_LIMIT_MAX_REQUESTS, _RATE_LIMIT_WINDOW_SECONDS)

# Closed allowlist for the outcome code logged below, mirroring app.py's
# own _safe_outcome_for_log: request_double_optin() only ever returns one
# of these fixed constants, but logging through this allowlist means a
# future change to that contract can never silently turn this log line
# into a free-text/PII sink.
_KNOWN_SIGNUP_OUTCOMES = frozenset(
    {
        SignupOutcome.CONFIRMATION_SENT,
        SignupOutcome.ALREADY_PENDING_OR_CONFIRMED,
        SignupOutcome.INVALID_EMAIL,
        SignupOutcome.CONFIG_MISSING,
        SignupOutcome.ERROR,
    }
)


def _safe_outcome_for_log(outcome: str) -> str:
    return outcome if outcome in _KNOWN_SIGNUP_OUTCOMES else "unknown"


def _client_key(request: Request) -> str:
    """The rate-limit bucket key for a request.

    Uses the immediate TCP peer address. Behind a reverse proxy (Railway
    included) this is the proxy's own address unless the proxy is
    configured to pass along and be trusted for a real client-IP header
    -- see README.md; this PoC does not trust any such header, since
    trusting a client-suppliable header for rate limiting would let a
    caller trivially claim a fresh IP on every request.
    """
    return request.client.host if request.client else "unknown"


async def subscribe(request: Request) -> JSONResponse:
    # PII-free diagnostic logging, deliberately mirroring the pattern
    # already established for the Streamlit signup flow in app.py: fixed
    # marker strings and outcome *codes* only, never the email address
    # or any secret.
    logger.warning("POC_NEWSLETTER_SUBMIT_RECEIVED")

    # Checked before the rate limiter (raised in review): a request with
    # a CORS-safelisted content type is rejected here for free, without
    # spending any of the caller's rate-limit budget on it. Getting this
    # order backwards would let a handful of trivially-sent, no-preflight
    # cross-origin requests exhaust a shared IP's rate-limit window (see
    # README.md: behind Railway's proxy, that key may already be shared
    # across unrelated visitors) and deny legitimate signups -- a cheap
    # denial-of-service that content-type checking should cost nothing to
    # avoid.
    if not is_acceptable_content_type(request.headers.get("content-type", "")):
        logger.warning("POC_NEWSLETTER_VALIDATION_ERROR reason=content_type")
        return _json_response(
            SignupResponseStatus.VALIDATION_ERROR,
            "Content-Type muss application/json sein.",
            field="content-type",
        )

    if not _rate_limiter.allow(_client_key(request)):
        logger.warning("POC_NEWSLETTER_RATE_LIMITED")
        return _json_response(SignupResponseStatus.RATE_LIMITED, "Zu viele Anfragen. Bitte versuche es später erneut.")

    try:
        payload = await request.json()
    except ValueError:
        logger.warning("POC_NEWSLETTER_VALIDATION_ERROR reason=invalid_json")
        return _json_response(
            SignupResponseStatus.VALIDATION_ERROR, "Ungültiger JSON-Request-Body.", field="body"
        )

    parsed = validate_request_body(payload)
    if isinstance(parsed, ValidationFailure):
        logger.warning("POC_NEWSLETTER_VALIDATION_ERROR reason=%s", parsed.field)
        return _json_response(
            SignupResponseStatus.VALIDATION_ERROR, parsed.message, field=parsed.field
        )

    logger.warning("POC_NEWSLETTER_REQUEST_START")
    try:
        # request_double_optin() does blocking network I/O via urllib --
        # run it off the event loop so one slow/hanging Brevo call can't
        # stall every other concurrent request this process is serving.
        result = await run_in_threadpool(request_double_optin, parsed.email)
    except Exception as exc:
        # request_double_optin() is documented and tested (see
        # src/subscribers.py and tests/test_subscribers.py) to never
        # raise -- every failure mode is already converted into a safe
        # SignupResult. This is the same defensive backstop already
        # used for the Streamlit flow (app.py): log only the exception
        # TYPE and a sanitized traceback (file/line/source text per
        # frame, via traceback.format_tb) -- never str(exc)/exc.args,
        # which could in principle echo request data if that contract
        # were ever broken by a future change -- and always return a
        # real response, never let the request just hang or 500 with no
        # body.
        logger.warning(
            "POC_NEWSLETTER_REQUEST_UNEXPECTED_ERROR exception_type=%s\n%s",
            type(exc).__name__,
            "".join(traceback.format_tb(exc.__traceback__)),
        )
        return _json_response(
            SignupResponseStatus.API_ERROR,
            "Bei der Anmeldung ist ein unerwarteter Fehler aufgetreten. Bitte versuche es später erneut.",
        )

    logger.warning(
        "POC_NEWSLETTER_REQUEST_RESULT result=%s", _safe_outcome_for_log(result.outcome)
    )
    body = response_body_for_signup_result(result.outcome, result.message_de)
    return JSONResponse(body, status_code=http_status_for(body["status"]))


def _json_response(status: str, message: str, *, field: str | None = None) -> JSONResponse:
    body: dict[str, object] = {"status": status, "message": message}
    if field is not None:
        body["field"] = field
    return JSONResponse(body, status_code=http_status_for(status))
