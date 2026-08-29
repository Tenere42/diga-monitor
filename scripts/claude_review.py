"""Run the local Codex-Claude review loop with isolated API-key authentication."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.anthropic_auth_check import check_anthropic_api_key


AUTH_OVERRIDES_TO_REMOVE = (
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CODE_USE_VERTEX",
)


def isolated_claude_environment(config_dir: Path) -> dict[str, str]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError("ANTHROPIC_API_KEY is not available; refusing OAuth fallback.")
    environment = os.environ.copy()
    for name in AUTH_OVERRIDES_TO_REMOVE:
        environment.pop(name, None)
    environment["ANTHROPIC_API_KEY"] = api_key
    environment["CLAUDE_CONFIG_DIR"] = str(config_dir)
    environment["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return environment


def review_prompt(pr_number: int, base_ref: str) -> str:
    return f"""Review pull request #{pr_number} as an independent read-only reviewer.
Read AGENTS.md and PROJECT_STATE.md, then inspect the complete diff against {base_ref}.
Focus on correctness, regressions, security, data integrity, operational risk, and tests.
Do not edit files, commit, push, or mutate GitHub state.
Return concise substantive findings with file and line references, or state that there are no substantive findings.
"""


def run_review(claude_executable: Path, prompt: str) -> int:
    check_anthropic_api_key()
    with tempfile.TemporaryDirectory(prefix="diga-claude-review-") as directory:
        environment = isolated_claude_environment(Path(directory))
        result = subprocess.run(
            [
                str(claude_executable),
                "-p",
                prompt,
                "--allowedTools",
                "Read,Grep,Glob,Bash(git diff:*)",
                "--max-turns",
                "20",
            ],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
    key = environment["ANTHROPIC_API_KEY"]
    if result.stdout:
        print(result.stdout.replace(key, "[redacted]"), end="")
    if result.stderr:
        print(result.stderr.replace(key, "[redacted]"), end="", file=sys.stderr)
    if result.returncode:
        print(f"Claude review failed with exit code {result.returncode}.", file=sys.stderr)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--claude-executable", type=Path)
    return parser


def resolve_claude_executable(configured: Path | None) -> Path:
    if configured is not None:
        return configured
    discovered = shutil.which("claude")
    if not discovered:
        raise RuntimeError("Claude executable was not found; pass --claude-executable explicitly.")
    return Path(discovered)


def main() -> int:
    args = build_parser().parse_args()
    try:
        executable = resolve_claude_executable(args.claude_executable)
        return run_review(executable, review_prompt(args.pr_number, args.base_ref))
    except RuntimeError as exc:
        print(f"Claude review preflight failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
