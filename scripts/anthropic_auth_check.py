"""Fail-closed Anthropic API-key connectivity check without secret output."""

from __future__ import annotations

import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models?limit=1"
ANTHROPIC_VERSION = "2023-06-01"


def check_anthropic_api_key(api_key: str | None = None) -> None:
    key = api_key if api_key is not None else os.getenv("ANTHROPIC_API_KEY")
    if not key or not key.strip():
        raise RuntimeError("ANTHROPIC_API_KEY is not available.")

    request = Request(
        ANTHROPIC_MODELS_URL,
        headers={
            "accept": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
            "x-api-key": key,
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            status = response.status
            response.read(1)
    except HTTPError as exc:
        exc.read()
        raise RuntimeError(f"Anthropic API authentication/connectivity check failed with HTTP {exc.code}.") from None
    except URLError as exc:
        raise RuntimeError("Anthropic API connectivity check could not reach the API.") from None

    if status != 200:
        raise RuntimeError(f"Anthropic API authentication/connectivity check failed with HTTP {status}.")


def main() -> int:
    try:
        check_anthropic_api_key()
    except RuntimeError as exc:
        print(f"Claude auth preflight failed: {exc}", file=sys.stderr)
        return 1
    print("Claude auth preflight passed: ANTHROPIC_API_KEY is available and accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
