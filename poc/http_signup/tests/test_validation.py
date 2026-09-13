from __future__ import annotations

import unittest

from src.subscribers import SignupOutcome
from poc.http_signup.validation import (
    ParsedSignupRequest,
    SignupResponseStatus,
    ValidationFailure,
    http_status_for,
    is_acceptable_content_type,
    response_body_for_signup_result,
    validate_request_body,
)


class ValidateRequestBodyTests(unittest.TestCase):
    def test_valid_body_is_parsed(self) -> None:
        result = validate_request_body({"email": "visitor@example.com", "consent": True})
        self.assertEqual(result, ParsedSignupRequest(email="visitor@example.com", consent=True))

    def test_email_is_stripped(self) -> None:
        result = validate_request_body({"email": "  visitor@example.com  ", "consent": True})
        self.assertIsInstance(result, ParsedSignupRequest)
        self.assertEqual(result.email, "visitor@example.com")  # type: ignore[union-attr]

    def test_non_dict_body_is_rejected(self) -> None:
        for bad_body in ["a string", 42, None, ["email", "consent"]]:
            with self.subTest(bad_body=bad_body):
                result = validate_request_body(bad_body)
                self.assertIsInstance(result, ValidationFailure)
                self.assertEqual(result.field, "body")  # type: ignore[union-attr]

    def test_missing_email_is_rejected(self) -> None:
        result = validate_request_body({"consent": True})
        self.assertIsInstance(result, ValidationFailure)
        self.assertEqual(result.field, "email")  # type: ignore[union-attr]

    def test_blank_email_is_rejected(self) -> None:
        result = validate_request_body({"email": "   ", "consent": True})
        self.assertIsInstance(result, ValidationFailure)
        self.assertEqual(result.field, "email")  # type: ignore[union-attr]

    def test_non_string_email_is_rejected(self) -> None:
        result = validate_request_body({"email": 12345, "consent": True})
        self.assertIsInstance(result, ValidationFailure)
        self.assertEqual(result.field, "email")  # type: ignore[union-attr]

    def test_missing_consent_is_rejected(self) -> None:
        result = validate_request_body({"email": "visitor@example.com"})
        self.assertIsInstance(result, ValidationFailure)
        self.assertEqual(result.field, "consent")  # type: ignore[union-attr]

    def test_consent_false_is_rejected(self) -> None:
        result = validate_request_body({"email": "visitor@example.com", "consent": False})
        self.assertIsInstance(result, ValidationFailure)
        self.assertEqual(result.field, "consent")  # type: ignore[union-attr]

    def test_consent_truthy_non_bool_is_rejected(self) -> None:
        # "true" (string), 1, etc. must NOT be accepted -- consent has to
        # be an actual JSON boolean `true`, not merely a truthy value.
        for truthy_non_bool in ["true", "yes", 1, 1.0, ["true"]]:
            with self.subTest(value=truthy_non_bool):
                result = validate_request_body(
                    {"email": "visitor@example.com", "consent": truthy_non_bool}
                )
                self.assertIsInstance(result, ValidationFailure)
                self.assertEqual(result.field, "consent")  # type: ignore[union-attr]

    def test_obviously_malformed_email_is_not_rejected_here(self) -> None:
        # Deliberate: format validation is request_double_optin()'s job,
        # not this function's -- see the module docstring. A clearly
        # invalid address like "not-an-email" must still pass *this*
        # shape check; test_routes_integration.py covers the outcome
        # once it reaches request_double_optin().
        result = validate_request_body({"email": "not-an-email", "consent": True})
        self.assertIsInstance(result, ParsedSignupRequest)


class IsAcceptableContentTypeTests(unittest.TestCase):
    def test_exact_application_json_is_accepted(self) -> None:
        self.assertTrue(is_acceptable_content_type("application/json"))

    def test_application_json_with_charset_parameter_is_accepted(self) -> None:
        self.assertTrue(is_acceptable_content_type("application/json; charset=utf-8"))

    def test_case_is_ignored(self) -> None:
        self.assertTrue(is_acceptable_content_type("Application/JSON"))

    def test_cors_safelisted_content_types_are_rejected(self) -> None:
        # These are exactly the three types a browser will send
        # cross-origin *without* a CORS preflight -- see
        # is_acceptable_content_type's own docstring for why accepting
        # any of these here would make CORS configuration toothless.
        for content_type in (
            "application/x-www-form-urlencoded",
            "multipart/form-data; boundary=----x",
            "text/plain",
        ):
            with self.subTest(content_type=content_type):
                self.assertFalse(is_acceptable_content_type(content_type))

    def test_missing_or_empty_content_type_is_rejected(self) -> None:
        self.assertFalse(is_acceptable_content_type(""))


class HttpStatusForTests(unittest.TestCase):
    def test_known_statuses_map_to_expected_codes(self) -> None:
        expectations = {
            SignupResponseStatus.SUCCESS: 201,
            SignupResponseStatus.ALREADY_SUBSCRIBED: 200,
            SignupResponseStatus.VALIDATION_ERROR: 400,
            SignupResponseStatus.CONFIG_ERROR: 503,
            SignupResponseStatus.API_ERROR: 502,
            SignupResponseStatus.RATE_LIMITED: 429,
        }
        for status, expected_code in expectations.items():
            with self.subTest(status=status):
                self.assertEqual(http_status_for(status), expected_code)

    def test_unknown_status_falls_back_to_500(self) -> None:
        self.assertEqual(http_status_for("something_new"), 500)


class ResponseBodyForSignupResultTests(unittest.TestCase):
    def test_confirmation_sent_maps_to_success(self) -> None:
        body = response_body_for_signup_result(SignupOutcome.CONFIRMATION_SENT, "Fast geschafft!")
        self.assertEqual(body, {"status": SignupResponseStatus.SUCCESS, "message": "Fast geschafft!"})

    def test_already_pending_maps_to_already_subscribed(self) -> None:
        body = response_body_for_signup_result(
            SignupOutcome.ALREADY_PENDING_OR_CONFIRMED, "bereits angemeldet"
        )
        self.assertEqual(body["status"], SignupResponseStatus.ALREADY_SUBSCRIBED)

    def test_invalid_email_maps_to_validation_error(self) -> None:
        body = response_body_for_signup_result(SignupOutcome.INVALID_EMAIL, "ungültig")
        self.assertEqual(body["status"], SignupResponseStatus.VALIDATION_ERROR)

    def test_config_missing_maps_to_config_error(self) -> None:
        body = response_body_for_signup_result(SignupOutcome.CONFIG_MISSING, "nicht verfügbar")
        self.assertEqual(body["status"], SignupResponseStatus.CONFIG_ERROR)

    def test_error_maps_to_api_error(self) -> None:
        body = response_body_for_signup_result(SignupOutcome.ERROR, "Fehler")
        self.assertEqual(body["status"], SignupResponseStatus.API_ERROR)

    def test_unrecognized_outcome_falls_back_to_api_error(self) -> None:
        body = response_body_for_signup_result("something_new", "msg")
        self.assertEqual(body["status"], SignupResponseStatus.API_ERROR)

    def test_unrecognized_outcome_uses_a_fixed_message_not_the_provided_one(self) -> None:
        # The message accompanying an outcome this mapping doesn't
        # recognize hasn't been vetted as safe to expose -- must not be
        # passed through verbatim, unlike the recognized-outcome path.
        body = response_body_for_signup_result(
            "something_new", "a message this endpoint has never reviewed"
        )
        self.assertNotEqual(body["message"], "a message this endpoint has never reviewed")

    def test_message_is_passed_through_unchanged(self) -> None:
        body = response_body_for_signup_result(SignupOutcome.CONFIRMATION_SENT, "exact copy")
        self.assertEqual(body["message"], "exact copy")


if __name__ == "__main__":
    unittest.main()
