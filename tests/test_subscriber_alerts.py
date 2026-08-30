from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.subscriber_alerts import (
    BREVO_CAMPAIGNS_API_URL,
    BREVO_UNSUBSCRIBE_MERGE_TAG,
    MissingSubscriberAlertConfig,
    build_alert_html_body,
    dispatch_subscriber_alerts,
    load_subscriber_alert_settings,
)


ENVIRONMENT = {
    "BREVO_API_KEY": "test-api-key",
    "DIGA_MONITOR_EMAIL_FROM": "updates@diga-tracker.de",
    "DIGA_MONITOR_EMAIL_FROM_NAME": "DiGA Tracker",
    "BREVO_NEWSLETTER_LIST_ID": "99",
}


def real_change_event(name: str = "Test DiGA") -> dict[str, object]:
    return {
        "detected_at": "2026-08-27T12:00:00+00:00",
        "diga_name": name,
        "manufacturer": "Test Hersteller",
        "change_type": "price_change",
        "changed_field": "pricing_information",
        "previous_value": "499,00 €",
        "new_value": "529,00 €",
        "summary_de": "Simulierte Preisänderung.",
    }


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status = status_code
        self.payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class SubscriberAlertSettingsTests(unittest.TestCase):
    def test_missing_config_is_reported(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingSubscriberAlertConfig) as ctx:
                load_subscriber_alert_settings()
            self.assertIn("BREVO_NEWSLETTER_LIST_ID", ctx.exception.missing)

    def test_complete_config_loads(self) -> None:
        with mock.patch.dict(os.environ, ENVIRONMENT, clear=True):
            settings = load_subscriber_alert_settings()
            self.assertEqual(settings.list_id, 99)


class AlertHtmlBodyTests(unittest.TestCase):
    def test_body_always_contains_a_working_unsubscribe_link(self) -> None:
        body = build_alert_html_body([real_change_event()], "https://www.diga-tracker.de")
        self.assertIn(BREVO_UNSUBSCRIBE_MERGE_TAG, body)

    def test_body_never_contains_individual_recipient_addresses(self) -> None:
        # This module never has access to individual subscriber addresses
        # in the first place -- Brevo's Campaign API resolves the audience
        # server-side from the confirmed list. This asserts that nothing
        # resembling a recipient email is ever interpolated into the body.
        body = build_alert_html_body([real_change_event()], "https://www.diga-tracker.de")
        self.assertNotIn("@", body.replace("diga-tracker.de", ""))


class DispatchSubscriberAlertsTests(unittest.TestCase):
    def test_t1_relevant_change_triggers_alert(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch(
                "src.subscriber_alerts.urlopen",
                side_effect=[
                    FakeResponse(201, {"id": 555}),
                    FakeResponse(204, {}),
                ],
            ) as urlopen_mock,
            mock.patch("src.subscriber_alerts._log_subscriber_alert"),
        ):
            result = dispatch_subscriber_alerts([real_change_event()])

        self.assertTrue(result)
        self.assertEqual(urlopen_mock.call_count, 2)
        create_request = urlopen_mock.call_args_list[0].args[0]
        send_request = urlopen_mock.call_args_list[1].args[0]
        self.assertEqual(create_request.full_url, BREVO_CAMPAIGNS_API_URL)
        self.assertEqual(send_request.full_url, f"{BREVO_CAMPAIGNS_API_URL}/555/sendNow")

    def test_t2_no_change_does_not_trigger_alert(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscriber_alerts.urlopen") as urlopen_mock,
            mock.patch("src.subscriber_alerts._log_subscriber_alert"),
        ):
            result = dispatch_subscriber_alerts([])

        self.assertFalse(result)
        urlopen_mock.assert_not_called()

    def test_simulated_only_events_do_not_trigger_alert_by_default(self) -> None:
        simulated_event = dict(real_change_event(), simulated=True)
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscriber_alerts.urlopen") as urlopen_mock,
            mock.patch("src.subscriber_alerts._log_subscriber_alert"),
        ):
            result = dispatch_subscriber_alerts([simulated_event])

        self.assertFalse(result)
        urlopen_mock.assert_not_called()

    def test_dry_run_never_calls_brevo(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscriber_alerts.urlopen") as urlopen_mock,
            mock.patch("src.subscriber_alerts._log_subscriber_alert"),
        ):
            result = dispatch_subscriber_alerts([real_change_event()], dry_run=True)

        self.assertFalse(result)
        urlopen_mock.assert_not_called()

    def test_t3_t4_audience_is_always_the_confirmed_list_only(self) -> None:
        # dispatch_subscriber_alerts never fetches or filters individual
        # contacts -- the only Brevo call that defines the audience is the
        # campaign create call, and it always targets exactly the
        # confirmed-subscribers list configured via
        # BREVO_NEWSLETTER_LIST_ID. Brevo itself, as system of record,
        # guarantees pending/unconfirmed and unsubscribed contacts are
        # excluded from that list's delivery.
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch(
                "src.subscriber_alerts.urlopen",
                side_effect=[FakeResponse(201, {"id": 1}), FakeResponse(204, {})],
            ) as urlopen_mock,
            mock.patch("src.subscriber_alerts._log_subscriber_alert"),
        ):
            dispatch_subscriber_alerts([real_change_event()])

        create_request = urlopen_mock.call_args_list[0].args[0]
        payload = json.loads(create_request.data)
        self.assertEqual(payload["recipients"], {"listIds": [99]})

    def test_t7_brevo_error_is_caught_and_does_not_raise(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscriber_alerts.urlopen", side_effect=RuntimeError("brevo is down")),
            mock.patch("src.subscriber_alerts._log_subscriber_alert") as log_mock,
        ):
            result = dispatch_subscriber_alerts([real_change_event()])

        self.assertFalse(result)
        self.assertEqual(log_mock.call_args.kwargs.get("status"), "failed")

    def test_t7_missing_config_is_a_non_fatal_skip(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("src.subscriber_alerts.urlopen") as urlopen_mock,
            mock.patch("src.subscriber_alerts._log_subscriber_alert"),
        ):
            result = dispatch_subscriber_alerts([real_change_event()])

        self.assertFalse(result)
        urlopen_mock.assert_not_called()

    def test_t7_never_raises_even_if_the_fallback_log_write_also_fails(self) -> None:
        # Double-fault edge case: the primary dispatch fails AND the
        # fallback logging call itself raises (e.g. disk error). The
        # "never raises" contract must hold on its own merits, not only
        # via the caller's own defense-in-depth wrapper in src/main.py.
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.subscriber_alerts.urlopen", side_effect=RuntimeError("brevo is down")),
            mock.patch(
                "src.subscriber_alerts._log_subscriber_alert",
                side_effect=OSError("disk full"),
            ),
        ):
            result = dispatch_subscriber_alerts([real_change_event()])
        self.assertFalse(result)

    def test_no_subscriber_email_address_is_ever_logged(self) -> None:
        # AC18 / no shadow subscriber database: the log entry only ever
        # contains counts/status/subject, never an email address.
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch(
                "src.subscriber_alerts.urlopen",
                side_effect=[FakeResponse(201, {"id": 1}), FakeResponse(204, {})],
            ),
        ):
            with tempfile.TemporaryDirectory() as tmp_dir:
                log_path = Path(tmp_dir) / "subscriber_alert_log.json"
                with mock.patch(
                    "src.subscriber_alerts.DEFAULT_SUBSCRIBER_ALERT_LOG_PATH", log_path
                ):
                    dispatch_subscriber_alerts([real_change_event()])
                contents = log_path.read_text(encoding="utf-8")
                self.assertNotIn("@", contents)


if __name__ == "__main__":
    unittest.main()
