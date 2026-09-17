"""Public status labels and single external action; no external requests."""
import copy
import unittest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup
from streamlit.testing.v1 import AppTest
import app
from test_homepage import event


class StatusPresentationTests(unittest.TestCase):
    def test_every_value_renderer_translates_canonical_statuses(self):
        for raw, label in [('provisional', 'vorläufig'), ('permanent', 'dauerhaft'), ('removed', 'entfernt')]:
            with self.subTest(status=raw):
                values = [raw, {'status': raw}, [{'status': raw}]]
                for value in values:
                    original = copy.deepcopy(value)
                    for render in (app.format_value, app.format_inline_value, app.value_to_html):
                        markup = render(value)
                        self.assertIn(label, markup)
                        self.assertNotIn(raw, markup)
                    box = MagicMock()
                    app.render_value_box(box, value)
                    markup = ' '.join(c.args[0] for c in box.markdown.call_args_list)
                    self.assertIn(label, markup)
                    self.assertNotIn(raw, markup)
                    self.assertEqual(value, original)

    def test_reentry_and_other_directions_preserve_before_after(self):
        for before, after, expected in [('removed', 'provisional', ('entfernt', 'vorläufig')),
                                        ('permanent', 'removed', ('dauerhaft', 'entfernt')),
                                        ('permanent', 'provisional', ('dauerhaft', 'vorläufig'))]:
            row = {**event(1), 'previous_value': before, 'new_value': after}
            original = copy.deepcopy(row)
            with patch.object(app, 'st') as st:
                app.render_public_details(row)
            markup = ' '.join(c.args[0] for c in st.markdown.call_args_list)
            soup = BeautifulSoup(markup, 'html.parser')
            cards = soup.select('.before-after-card')
            self.assertIn('Vorher', cards[0].get_text())
            self.assertIn(expected[0], cards[0].get_text())
            self.assertIn('Nachher', cards[1].get_text())
            self.assertIn(expected[1], cards[1].get_text())
            self.assertNotIn(before, markup)
            self.assertNotIn(after, markup)
            item = app.homepage_change_items(app.homepage_event_groups([row]))[0]
            self.assertEqual(item['summary'], ' → '.join(expected))
            self.assertEqual(row, original)

    def test_only_categorical_status_aliases_are_translated(self):
        for raw, label in [('active', 'dauerhaft'), ('draft', 'vorläufig'),
                           ('retired', 'entfernt'), ('unknown', 'unbekannt'),
                           ('future_enum', 'unbekannt')]:
            self.assertEqual(app.status_display_label(raw, categorical=True), label)
            self.assertEqual(app.format_inline_value(raw), raw)
        prose = 'The permanent module was removed from the active configuration.'
        self.assertEqual(app.format_inline_value(prose), prose)

    def test_internal_explanation_absent_for_all_detail_types(self):
        for kind, field, before, after in [
            ('price_change', 'pricing_information', {'value': 100, 'currency': 'EUR'}, {'value': 120, 'currency': 'EUR'}),
            ('price_change', 'pricing_information', 'custom old price', 'custom new price'),
            ('status_change', 'status', 'removed', 'provisional'),
            ('text_change', 'evidence_summary_text', 'old evidence', 'new evidence'),
            ('other_field_change', 'duration', '30 Tage', '90 Tage'),
            ('other_field_change', 'manufacturer', 'old maker', 'new maker'),
        ]:
            with self.subTest(kind=kind, field=field), patch.object(app, 'st') as st:
                app.render_public_details({**event(1), 'change_type': kind, 'changed_field': field,
                                           'previous_value': before, 'new_value': after})
                self.assertNotIn('Warum wurde diese Änderung erkannt?',
                                 [c.args[0] for c in st.expander.call_args_list])
                markup = ' '.join(c.args[0] for c in st.markdown.call_args_list)
                self.assertIn('Vorher', markup)
                self.assertIn('Nachher', markup)
                if before == 'custom old price':
                    self.assertIn(before, markup)
                    self.assertIn(after, markup)


class SingleExternalActionTests(unittest.TestCase):
    def test_lifecycle_details_have_exactly_one_correct_bottom_link(self):
        url = 'https://diga.bfarm.de/de/verzeichnis/123?x=1&y=2'
        for kind in ('new_diga', 'status_change', 'removed_diga'):
            for embedded in (False, True):
                if kind == 'status_change' and embedded:
                    continue
                with self.subTest(kind=kind, embedded=embedded):
                    entry = {'name': 'Example', 'status': 'provisional', 'bfarm_directory_url': url}
                    row = {**event(1), 'change_type': kind,
                           'previous_value': entry if kind == 'removed_diga' else 'removed',
                           'new_value': entry if kind == 'new_diga' else 'provisional'}
                    if not embedded:
                        row['bfarm_directory_url'] = url
                    # Run the real page and native elements through Streamlit.
                    source = 'import app\nrow = ' + repr(row) + '\napp.render_change_detail([row], app.change_group_anchor(app.homepage_event_groups([row])[0]))'
                    at = AppTest.from_string(source, default_timeout=30).run()
                    self.assertFalse(at.exception)
                    markup = ' '.join(m.value for m in at.markdown)
                    links = BeautifulSoup(markup, 'html.parser').find_all('a', string='BfArM-Eintrag öffnen')
                    self.assertEqual(len(links), 1)
                    self.assertEqual(len(at.get('link_button')), 0)
                    self.assertEqual(links[0]['href'], url)
                    self.assertIn('diga-detail-actions', links[0].parent.get('class', []))
                    self.assertIn('Zurück', links[0].parent.get_text())
                    self.assertNotIn('provisional', markup)
                    self.assertNotIn('removed', markup)

    def test_missing_or_invalid_link_does_not_create_external_action(self):
        for url in (None, 'javascript:alert(1)', 'https://example.invalid/entry'):
            row = {**event(1), 'bfarm_directory_url': url}
            group = app.homepage_event_groups([row])[0]
            self.assertIsNone(app.detail_bfarm_url(group))
            with patch.object(app, 'st') as st:
                app.render_change_detail([row], app.change_group_anchor(group))
            self.assertNotIn('BfArM-Eintrag öffnen', st.markdown.call_args.args[0])
            self.assertIn('Zurück', st.markdown.call_args.args[0])
