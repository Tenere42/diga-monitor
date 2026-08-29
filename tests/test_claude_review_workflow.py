from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "claude-pr-review.yml"


class ClaudeReviewWorkflowTests(unittest.TestCase):
    def test_workflow_uses_only_repository_api_key_authentication(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}", workflow)
        self.assertIn("anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}", workflow)
        self.assertNotIn("claude_code_oauth_token", workflow)
        self.assertNotIn("anthropic_federation_rule_id", workflow)
        self.assertNotIn("anthropic_organization_id", workflow)
        self.assertNotIn("anthropic_service_account_id", workflow)
        self.assertNotIn("id-token: write", workflow)

    def test_auth_check_precedes_read_only_review(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        check_position = workflow.index("Check Anthropic API-key authentication")
        review_position = workflow.index("Review pull request")
        self.assertLess(check_position, review_position)
        self.assertIn("run: python scripts/anthropic_auth_check.py", workflow)
        self.assertIn("--max-turns 10", workflow)
        self.assertNotIn("Bash(git commit", workflow)
        self.assertNotIn("Bash(git push", workflow)


if __name__ == "__main__":
    unittest.main()
