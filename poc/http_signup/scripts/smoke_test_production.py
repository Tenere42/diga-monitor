#!/usr/bin/env python3
"""Manual, deliberately NOT-automatic production-like smoke test for a
deployed poc/http_signup instance.

This script is NOT run by any test suite (main or PoC) and NOT run by
CI. It makes a real HTTP request against a real deployed URL and, in
its default (non-healthcheck-only) mode, can trigger a real Brevo
double-opt-in email to a real address -- that is the whole point of a
"production-like" smoke test, but it means this script must only ever
be run deliberately, by a human who has chosen the target URL and the
recipient address, never automatically.

Safeguards, all deliberate:
  - No default URL and no default email address -- both must be passed
    explicitly (--url / --email, or the POC_SMOKE_TEST_URL /
    POC_SMOKE_TEST_EMAIL env vars). There is nothing to accidentally
    run "as-is".
  - Sending the actual signup request additionally requires the
    explicit --send flag. Without it, only --healthcheck-only-style
    connectivity information is possible (see below) -- this script
    will refuse to POST to /api/newsletter/subscribe otherwise.
  - --healthcheck-only checks GET /healthz and exits -- no email
    address needed, no signup request made, safe to run freely against
    any deployed instance to confirm it's up.
  - This script cannot verify email delivery itself (it has no access
    to any inbox) -- it only reports the HTTP response and reminds you
    to check the inbox and/or the Brevo dashboard yourself.

Examples
--------
Check the service is reachable at all (no email involved):
    python poc/http_signup/scripts/smoke_test_production.py \\
        --url https://<temp-service>.up.railway.app --healthcheck-only

Actually trigger a real DOI email to a real, checkable address:
    python poc/http_signup/scripts/smoke_test_production.py \\
        --url https://<temp-service>.up.railway.app \\
        --email you@example.com \\
        --send
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _get(url: str, *, timeout: float) -> tuple[int, dict | None, str]:
    request = Request(url, method="GET")
    return _do_request(request, timeout)


def _post_json(url: str, payload: dict, *, timeout: float) -> tuple[int, dict | None, str]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return _do_request(request, timeout)


def _do_request(request: Request, timeout: float) -> tuple[int, dict | None, str]:
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            status_code = response.status
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status_code = exc.code
    except URLError as exc:
        return 0, None, f"Could not reach the URL: {exc.reason}"

    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = None
    return status_code, parsed, raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--url",
        default=None,
        help="Base URL of the deployed poc/http_signup instance, e.g. "
        "https://<temp-service>.up.railway.app (no trailing slash). "
        "Falls back to the POC_SMOKE_TEST_URL env var.",
    )
    parser.add_argument(
        "--email",
        default=None,
        help="A real, checkable address you control. Required unless "
        "--healthcheck-only is used. Falls back to the "
        "POC_SMOKE_TEST_EMAIL env var. NEVER pass a third party's "
        "address -- this can trigger a real email to it.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually POST to /api/newsletter/subscribe. Without this "
        "flag, only --healthcheck-only is possible -- the script "
        "refuses to send a signup request by default.",
    )
    parser.add_argument(
        "--healthcheck-only",
        action="store_true",
        help="Only check GET /healthz, then exit. No email address "
        "needed, no signup request made.",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="Request timeout in seconds (default: 15).")
    args = parser.parse_args()

    import os

    # All argument validation happens here, before any network call at
    # all (including the health check) -- a missing/invalid argument
    # must be a hard error with zero side effects, not something
    # discovered partway through.
    url = (args.url or os.environ.get("POC_SMOKE_TEST_URL") or "").rstrip("/")
    if not url:
        parser.error("--url (or POC_SMOKE_TEST_URL) is required.")
    if not url.startswith("https://"):
        print(
            f"WARNING: URL '{url}' does not start with https:// -- a temporary Railway "
            "service should always be reachable over HTTPS. Continuing anyway.",
            file=sys.stderr,
        )

    email = args.email or os.environ.get("POC_SMOKE_TEST_EMAIL")
    if not args.healthcheck_only and not email:
        parser.error(
            "--email (or POC_SMOKE_TEST_EMAIL) is required unless --healthcheck-only is set. "
            "Use a real address you control -- never a third party's."
        )

    print(f"GET {url}/healthz ...")
    status, body, raw = _get(f"{url}/healthz", timeout=args.timeout)
    print(f"  -> HTTP {status}: {raw}")
    if status != 200 or not body or body.get("status") != "ok":
        print("Health check did not return the expected {'status': 'ok'}. Stopping here.", file=sys.stderr)
        return 1

    if args.healthcheck_only:
        print("Health check passed. --healthcheck-only was set, so stopping here (no signup request made).")
        return 0

    if not args.send:
        print(
            "\nHealth check passed. Refusing to send the actual signup request without --send.\n"
            f"Re-run with --send to POST to {url}/api/newsletter/subscribe using email={email!r}.\n"
            "This WILL trigger a real Brevo double-opt-in email to that address if the "
            "deployed instance has real BREVO_* credentials configured.",
        )
        return 0

    print(f"\nPOST {url}/api/newsletter/subscribe (email={email!r}, consent=true) ...")
    status, body, raw = _post_json(
        f"{url}/api/newsletter/subscribe",
        {"email": email, "consent": True},
        timeout=args.timeout,
    )
    print(f"  -> HTTP {status}: {raw}")
    result_status = body.get("status") if body else None

    # Deliberately distinct from `already_subscribed` (HTTP 200): that
    # outcome means Brevo already has this address as pending/confirmed,
    # which may mean *no new* DOI email was sent this time -- treating
    # it the same as a fresh `success` would tell you to go check an
    # inbox that may receive nothing, making the smoke test misleading.
    if status == 201 and result_status == "success":
        print(
            "\nA NEW double-opt-in email should have been triggered. This script cannot verify "
            "email delivery itself:\n"
            f"  1. Check the inbox for {email} for a Brevo double-opt-in confirmation email.\n"
            "  2. Optionally cross-check the Brevo dashboard's contact/statistics view.\n"
            "  3. Click the confirmation link and confirm the linked page loads.\n"
            "Report back what you see -- this script's job ends at 'the HTTP request was accepted'.",
        )
        return 0

    if status == 200 and result_status == "already_subscribed":
        print(
            f"\nRequest accepted, but Brevo reports {email!r} as already pending or confirmed "
            "on this list. A NEW confirmation email may NOT have been sent this time -- this "
            "does not confirm the DOI-triggering path. To actually test a fresh DOI send, use "
            "an address that has never signed up to this list before (or has been fully "
            "unsubscribed from it first).",
        )
        return 0

    print(
        f"\nRequest was NOT accepted as a success (HTTP {status}, status={result_status!r}). "
        "No email should have been sent. Check the response body above and the deployed "
        "service's logs.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
