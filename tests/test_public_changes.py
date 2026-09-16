"""Shared public presentation tests; no external requests."""
import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import app
from src.public_changes import category, subject, is_public, labels, matches
from test_homepage import event
import test_homepage

class PublicTaxonomyTests(unittest.TestCase):
    def test_lifecycle_identity_and_reactivation(self):
        for kind, expected in [('new_diga','NEU'),('removed_diga','ENTFERNT'),('status_change','AKTUALISIERT')]:
            row={**event(1), 'diga_id':'00123', 'change_type':kind, 'previous_value':'removed', 'new_value':'provisional'}
            self.assertTrue(is_public(row))
            self.assertEqual(category(row),expected)
            self.assertEqual(row['diga_id'],'00123')
        self.assertEqual(subject(row),'STATUS')

    def test_subjects_from_fields_and_context(self):
        cases=[('pricing_information','PREIS'),('evidence_summary_text','EVIDENZ'),
               ('indication','ANWENDUNG'),('descriptive_texts.Kontraindikationen','ANWENDUNG'),
               ('descriptive_texts.Softwarekompatibilität','TECHNIK'),('descriptive_texts.Versionsnummer','TECHNIK'),
               ('descriptive_texts.Datenschutz','DATENSCHUTZ'),('manufacturer_website','HERSTELLER'),
               ('new_unknown_field','ANGABEN'),('descriptive_texts.Kosten für weitere 90 Tage','PREIS')]
        for field,expected in cases:
            with self.subTest(field=field):
                self.assertEqual(subject({**event(1),'change_type':'other_field_change','changed_field':field}),expected)
        self.assertEqual(subject({**event(1),'change_type':'visible_diff_unresolved',
                                 'original_changed_field':'pricing_information','changed_field':'unknown',
                                 'localization_confidence':'low'}),'PREIS')
        self.assertEqual(subject({**event(1),'change_type':'other_field_change',
                                 'changed_field':'visible_directory.1','display_path':'Informationen zum positiven Versorgungseffekt'}),'EVIDENZ')

    def test_uncertain_context_does_not_override_trusted_field(self):
        row={**event(1),'change_type':'visible_diff_unresolved', 'changed_field':'questionnaire.923',
             'display_path':'Preis', 'localization_confidence':'low'}
        self.assertEqual(subject(row),'ANGABEN')
        row['original_changed_field']='indication'
        self.assertEqual(subject(row),'ANWENDUNG')
        row={**event(1),'change_type':'text_change','changed_field':'visible_directory.1',
             'display_path':'Medizinische Zweckbestimmung entsprechend den Angaben des Herstellers'}
        self.assertEqual(subject(row),'ANWENDUNG')

    def test_status_removal_is_update_and_mixed_day_keeps_categories(self):
        row={**event(1),'new_value':'removed'}
        self.assertEqual(labels([row]),['AKTUALISIERT','STATUS'])
        self.assertEqual(labels([{**row,'change_type':'new_diga'},row]),['NEU','AKTUALISIERT','STATUS'])

    def test_original_technical_filters_still_apply(self):
        rows=[{**event(1),'simulated':True},{**event(2),'development':True},
              {**event(3),'changed_field':'raw_public_fhir.module_ids'},
              {**event(4),'change_type':'price_change','changed_field':'pricing_information',
               'previous_value':[],'new_value':[]}]
        self.assertEqual(app.homepage_event_groups(rows),[])

    def test_directory_and_missing_identity_excluded(self):
        for overrides in ({'diga_id':'__directory__'},{'diga_name':'DiGA-Verzeichnis'},
                          {'diga_name':'DiGA Verzeichnis'},{'change_type':'directory_metric_change'},
                          {'diga_id':''},{'diga_name':''},{'directory_metric':True}):
            self.assertFalse(is_public({**event(1),**overrides}))

    def test_aggregate_counters_do_not_inflate_kpi_or_mutate_data(self):
        new={**event(1,'2026-09-07T15:25:40Z'),'change_type':'new_diga'}
        rows=[new]+[{**new,'diga_id':'__directory__','diga_name':'DiGA-Verzeichnis',
                     'change_type':'directory_metric_change','changed_field':f} for f in ('total_count','provisional')]
        original=copy.deepcopy(rows)
        groups=app.homepage_event_groups(rows)
        self.assertEqual(len(groups),1)
        self.assertEqual(app.recent_adjustment_count(groups,date(2026,9,16)),1)
        self.assertEqual(rows,original)

    def test_filter_search_and_multi_subjects(self):
        row={**event(1),'diga_name':'Example DiGA','manufacturer':'Example Maker'}
        self.assertTrue(matches(row,'Aktualisiert','diga'))
        self.assertTrue(matches(row,'Alle','maker'))
        self.assertFalse(matches(row,'Neu',''))
        self.assertFalse(matches(row,'Alle','missing'))
        price={**row,'change_type':'price_change','changed_field':'pricing_information'}
        self.assertEqual(labels([row,price]),['AKTUALISIERT','STATUS','PREIS'])

    def test_current_corpus_public_groups_preserve_order_and_details(self):
        rows=app.load_change_events(app.DEFAULT_CHANGES_DIR)
        real=[e for e in rows if app.is_real_change_event(e)]
        baseline=app.group_events_by_diga(real)
        expected=[g for g in baseline if all(is_public(e) for e in g['events'])]
        actual=app.homepage_event_groups(real)
        self.assertEqual(actual,expected)
        self.assertEqual(len(actual),23)
        self.assertEqual(sum(len(g['events']) for g in actual),169)
        self.assertEqual(app.recent_adjustment_count(actual,date(2026,9,16)),13)
        items=app.homepage_change_items(actual)
        self.assertEqual(len(items),5)
        self.assertTrue(all(i['name'] not in ('DiGA-Verzeichnis','DiGA Verzeichnis') for i in items))
        self.assertEqual(items[0]['labels'],labels(actual[0]['events']))
        self.assertEqual(items[0]['anchor'],app.change_group_anchor(actual[0]))

    def test_checkbox_wrapper_focus_removed_but_input_focus_retained(self):
        css=Path('assets/styles.css').read_text(encoding='utf-8')
        self.assertNotIn('[data-testid="stCheckbox"]:focus-within',css)
        self.assertIn('[data-testid="stTextInput"]:focus-within',css)
        self.assertIn(':focus-visible',css)

class PublicViewTests(unittest.TestCase):
    def test_filters_search_and_directory_exclusion(self):
        at=test_homepage.HomepageRouteTests().run_view('changes')
        markup=' '.join(m.value for m in at.markdown if not m.value.startswith('<style>'))
        self.assertNotIn('### DiGA-Verzeichnis',markup)
        self.assertNotIn('VERZEICHNIS</span>',markup)
        self.assertIn('AKTUALISIERT',markup)
        at.radio(key='changes_category').set_value('Neu').run()
        self.assertFalse(at.exception)
        markup=' '.join(m.value for m in at.markdown)
        self.assertIn('Frieda Menova',markup)
        self.assertNotIn('### Untire',markup)
        at.text_input(key='changes_search').set_value('isi PMS').run()
        markup=' '.join(m.value for m in at.markdown)
        self.assertIn('isi PMS App',markup)
        self.assertNotIn('Frieda Menova',markup)
        at.radio(key='changes_category').set_value('Entfernt').run()
        self.assertTrue(at.info)
        self.assertEqual(len([x for x in at.text_input if x.key=='newsletter_email_input']),1)
