from __future__ import annotations

import json
import os
import unittest
from unittest import mock
from urllib.error import HTTPError

from src.subscribers import (
    BREVO_DOI_API_URL,
    MAX_EMAIL_LENGTH,
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
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status = status_code
        self._payload = payload or {}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


def http_error(status_code: int, payload: dict) -> HTTPError:
    body = json.dumps(payload).encode()
    exc = HTTPError(BREVO_DOI_API_URL, status_code, "error", None, None)
    exc.read = lambda: body  # type: ignore[method-assign]
    return exc


def not_found_error() -> HTTPError:
    exc = HTTPError("https://api.brevo.com/v3/contacts/visitor%40example.com", 404, "not found", None, None)
    exc.read = lambda: b"{}"  # type: ignore[method-assign]
    return exc


class EmailValidationTests(unittest.TestCase):
    def test_valid_emails_accepted(self) -> None:
        for candidate in ["a@b.de", "user.name+tag@example.co.uk", " spaced@example.com "]:
            self.assertTrue(is_valid_email(candidate), candidate)

    def test_invalid_emails_rejected(self) -> None:
        for candidate in ["", "not-an-email", "missing-domain@", "@missing-local.de", "spaces in@email.com"]:
            self.assertFalse(is_valid_email(candidate), candidate)

    def test_all_c0_control_characters_are_rejected_in_local_and_domain_parts(self) -> None:
        for code_point in range(0x20):
            control = chr(code_point)
            self.assertFalse(is_valid_email(f"user{control}name@example.com"), code_point)
            self.assertFalse(is_valid_email(f"user@example{control}.com"), code_point)

    def test_email_at_maximum_length_is_accepted(self) -> None:
        candidate = f"{'a' * (MAX_EMAIL_LENGTH - len('@example.com'))}@example.com"
        self.assertEqual(len(candidate), MAX_EMAIL_LENGTH)
        self.assertTrue(is_valid_email(candidate))

    def test_email_over_maximum_length_is_rejected(self) -> None:
        candidate = f"{'a' * (MAX_EMAIL_LENGTH + 1 - len('@example.com'))}@example.com"
        self.assertEqual(len(candidate), MAX_EMAIL_LENGTH + 1)
        self.assertFalse(is_valid_email(candidate))


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

    def test_overlong_email_returns_clear_error_without_calling_brevo(self) -> None:
        candidate = f"{'a' * (MAX_EMAIL_LENGTH + 1 - len('@example.com'))}@example.com"
        with mock.patch("src.subscribers.urlopen") as urlopen_mock:
            result = request_double_optin(candidate)
        self.assertEqual(result.outcome, SignupOutcome.INVALID_EMAIL)
        self.assertEqual(result.message_de, "Die E-Mail-Adresse darf maximal 254 Zeichen lang sein.")
        urlopen_mock.assert_not_called()

    def test_missing_config_never_calls_brevo(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("src.subscribers.urlopen") as urlopen_mock,
        ):
            result = request_double_optin("visitor@example.com")
        self.assertEqual(result.outcome, SignupOutcome.CONFIG_MISSING)
        urlopen_mock.assert_not_called()

    def test_new_contact_signup_triggers_doi(self) -> None:
        def side_effect(request, timeout=30):
            if request.get_method() == "GET":
                raise not_found_error()
            self.assertEqual(request.full_url, BREVO_DOI_API_URL)
            payload = json.loads(request.data)
            self.assertEqual(payload["includeListIds"], [42])
            self.assertEqual(payload["templateId"], 7)
            return FakeResponse(201)

        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=side_effect),
        ):
            result = request_double_optin("visitor@example.com")

        self.assertEqual(result.outcome, SignupOutcome.CONFIRMATION_SENT)

    def test_unsubscribed_contact_is_removed_from_final_list_unblocked_and_sent_through_fresh_doi(self) -> None:
        calls: list[tuple[str, str, dict | None]] = []

        def side_effect(request, timeout=30):
            method = request.get_method()
            payload = json.loads(request.data) if request.data else None
            calls.append((method, request.full_url, payload))
            if method == "GET":
                return FakeResponse(200, {"emailBlacklisted": True, "listIds": [42]})
            if method == "PUT":
                return FakeResponse(204)
            if method == "POST":
                return FakeResponse(201)
            raise AssertionError(method)

        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=side_effect),
        ):
            result = request_double_optin("visitor@example.com")

        self.assertEqual(result.outcome, SignupOutcome.CONFIRMATION_SENT)
        self.assertEqual([call[0] for call in calls], ["GET", "PUT", "POST"])
        self.assertEqual(calls[1][2], {"emailBlacklisted": False, "unlinkListIds": [42]})
        self.assertEqual(calls[2][2]["includeListIds"], [42])

    def test_existing_unblocked_contact_is_not_modified_before_doi(self) -> None:
        calls: list[str] = []

        def side_effect(request, timeout=30):
            method = request.get_method()
            calls.append(method)
            if method == "GET":
                return FakeResponse(200, {"emailBlacklisted": False, "listIds": [42]})
            if method == "POST":
                return FakeResponse(201)
            raise AssertionError(method)

        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=side_effect),
        ):
            result = request_double_optin("visitor@example.com")

        self.assertEqual(result.outcome, SignupOutcome.CONFIRMATION_SENT)
        self.assertEqual(calls, ["GET", "POST"])

    def test_duplicate_signup_returns_friendly_already_pending_result(self) -> None:
        error = http_error(400, {"code": "duplicate_parameter", "message": "Contact already exist"})

        def side_effect(request, timeout=30):
            if request.get_method() == "GET":
                return FakeResponse(200, {"emailBlacklisted": False})
            raise error

        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=side_effect),
        ):
            result = request_double_optin("visitor@example.com")
        self.assertEqual(result.outcome, SignupOutcome.ALREADY_PENDING_OR_CONFIRMED)

    def test_contact_lookup_failure_returns_safe_error(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=RuntimeError("network down")),
        ):
            result = request_double_optin("visitor@example.com")
        self.assertEqual(result.outcome, SignupOutcome.ERROR)

    def test_unblock_failure_never_sends_doi(self) -> None:
        calls: list[str] = []

        def side_effect(request, timeout=30):
            method = request.get_method()
            calls.append(method)
            if method == "GET":
                return FakeResponse(200, {"emailBlacklisted": True})
            if method == "PUT":
                raise RuntimeError("update failed")
            raise AssertionError("DOI must not be sent after failed preparation")

        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=side_effect),
        ):
            result = request_double_optin("visitor@example.com")
        self.assertEqual(result.outcome, SignupOutcome.ERROR)
        self.assertEqual(calls, ["GET", "PUT"])

    def test_result_message_never_contains_api_key(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscribers.urlopen", side_effect=RuntimeError("boom")),
        ):
            result = request_double_optin("visitor@example.com")
        self.assertNotIn(ENVIRONMENT["BREVO_API_KEY"], result.message_de)


if __name__ == "__main__":
    unittest.main()
