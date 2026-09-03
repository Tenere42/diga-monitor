"""T5/T7: the admin notification and the subscriber-alert dispatch are
called in the correct order and are fully isolated from each other, at
the exact orchestration point used by the production scan pipeline
(src.main.notify_and_dispatch_subscriber_alerts).
"""

from __future__ import annotations

import unittest
from unittest import mock

from src.main import notify_and_dispatch_subscriber_alerts


EVENTS = [{"diga_name": "Test DiGA", "change_type": "price_change"}]


class NotifyAndDispatchIsolationTests(unittest.TestCase):
    def test_admin_notification_is_always_called_first(self) -> None:
        call_order: list[str] = []
        with (
            mock.patch(
                "src.main.notify_changes",
                side_effect=lambda *a, **k: call_order.append("admin"),
            ),
            mock.patch(
                "src.main.dispatch_subscriber_alerts",
                side_effect=lambda *a, **k: call_order.append("subscriber"),
            ),
        ):
            notify_and_dispatch_subscriber_alerts(EVENTS, dry_run=False)

        self.assertEqual(call_order, ["admin", "subscriber"])

    def test_t5_admin_notification_receives_the_same_arguments_as_before(self) -> None:
        with (
            mock.patch("src.main.notify_changes") as notify_mock,
            mock.patch("src.main.dispatch_subscriber_alerts"),
        ):
            notify_and_dispatch_subscriber_alerts(EVENTS, dry_run=True)

        notify_mock.assert_called_once_with(EVENTS, dry_run=True)

    def test_subscriber_dispatch_receives_the_same_events_and_dry_run_arguments(self) -> None:
        with (
            mock.patch("src.main.notify_changes"),
            mock.patch("src.main.dispatch_subscriber_alerts") as dispatch_mock,
        ):
            notify_and_dispatch_subscriber_alerts(EVENTS, dry_run=True)

        dispatch_mock.assert_called_once_with(EVENTS, dry_run=True)

    def test_t7_subscriber_alert_exception_never_propagates(self) -> None:
        with (
            mock.patch("src.main.notify_changes") as notify_mock,
            mock.patch(
                "src.main.dispatch_subscriber_alerts",
                side_effect=RuntimeError("brevo campaign api is down"),
            ),
        ):
            # Must not raise.
            notify_and_dispatch_subscriber_alerts(EVENTS, dry_run=False)

        notify_mock.assert_called_once()

    def test_t7_admin_notification_still_runs_even_if_subscriber_dispatch_would_fail(self) -> None:
        # Admin notification always runs first and completes regardless of
        # what happens afterwards in the subscriber-alert path.
        with (
            mock.patch("src.main.notify_changes", return_value=True) as notify_mock,
            mock.patch(
                "src.main.dispatch_subscriber_alerts",
                side_effect=RuntimeError("boom"),
            ),
        ):
            notify_and_dispatch_subscriber_alerts(EVENTS, dry_run=False)

        self.assertTrue(notify_mock.called)


if __name__ == "__main__":
    unittest.main()
