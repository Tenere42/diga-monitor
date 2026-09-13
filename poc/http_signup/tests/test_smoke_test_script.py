"""Tests for the safety-guard logic in scripts/smoke_test_production.py.

This script is deliberately NOT run by any automated test suite in
normal operation (it makes real HTTP requests and can trigger a real
email) -- these tests exercise only its argument-validation and
safety-refusal logic, with all actual network I/O mocked out. No test
here ever calls a real URL.
"""

from __future__ import annotations

import sys
import unittest
from unittest import mock

from poc.http_signup.scripts import smoke_test_production as script


def _run_with_args(args: list[str]) -> int:
    with mock.patch.object(sys, "argv", ["smoke_test_production.py", *args]):
        return script.main()


class HealthcheckGatingTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(
            script, "_get", return_value=(200, {"status": "ok"}, '{"status": "ok"}')
        )
        self.mock_get = patcher.start()
        self.addCleanup(patcher.stop)
        post_patcher = mock.patch.object(script, "_post_json")
        self.mock_post = post_patcher.start()
        self.addCleanup(post_patcher.stop)

    def test_healthcheck_only_never_calls_post(self) -> None:
        exit_code = _run_with_args(
            ["--url", "https://example.invalid", "--healthcheck-only"]
        )
        self.assertEqual(exit_code, 0)
        self.mock_post.assert_not_called()

    def test_email_without_send_refuses_to_post(self) -> None:
        exit_code = _run_with_args(
            ["--url", "https://example.invalid", "--email", "you@example.com"]
        )
        self.assertEqual(exit_code, 0)
        self.mock_post.assert_not_called()

    def test_send_actually_posts_with_the_given_email(self) -> None:
        self.mock_post.return_value = (
            201,
            {"status": "success", "message": "ok"},
            '{"status": "success", "message": "ok"}',
        )
        exit_code = _run_with_args(
            [
                "--url",
                "https://example.invalid",
                "--email",
                "you@example.com",
                "--send",
            ]
        )
        self.assertEqual(exit_code, 0)
        self.mock_post.assert_called_once()
        called_url, called_payload = self.mock_post.call_args.args[0], self.mock_post.call_args.args[1]
        self.assertEqual(called_url, "https://example.invalid/api/newsletter/subscribe")
        self.assertEqual(called_payload, {"email": "you@example.com", "consent": True})

    def test_missing_url_is_a_hard_error_without_any_request(self) -> None:
        with self.assertRaises(SystemExit):
            _run_with_args(["--healthcheck-only"])
        self.mock_get.assert_not_called()
        self.mock_post.assert_not_called()

    def test_missing_email_without_healthcheck_only_is_a_hard_error(self) -> None:
        # Regression test (raised in review): email is required *before*
        # the health check runs, not discovered partway through -- a
        # missing required argument must have zero network side effects.
        with self.assertRaises(SystemExit):
            _run_with_args(["--url", "https://example.invalid"])
        self.mock_get.assert_not_called()
        self.mock_post.assert_not_called()

    def test_already_subscribed_is_reported_distinctly_from_a_fresh_success(self) -> None:
        # Regression test (raised in review): HTTP 200/already_subscribed
        # must be told apart from HTTP 201/success -- an already
        # pending/confirmed address may not receive a *new* DOI email,
        # so instructing the operator to "check your inbox" the same way
        # would be misleading about what was actually validated.
        self.mock_post.return_value = (
            200,
            {"status": "already_subscribed", "message": "already there"},
            '{"status": "already_subscribed", "message": "already there"}',
        )
        with mock.patch("builtins.print") as mock_print:
            exit_code = _run_with_args(
                [
                    "--url",
                    "https://example.invalid",
                    "--email",
                    "you@example.com",
                    "--send",
                ]
            )
        self.assertEqual(exit_code, 0)
        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("already", printed.lower())
        self.assertNotIn("NEW double-opt-in email should have been triggered", printed)

    def test_failed_healthcheck_stops_before_any_post(self) -> None:
        self.mock_get.return_value = (503, None, "service unavailable")
        exit_code = _run_with_args(
            [
                "--url",
                "https://example.invalid",
                "--email",
                "you@example.com",
                "--send",
            ]
        )
        self.assertEqual(exit_code, 1)
        self.mock_post.assert_not_called()

    def test_env_var_fallbacks_are_honored(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "POC_SMOKE_TEST_URL": "https://example.invalid",
                "POC_SMOKE_TEST_EMAIL": "you@example.com",
            },
        ):
            exit_code = _run_with_args(["--healthcheck-only"])
        self.assertEqual(exit_code, 0)
        self.mock_get.assert_called_once_with("https://example.invalid/healthz", timeout=mock.ANY)


if __name__ == "__main__":
    unittest.main()
