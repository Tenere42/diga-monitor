import unittest
from unittest.mock import patch, Mock
from src.public_changes import needs_review, is_public
from src.notification_email import email_items
from src.notifications import notify_review_required

class ReviewQuarantineTests(unittest.TestCase):
    def event(self, field='descriptive_texts.questionnaire.923'):
        return dict(diga_id='00450', diga_name='deprexis', changed_field=field,
                    change_type='visible_diff_unresolved', previous_value='Zutreffend', new_value=None)

    def test_hidden_everywhere_without_mutating_history(self):
        event = self.event()
        original = event.copy()
        self.assertTrue(needs_review(event))
        self.assertFalse(is_public(event))
        self.assertEqual(email_items([event]), [])
        self.assertEqual(event, original)

    def test_clear_changes_remain_public(self):
        event = self.event('manufacturer')
        event.update(change_type='other_field_change', previous_value='Old GmbH', new_value='New GmbH')
        self.assertFalse(needs_review(event))
        self.assertTrue(is_public(event))

    def test_generic_unresolved_missing_value(self):
        self.assertTrue(needs_review(self.event('unmapped_field')))

    @patch('src.notifications.send_email')
    @patch('src.notifications.load_notification_settings')
    def test_internal_audience_only(self, settings, send):
        settings.return_value = Mock(recipients=('admin@example.test',))
        self.assertTrue(notify_review_required([self.event()]))
        message = send.call_args.args[1]
        self.assertEqual(message['to'], [{'email': 'admin@example.test'}])
        self.assertIn('Prüfung erforderlich', message['subject'])
        self.assertIn('923', message['textContent'])

    @patch('src.notifications.send_email')
    def test_cleanup_and_dry_run_do_not_send(self, send):
        self.assertFalse(notify_review_required([], dry_run=False))
        self.assertFalse(notify_review_required([self.event()], dry_run=True))
        send.assert_not_called()

    @patch('src.main.dispatch_subscriber_alerts')
    @patch('src.main.notify_changes')
    @patch('src.main.notify_review_required')
    def test_mixed_scan_routes_only_clear_events_to_alerts(self, review, admin, subscribers):
        from src.main import notify_and_dispatch_subscriber_alerts
        unclear = self.event()
        clear = dict(self.event('manufacturer'), change_type='other_field_change',
                     previous_value='Old GmbH', new_value='New GmbH')
        notify_and_dispatch_subscriber_alerts([unclear, clear])
        review.assert_called_once_with([unclear, clear], dry_run=False)
        admin.assert_called_once_with([clear], dry_run=False)
        subscribers.assert_called_once_with([clear], dry_run=False)

    def test_historical_923_hidden_but_other_adjustments_survive(self):
        import app
        events = app.load_change_events(app.DEFAULT_CHANGES_DIR)
        numeric = [e for e in events if e.get('changed_field', '').endswith('.923')]
        self.assertEqual(len(numeric), 29)
        self.assertTrue(all(not is_public(e) for e in numeric))
        groups = app.homepage_event_groups(events)
        self.assertFalse(any(needs_review(e) for g in groups for e in g['events']))
        self.assertTrue(any(e.get('changed_field') == 'manufacturer' for g in groups for e in g['events']))
