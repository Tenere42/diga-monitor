from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "diga-monitor.yml"


class WorkflowScheduleTests(unittest.TestCase):
    def test_schedule_and_supported_fallback_triggers(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("repository_dispatch:", workflow)
        self.assertIn("types: [scheduled-scan]", workflow)
        self.assertIn('cron: "0 6,9,12,15,18 * * *"', workflow)
        self.assertIn('timezone: "Europe/Zurich"', workflow)

    def test_concurrency_and_r2_configuration(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("concurrency:\n  group: diga-monitor\n  cancel-in-progress: false", workflow)
        self.assertIn("R2_ENDPOINT: ${{ vars.R2_ENDPOINT || vars.S3_ENDPOINT }}", workflow)
        self.assertIn("R2_BUCKET_NAME: ${{ vars.R2_BUCKET_NAME || 'diga-monitor' }}", workflow)
        self.assertIn(
            "R2_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID || secrets.ACCESS_KEY_ID }}",
            workflow,
        )
        self.assertIn(
            "R2_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY || secrets.SECRET_ACCESS_KEY }}",
            workflow,
        )
        self.assertIn('R2_ARCHIVE_REQUIRED: "true"', workflow)
        self.assertIn("- name: Diagnose R2 configuration metadata", workflow)
        for metadata in (
            "present=",
            "length=",
            "contains_lf=",
            "contains_cr=",
            "boundary_whitespace=",
        ):
            self.assertIn(metadata, workflow)
        self.assertNotIn("data/snapshots outputs/changes", workflow)

    def test_notification_sender_and_manual_test_are_safely_configured(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(
            workflow.count("DIGA_MONITOR_EMAIL_FROM: ${{ vars.DIGA_MONITOR_EMAIL_FROM }}"),
            3,
        )
        self.assertEqual(
            workflow.count("DIGA_MONITOR_EMAIL_FROM_NAME: ${{ vars.DIGA_MONITOR_EMAIL_FROM_NAME }}"),
            3,
        )
        self.assertNotIn("EMAIL_FROM: ${{ vars.EMAIL_FROM }}", workflow)
        self.assertIn("run: python -m src.main notify-test", workflow)
        self.assertIn(
            "github.event_name != 'workflow_dispatch' || inputs.notification_test != 'true'",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
