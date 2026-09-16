"""Query-routed public groups; all newsletter integrations are mocked."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import app
import test_homepage
from src.ui import public_header_html, recent_changes_html

class DirectDetailTests(unittest.TestCase):
    def groups(self):
        return app.homepage_event_groups(app.load_change_events(app.DEFAULT_CHANGES_DIR))

    def run_detail(self, identifier):
        at=AppTest.from_string(test_homepage.HomepageRouteTests.PREVIEW, default_timeout=30)
        at.query_params['view']='changes'
        at.query_params['detail']=identifier
        at.run()
        self.assertFalse(at.exception)
        return at

    def test_homepage_simplification_and_links(self):
        at=test_homepage.HomepageRouteTests().run_view()
        markup=' '.join(m.value for m in at.markdown if not m.value.startswith('<style>'))
        self.assertNotIn('Was wir beobachten',markup)
        self.assertNotIn('id="about"',markup)
        self.assertNotIn('<details',markup)
        self.assertNotIn('Menü',markup)
        self.assertIn('DiGA Tracker verfolgt neue DiGA, Statusänderungen, Preise',markup)
        self.assertEqual(len(at.text_input),1)
        self.assertIn('href="?view=changes"',markup)
        identifier=app.change_group_anchor(self.groups()[0])
        self.assertIn('?view=changes&amp;detail='+identifier,markup)
        self.assertIn('href="./"',public_header_html())

    def test_selected_group_only_with_all_adjustments_and_reload(self):
        group=self.groups()[0]
        identifier=app.change_group_anchor(group)
        at=self.run_detail(identifier)
        self.assertEqual(at.title[0].value,'Änderungsdetails')
        self.assertEqual(len(at.date_input),0)
        self.assertEqual(len(at.radio),0)
        self.assertEqual(len(at.text_input),0)
        markup=' '.join(m.value for m in at.markdown)
        self.assertIn(group['diga_name'],markup)
        self.assertNotIn('Frieda Menova',markup)
        self.assertIn('← Alle Änderungen',markup)
        # Every adjustment goes through the same full detail renderer, in order.
        with patch.object(app, 'render_public_details') as render, patch.object(app,'st'):
            app.render_change_detail(app.load_change_events(app.DEFAULT_CHANGES_DIR),identifier)
        self.assertEqual([c.args[0] for c in render.call_args_list],group['events'])
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.query_params['detail'],[identifier])
        self.assertEqual(at.title[0].value,'Änderungsdetails')
        at.query_params.pop('detail')
        at.run()
        self.assertEqual(at.title[0].value,'Änderungen')
        self.assertEqual(len(at.date_input),1)
        fresh=self.run_detail(identifier)
        self.assertEqual(fresh.title[0].value,'Änderungsdetails')

    def test_invalid_empty_and_directory_details_fail_closed(self):
        rows=app.load_change_events(app.DEFAULT_CHANGES_DIR)
        directory=next(g for g in app.group_events_by_diga(rows) if g['diga_name']=='DiGA-Verzeichnis')
        for identifier in ('', 'does-not-exist',app.change_group_anchor(directory)):
            with self.subTest(identifier=identifier):
                at=self.run_detail(identifier)
                self.assertEqual(at.info[0].value,'Diese Änderung konnte nicht gefunden werden.')
                self.assertEqual(len(at.date_input),0)
                self.assertTrue(any('Alle Änderungen ansehen' in m.value for m in at.markdown))

    def test_identity_uses_diga_and_date_not_position_or_display_name(self):
        group=self.groups()[0]
        identifier=app.change_group_anchor(group)
        renamed={**group,'diga_name':'Renamed'}
        self.assertEqual(app.change_group_anchor(renamed),identifier)
        other_day={**group,'date':'2000-01-01'}
        self.assertNotEqual(app.change_group_anchor(other_day),identifier)
