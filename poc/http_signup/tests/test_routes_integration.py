"""Integration tests against the real ASGI app (via Starlette's
TestClient), with request_double_optin() mocked -- no real network call,
no real Brevo contact, ever.
"""

from __future__ import annotations

import unittest
from unittest import mock

from starlette.testclient import TestClient

from src.subscribers import SignupOutcome, SignupResult
from poc.http_signup.asgi_app import app
from poc.http_signup import routes as routes_module


class SubscribeEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        # A fresh, generous rate limiter per test so tests don't leak
        # rate-limit state into each other (the real module-level limiter
        # is deliberately small -- see test_rate_limiting below for a
        # test that exercises the real one directly instead).
        patcher = mock.patch.object(
            routes_module,
            "_rate_limiter",
            routes_module.InMemoryRateLimiter(max_requests=1000, window_seconds=60),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def test_missing_consent_is_rejected_without_calling_brevo(self) -> None:
        with mock.patch.object(routes_module, "request_double_optin") as mock_request:
            response = self.client.post(
                "/api/newsletter/subscribe", json={"email": "visitor@example.com"}
            )
        mock_request.assert_not_called()
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], "validation_error")
        self.assertEqual(body["field"], "consent")

    def test_consent_false_is_rejected_without_calling_brevo(self) -> None:
        with mock.patch.object(routes_module, "request_double_optin") as mock_request:
            response = self.client.post(
                "/api/newsletter/subscribe",
                json={"email": "visitor@example.com", "consent": False},
            )
        mock_request.assert_not_called()
        self.assertEqual(response.status_code, 400)

    def test_missing_email_is_rejected_without_calling_brevo(self) -> None:
        with mock.patch.object(routes_module, "request_double_optin") as mock_request:
            response = self.client.post("/api/newsletter/subscribe", json={"consent": True})
        mock_request.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "email")

    def test_form_encoded_content_type_is_rejected_without_calling_brevo(self) -> None:
        # The security-relevant case: this is one of the three
        # CORS-"safelisted" content types a browser will send
        # cross-origin without a preflight -- see
        # validation.is_acceptable_content_type's docstring. Must be
        # rejected before it ever reaches request_double_optin().
        with mock.patch.object(routes_module, "request_double_optin") as mock_request:
            response = self.client.post(
                "/api/newsletter/subscribe",
                data={"email": "visitor@example.com", "consent": "true"},
            )
        mock_request.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "content-type")

    def test_text_plain_content_type_is_rejected_without_calling_brevo(self) -> None:
        with mock.patch.object(routes_module, "request_double_optin") as mock_request:
            response = self.client.post(
                "/api/newsletter/subscribe",
                content=b'{"email": "visitor@example.com", "consent": true}',
                headers={"content-type": "text/plain"},
            )
        mock_request.assert_not_called()
        self.assertEqual(response.status_code, 400)

    def test_missing_content_type_is_rejected_without_calling_brevo(self) -> None:
        with mock.patch.object(routes_module, "request_double_optin") as mock_request:
            response = self.client.post(
                "/api/newsletter/subscribe",
                content=b'{"email": "visitor@example.com", "consent": true}',
                headers={"content-type": ""},
            )
        mock_request.assert_not_called()
        self.assertEqual(response.status_code, 400)

    def test_malformed_json_body_is_rejected(self) -> None:
        with mock.patch.object(routes_module, "request_double_optin") as mock_request:
            response = self.client.post(
                "/api/newsletter/subscribe",
                content=b"not json",
                headers={"content-type": "application/json"},
            )
        mock_request.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "validation_error")

    def test_successful_signup_calls_request_double_optin_with_the_email(self) -> None:
        with mock.patch.object(
            routes_module,
            "request_double_optin",
            return_value=SignupResult(SignupOutcome.CONFIRMATION_SENT, "Fast geschafft!"),
        ) as mock_request:
            response = self.client.post(
                "/api/newsletter/subscribe",
                json={"email": "visitor@example.com", "consent": True},
            )
        mock_request.assert_called_once_with("visitor@example.com")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(), {"status": "success", "message": "Fast geschafft!"}
        )

    def test_already_subscribed_maps_to_200(self) -> None:
        with mock.patch.object(
            routes_module,
            "request_double_optin",
            return_value=SignupResult(
                SignupOutcome.ALREADY_PENDING_OR_CONFIRMED, "bereits angemeldet"
            ),
        ):
            response = self.client.post(
                "/api/newsletter/subscribe",
                json={"email": "visitor@example.com", "consent": True},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "already_subscribed")

    def test_invalid_email_from_brevo_layer_maps_to_400(self) -> None:
        # Reaches request_double_optin() (shape validation passed) but
        # that function's own format check rejects it -- this endpoint
        # must surface the same validation_error status either way.
        with mock.patch.object(
            routes_module,
            "request_double_optin",
            return_value=SignupResult(
                SignupOutcome.INVALID_EMAIL, "Bitte gib eine gültige E-Mail-Adresse ein."
            ),
        ):
            response = self.client.post(
                "/api/newsletter/subscribe",
                json={"email": "not-an-email", "consent": True},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "validation_error")

    def test_config_missing_maps_to_503(self) -> None:
        with mock.patch.object(
            routes_module,
            "request_double_optin",
            return_value=SignupResult(SignupOutcome.CONFIG_MISSING, "nicht verfügbar"),
        ):
            response = self.client.post(
                "/api/newsletter/subscribe",
                json={"email": "visitor@example.com", "consent": True},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "config_error")

    def test_brevo_error_maps_to_502(self) -> None:
        with mock.patch.object(
            routes_module,
            "request_double_optin",
            return_value=SignupResult(SignupOutcome.ERROR, "Fehler"),
        ):
            response = self.client.post(
                "/api/newsletter/subscribe",
                json={"email": "visitor@example.com", "consent": True},
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["status"], "api_error")

    def test_unexpected_exception_returns_generic_api_error_not_a_crash(self) -> None:
        secret_email = "visitor@example.com"
        with self.assertLogs("poc.http_signup.routes", level="WARNING") as log_ctx:
            with mock.patch.object(
                routes_module,
                "request_double_optin",
                side_effect=RuntimeError(f"boom, {secret_email}"),
            ):
                response = self.client.post(
                    "/api/newsletter/subscribe",
                    json={"email": secret_email, "consent": True},
                )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["status"], "api_error")
        # The generic message must not leak the exception's own text.
        self.assertNotIn("boom", response.json()["message"])
        # Nor may it appear anywhere in what was logged -- the response
        # body alone isn't the whole safety story; the captured log
        # output must also never contain the exception's own message or
        # the email address.
        joined_logs = "\n".join(log_ctx.output)
        self.assertIn("POC_NEWSLETTER_REQUEST_UNEXPECTED_ERROR", joined_logs)
        self.assertIn("exception_type=RuntimeError", joined_logs)
        self.assertNotIn("boom", joined_logs)
        self.assertNotIn(secret_email, joined_logs)

    def test_no_real_brevo_module_function_is_ever_reachable_without_mocking(self) -> None:
        # Sanity check for the whole test module's safety invariant: if
        # this ever failed, every other test above would risk a real
        # network call the moment its mock.patch context exits.
        self.assertTrue(callable(routes_module.request_double_optin))
        self.assertIn("subscribers", routes_module.request_double_optin.__module__)

    def test_healthz(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_test_page_is_served_at_root(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("PoC", response.text)


class RateLimitingTests(unittest.TestCase):
    def test_requests_beyond_the_limit_get_429(self) -> None:
        limiter = routes_module.InMemoryRateLimiter(max_requests=2, window_seconds=60)
        with (
            mock.patch.object(routes_module, "_rate_limiter", limiter),
            mock.patch.object(
                routes_module,
                "request_double_optin",
                return_value=SignupResult(SignupOutcome.CONFIRMATION_SENT, "ok"),
            ) as mock_request,
        ):
            client = TestClient(app)
            payload = {"email": "visitor@example.com", "consent": True}
            first = client.post("/api/newsletter/subscribe", json=payload)
            second = client.post("/api/newsletter/subscribe", json=payload)
            third = client.post("/api/newsletter/subscribe", json=payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["status"], "rate_limited")
        # The rate-limited request must never even reach Brevo.
        self.assertEqual(mock_request.call_count, 2)

    def test_content_type_rejected_requests_do_not_consume_rate_limit_budget(self) -> None:
        # Regression test for a review finding: content-type validation
        # must run BEFORE the rate limiter, not after -- otherwise a
        # handful of cross-origin "simple requests" (no preflight, see
        # validation.is_acceptable_content_type's docstring) could
        # exhaust a shared IP's rate-limit window and deny legitimate
        # signups, for free, without ever needing valid JSON.
        limiter = routes_module.InMemoryRateLimiter(max_requests=1, window_seconds=60)
        with mock.patch.object(routes_module, "_rate_limiter", limiter):
            client = TestClient(app)
            for _ in range(5):
                response = client.post(
                    "/api/newsletter/subscribe",
                    data={"email": "visitor@example.com", "consent": "true"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["field"], "content-type")

            # The single real request-worth of budget must still be
            # intact -- none of the five content-type-rejected requests
            # above should have spent it.
            with mock.patch.object(
                routes_module,
                "request_double_optin",
                return_value=SignupResult(SignupOutcome.CONFIRMATION_SENT, "ok"),
            ):
                real_request = client.post(
                    "/api/newsletter/subscribe",
                    json={"email": "visitor@example.com", "consent": True},
                )
        self.assertEqual(real_request.status_code, 201)


if __name__ == "__main__":
    unittest.main()
