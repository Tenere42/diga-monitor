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
        for name in ("R2_ENDPOINT", "R2_BUCKET_NAME", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
            self.assertIn(name, workflow)
        self.assertNotIn("data/snapshots outputs/changes", workflow)


if __name__ == "__main__":
    unittest.main()
