"""Calendar-period and public navigation regression checks; no external APIs."""
import unittest
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch
from html.parser import HTMLParser
from pathlib import Path
from streamlit.testing.v1 import AppTest
import app
from test_homepage import event
import test_homepage


class Links(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.links = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs))


class CalendarPeriodTests(unittest.TestCase):
    def test_all_periods_include_full_today_and_exact_calendar_start(self):
        # Spring/fall DST, year boundary, leap day and a regular summer day.
        for today in (date(2026, 3, 29), date(2026, 10, 25), date(2026, 1, 1),
                      date(2024, 2, 29), date(2026, 9, 16)):
            for days in (7, 14, 30, 90, 180):
                with self.subTest(today=today, days=days):
                    start = datetime.combine(today - timedelta(days=days-1), time.min, app.DISPLAY_TIMEZONE)
                    end = datetime.combine(today + timedelta(days=1), time.min, app.DISPLAY_TIMEZONE)
                    midnight = datetime.combine(today, time.min, app.DISPLAY_TIMEZONE)
                    instants = [start-timedelta(seconds=1), start, midnight,
                                end-timedelta(microseconds=1), end]
                    rows = [event(i, t.astimezone(timezone.utc).isoformat()) for i, t in enumerate(instants)]
                    rows += [event(99, 'invalid'), event(100, '')]
                    self.assertEqual(app.filter_recent_events(rows, days, today), rows[1:4])

    def test_dropdown_defaults_and_uses_berlin_today(self):
        for days in (7, 14, 30, 90, 180):
            with patch.object(app, 'st') as st, patch.object(app, 'datetime', wraps=datetime) as clock:
                st.selectbox.return_value = days
                clock.now.return_value = datetime(2026, 9, 16, 0, 5, tzinfo=app.DISPLAY_TIMEZONE)
                row = event(1, '2026-09-15T22:01:00Z')
                self.assertEqual(app.render_filters([row]), [row])
                clock.now.assert_called_once_with(app.DISPLAY_TIMEZONE)
                self.assertEqual(st.selectbox.call_args.args[1], (7, 14, 30, 90, 180))
                self.assertEqual(st.selectbox.call_args.kwargs['index'], 2)
                st.date_input.assert_not_called()

    def test_real_dropdown_rerenders_each_period(self):
        preview = '''
from datetime import datetime, timedelta
import app
now = datetime.now(app.DISPLAY_TIMEZONE)
rows = [{'detected_at': (now-timedelta(days=i)).isoformat()} for i in range(181)]
app.st.write(str(len(app.render_filters(rows))))
'''
        at = AppTest.from_string(preview).run()
        self.assertEqual(at.selectbox[0].value, 30)
        self.assertEqual(at.selectbox[0].options, ['7 Tage','14 Tage','30 Tage','90 Tage','180 Tage'])
        for days in (7, 14, 30, 90, 180):
            at.selectbox[0].set_value(days).run()
            self.assertFalse(at.exception)
            self.assertEqual(at.markdown[0].value, str(days))


class NavigationTests(unittest.TestCase):
    def test_overview_has_only_direct_details_and_home_back_link(self):
        at = test_homepage.HomepageRouteTests().run_view('changes')
        self.assertEqual(at.title[0].value, 'Alle Änderungen')
        self.assertFalse(at.expander)
        self.assertFalse(at.date_input)
        markup = ' '.join(m.value for m in at.markdown if not m.value.startswith('<style>'))
        links = Links(markup).links
        self.assertTrue(any(a.get('href') == './' and a.get('class') == 'diga-button' for a in links))
        self.assertTrue(any('detail=' in a.get('href', '') for a in links))
        self.assertNotIn('Änderungen im Detail', markup)

    def test_detail_preserves_external_url_and_stacked_back_navigation(self):
        row = event(1)
        row['bfarm_directory_url'] = 'https://diga.bfarm.de/de/verzeichnis/123?x=1&y=2'
        group = app.homepage_event_groups([row])[0]
        with patch.object(app, 'st') as st, patch.object(app, 'render_public_details') as render:
            app.render_change_detail([row], app.change_group_anchor(group))
        st.title.assert_called_once_with('Änderungen')
        render.assert_called_once_with(row)
        markup = st.markdown.call_args.args[0]
        self.assertIn('class="diga-detail-actions"', markup)
        links = Links(markup).links
        self.assertEqual([a['href'] for a in links], [row['bfarm_directory_url'], '?view=changes'])
        self.assertEqual([a['class'] for a in links], ['diga-button', 'diga-button'])
        self.assertEqual(links[0]['target'], '_blank')
        self.assertEqual(links[1]['target'], '_self')
        self.assertLess(markup.index('BfArM-Eintrag öffnen'), markup.index('Zurück'))

    def test_unresolved_detail_retains_values_without_generic_sentence(self):
        row = {**event(1), 'change_type': 'visible_diff_unresolved',
               'previous_value': 'Unique old value', 'new_value': 'Unique new value'}
        with patch.object(app, 'st') as st:
            app.render_public_details(row)
        st.caption.assert_not_called()
        markup = ' '.join(c.args[0] for c in st.markdown.call_args_list)
        self.assertIn('Unique old value', markup)
        self.assertIn('Unique new value', markup)


class ResponsiveStyleTests(unittest.TestCase):
    def test_navigation_shares_primary_style_and_mobile_touch_targets(self):
        css = Path('assets/styles.css').read_text(encoding='utf-8')
        self.assertIn('.block-container .diga-button,\n.block-container [data-testid="stLinkButton"] a {', css)
        primary = css.split('.block-container [data-testid="stLinkButton"] a {', 1)[1].split('}', 1)[0]
        for rule in ('background: var(--color-black)', 'color: var(--color-white)',
                     'min-height: 3rem', 'max-width: 100%', 'box-sizing: border-box',
                     'padding: var(--space-3) var(--space-5)', 'border-radius: var(--radius-sm)'):
            self.assertIn(rule, primary)
        stack = css.split('.diga-detail-actions {', 1)[1].split('}', 1)[0]
        self.assertIn('flex-direction: column', stack)
        self.assertIn('gap: var(--space-3)', stack)
        self.assertIn(':focus-visible', css)
        self.assertIn('.diga-button:hover', css)
        self.assertIn('[data-testid="stSelectbox"]:focus-within', css)
        self.assertIn('@media (max-width: 47.99rem)', css)
        self.assertNotIn('diga-button-secondary', css)
