"""Interactive newsletter signup flow: loading/disabled state, and the
signup result banner persisting across reruns that are not themselves a
new submission.

See also tests/test_app_newsletter_gate.py (legal-readiness gating) and
tests/test_subscribers.py (Brevo request behaviour). This module covers
only the app.py-level state machine wired around
``request_double_optin``.
"""

from __future__ import annotations

import unittest
from unittest import mock

import app
from src.subscribers import SignupOutcome, SignupResult


class NewsletterSignupFlowTests(unittest.TestCase):
    def _run(self, mock_st: mock.MagicMock, *, submitted: bool, consent: bool = True) -> None:
        mock_st.form_submit_button.return_value = submitted
        mock_st.checkbox.return_value = consent
        with mock.patch("app.is_legal_content_ready", return_value=True):
            app.render_newsletter_signup_section()

    def test_first_submit_stores_pending_email_and_reruns_without_calling_backend(self) -> None:
        with (
            mock.patch("app.st") as mock_st,
            mock.patch("app.request_double_optin") as mock_request,
        ):
            mock_st.session_state = {}
            mock_st.text_input.return_value = "visitor@example.com"
            self._run(mock_st, submitted=True, consent=True)

        mock_request.assert_not_called()
        self.assertEqual(
            mock_st.session_state[app._NEWSLETTER_PENDING_EMAIL_KEY], "visitor@example.com"
        )
        mock_st.rerun.assert_called_once()

    def test_consent_not_given_shows_warning_immediately_without_pending_state(self) -> None:
        with (
            mock.patch("app.st") as mock_st,
            mock.patch("app.request_double_optin") as mock_request,
        ):
            mock_st.session_state = {}
            mock_st.text_input.return_value = "visitor@example.com"
            self._run(mock_st, submitted=True, consent=False)

        mock_request.assert_not_called()
        mock_st.rerun.assert_not_called()
        self.assertIsNone(mock_st.session_state.get(app._NEWSLETTER_PENDING_EMAIL_KEY))
        mock_st.warning.assert_called_once_with(
            "Bitte bestätige, dass du die Datenschutzerklärung gelesen hast."
        )

    def test_pending_state_disables_the_form_and_shows_a_loading_label(self) -> None:
        with mock.patch("app.st") as mock_st:
            mock_st.session_state = {app._NEWSLETTER_PENDING_EMAIL_KEY: "visitor@example.com"}
            mock_st.form_submit_button.return_value = False
            with mock.patch(
                "app.request_double_optin",
                return_value=SignupResult(SignupOutcome.CONFIRMATION_SENT, "ok"),
            ):
                with mock.patch("app.is_legal_content_ready", return_value=True):
                    app.render_newsletter_signup_section()

        self.assertTrue(mock_st.text_input.call_args.kwargs["disabled"])
        self.assertTrue(mock_st.checkbox.call_args.kwargs["disabled"])
        submit_call = mock_st.form_submit_button.call_args
        self.assertEqual(submit_call.args[0], "Wird gesendet …")
        self.assertTrue(submit_call.kwargs["disabled"])

    def test_pending_state_calls_backend_inside_a_spinner_and_stores_the_result(self) -> None:
        # Not just "both were called": the Brevo request must happen
        # *between* the spinner's __enter__ and __exit__, so the loading
        # indicator is actually visible for the duration of the call.
        call_order: list[str] = []

        def fake_request(email: str) -> SignupResult:
            call_order.append("request")
            return SignupResult(SignupOutcome.CONFIRMATION_SENT, "Fast geschafft!")

        with (
            mock.patch("app.st") as mock_st,
            mock.patch("app.request_double_optin", side_effect=fake_request) as mock_request,
        ):
            mock_st.session_state = {app._NEWSLETTER_PENDING_EMAIL_KEY: "visitor@example.com"}
            mock_st.form_submit_button.return_value = False
            mock_st.spinner.return_value.__enter__.side_effect = (
                lambda: call_order.append("spinner_enter")
            )
            mock_st.spinner.return_value.__exit__.side_effect = (
                lambda *args: call_order.append("spinner_exit")
            )
            with mock.patch("app.is_legal_content_ready", return_value=True):
                app.render_newsletter_signup_section()

        mock_request.assert_called_once_with("visitor@example.com")
        self.assertEqual(call_order, ["spinner_enter", "request", "spinner_exit"])
        self.assertIsNone(mock_st.session_state[app._NEWSLETTER_PENDING_EMAIL_KEY])
        self.assertEqual(
            mock_st.session_state[app._NEWSLETTER_RESULT_KEY],
            {"outcome": SignupOutcome.CONFIRMATION_SENT, "message": "Fast geschafft!"},
        )
        mock_st.rerun.assert_called_once()

    def test_result_banner_persists_across_a_later_rerun_that_is_not_a_new_submission(self) -> None:
        """Regression test for the reported bug: the confirmation must
        still be visible on a rerun triggered by something other than the
        signup form itself (e.g. an unrelated widget elsewhere on the
        page), not just for the one script run that produced it.
        """
        with (
            mock.patch("app.st") as mock_st,
            mock.patch("app.request_double_optin") as mock_request,
        ):
            mock_st.session_state = {
                app._NEWSLETTER_RESULT_KEY: {
                    "outcome": SignupOutcome.CONFIRMATION_SENT,
                    "message": "Fast geschafft!",
                }
            }
            self._run(mock_st, submitted=False)

        mock_request.assert_not_called()
        mock_st.success.assert_called_once_with("Fast geschafft!")

    def test_outcomes_map_to_the_expected_banner_type(self) -> None:
        cases = [
            (SignupOutcome.CONFIRMATION_SENT, "success"),
            (SignupOutcome.ALREADY_PENDING_OR_CONFIRMED, "info"),
            (SignupOutcome.INVALID_EMAIL, "warning"),
            (SignupOutcome.CONFIG_MISSING, "error"),
            (SignupOutcome.ERROR, "error"),
            (app._CONSENT_REQUIRED_OUTCOME, "warning"),
        ]
        for outcome, expected_method in cases:
            with self.subTest(outcome=outcome):
                with mock.patch("app.st") as mock_st:
                    mock_st.session_state = {
                        app._NEWSLETTER_RESULT_KEY: {"outcome": outcome, "message": "msg"}
                    }
                    self._run(mock_st, submitted=False)
                getattr(mock_st, expected_method).assert_called_once_with("msg")

    def test_no_banner_before_any_submission(self) -> None:
        with mock.patch("app.st") as mock_st:
            mock_st.session_state = {}
            self._run(mock_st, submitted=False)
        mock_st.success.assert_not_called()
        mock_st.info.assert_not_called()
        mock_st.warning.assert_not_called()
        mock_st.error.assert_not_called()

    def test_unexpected_exception_during_request_shows_generic_error_and_clears_pending(
        self,
    ) -> None:
        """Regression test for the production incident: request_double_optin()
        is documented to never raise, but if something unexpected does raise
        anyway, the visitor must still see a result -- never silence.
        """
        with (
            mock.patch("app.st") as mock_st,
            mock.patch("app.request_double_optin", side_effect=RuntimeError("boom")),
        ):
            mock_st.session_state = {app._NEWSLETTER_PENDING_EMAIL_KEY: "visitor@example.com"}
            mock_st.form_submit_button.return_value = False
            with mock.patch("app.is_legal_content_ready", return_value=True):
                app.render_newsletter_signup_section()

        self.assertIsNone(mock_st.session_state[app._NEWSLETTER_PENDING_EMAIL_KEY])
        stored = mock_st.session_state[app._NEWSLETTER_RESULT_KEY]
        self.assertEqual(stored["outcome"], SignupOutcome.ERROR)
        self.assertEqual(stored["message"], app._NEWSLETTER_UNEXPECTED_ERROR_MESSAGE)
        self.assertNotIn("boom", stored["message"])
        mock_st.rerun.assert_called_once()

    def test_diagnostic_log_markers_are_emitted_without_the_email_address(self) -> None:
        """Regression test for the production incident: Railway's runtime
        logs showed only NEWSLETTER_RUNTIME_GATE and nothing between a
        submit and the (missing) Brevo request -- there was no observability
        into this flow at all. These markers close that gap; this test also
        pins down that the email address itself is never logged.
        """
        secret_email = "secret-visitor@example.com"
        markers = (
            "NEWSLETTER_FORM_RENDER",
            "NEWSLETTER_SUBMIT_RECEIVED",
            "NEWSLETTER_PENDING_SET",
            "NEWSLETTER_REQUEST_START",
            "NEWSLETTER_REQUEST_RESULT",
            "NEWSLETTER_RERUN_TRIGGERED",
        )

        def marker_sequence(log_lines: list[str]) -> list[str]:
            found = []
            for line in log_lines:
                for marker in markers:
                    if marker in line:
                        found.append(marker)
                        break
            return found

        with self.assertLogs("app", level="WARNING") as log_ctx:
            with (
                mock.patch("app.st") as mock_st,
                mock.patch("app.request_double_optin") as mock_request,
            ):
                mock_st.session_state = {}
                mock_st.text_input.return_value = secret_email
                self._run(mock_st, submitted=True, consent=True)
        mock_request.assert_not_called()
        submit_phase_log = "\n".join(log_ctx.output)
        self.assertEqual(
            marker_sequence(log_ctx.output),
            ["NEWSLETTER_FORM_RENDER", "NEWSLETTER_SUBMIT_RECEIVED", "NEWSLETTER_PENDING_SET",
             "NEWSLETTER_RERUN_TRIGGERED"],
        )
        self.assertNotIn(secret_email, submit_phase_log)

        with self.assertLogs("app", level="WARNING") as log_ctx:
            with (
                mock.patch("app.st") as mock_st,
                mock.patch(
                    "app.request_double_optin",
                    return_value=SignupResult(SignupOutcome.CONFIRMATION_SENT, "ok"),
                ),
            ):
                mock_st.session_state = {app._NEWSLETTER_PENDING_EMAIL_KEY: secret_email}
                mock_st.form_submit_button.return_value = False
                with mock.patch("app.is_legal_content_ready", return_value=True):
                    app.render_newsletter_signup_section()
        request_phase_log = "\n".join(log_ctx.output)
        self.assertEqual(
            marker_sequence(log_ctx.output),
            ["NEWSLETTER_FORM_RENDER", "NEWSLETTER_REQUEST_START",
             "NEWSLETTER_REQUEST_RESULT", "NEWSLETTER_RERUN_TRIGGERED"],
        )
        self.assertIn(
            f"NEWSLETTER_REQUEST_RESULT result={SignupOutcome.CONFIRMATION_SENT}",
            request_phase_log,
        )
        self.assertNotIn(secret_email, request_phase_log)

    def test_diagnostic_log_marker_on_unexpected_exception_carries_no_email(self) -> None:
        # Worst case for the reviewed leak risk: the exception's own message
        # (not just app.py's own code) contains the email address, e.g. a
        # hypothetical future bug in request_double_optin() that lets a
        # network-library exception carrying the request URL escape its
        # current catch-all. The fix must not leak it even then.
        secret_email = "secret-visitor@example.com"

        with self.assertLogs("app", level="WARNING") as log_ctx:
            with (
                mock.patch("app.st") as mock_st,
                mock.patch(
                    "app.request_double_optin",
                    side_effect=RuntimeError(f"connection failed for {secret_email}"),
                ),
            ):
                mock_st.session_state = {app._NEWSLETTER_PENDING_EMAIL_KEY: secret_email}
                mock_st.form_submit_button.return_value = False
                with mock.patch("app.is_legal_content_ready", return_value=True):
                    app.render_newsletter_signup_section()
        joined = "\n".join(log_ctx.output)
        self.assertIn("NEWSLETTER_REQUEST_UNEXPECTED_ERROR", joined)
        self.assertIn("exception_type=RuntimeError", joined)
        self.assertNotIn(secret_email, joined)
        self.assertNotIn("connection failed", joined)

    def test_unknown_outcome_is_logged_as_unknown_not_leaked_verbatim(self) -> None:
        # Defense in depth: if request_double_optin()'s contract were ever
        # broken and it returned an outcome code outside the known set, the
        # log line must not just pass that value through verbatim.
        with self.assertLogs("app", level="WARNING") as log_ctx:
            with (
                mock.patch("app.st") as mock_st,
                mock.patch(
                    "app.request_double_optin",
                    return_value=SignupResult("totally_unexpected_code", "msg"),
                ),
            ):
                mock_st.session_state = {
                    app._NEWSLETTER_PENDING_EMAIL_KEY: "visitor@example.com"
                }
                mock_st.form_submit_button.return_value = False
                with mock.patch("app.is_legal_content_ready", return_value=True):
                    app.render_newsletter_signup_section()
        joined = "\n".join(log_ctx.output)
        self.assertIn("NEWSLETTER_REQUEST_RESULT result=unknown", joined)
        self.assertNotIn("totally_unexpected_code", joined)


if __name__ == "__main__":
    unittest.main()
