"""Presentation contracts; no network, Brevo calls, or production state."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import app
from streamlit.testing.v1 import AppTest
from src.ui import diff_text_html, public_header_html, stylesheet_html


class PresentationTests(unittest.TestCase):
    def test_stylesheet_loads_independently_of_working_directory(self) -> None:
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                self.assertIn('--content-max-width:', stylesheet_html())
            finally:
                os.chdir(previous)

    def test_public_header_has_only_product_home_link(self) -> None:
        markup = public_header_html()
        self.assertIn('>DiGA Tracker</a>', markup)
        self.assertNotIn('DiGA Monitor', markup)
        self.assertIn('href="./"', markup)
        self.assertEqual(markup.count('<a '), 1)
        self.assertNotIn('Menü', markup)
        self.assertNotIn('<details', markup)

    def test_diff_text_is_escaped_and_explained_without_color(self) -> None:
        for removed, tag, label in ((True, 'del', 'Entfernt'), (False, 'ins', 'Ergänzt')):
            with self.subTest(removed=removed):
                markup = diff_text_html('<script>&', removed=removed)
                self.assertIn(f'<{tag} ', markup)
                self.assertIn(f'{label}: ', markup)
                self.assertIn('&lt;script&gt;&amp;', markup)
                self.assertNotIn('<script>', markup)

    def test_diff_columns_keep_before_after_operations(self) -> None:
        tokens = [
            {'op': 'equal', 'text': 'Kontext'},
            {'op': 'delete', 'text': 'alt'},
            {'op': 'insert', 'text': 'neu'},
        ]
        before, after, _ = app.compact_text_diff(tokens)
        before_html = app.render_diff_column(before, 'before')
        after_html = app.render_diff_column(after, 'after')
        self.assertIn('<del ', before_html)
        self.assertNotIn('<ins ', before_html)
        self.assertIn('<ins ', after_html)
        self.assertNotIn('<del ', after_html)
        self.assertIn('Kontext', before_html)
        self.assertIn('Kontext', after_html)

    def test_status_labels_remain_visible_and_non_color_cues_differ(self) -> None:
        for label, cue in (('Vorläufig aufgenommen', 'dashed'),
                           ('Dauerhaft aufgenommen', 'solid'),
                           ('Gestrichen', 'line-through')):
            with self.subTest(label=label):
                markup = app.render_inline_value(label)
                self.assertIn(label, markup)
                self.assertIn(cue, markup)
        self.assertEqual(app.render_inline_value('<unbekannt>'), '&lt;unbekannt&gt;')

    def test_legal_routes_keep_gate_and_do_not_load_feed_or_submit(self) -> None:
        for view, renderer in (('datenschutz', 'render_datenschutz_page'),
                               ('confirmed', 'render_subscription_confirmed_page')):
            with (
                self.subTest(view=view),
                mock.patch('app.st') as streamlit,
                mock.patch('app.is_legal_content_ready', return_value=True),
                mock.patch('app.' + renderer) as render,
                mock.patch('app.render_page_header'),
                mock.patch('app.render_public_footer') as footer,
                mock.patch('app.load_dashboard_data') as load,
                mock.patch('app.request_double_optin') as submit,
            ):
                streamlit.query_params = {'view': view}
                app.main()
                streamlit.set_page_config.assert_called_once_with(page_title='DiGA Tracker', layout='wide')
                self.assertIn('<style>', streamlit.markdown.call_args.args[0])
                render.assert_called_once_with()
                footer.assert_called_once_with()
                load.assert_not_called()
                submit.assert_not_called()

    def test_unready_legal_routes_still_fall_through_to_dashboard(self) -> None:
        for view in ('datenschutz', 'confirmed'):
            with (
                self.subTest(view=view),
                mock.patch('app.st') as streamlit,
                mock.patch('app.is_legal_content_ready', return_value=False),
                mock.patch('app.render_datenschutz_page') as privacy,
                mock.patch('app.render_subscription_confirmed_page') as confirmed,
                mock.patch('app.load_dashboard_data', return_value=([], [])) as load,
                mock.patch('app.render_filters', return_value=[]),
                mock.patch('app.request_double_optin') as submit,
            ):
                streamlit.query_params = {'view': view}
                app.main()
                load.assert_called_once()
                privacy.assert_not_called()
                confirmed.assert_not_called()
                submit.assert_not_called()


class StreamlitIntegrationTests(unittest.TestCase):
    # Execute real widgets/reruns through AppTest, never a browser or live API.
    PREVIEW = '''
from unittest.mock import patch
import app
from src.legal_content import OperatorProfile
from src.subscribers import SignupOutcome, SignupResult
profile = OperatorProfile("Preview", "preview@example.invalid", "Test", "Test")
result = SignupResult(SignupOutcome.CONFIRMATION_SENT, "Mock confirmation; no email sent.")
with (
    patch("app.is_legal_content_ready", return_value=True),
    patch("app.load_operator_profile", return_value=profile),
    patch("app.request_double_optin", return_value=result),
):
    app.main()
'''

    def test_newsletter_consent_submission_and_result_survive_filter_rerun(self) -> None:
        at = AppTest.from_string(self.PREVIEW, default_timeout=30)
        at.query_params['view'] = 'changes'
        at.run()
        self.assertFalse(at.exception)
        at.text_input(key='newsletter_email_input').set_value('test@example.invalid')
        at.button(key='newsletter_submit_button').click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.warning)
        self.assertFalse(at.success)
        at.text_input(key='newsletter_email_input').set_value('test@example.invalid')
        at.checkbox(key='newsletter_consent_checkbox').check()
        at.button(key='newsletter_submit_button').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.success[0].value, 'Mock confirmation; no email sent.')
        at.selectbox(key='changes_period').set_value(14).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.success[0].value, 'Mock confirmation; no email sent.')

    def test_existing_routes_render_without_newsletter_form(self) -> None:
        for view, expected in (('datenschutz', 'Datenschutzerklärung'),
                               ('confirmed', 'Deine Anmeldung ist bestätigt.')):
            with self.subTest(view=view):
                at = AppTest.from_string(self.PREVIEW, default_timeout=30)
                at.query_params['view'] = view
                at.run()
                self.assertFalse(at.exception)
                self.assertEqual(len(at.text_input), 0)
                values = [e.value for e in (*at.subheader, *at.success)]
                self.assertIn(expected, values)


if __name__ == '__main__':
    unittest.main()
