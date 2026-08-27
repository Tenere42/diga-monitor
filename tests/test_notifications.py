from __future__ import annotations

import os
import unittest
from unittest import mock

from src.notifications import (
    MissingNotificationConfig,
    build_email_messages,
    configured_recipients,
    load_notification_settings,
    notify_changes,
    send_email,
)


class NotificationConfigurationTests(unittest.TestCase):
    def test_recipient_configuration_is_external_and_future_multi_recipient_ready(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"DIGA_MONITOR_EMAIL_TO": "first@example.com, SECOND@example.com;first@example.com"},
            clear=True,
        ):
            self.assertEqual(
                configured_recipients(),
                ("first@example.com", "SECOND@example.com"),
            )

    def test_legacy_email_to_does_not_configure_production_recipient(self) -> None:
        environment = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "username",
            "SMTP_PASSWORD": "password",
            "EMAIL_FROM": "sender@example.com",
            "EMAIL_TO": "legacy@example.com",
            "DASHBOARD_URL": "https://example.com",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(MissingNotificationConfig) as raised:
                load_notification_settings()
        self.assertIn("DIGA_MONITOR_EMAIL_TO", raised.exception.missing)

    def test_notification_settings_keep_smtp_and_recipients_separate(self) -> None:
        environment = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "username",
            "SMTP_PASSWORD": "password",
            "EMAIL_FROM": "sender@example.com",
            "DIGA_MONITOR_EMAIL_TO": "recipient@example.com",
            "DASHBOARD_URL": "https://example.com",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            settings = load_notification_settings()
        self.assertEqual(settings.recipients, ("recipient@example.com",))
        self.assertEqual(settings.smtp.email_from, "sender@example.com")

    def test_whitespace_only_recipient_configuration_is_rejected(self) -> None:
        environment = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "username",
            "SMTP_PASSWORD": "password",
            "EMAIL_FROM": "sender@example.com",
            "DIGA_MONITOR_EMAIL_TO": " , ; ",
            "DASHBOARD_URL": "https://example.com",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(MissingNotificationConfig) as raised:
                load_notification_settings()
        self.assertIn("DIGA_MONITOR_EMAIL_TO", raised.exception.missing)

    def test_message_creation_and_smtp_delivery_are_separate(self) -> None:
        messages = build_email_messages(
            "sender@example.com",
            ("first@example.com", "second@example.com"),
            "Subject",
            "Body",
        )
        self.assertEqual([message["To"] for message in messages], ["first@example.com", "second@example.com"])

        settings_environment = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "username",
            "SMTP_PASSWORD": "password",
            "EMAIL_FROM": "sender@example.com",
            "DIGA_MONITOR_EMAIL_TO": "first@example.com,second@example.com",
            "DASHBOARD_URL": "https://example.com",
        }
        with mock.patch.dict(os.environ, settings_environment, clear=True):
            smtp_config = load_notification_settings().smtp
        with mock.patch("src.notifications.smtplib.SMTP") as smtp_type:
            send_email(smtp_config, messages)
        smtp = smtp_type.return_value.__enter__.return_value
        self.assertEqual(smtp.send_message.call_count, 2)

    def test_notification_send_failure_is_caught_and_logged(self) -> None:
        environment = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "username",
            "SMTP_PASSWORD": "password",
            "EMAIL_FROM": "sender@example.com",
            "DIGA_MONITOR_EMAIL_TO": "recipient@example.com",
            "DASHBOARD_URL": "https://example.com",
        }
        event = {
            "detected_at": "2026-08-27T12:00:00+00:00",
            "diga_name": "Test DiGA",
            "changed_field": "manufacturer",
            "previous_value": "Before",
            "new_value": "After",
        }
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch("src.notifications.send_email", side_effect=RuntimeError("SMTP failed")),
            mock.patch("src.notifications.log_notification") as log_notification,
        ):
            self.assertFalse(notify_changes([event]))

        self.assertEqual(log_notification.call_args.kwargs["status"], "failed")
        self.assertIn("SMTP failed", log_notification.call_args.kwargs["error_message"])


if __name__ == "__main__":
    unittest.main()
