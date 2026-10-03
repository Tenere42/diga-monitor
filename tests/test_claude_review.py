from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

from scripts.anthropic_auth_check import ANTHROPIC_MODELS_URL, check_anthropic_api_key, main as auth_main
from scripts.claude_review import (
    AUTH_OVERRIDES_TO_REMOVE,
    isolated_claude_environment,
    resolve_claude_executable,
    review_command,
    run_review,
)


class FakeResponse:
    status = 200

    def read(self, size: int = -1) -> bytes:
        return b"{}"[:size]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class ClaudeReviewTests(unittest.TestCase):
    def test_auth_check_requires_api_key_without_network_call(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "scripts.anthropic_auth_check.urlopen"
        ) as open_url:
            with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY is not available"):
                check_anthropic_api_key()
        open_url.assert_not_called()

    def test_auth_check_uses_header_and_does_not_print_key(self) -> None:
        with mock.patch("scripts.anthropic_auth_check.urlopen", return_value=FakeResponse()) as open_url:
            check_anthropic_api_key("test-secret-key")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, ANTHROPIC_MODELS_URL)
        self.assertEqual(request.get_header("X-api-key"), "test-secret-key")

    def test_auth_failure_does_not_expose_key_or_response_body(self) -> None:
        error = HTTPError(
            ANTHROPIC_MODELS_URL,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b"invalid test-secret-key"),
        )
        with (
            mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret-key"}, clear=True),
            mock.patch("scripts.anthropic_auth_check.urlopen", side_effect=error),
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            self.assertEqual(auth_main(), 1)
        self.assertNotIn("test-secret-key", stderr.getvalue())
        self.assertNotIn("invalid", stderr.getvalue())
        self.assertIn("HTTP 401", stderr.getvalue())

    def test_isolated_environment_removes_oauth_and_provider_overrides(self) -> None:
        source = {
            "ANTHROPIC_API_KEY": "test-secret-key",
            "ANTHROPIC_AUTH_TOKEN": "old-auth-token",
            "ANTHROPIC_BASE_URL": "https://old-gateway.invalid",
            "CLAUDE_CODE_OAUTH_TOKEN": "old-oauth-token",
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "CLAUDE_CODE_USE_FOUNDRY": "1",
            "CLAUDE_CODE_USE_VERTEX": "1",
        }
        with mock.patch.dict(os.environ, source, clear=True):
            environment = isolated_claude_environment(Path("isolated-config"))
        self.assertEqual(environment["ANTHROPIC_API_KEY"], "test-secret-key")
        self.assertEqual(environment["CLAUDE_CONFIG_DIR"], "isolated-config")
        for name in AUTH_OVERRIDES_TO_REMOVE:
            self.assertNotIn(name, environment)

    def _run(self, stdout: str, returncode: int = 0, **kwargs: object) -> tuple[int, mock.MagicMock, str]:
        completed = subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")
        with (
            mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret-key"}, clear=True),
            mock.patch("scripts.claude_review.check_anthropic_api_key"),
            mock.patch(
                "scripts.claude_review.tempfile.TemporaryDirectory"
            ) as temporary_directory,
            mock.patch("scripts.claude_review.subprocess.run", return_value=completed) as run,
            mock.patch("sys.stdout", new_callable=io.StringIO) as output,
            mock.patch("sys.stderr", new_callable=io.StringIO),
        ):
            temporary_directory.return_value.__enter__.return_value = "isolated-config"
            code = run_review(Path("claude"), "Review PR", **kwargs)
        return code, run, output.getvalue()

    def test_review_is_read_only_isolated_and_redacts_output(self) -> None:
        payload = json.dumps({"result": "review ok test-secret-key", "is_error": False})
        code, run, output = self._run(payload, model="claude-sonnet-5-5")
        self.assertEqual(code, 0)

        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertEqual(
            command,
            [
                "claude",
                "-p",
                "Review PR",
                "--tools",
                "Read,Grep,Glob,Bash",
                "--allowedTools",
                "Read,Grep,Glob,Bash(git diff:*)",
                "--max-turns",
                "20",
                "--setting-sources",
                "user",
                "--strict-mcp-config",
                "--no-session-persistence",
                "--output-format",
                "json",
                "--model",
                "claude-sonnet-5-5",
            ],
        )
        self.assertNotIn("Edit", command)
        self.assertNotIn("Write", command)
        self.assertNotIn("test-secret-key", " ".join(command))
        self.assertNotIn("test-secret-key", output)
        self.assertIn("[redacted]", output)
        self.assertNotEqual(environment["CLAUDE_CONFIG_DIR"], str(Path.home() / ".claude"))

    def test_project_settings_and_model_default_are_not_used(self) -> None:
        command = review_command(Path("claude"), "Review PR", None)
        self.assertNotIn("--model", command)
        self.assertEqual(command[command.index("--setting-sources") + 1], "user")
        self.assertIn("--strict-mcp-config", command)

    def test_summary_records_model_tokens_cost_and_head(self) -> None:
        payload = json.dumps(
            {
                "result": "No substantive findings.",
                "is_error": False,
                "num_turns": 7,
                "total_cost_usd": 0.1234,
                "modelUsage": {
                    "claude-sonnet-5-5": {
                        "inputTokens": 1200,
                        "outputTokens": 340,
                        "cacheReadInputTokens": 50000,
                        "cacheCreationInputTokens": 8000,
                        "costUSD": 0.1234,
                    }
                },
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            summary_file = Path(directory) / "review.md"
            code, _, output = self._run(
                payload, pr_number=42, base_ref="origin/main", head_sha="a" * 40, summary_file=summary_file
            )
            summary = summary_file.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertEqual(summary.strip(), output.strip())
        self.assertIn("PR #42 · HEAD `" + "a" * 40 + "`", summary)
        self.assertIn("No substantive findings.", summary)
        self.assertIn("`claude-sonnet-5-5`: input 1,200, output 340, cache read 50,000, cache write 8,000 tokens", summary)
        self.assertIn("total cost estimate: USD 0.1234", summary)
        self.assertIn("turns: 7 (limit 20)", summary)

    def test_error_result_fails_and_still_reports_usage(self) -> None:
        payload = json.dumps({"subtype": "error_max_turns", "is_error": True, "usage": {"input_tokens": 5}})
        code, _, output = self._run(payload)
        self.assertEqual(code, 1)
        self.assertIn("error_max_turns", output)
        self.assertIn("input 5", output)

    def test_unparseable_output_fails(self) -> None:
        code, _, _ = self._run("Credit balance is too low", returncode=1)
        self.assertEqual(code, 1)

    def test_executable_is_portable_and_fails_clearly_when_missing(self) -> None:
        with mock.patch("scripts.claude_review.shutil.which", return_value="/usr/local/bin/claude"):
            self.assertEqual(resolve_claude_executable(None), Path("/usr/local/bin/claude"))
        with mock.patch("scripts.claude_review.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Claude executable was not found"):
                resolve_claude_executable(None)
        self.assertEqual(resolve_claude_executable(Path("custom-claude")), Path("custom-claude"))


if __name__ == "__main__":
    unittest.main()
