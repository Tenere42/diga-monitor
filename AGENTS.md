# AGENTS.md

## Source of Truth

- GitHub repository `Tenere42/diga-monitor` is the shared source of truth for ChatGPT, Codex, and Claude Code.
- Before starting a task, read the current state of `main` and review `PROJECT_STATE.md`.
- Keep `PROJECT_STATE.md` focused on the current handoff state. Update it after relevant completed work, not after every prompt.

## Roles

- ChatGPT owns architecture, prioritization, decisions, and the final GO/NO-GO assessment.
- Codex is the default primary implementer and owns implementation, tests, and GitHub work.
- Claude Code provides an independent review for larger or riskier changes.
- GitHub holds the shared code, branches, pull requests, review findings, and current project state.

## Change Workflow

Small, low-risk changes may be committed directly to `main`.

Larger or riskier changes must use this workflow:

```text
ChatGPT decision/spec
→ Codex implementation branch
→ tests
→ Claude Code CLI read-only review
→ Codex triages and fixes valid findings
→ tests and optional re-review (maximum 3 rounds)
→ create or update Pull Request
→ ChatGPT GO/NO-GO
→ merge to main
```

- Do not implement larger or riskier changes directly on `main`; use a dedicated branch and pull request.
- Run all relevant tests before merging.
- Codex executes required Git and shell commands itself. The user must not need to run manual Git or PowerShell commands.
- Prefer the direct GitHub Connector for GitHub operations.
- Prefer direct connectors and APIs; use local PowerShell or CLI workarounds only when necessary.

## Codex-Claude Duo Loop

For larger, riskier, or architecture-relevant changes, use the local Gauntlet workflow: Codex implements and runs tests and linters; Claude Code orchestrates independent Claude-Critic reviews; Claude Code then performs Git plumbing (add, commit, and push) on the implementation branch.

- The automatic GitHub Actions Claude PR review has been removed and is no longer the standard review path.
- `python -m scripts.claude_review --pr-number <PR>` remains available as a manually invoked local review tool; the wrapper invokes the verified Claude executable without depending on `PATH`.
- Manual automated reviews require `ANTHROPIC_API_KEY` from the local process environment. Never use, print, persist, or renew personal OAuth credentials for automated reviews.
- The wrapper must pass the Anthropic connectivity preflight before invoking Claude, remove OAuth/provider override variables from the child process, and use an isolated temporary `CLAUDE_CONFIG_DIR` so stored personal login state cannot take precedence or act as a fallback.
- Give Claude the task context and the complete relevant diff. Restrict it to `--allowedTools "Read,Grep,Glob,Bash(git diff:*)"` and cap each review with `--max-turns 20`.
- Claude must not edit files, run unrestricted shell commands, commit, push, or mutate GitHub state.
- Codex captures and critically triages Claude's findings. Fix valid findings, assess debatable suggestions on their merits, and do not blindly accept incorrect or out-of-scope feedback.
- Document a short reason when rejecting a substantive finding.
- After fixes, rerun relevant tests and linters. Request another Claude review only when the response caused substantive changes.
- Stop after Claude reports no substantive issues or after at most three Claude review rounds, whichever comes first. Codex remains accountable for the result; Claude is a reviewer, not a gatekeeper.
- Create or update the pull request after the review loop is complete, and summarize Claude's findings, accepted changes, and substantive rejections in the handoff.
- When a pull request receives a Claude CLI review, add a compact `Claude Review` section to the pull request description or update it before handoff. Record the number of review rounds, Claude's substantive findings, the findings Codex accepted and the resulting changes, any substantive findings Codex rejected with a short reason, and the final result as either `no substantive open findings` or `open findings`. Do not post complete internal logs or unnecessarily long Claude output.
- Small, obviously low-risk changes do not require a Claude review.
- If Claude CLI is unavailable or fails, do not block delivery: report the limitation transparently and perform an explicit Codex self-review instead.
- The manual local CLI review uses Anthropic API-key authentication and does not depend on personal OAuth, GitHub OIDC, or Workload Identity Federation.

## Safety and Production

- Do not delete production data or history until integrity, backup, and restore have been verified.
- Do not change existing production functionality without explicit authorization.
- Preserve unrelated user changes and keep each change scoped to the task.
