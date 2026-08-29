from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from src.notifications import (
    BREVO_EMAIL_API_URL,
    BrevoConfig,
    MissingNotificationConfig,
    build_email_body,
    build_email_message,
    configured_recipients,
    load_notification_settings,
    notify_changes,
    send_email,
    send_test_notification,
)


ENVIRONMENT = {
    "BREVO_API_KEY": "test-api-key",
    "DIGA_MONITOR_EMAIL_FROM": "updates@diga-tracker.de",
    "DIGA_MONITOR_EMAIL_FROM_NAME": "DiGA Tracker",
    "DIGA_MONITOR_EMAIL_TO": "recipient@example.com",
    "DASHBOARD_URL": "https://example.com/dashboard",
}


def event(name: str = "Test DiGA") -> dict[str, str]:
    return {
        "detected_at": "2026-08-27T12:00:00+00:00",
        "diga_name": name,
        "manufacturer": "Test Hersteller",
        "change_type": "price_change",
        "changed_field": "pricing_information",
        "previous_value": "499,00 €",
        "new_value": "529,00 €",
        "summary_de": "Simulierte Preisänderung von 499,00 € auf 529,00 €.",
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


class NotificationTests(unittest.TestCase):
    def test_test_notification_uses_normal_path_with_one_simulated_change(self) -> None:
        with mock.patch("src.notifications.notify_changes", return_value=True) as notify:
            self.assertTrue(send_test_notification())

        events = notify.call_args.args[0]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["diga_name"], "Test DiGA")
        self.assertEqual(events[0]["manufacturer"], "Test Hersteller")
        self.assertEqual(events[0]["change_type"], "price_change")
        self.assertEqual(events[0]["previous_value"], "499,00 €")
        self.assertEqual(events[0]["new_value"], "529,00 €")
        self.assertTrue(events[0]["simulated"])
        self.assertEqual(
            notify.call_args.kwargs,
            {"dry_run": False, "include_simulated": True, "test_mode": True},
        )

    def test_test_email_body_contains_all_acceptance_criteria(self) -> None:
        body = build_email_body([event()], ENVIRONMENT["DASHBOARD_URL"], test_mode=True)
        for expected in (
            "TEST / SIMULATION",
            "Keine echte BfArM-Änderung",
            "Test DiGA",
            "Test Hersteller",
            "Preisänderung",
            "499,00 €",
            "529,00 €",
            "27.08.2026",
            ENVIRONMENT["DASHBOARD_URL"],
        ):
            self.assertIn(expected, body)

    def test_recipient_configuration_is_external_and_multi_recipient_ready(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"DIGA_MONITOR_EMAIL_TO": "first@example.com, SECOND@example.com;first@example.com"},
            clear=True,
        ):
            self.assertEqual(configured_recipients(), ("first@example.com", "SECOND@example.com"))

    def test_missing_api_key_is_reported(self) -> None:
        environment = {key: value for key, value in ENVIRONMENT.items() if key != "BREVO_API_KEY"}
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(MissingNotificationConfig) as raised:
                load_notification_settings()
        self.assertEqual(raised.exception.missing, ["BREVO_API_KEY"])

    def test_whitespace_only_recipients_are_rejected(self) -> None:
        with mock.patch.dict(
            os.environ,
            {**ENVIRONMENT, "DIGA_MONITOR_EMAIL_TO": " , ; "},
            clear=True,
        ):
            with self.assertRaises(MissingNotificationConfig) as raised:
                load_notification_settings()
        self.assertIn("DIGA_MONITOR_EMAIL_TO", raised.exception.missing)

    def test_sender_settings_are_loaded_from_environment(self) -> None:
        with mock.patch.dict(os.environ, ENVIRONMENT, clear=True):
            settings = load_notification_settings()

        self.assertEqual(settings.brevo.email_from, "updates@diga-tracker.de")
        self.assertEqual(settings.brevo.email_from_name, "DiGA Tracker")
        self.assertEqual(settings.recipients, ("recipient@example.com",))

    def test_message_creation_is_separate_and_idempotent(self) -> None:
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "12345"}, clear=True):
            first = build_email_message(
                "sender@example.com",
                "Sender Name",
                ("first@example.com", "second@example.com"),
                "Subject",
                "Body",
            )
            second = build_email_message(
                "sender@example.com",
                "Sender Name",
                ("first@example.com", "second@example.com"),
                "Changed on retry",
                "Changed on retry",
            )
        self.assertEqual(first["headers"], second["headers"])
        self.assertEqual(first["sender"], {"email": "sender@example.com", "name": "Sender Name"})
        self.assertEqual(first["to"], [{"email": "first@example.com"}, {"email": "second@example.com"}])
        self.assertTrue(first["headers"]["idempotencyKey"])

    def test_successful_brevo_api_send(self) -> None:
        config = BrevoConfig(api_key="secret-key", email_from="sender@example.com", email_from_name="Sender Name")
        message = build_email_message(
            "sender@example.com", "Sender Name", ("recipient@example.com",), "Subject", "Body"
        )
        with mock.patch(
            "src.notifications.urlopen",
            return_value=FakeResponse(201, {"messageId": "message-123"}),
        ) as open_url:
            self.assertEqual(send_email(config, message), "message-123")

        self.assertEqual(open_url.call_count, 1)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, BREVO_EMAIL_API_URL)
        self.assertEqual(request.get_header("Api-key"), "secret-key")
        self.assertEqual(json.loads(request.data), message)

    def test_invalid_api_key_is_reported_without_secret(self) -> None:
        config = BrevoConfig(
            api_key="never-log-this-key", email_from="sender@example.com", email_from_name="Sender Name"
        )
        response = FakeResponse(401, {"code": "unauthorized", "message": "Key never-log-this-key invalid"})
        with mock.patch("src.notifications.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, r"HTTP 401") as raised:
                send_email(config, {})
        self.assertNotIn(config.api_key, str(raised.exception))
        self.assertIn("[redacted]", str(raised.exception))

    def test_api_error_is_caught_and_logged_without_secret(self) -> None:
        secret = ENVIRONMENT["BREVO_API_KEY"]
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch(
                "src.notifications.urlopen",
                return_value=FakeResponse(500, {"message": f"provider failure {secret}"}),
            ),
            mock.patch("src.notifications.log_notification") as notification_log,
            mock.patch("builtins.print") as output,
        ):
            self.assertFalse(notify_changes([event()]))

        logged_error = notification_log.call_args.kwargs["error_message"]
        printed = " ".join(str(call.args[0]) for call in output.call_args_list)
        self.assertEqual(notification_log.call_args.kwargs["status"], "failed")
        self.assertNotIn(secret, logged_error)
        self.assertNotIn(secret, printed)
        self.assertIn("HTTP 500", logged_error)

    def test_no_changes_does_not_call_brevo(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch("src.notifications.urlopen") as open_url,
            mock.patch("src.notifications.log_notification"),
        ):
            self.assertFalse(notify_changes([]))
        open_url.assert_not_called()

    def test_multiple_changes_send_one_consolidated_request(self) -> None:
        with (
            mock.patch.dict(os.environ, ENVIRONMENT, clear=True),
            mock.patch(
                "src.notifications.urlopen",
                return_value=FakeResponse(201, {"messageId": "message-456"}),
            ) as open_url,
            mock.patch("src.notifications.log_notification"),
        ):
            self.assertTrue(notify_changes([event("First DiGA"), event("Second DiGA")]))

        self.assertEqual(open_url.call_count, 1)
        payload = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(payload["sender"], {"email": "updates@diga-tracker.de", "name": "DiGA Tracker"})
        self.assertEqual(payload["to"], [{"email": "recipient@example.com"}])
        self.assertEqual(payload["subject"], "DiGA Watch: 2 Änderung(en) erkannt")
        self.assertIn("First DiGA", payload["textContent"])
        self.assertIn("Second DiGA", payload["textContent"])


if __name__ == "__main__":
    unittest.main()
