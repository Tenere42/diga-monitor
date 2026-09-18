"""DOI return, native form behavior and email artifact; never send live email."""
import unittest
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup
from streamlit.testing.v1 import AppTest
import app
from src.subscribers import doi_return_url
import test_homepage


class DoiReturnTests(unittest.TestCase):
    def test_production_legacy_and_canonical_urls_return_home(self):
        for url in ('https://www.diga-tracker.de/?view=confirmed',
                    'https://diga-tracker.de?view=confirmed',
                    'https://www.diga-tracker.de/', 'https://www.diga-tracker.de'):
            self.assertEqual(doi_return_url(url), 'https://www.diga-tracker.de')

    def test_other_environments_and_paths_are_preserved(self):
        for url in ('http://localhost:8501/?view=confirmed',
                    'https://preview.example.test/?view=confirmed',
                    'https://www.diga-tracker.de/other',
                    'https://www.diga-tracker.de/?campaign=example',
                    'https://www.diga-tracker.de.example.test/?view=confirmed'):
            self.assertEqual(doi_return_url(url), url)

    def test_legacy_return_renders_home_without_claiming_confirmation(self):
        at = AppTest.from_string(test_homepage.HomepageRouteTests.PREVIEW, default_timeout=30)
        at.query_params['view'] = 'confirmed'
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(any('hero-title' in m.value for m in at.markdown))
        self.assertEqual(len(at.text_input), 1)
        self.assertFalse(at.success)
        at.run()
        self.assertFalse(at.exception)
        self.assertFalse(at.success)

    def test_return_never_starts_doi_or_mutates_contacts(self):
        with (patch.object(app, 'st') as st,
              patch.object(app, 'is_legal_content_ready', return_value=True),
              patch.object(app, 'load_dashboard_data', return_value=([], [])),
              patch.object(app, 'render_homepage') as home,
              patch.object(app, 'request_double_optin') as doi):
            st.query_params = {'view': 'confirmed'}
            app.render_tracker_page()
        home.assert_called_once_with([], [])
        doi.assert_not_called()
        st.success.assert_not_called()


class NewsletterFormTests(unittest.TestCase):
    def test_native_enter_hint_disabled_and_submit_still_requires_consent(self):
        at = AppTest.from_string(test_homepage.HomepageRouteTests.PREVIEW, default_timeout=30).run()
        self.assertFalse(at.exception)
        self.assertFalse(at.get('form')[0].proto.form.enter_to_submit)
        at.text_input(key='newsletter_email_input').set_value('preview@example.invalid')
        at.button(key='newsletter_submit_button').click().run()
        self.assertTrue(at.warning)
        self.assertFalse(at.success)
        at.text_input(key='newsletter_email_input').set_value('preview@example.invalid')
        at.checkbox(key='newsletter_consent_checkbox').check()
        at.button(key='newsletter_submit_button').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.success[0].value, 'Mock confirmation')
        self.assertIsNone(at.session_state[app._NEWSLETTER_PENDING_EMAIL_KEY])

    def test_mobile_rules_do_not_hide_instructions_or_fix_section_height(self):
        css = Path('assets/styles.css').read_text(encoding='utf-8')
        self.assertIn('env(safe-area-inset-top', css)
        self.assertIn('height: 100dvh', css)
        self.assertNotIn('100vh', css)
        self.assertNotIn('InputInstructions', css)
        section = css.split('.st-key-newsletter_signup {')[1].split('}')[0]
        self.assertIn('position: static', section)
        self.assertNotIn('height:', section)
        email = css.split('.st-key-newsletter_signup [data-testid="stTextInput"] input {')[1].split('}')[0]
        self.assertIn('font-size: 16px', email)
        self.assertIn('min-height: 3rem', email)


class DoiEmailTests(unittest.TestCase):
    def test_native_doi_link_and_mobile_email_structure(self):
        html = Path('templates/brevo-doi-confirmation.html').read_text(encoding='utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a')
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['href'], '{{ params.DOIurl }}')
        self.assertEqual(links[0].get_text(), 'E-Mail-Adresse bestätigen')
        self.assertIn('background-color:#111111', links[0]['style'])
        self.assertIn('color:#ffffff', links[0]['style'])
        self.assertIn('display:block', links[0]['style'])
        self.assertIn('max-width:560px', html)
        self.assertTrue(all(t.get('role') == 'presentation' for t in soup.find_all('table')))
        self.assertEqual(soup.html['lang'], 'de')
        self.assertEqual(soup.h1.get_text(), 'Updates bestätigen')
        self.assertIn('Du hast dich für die DiGA Tracker Updates angemeldet.', soup.get_text())
        self.assertNotIn('DiGA Monitor', html)
        self.assertFalse(soup.find_all(['script', 'iframe', 'link']))
