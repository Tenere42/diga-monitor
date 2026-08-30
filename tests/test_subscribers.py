from __future__ import annotations

import json
import os
import unittest
from unittest import mock
from urllib.error import HTTPError

from src.subscribers import (
    BREVO_DOI_API_URL,
    MissingSignupConfig,
    SignupOutcome,
    is_valid_email,
    load_signup_config,
    request_double_optin,
)


ENVIRONMENT = {
    "BREVO_API_KEY": "test-api-key",
    "BREVO_NEWSLETTER_LIST_ID": "42",
    "BREVO_DOI_TEMPLATE_ID": "7",
    "BREVO_DOI_REDIRECT_URL": "https://www.diga-tracker.de/?view=confirmed",
}


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status = status_code

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def http_error(status_code: int, payload: dict) -> HTTPError:
    body = json.dumps(payload).encode()
    exc = HTTPError(BREVO_DOI_API_URL, status_code, "error", None, None)
    exc.read = lambda: body  # type: ignore[method-assign]
    return exc


class EmailValidationTests(unittest.TestCase):
    def test_valid_emails_accepted(self) -> None:
        for candidate in ["a@b.de", "user.name+tag@example.co.uk", " spaced@example.com "]:
            self.assertTrue(is_valid_email(candidate), candidate)

    def test_invalid_emails_rejected(self) -> None:
        for candidate in ["", "not-an-email", "missing-domain@", "@missing-local.de", "spaces in@email.com"]:
            self.assertFalse(is_valid_email(candidate), candidate)


class SignupConfigTests(unittest.TestCase):
    def test_missing_config_lists_every_missing_variable(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingSignupConfig) as ctx:
                load_signup_config()
            for var in ("BREVO_API_KEY", "BREVO_NEWSLETTER_LIST_ID", "BREVO_DOI_TEMPLATE_ID", "BREVO_DOI_REDIRECT_URL"):
                self.assertIn(var, ctx.exception.missing)

    def test_non_numeric_list_id_is_treated_as_missing_config(self) -> None:
        env = dict(ENVIRONMENT)
        env["BREVO_NEWSLETTER_LIST_ID"] = "not-a-number"
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(MissingSignupConfig):
                load_signup_config()

    def test_complete_config_loads(self) -> None:
        with mock.patch.dict(os.environ, ENVIRONMENT, clear=True):
            config = load_signup_config()
            self.assertEqual(config.list_id, 42)
            self.assertEqual(config.template_id, 7)


class RequestDoubleOptinTests(unittest.TestCase):
    def test_invalid_email_never_calls_brevo(self) -> None:
        with mock.patch("src.subscribers.urlopen") as urlopen_mock:
            result = request_double_optin("not-an-email")
        self.assertEqual(result.outcome, SignupOutcome.INVALID_EMAIL)
        urlopen_mock.assert_not_called()

    def test_missing_config_never_calls_brevo(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("src.subscribers.urlopen") as urlopen_mock,
        ):
            result = request_double_optin("visitor@example.com")
        self.assertEqual(result.outcome, SignupOutcome.CONFIG_MISSING)
        urlopen_mock.assert_not_called()

    def test_successful_signup_triggers_double_optin_with_correct_payload(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", return_value=FakeResponse(201)) as urlopen_mock,
        ):
            result = request_double_optin("visitor@example.com")

        self.assertEqual(result.outcome, SignupOutcome.CONFIRMATION_SENT)
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, BREVO_DOI_API_URL)
        payload = json.loads(request.data)
        self.assertEqual(payload["email"], "visitor@example.com")
        self.assertEqual(payload["includeListIds"], [42])
        self.assertEqual(payload["templateId"], 7)
        self.assertEqual(payload["redirectionUrl"], ENVIRONMENT["BREVO_DOI_REDIRECT_URL"])

    def test_duplicate_signup_returns_friendly_already_pending_result(self) -> None:
        error = http_error(400, {"code": "duplicate_parameter", "message": "Contact already exist"})
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=error),
        ):
            result = request_double_optin("visitor@example.com")
        self.assertEqual(result.outcome, SignupOutcome.ALREADY_PENDING_OR_CONFIRMED)

    def test_duplicate_signup_detected_via_message_text_fallback(self) -> None:
        error = http_error(400, {"code": "unrelated_code", "message": "This contact is already subscribed"})
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=error),
        ):
            result = request_double_optin("visitor@example.com")
        self.assertEqual(result.outcome, SignupOutcome.ALREADY_PENDING_OR_CONFIRMED)

    def test_generic_brevo_error_returns_safe_error_result_without_raising(self) -> None:
        error = http_error(500, {"code": "internal_error", "message": "boom"})
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=error),
        ):
            result = request_double_optin("visitor@example.com")
        self.assertEqual(result.outcome, SignupOutcome.ERROR)

    def test_unexpected_exception_never_propagates(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=RuntimeError("network down")),
        ):
            result = request_double_optin("visitor@example.com")
        self.assertEqual(result.outcome, SignupOutcome.ERROR)

    def test_result_message_never_contains_api_key(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=RuntimeError("boom")),
        ):
            result = request_double_optin("visitor@example.com")
        self.assertNotIn(ENVIRONMENT["BREVO_API_KEY"], result.message_de)


if __name__ == "__main__":
    unittest.main()
