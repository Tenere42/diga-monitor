"""Homepage routing, KPI semantics and previews; only mocked signup requests."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import app
from src.homepage_data import load_market_snapshot
from src.snapshot import calculate_directory_metrics
from src.ui import hero_html, market_snapshot_html, recent_changes_html
from streamlit.testing.v1 import AppTest


def snapshot_payload() -> dict:
    # Includes an inactive record, unknown status and historical fallback to
    # demonstrate that active is not total scanned entries or raw status count.
    entries = [
        {"status": "permanent", "status_source": "catalog_entry.status"},
        {"status": "provisional", "status_source": "catalog_entry.status"},
        {"status": "removed", "status_source": "catalog_entry.status"},
        {"status": "unknown"},
        {"status": "unknown", "change_history": [{"date": "2026-09-01", "type": "permanent"}]},
    ]
    timestamp = "2026-09-15T19:24:11+00:00"
    return {"entries": entries, "created_at": timestamp,
            "directory_metrics": calculate_directory_metrics(entries, calculated_at=timestamp)}


def event(index: int, timestamp: str | None = None) -> dict:
    return {"diga_id": str(index), "diga_name": f"DiGA {index}",
            "detected_at": timestamp or f"2026-09-{index + 1:02d}T10:00:00+00:00",
            "change_type": "status_change", "changed_field": "status",
            "previous_value": "provisional", "new_value": "permanent",
            "manufacturer": "Hersteller", "snapshot_context": {"id": str(index)}}


class MarketMetricTests(unittest.TestCase):
    def read(self, payload):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return load_market_snapshot(path)

    def test_market_counts_use_existing_snapshot_status_semantics(self):
        market = self.read(snapshot_payload())
        self.assertEqual((market.active, market.permanent, market.provisional, market.unknown), (3, 2, 1, 1))
        self.assertEqual(market.as_of, "2026-09-15T19:24:11+00:00")

    def test_missing_or_broken_snapshot_is_unavailable_not_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "absent.json"
            self.assertIsNone(load_market_snapshot(path))
            path.write_text("{broken", encoding="utf-8")
            self.assertIsNone(load_market_snapshot(path))
        for payload in (None, [], {}, {"entries": None}):
            with self.subTest(payload=payload):
                self.assertIsNone(self.read(payload))

    def test_inconsistent_or_mislabelled_aggregates_are_not_displayed(self):
        for field, value in (("active_count", 99), ("active_count", True),
                             ("source", "historical_events"), ("calculated_at", "yesterday")):
            with self.subTest(field=field, value=value):
                payload = snapshot_payload()
                payload["directory_metrics"][field] = value
                self.assertIsNone(self.read(payload))

    def test_unknown_only_snapshot_is_valid_but_has_no_active_listings(self):
        payload = snapshot_payload()
        payload["entries"] = [{"status": "unknown"}]
        payload["directory_metrics"] = calculate_directory_metrics(payload["entries"], calculated_at=payload["created_at"])
        market = self.read(payload)
        self.assertEqual((market.active, market.unknown), (0, 1))

    def test_new_market_cache_refreshes_on_content_change(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            payload = snapshot_payload()
            path.write_text(json.dumps(payload), encoding="utf-8")
            first = app.load_homepage_market(str(path), app.files_content_signature((path,)))
            payload["entries"][0]["status"] = "removed"
            payload["directory_metrics"] = calculate_directory_metrics(payload["entries"], calculated_at=payload["created_at"])
            path.write_text(json.dumps(payload), encoding="utf-8")
            second = app.load_homepage_market(str(path), app.files_content_signature((path,)))
            self.assertEqual((first.active, second.active), (3, 2))


class RecentChangeTests(unittest.TestCase):
    def test_homepage_matches_full_dashboard_default_date_range(self):
        events = [event(1), event(2, "2026-05-30T12:00:00Z"), event(3, "invalid"),
                  event(4, "2026-05-30T22:00:00Z")]
        with patch.object(app.st, 'date_input', return_value=(app.TRACKING_START_DATE, date(2026, 9, 16))):
            full_groups = app.group_events_by_diga(app.render_filters(events))
        self.assertEqual(app.homepage_event_groups(events), full_groups)
        self.assertEqual(len(full_groups), 2)

    def test_preview_keeps_group_order_limits_to_five_and_does_not_mutate(self):
        groups = app.group_events_by_diga([event(i) for i in (2, 6, 1, 5, 0, 4, 3)])
        original = copy.deepcopy(groups)
        items = app.homepage_change_items(groups)
        self.assertEqual([i["name"] for i in items], [f"DiGA {i}" for i in (6, 5, 4, 3, 2)])
        self.assertEqual(groups, original)
        self.assertEqual(len({item["anchor"] for item in items}), 5)
        self.assertEqual(app.homepage_change_items(groups, limit=0), [])

    def test_grouping_exclusions_and_deduplication_are_used_before_preview(self):
        real = event(1)
        fake = {**event(2), "simulated": True}
        development = {**event(3), "development": True}
        eligible = [e for e in [real, copy.deepcopy(real), fake, development] if app.is_real_change_event(e)]
        groups = app.group_events_by_diga(eligible)
        self.assertEqual(len(app.homepage_change_items(groups)), 1)
        self.assertEqual(app.recent_adjustment_count(groups, date(2026, 9, 16)), 1)

    def test_recent_count_is_30_berlin_calendar_days_not_groups_or_raw_events(self):
        # Window is Aug 18 through Sep 16 inclusive. Berlin is UTC+2 here.
        records = [event(1, "2026-08-17T22:00:00Z"), event(2, "2026-08-17T21:59:59Z"),
                   event(3, "2026-09-16T21:59:59Z"), event(4, "2026-09-16T22:00:00Z")]
        records += [{**records[0], "changed_field": "name", "previous_value": "Alt", "new_value": "Neu"}]
        groups = app.group_events_by_diga(records)
        self.assertEqual(app.recent_adjustment_count(groups, date(2026, 9, 16)), 3)

    def test_preview_reuses_status_labels_and_local_time(self):
        items = app.homepage_change_items(app.group_events_by_diga([event(1, "2026-09-01T23:00:00Z")]))
        self.assertEqual(items[0]["date_label"], "02.09.2026 01:00")
        self.assertEqual(items[0]["summary"], "Vorläufig aufgenommen → Dauerhaft aufgenommen")
        self.assertEqual(items[0]["labels"], ["Statusänderung"])

    def test_preview_html_escapes_names_labels_and_summaries(self):
        groups = app.group_events_by_diga([{**event(1), "diga_name": '<script>alert("x")</script>'}])
        markup = recent_changes_html(app.homepage_change_items(groups))
        self.assertNotIn('<script>', markup)
        self.assertIn('&lt;script&gt;', markup)
        self.assertIn('?view=changes#change-', markup)

    def test_missing_metrics_and_empty_preview_have_explicit_states(self):
        self.assertIn('—', market_snapshot_html([("Aktive DiGA", None)], "Nicht verfügbar"))
        self.assertIn('Bisher keine fachlichen Änderungen', recent_changes_html([]))
        self.assertNotIn('#newsletter', hero_html(newsletter_ready=False))


class HomepageRouteTests(unittest.TestCase):
    # Full app with real local monitoring artifacts, dummy legal facts, and a
    # mocked DOI function. No credentials or external service calls are used.
    PREVIEW = '''
from unittest.mock import patch
import app
from src.legal_content import OperatorProfile
from src.subscribers import SignupOutcome, SignupResult
with (
    patch("app.is_legal_content_ready", return_value=True),
    patch("app.load_operator_profile", return_value=OperatorProfile("Preview", "preview@example.invalid", "Test", "Test")),
    patch("app.request_double_optin", return_value=SignupResult(SignupOutcome.CONFIRMATION_SENT, "Mock confirmation")),
):
    app.main()
'''

    def run_view(self, view=None):
        at = AppTest.from_string(self.PREVIEW, default_timeout=30)
        if view:
            at.query_params['view'] = view
        at.run()
        self.assertFalse(at.exception)
        return at

    def test_default_homepage_section_order_preview_limit_and_single_signup(self):
        at = self.run_view()
        markup = '\n'.join(m.value for m in at.markdown if not m.value.startswith('<style>'))
        markers = ['diga-site-header', 'hero-title', 'market-title', 'recent-title', 'id="about"', 'id="newsletter"', 'diga-footer']
        self.assertEqual([markup.index(m) for m in markers], sorted(markup.index(m) for m in markers))
        self.assertEqual(markup.count('<li class="diga-recent-item">'), 5)
        self.assertEqual(len(at.text_input), 1)
        self.assertEqual(len(at.checkbox), 1)
        self.assertEqual(len(at.button), 1)
        self.assertEqual(len(at.date_input), 0)
        self.assertEqual(markup.count('id="newsletter"'), 1)
        self.assertIn('href="#newsletter"', markup)

    def test_full_changes_route_retains_filter_details_and_single_signup(self):
        at = self.run_view('changes')
        self.assertEqual(len(at.date_input), 1)
        self.assertEqual(len(at.text_input), 1)
        markup = '\n'.join(m.value for m in at.markdown if not m.value.startswith('<style>'))
        self.assertNotIn('hero-title', markup)
        self.assertIn('class="before-after-grid', markup)
        self.assertIn('id="change-', markup)

    def test_homepage_signup_result_survives_rerun_without_duplicate_form(self):
        at = self.run_view()
        at.text_input(key='newsletter_email_input').set_value('test@example.invalid')
        at.checkbox(key='newsletter_consent_checkbox').check()
        at.button(key='newsletter_submit_button').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.success[0].value, 'Mock confirmation')
        at.run()
        self.assertEqual(at.success[0].value, 'Mock confirmation')
        self.assertEqual(len(at.text_input), 1)

    def test_unknown_route_falls_back_to_homepage(self):
        at = self.run_view('unknown')
        self.assertTrue(any('id="hero-title"' in m.value for m in at.markdown))

    def test_closed_legal_gate_hides_signup_and_its_anchor_links(self):
        at = AppTest.from_string(self.PREVIEW.replace('return_value=True', 'return_value=False'), default_timeout=30).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.text_input), 0)
        markup = '\n'.join(m.value for m in at.markdown if not m.value.startswith('<style>'))
        self.assertNotIn('#newsletter', markup)
        self.assertNotIn('id="newsletter"', markup)
        self.assertNotIn('?view=datenschutz', markup)
        self.assertIn('id="hero-title"', markup)


if __name__ == '__main__':
    unittest.main()
