"""Rendering and transport checks use synthetic events and mocked Brevo only."""
import contextlib
import copy
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from bs4 import BeautifulSoup
from streamlit.testing.v1 import AppTest
import app
from src.change_links import change_url, local_event_date, page_url
from src.notification_email import email_items, render_html, render_text, intro, HEADLINE
from src.subscriber_alerts import dispatch_subscriber_alerts
from test_subscriber_alerts import ENVIRONMENT, FakeResponse

LEGAL = 'https://www.diga-tracker.de/impressum'


def event(identity='one', **changes):
    return dict(dict(diga_id=identity, diga_name='DiGA '+identity,
        detected_at='2026-09-17T12:00:00Z', change_type='price_change',
        changed_field='pricing_information', previous_value='100 EUR', new_value='120 EUR'), **changes)


class NotificationEmailTests(unittest.TestCase):
    def test_one_and_multiple_cards_and_copy(self):
        for count in (1, 2):
            rows=[event(str(i)) for i in range(count)]
            soup=BeautifulSoup(render_html(rows, unsubscribe=True, impressum_url=LEGAL), 'html.parser')
            self.assertEqual(soup.h1.get_text(), HEADLINE)
            self.assertEqual(len(soup.find_all('h2')), count)
            self.assertIn(intro(count), soup.get_text())
            links=soup.find_all('a', string='Änderung ansehen →')
            self.assertEqual(len(links),count)
            self.assertEqual(len({a['href'] for a in links}),count)
            self.assertTrue(all('detail=change-' in a['href'] for a in links))
            self.assertEqual(soup.find('a',string='Abmelden')['href'],'{{ unsubscribe }}')

    def test_raw_events_group_by_identity_and_public_day(self):
        row=event()
        extra=event(change_type='text_change', changed_field='indication',new_value='another')
        self.assertEqual(len(email_items([row,row,extra])),1)
        self.assertEqual(email_items([row,extra])[0].label,'Aktualisierung')
        self.assertEqual(len(email_items([row,event(detected_at='2026-09-18T12:00:00Z')])),2)
        self.assertEqual(len(email_items([row,event('two',diga_name=row['diga_name'])])),2)

    def test_reliable_german_classification(self):
        cases=[({'change_type':'new_diga'},'Neue DiGA'),
               ({'change_type':'removed_diga'},'Aus dem Verzeichnis entfernt'),
               ({'change_type':'status_change','new_value':'permanent'},'Dauerhaft aufgenommen'),
               ({'change_type':'status_change','previous_value':'removed','new_value':'provisional'},'Wieder aufgenommen'),
               ({'change_type':'status_change','new_value':'future'},'Statusänderung'),
               ({'change_type':'future_kind'},'Aktualisierung')]
        for values,label in cases:
            with self.subTest(label=label):
                row=event(**values)
                self.assertEqual(email_items([row])[0].label,label)
                for body in (render_html([row]),render_text([row])):
                    self.assertNotIn('provisional',body)
                    self.assertNotIn('permanent',body)
                    self.assertNotIn('future_kind',body)

    def test_remove_and_readd_remains_one_neutral_card_without_mutation(self):
        rows=[event(change_type='removed_diga',previous_value={'status':'removed'},new_value=None),
              event(change_type='status_change',previous_value='removed',new_value='provisional')]
        original=copy.deepcopy(rows)
        items=email_items(rows)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0].label,'Aktualisierung')
        render_html(rows)
        render_text(rows)
        self.assertEqual(rows,original)

    def test_noop_and_unaddressable_rows_do_not_create_cards(self):
        self.assertEqual(email_items([event(previous_value=['a','b'],new_value=['b','a'])]),[])
        self.assertEqual(email_items([event(detected_at='invalid')]),[])
        with patch.dict(os.environ,ENVIRONMENT,clear=True),patch('src.subscriber_alerts.urlopen') as send,patch('src.subscriber_alerts._log_subscriber_alert'):
            self.assertFalse(dispatch_subscriber_alerts([event(previous_value='same',new_value='same')]))
            send.assert_not_called()

    def test_escape_markup_and_provider_template_injection(self):
        name='<script>alert("x")</script> & {{ contact.EMAIL }}'
        soup=BeautifulSoup(render_html([event(diga_name=name)]),'html.parser')
        self.assertIsNone(soup.find('script'))
        self.assertNotIn('{{ contact.EMAIL }}',str(soup))
        self.assertIn('<script>',soup.h2.get_text())
        for url in ['javascript:alert(1)','https://user:pass@example.com','https://example.com/{{contact.EMAIL}}']:
            with self.assertRaises(ValueError):
                render_html([event()],url)

    def test_plain_text_is_concise_and_contains_corresponding_links(self):
        rows=[event(),event('two')]
        text=render_text(rows,unsubscribe=True,impressum_url=LEGAL)
        for row in rows:
            self.assertIn(change_url(row),text)
        self.assertIn('Abmelden: {{ unsubscribe }}',text)
        self.assertIn('Impressum: '+LEGAL,text)
        for unwanted in ['100 EUR','120 EUR','2026-09','Geändert in','Hallo','Vorher','Nachher']:
            self.assertNotIn(unwanted,text)

    def test_url_matches_dashboard_group_and_survives_fresh_session(self):
        for stamp in ['2026-09-17T23:30:00Z','2026-09-17T12:00:00']:
            row=event(change_type='status_change',changed_field='status',previous_value='provisional',new_value='permanent',detected_at=stamp)
            group=app.homepage_event_groups([row])[0]
            link=change_url(row,'https://www.diga-tracker.de/?old=yes#stale')
            detail=parse_qs(urlsplit(link).query)['detail'][0]
            self.assertEqual(detail,app.change_group_anchor(group))
            self.assertNotIn('old=',link)
            source='import app\napp.render_change_detail('+repr([row])+', '+repr(detail)+')'
            at=AppTest.from_string(source).run()
            self.assertFalse(at.exception)
            self.assertNotIn('Diese Änderung konnte nicht gefunden werden.',[i.value for i in at.info])
        self.assertEqual(str(local_event_date(event(detected_at='2026-09-17T23:30:00Z'))),'2026-09-18')
        self.assertEqual(str(local_event_date(event(detected_at='2026-03-29T01:30:00Z'))),'2026-03-29')
        self.assertIsNone(local_event_date(event(detected_at=None)))

    def test_missing_old_record_has_graceful_navigation(self):
        at=AppTest.from_string("import app\napp.render_change_detail([], 'change-unavailable')").run()
        self.assertFalse(at.exception)
        self.assertIn('Diese Änderung konnte nicht gefunden werden.',[i.value for i in at.info])
        self.assertIn('?view=changes',' '.join(m.value for m in at.markdown))

    def test_no_truncation_after_ten_diga_and_no_directory_card(self):
        self.assertEqual(len(email_items([event(str(i)) for i in range(12)])),12)
        self.assertEqual(email_items([event(change_type='directory_metric_change')]),[])

    def test_historical_email_links_resolve_to_public_groups(self):
        from src.change_events import load_change_events
        from src.notifications import is_notifiable_event
        rows=load_change_events()
        anchors={app.change_group_anchor(group) for group in app.homepage_event_groups(rows)}
        items=email_items([row for row in rows if is_notifiable_event(row)])
        self.assertTrue(items)
        self.assertEqual({parse_qs(urlsplit(item.url).query)['detail'][0] for item in items},anchors)

    def test_missing_impressum_fails_before_any_campaign_request(self):
        env={k:v for k,v in ENVIRONMENT.items() if k!='DIGA_TRACKER_IMPRESSUM_URL'}
        with patch.dict(os.environ,env,clear=True),patch('src.subscriber_alerts.urlopen') as send,patch('src.subscriber_alerts._log_subscriber_alert'):
            self.assertFalse(dispatch_subscriber_alerts([event()]))
            send.assert_not_called()

    def test_provider_suppression_path_and_payload_preserved(self):
        with patch.dict(os.environ,ENVIRONMENT,clear=True),patch('src.subscriber_alerts.urlopen',side_effect=[FakeResponse(201,{'id':1}),FakeResponse(204,{})]) as send,patch('src.subscriber_alerts._log_subscriber_alert'):
            self.assertTrue(dispatch_subscriber_alerts([event()]))
        payload=json.loads(send.call_args_list[0].args[0].data)
        self.assertEqual(payload['recipients'],{'listIds':[99]})
        self.assertNotIn('to',payload)
        self.assertNotIn('textContent',payload) # Not supported by Campaign API.
        self.assertIn('{{ unsubscribe }}',payload['htmlContent'])

    def test_provider_errors_cannot_leak_subscriber_pii(self):
        output=io.StringIO()
        with patch.dict(os.environ,ENVIRONMENT,clear=True),patch('src.subscriber_alerts.urlopen',side_effect=RuntimeError('private@example.com SECRET')),patch('src.subscriber_alerts._log_subscriber_alert') as log,contextlib.redirect_stdout(output):
            self.assertFalse(dispatch_subscriber_alerts([event()]))
        self.assertNotIn('private@example.com',output.getvalue()+repr(log.call_args_list))
        self.assertNotIn('SECRET',output.getvalue()+repr(log.call_args_list))
