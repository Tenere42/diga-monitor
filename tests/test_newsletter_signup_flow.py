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


if __name__ == "__main__":
    unittest.main()
