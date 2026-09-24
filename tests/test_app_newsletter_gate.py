"""Newsletter signup stays gated; public legal pages are always accessible."""

from __future__ import annotations

import unittest
from unittest import mock

import app


class NewsletterGateTests(unittest.TestCase):
    def test_router_registers_public_impressum_and_runs_selected_page(self) -> None:
        with mock.patch("app.st") as streamlit:
            app.main()
        streamlit.Page.assert_any_call(app.render_impressum_page, title="Impressum", url_path="impressum")
        streamlit.Page.assert_any_call(app.render_privacy_route, title="Datenschutz", url_path="datenschutz")
        streamlit.Page.assert_any_call(app.render_license_route, title="Lizenz & Copyright", url_path="lizenz")
        streamlit.navigation.return_value.run.assert_called_once_with()
        streamlit.set_page_config.assert_called_once_with(page_title="DiGA Tracker", layout="wide")

    def test_signup_section_renders_nothing_when_not_legal_ready(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=False),
            mock.patch("app.st") as mock_st,
        ):
            app.render_newsletter_signup_section()
        self.assertEqual(len(mock_st.method_calls), 0)

    def test_footer_keeps_all_legal_links_public(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=False),
            mock.patch("app.st") as mock_st,
        ):
            app.render_public_footer()
        markup = mock_st.markdown.call_args.args[0]
        self.assertIn('href="/impressum"', markup)
        self.assertIn('href="/datenschutz"', markup)
        self.assertIn('href="/lizenz"', markup)
        self.assertNotIn('Cookie Einstellungen', markup)

    def test_signup_section_renders_something_when_legal_ready(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=True),
            mock.patch("app.st") as mock_st,
        ):
            mock_st.session_state = {}
            mock_st.form_submit_button.return_value = False
            app.render_newsletter_signup_section()
        mock_st.subheader.assert_called_once_with("Keine Änderung verpassen.")

    def test_footer_links_to_datenschutz_view_when_legal_ready(self) -> None:
        with (
            mock.patch("app.is_legal_content_ready", return_value=True),
            mock.patch("app.st") as mock_st,
        ):
            app.render_public_footer()
        markdown_html = mock_st.markdown.call_args.args[0]
        self.assertIn('href="/datenschutz"', markdown_html)

    def test_datenschutz_page_is_public_without_newsletter_profile(self) -> None:
        with (
            mock.patch("app.load_operator_profile", return_value=None),
            mock.patch("app.st") as mock_st,
        ):
            app.render_datenschutz_page()
        mock_st.title.assert_called_once_with("Datenschutz")
        self.assertIn("Leevsten GmbH", mock_st.markdown.call_args.args[0])

    def test_privacy_notice_contains_confirmed_tracking_without_public_todos(self) -> None:
        from pathlib import Path
        text = (Path(app.__file__).parent / "content/legal/datenschutz.md").read_text(encoding="utf-8")
        for phrase in ("noch zu", "noch nicht", "offener rechtlicher Prüfpunkt", "EU-Vertretung"):
            self.assertNotIn(phrase, text)
        self.assertIn("Öffnungs- und Klickmessung", text)
        self.assertIn("datenschutz@diga-tracker.de", text)

    def test_no_placeholder_marker_ever_appears_in_source(self) -> None:
        with open("app.py", "r", encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("INPUT ERFORDERLICH", source)


if __name__ == "__main__":
    unittest.main()
