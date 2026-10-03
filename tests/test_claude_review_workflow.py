from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "claude-pr-review.yml"


def job_block(workflow: str, name: str) -> str:
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", workflow, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(1)


class ClaudeReviewWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_manual_only(self) -> None:
        triggers = self.workflow.split("\npermissions:", 1)[0]
        self.assertIn("workflow_dispatch:", triggers)
        for trigger in ("pull_request", "pull_request_target", "push:", "schedule:", "issue_comment", "workflow_run"):
            self.assertNotIn(trigger, triggers)

    def test_uses_only_repository_api_key_authentication(self) -> None:
        self.assertIn("ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}", self.workflow)
        for forbidden in (
            "anthropics/claude-code-action",
            "claude_code_oauth_token",
            "CLAUDE_CODE_OAUTH_TOKEN",
            "id-token: write",
            "anthropic_federation_rule_id",
            "secrets.GITHUB_TOKEN",
        ):
            self.assertNotIn(forbidden, self.workflow)

    def test_no_merge_deploy_or_repository_write(self) -> None:
        for forbidden in ("gh pr merge", "--auto", "railway", "git push", "contents: write", "actions: write"):
            self.assertNotIn(forbidden, self.workflow)
        self.assertIn("permissions: {}", self.workflow)

    def test_review_job_is_read_only_and_holds_the_only_api_key(self) -> None:
        review = job_block(self.workflow, "review")
        comment = job_block(self.workflow, "comment")
        self.assertIn("contents: read", review)
        self.assertIn("pull-requests: read", review)
        self.assertNotIn(": write", review)
        self.assertNotIn("ANTHROPIC_API_KEY", comment)
        self.assertIn("pull-requests: write", comment)
        self.assertNotIn("actions/checkout", comment)
        self.assertEqual(review.count("persist-credentials: false"), 2)

    def test_pull_request_is_validated_and_never_executed(self) -> None:
        review = job_block(self.workflow, "review")
        self.assertIn("Fork pull requests are not reviewed.", review)
        self.assertIn("Only open pull requests are reviewed.", review)
        self.assertIn('python "$GITHUB_WORKSPACE/trusted/scripts/claude_review.py"', review)
        self.assertIn('python "$GITHUB_WORKSPACE/trusted/scripts/anthropic_auth_check.py"', review)
        self.assertNotIn("pip install", review)
        self.assertNotIn("python -m scripts", review)

    def test_auth_check_precedes_review_and_cli_is_pinned(self) -> None:
        check_position = self.workflow.index("Check Anthropic API-key authentication")
        review_position = self.workflow.index("Run read-only Claude review")
        self.assertLess(check_position, review_position)
        self.assertRegex(self.workflow, r"@anthropic-ai/claude-code@\d+\.\d+\.\d+\n")
        self.assertIn("--model \"$MODEL\"", self.workflow)
        self.assertIn("fetch-depth: 0", self.workflow)

    def test_spend_is_capped(self) -> None:
        self.assertIn('--max-budget-usd "1.00"', job_block(self.workflow, "review"))

    def test_failed_reviews_still_publish_usage(self) -> None:
        review = job_block(self.workflow, "review")
        comment = job_block(self.workflow, "comment")
        upload = review[review.index("- name: Upload review"):]
        self.assertIn("if: always()", upload)
        self.assertNotIn("if-no-files-found: error", upload)
        self.assertIn("if: ${{ !cancelled() }}", comment)
        self.assertIn("continue-on-error: true", comment)
        self.assertIn("if [ ! -f claude-review.md ]", comment)

    def test_claude_gets_no_shell(self) -> None:
        self.assertNotIn("Bash(", self.workflow)
        self.assertNotIn("--allowedTools", self.workflow)


if __name__ == "__main__":
    unittest.main()
