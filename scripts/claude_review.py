"""Run a read-only Claude pull request review with isolated API-key authentication."""

from __future__ import annotations

import argparse
import json
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
# Claude only reads; the trusted wrapper runs git and hands over the diff as a file.
REVIEW_TOOLS = "Read,Grep,Glob"
MAX_TURNS = "20"
DEFAULT_MAX_BUDGET_USD = "1.00"
DIFF_FILE_NAME = "pull-request.diff"


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


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"git {args[0]} failed with exit code {result.returncode}.")
    return result.stdout


def write_pull_request_diff(base_ref: str, directory: Path) -> tuple[Path, str]:
    revision_range = f"{base_ref}...HEAD"
    options = ("--no-ext-diff", "--no-textconv", "--no-color")
    diff_path = directory / DIFF_FILE_NAME
    diff_path.write_text(_git("diff", *options, revision_range), encoding="utf-8")
    return diff_path, _git("diff", *options, "--stat", revision_range).strip()


def review_prompt(pr_number: int, base_ref: str, diff_path: Path, diff_stat: str) -> str:
    return f"""Review pull request #{pr_number} as an independent read-only reviewer.
The complete diff `{base_ref}...HEAD` is in `{diff_path}`. Changed files:
{diff_stat or "(empty diff)"}

Read AGENTS.md and PROJECT_STATE.md, then the diff file, and the surrounding code where needed.
Focus on correctness, regressions, security, data integrity, operational risk, and tests.
Do not edit files, commit, push, or mutate GitHub state.
Return concise substantive findings with file and line references, or state that there are no substantive findings.
"""


def review_command(
    claude_executable: Path,
    prompt: str,
    model: str | None,
    diff_directory: Path,
    max_budget_usd: str = DEFAULT_MAX_BUDGET_USD,
) -> list[str]:
    command = [
        str(claude_executable),
        "-p",
        prompt,
        "--tools",
        REVIEW_TOOLS,
        "--allowedTools",
        REVIEW_TOOLS,
        "--add-dir",
        str(diff_directory),
        "--max-turns",
        MAX_TURNS,
        "--max-budget-usd",
        max_budget_usd,
        "--setting-sources",
        "user",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format",
        "json",
    ]
    if model:
        command += ["--model", model]
    return command


def usage_lines(payload: dict, max_budget_usd: str) -> list[str]:
    lines = []
    model_usage = payload.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        for model, usage in sorted(model_usage.items()):
            if not isinstance(usage, dict):
                continue
            lines.append(
                f"- `{model}`: input {usage.get('inputTokens', 0):,}, "
                f"output {usage.get('outputTokens', 0):,}, "
                f"cache read {usage.get('cacheReadInputTokens', 0):,}, "
                f"cache write {usage.get('cacheCreationInputTokens', 0):,} tokens"
                + (f", USD {usage['costUSD']:.4f}" if isinstance(usage.get("costUSD"), (int, float)) else "")
            )
    elif isinstance(payload.get("usage"), dict):
        usage = payload["usage"]
        lines.append(
            f"- input {usage.get('input_tokens', 0):,}, output {usage.get('output_tokens', 0):,}, "
            f"cache read {usage.get('cache_read_input_tokens', 0):,}, "
            f"cache write {usage.get('cache_creation_input_tokens', 0):,} tokens"
        )
    else:
        lines.append("- usage not reported by Claude CLI")
    cost = payload.get("total_cost_usd")
    if isinstance(cost, (int, float)):
        lines.append(f"- total cost estimate: USD {cost:.4f} (budget limit USD {max_budget_usd})")
    else:
        lines.append(f"- total cost estimate: not reported (budget limit USD {max_budget_usd})")
    if payload.get("num_turns") is not None:
        lines.append(f"- turns: {payload['num_turns']} (limit {MAX_TURNS})")
    return lines


def review_summary(
    payload: dict,
    pr_number: int,
    base_ref: str,
    head_sha: str | None,
    failed: bool,
    max_budget_usd: str = DEFAULT_MAX_BUDGET_USD,
) -> str:
    head = f" · HEAD `{head_sha}`" if head_sha else ""
    status = (
        f"**Status: failed** (`{payload.get('subtype', 'unknown')}`); findings may be missing or incomplete."
        if failed
        else "Status: completed"
    )
    body = payload.get("result")
    if not isinstance(body, str) or not body.strip():
        body = f"_No review text returned (Claude CLI subtype: `{payload.get('subtype', 'unknown')}`)._"
    return "\n".join(
        [
            "## Claude Review",
            "",
            f"PR #{pr_number}{head} · diff `{base_ref}...HEAD`",
            "",
            status,
            "",
            body.strip(),
            "",
            "### Model and token usage",
            "",
            *usage_lines(payload, max_budget_usd),
            "",
        ]
    )


def run_review(
    claude_executable: Path,
    *,
    pr_number: int,
    base_ref: str = "origin/main",
    model: str | None = None,
    head_sha: str | None = None,
    summary_file: Path | None = None,
    max_budget_usd: str = DEFAULT_MAX_BUDGET_USD,
) -> int:
    check_anthropic_api_key()
    with (
        tempfile.TemporaryDirectory(prefix="diga-claude-review-") as config_directory,
        tempfile.TemporaryDirectory(prefix="diga-claude-diff-") as diff_directory,
    ):
        diff_path, diff_stat = write_pull_request_diff(base_ref, Path(diff_directory))
        environment = isolated_claude_environment(Path(config_directory))
        result = subprocess.run(
            review_command(
                claude_executable,
                review_prompt(pr_number, base_ref, diff_path, diff_stat),
                model,
                Path(diff_directory),
                max_budget_usd,
            ),
            env=environment,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
        )
    key = environment["ANTHROPIC_API_KEY"]
    stdout = (result.stdout or "").replace(key, "[redacted]")
    if result.stderr:
        print(result.stderr.replace(key, "[redacted]"), end="", file=sys.stderr)
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        if stdout:
            print(stdout, end="", file=sys.stderr)
        print("Claude review returned no parseable JSON result.", file=sys.stderr)
        payload = {"subtype": "no_parseable_output", "is_error": True}

    failed = bool(result.returncode or payload.get("is_error"))
    # Written on success and failure alike so that incurred usage is always reported.
    summary = review_summary(payload, pr_number, base_ref, head_sha, failed, max_budget_usd)
    print(summary)
    if summary_file is not None:
        summary_file.write_text(summary, encoding="utf-8")
    if failed:
        print(f"Claude review failed with exit code {result.returncode}.", file=sys.stderr)
        return result.returncode or 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--claude-executable", type=Path)
    parser.add_argument("--model", help="Claude model ID; defaults to the Claude CLI default.")
    parser.add_argument("--head-sha", help="Reviewed commit, recorded in the summary.")
    parser.add_argument("--summary-file", type=Path, help="Also write the Markdown summary to this file.")
    parser.add_argument(
        "--max-budget-usd",
        default=DEFAULT_MAX_BUDGET_USD,
        help=f"Hard API spend limit per review (default {DEFAULT_MAX_BUDGET_USD}).",
    )
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
        float(args.max_budget_usd)
        executable = resolve_claude_executable(args.claude_executable)
        return run_review(
            executable,
            pr_number=args.pr_number,
            base_ref=args.base_ref,
            model=args.model,
            head_sha=args.head_sha,
            summary_file=args.summary_file,
            max_budget_usd=args.max_budget_usd,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"Claude review preflight failed: {exc}", file=sys.stderr)
        if args.summary_file is not None:
            args.summary_file.write_text(
                f"## Claude Review\n\nPR #{args.pr_number}\n\n**Status: failed before Claude started** "
                f"(no API usage).\n\n{exc}\n",
                encoding="utf-8",
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
