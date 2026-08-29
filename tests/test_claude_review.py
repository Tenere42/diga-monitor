from __future__ import annotations

import io
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

from scripts.anthropic_auth_check import ANTHROPIC_MODELS_URL, check_anthropic_api_key, main as auth_main
from scripts.claude_review import AUTH_OVERRIDES_TO_REMOVE, isolated_claude_environment, run_review


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

    def test_review_is_read_only_isolated_and_redacts_output(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="review ok test-secret-key\n", stderr=""
        )
        with (
            mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-secret-key"}, clear=True),
            mock.patch("scripts.claude_review.check_anthropic_api_key"),
            mock.patch(
                "scripts.claude_review.tempfile.TemporaryDirectory"
            ) as temporary_directory,
            mock.patch("scripts.claude_review.subprocess.run", return_value=completed) as run,
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            temporary_directory.return_value.__enter__.return_value = "isolated-config"
            self.assertEqual(run_review(Path("claude"), "Review PR"), 0)

        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertEqual(
            command,
            [
                "claude",
                "-p",
                "Review PR",
                "--allowedTools",
                "Read,Grep,Glob,Bash(git diff*)",
                "--max-turns",
                "20",
            ],
        )
        self.assertNotIn("Edit", command)
        self.assertNotIn("Write", command)
        self.assertNotIn("test-secret-key", " ".join(command))
        self.assertNotIn("test-secret-key", stdout.getvalue())
        self.assertIn("[redacted]", stdout.getvalue())
        self.assertNotEqual(environment["CLAUDE_CONFIG_DIR"], str(Path.home() / ".claude"))


if __name__ == "__main__":
    unittest.main()
