from pathlib import Path
import unittest


WORKFLOW_PATH = Path(".github/workflows/r2-connectivity-check.yml")


class R2ConnectivityWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_workflow_is_manual_and_does_not_run_monitor(self) -> None:
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertNotIn("schedule:", self.workflow)
        self.assertNotIn("repository_dispatch:", self.workflow)
        self.assertNotIn("src.main", self.workflow)
        self.assertNotIn("Run DiGA monitor", self.workflow)

    def test_workflow_uses_existing_r2_configuration_and_diagnostic(self) -> None:
        self.assertIn("R2_ENDPOINT: ${{ vars.R2_ENDPOINT || vars.S3_ENDPOINT }}", self.workflow)
        self.assertIn("R2_BUCKET_NAME: diga-monitor", self.workflow)
        self.assertIn(
            "R2_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID || secrets.ACCESS_KEY_ID }}",
            self.workflow,
        )
        self.assertIn(
            "R2_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY || secrets.SECRET_ACCESS_KEY }}",
            self.workflow,
        )
        self.assertIn('R2_ARCHIVE_REQUIRED: "true"', self.workflow)
        self.assertIn("python -m scripts.r2_connectivity_check", self.workflow)

    def test_workflow_has_minimal_permissions(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.workflow)


if __name__ == "__main__":
    unittest.main()
