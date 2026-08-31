"""AC5: the newsletter signup section, the footer, and the
Datenschutzerklaerung route must never render anything -- not even a
placeholder -- unless the newsletter feature is legal-ready.
"""

from __future__ import annotations

import unittest
from unittest import mock

import app


class NewsletterGateTests(unittest.TestCase):
    def test_signup_section_renders_nothing_when_not_legal_ready(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=False),
            mock.patch("app.st") as mock_st,
        ):
            app.render_newsletter_signup_section()
        self.assertEqual(len(mock_st.method_calls), 0)

    def test_footer_renders_nothing_when_not_legal_ready(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=False),
            mock.patch("app.st") as mock_st,
        ):
            app.render_public_footer()
        self.assertEqual(len(mock_st.method_calls), 0)

    def test_signup_section_renders_something_when_legal_ready(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=True),
            mock.patch("app.st") as mock_st,
        ):
            mock_st.form_submit_button.return_value = False
            app.render_newsletter_signup_section()
        mock_st.subheader.assert_called_once_with("DiGA Tracker Alerts abonnieren")

    def test_footer_links_to_datenschutz_view_when_legal_ready(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=True),
            mock.patch("app.st") as mock_st,
        ):
            app.render_public_footer()
        markdown_html = mock_st.markdown.call_args.args[0]
        self.assertIn("?view=datenschutz", markdown_html)

    def test_confirmation_page_reports_completed_double_optin(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=True),
            mock.patch("app.st") as mock_st,
        ):
            app.render_subscription_confirmed_page()
        mock_st.success.assert_called_once_with("Deine Anmeldung ist bestätigt.")

    def test_confirmation_page_renders_nothing_when_not_legal_ready(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=False),
            mock.patch("app.st") as mock_st,
        ):
            app.render_subscription_confirmed_page()
        self.assertEqual(len(mock_st.method_calls), 0)

    def test_datenschutz_page_never_reached_without_a_complete_profile(self) -> None:
        # Defensive branch: even if somehow called while not ready, it
        # must render nothing rather than a partial page.
        with (
            mock.patch("app.load_operator_profile", return_value=None),
            mock.patch("app.st") as mock_st,
        ):
            app.render_datenschutz_page()
        self.assertEqual(len(mock_st.method_calls), 0)

    def test_no_placeholder_marker_ever_appears_in_source(self) -> None:
        with open("app.py", "r", encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("INPUT ERFORDERLICH", source)


if __name__ == "__main__":
    unittest.main()
