from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "claude-pr-review.yml"


class ClaudeReviewWorkflowTests(unittest.TestCase):
    def test_workflow_uses_only_repository_api_key_authentication(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}", workflow)
        self.assertNotIn("anthropics/claude-code-action", workflow)
        self.assertNotIn("secrets.GITHUB_TOKEN", workflow)
        self.assertNotIn("claude_code_oauth_token", workflow)
        self.assertNotIn("anthropic_federation_rule_id", workflow)
        self.assertNotIn("anthropic_organization_id", workflow)
        self.assertNotIn("anthropic_service_account_id", workflow)
        self.assertNotIn("id-token: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", workflow)

    def test_auth_check_precedes_read_only_review(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        check_position = workflow.index("Check Anthropic API-key authentication")
        review_position = workflow.index("Run read-only Claude review")
        self.assertLess(check_position, review_position)
        self.assertIn("run: python scripts/anthropic_auth_check.py", workflow)
        self.assertIn("python -m scripts.claude_review", workflow)
        self.assertIn("@anthropic-ai/claude-code@2.1.251", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertNotIn("Bash(git commit", workflow)
        self.assertNotIn("Bash(git push", workflow)


if __name__ == "__main__":
    unittest.main()
