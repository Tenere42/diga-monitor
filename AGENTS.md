# AGENTS.md

## Source of Truth

- GitHub repository `Tenere42/diga-monitor` is the shared source of truth for ChatGPT, Codex, and Claude Code.
- Before starting a task, read the current state of `main` and review `PROJECT_STATE.md`.
- Keep `PROJECT_STATE.md` focused on the current handoff state. Update it after relevant completed work, not after every prompt.

## Roles

- ChatGPT owns architecture, prioritization, decisions, and the final GO/NO-GO assessment.
- Codex is the default primary implementer and owns implementation, tests, and GitHub work.
- Claude Code provides an independent review for larger or riskier changes.
- Exception: when Claude Code operates as the lead orchestrator for a task (see "Claude-Led Duo Loop" below), the roles reverse for that task — Claude Code implements and Codex serves as the independent reviewer.
- GitHub holds the shared code, branches, pull requests, review findings, and current project state.

## Change Workflow

Small, low-risk changes may be committed directly to `main`.

Larger or riskier changes must use this workflow (shown here for the default Codex-led case; see "Claude-Led Duo Loop" below for the mirrored Claude-led case, which follows the same branch → implement → test → review → fix → PR → GO/NO-GO shape with roles reversed):

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
- Whichever agent leads a task (Codex or Claude Code) executes required Git and shell commands itself. The user must not need to run manual Git or PowerShell commands.
- Prefer the direct GitHub Connector for GitHub operations.
- Prefer direct connectors and APIs; use local PowerShell or CLI workarounds only when necessary.

## Codex-Led Duo Loop (Codex as Orchestrator)

Applies when Codex (typically driven from a ChatGPT/Codex session) is the lead implementer for larger, riskier, or architecture-relevant changes: Codex implements and runs tests and linters; Claude Code orchestrates independent Claude-Critic reviews; Claude Code then performs Git plumbing (add, commit, and push) on the implementation branch.

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

## Claude-Led Duo Loop (Claude Code as Orchestrator)

Applies when Claude Code (this CLI/desktop session) is the lead implementer for a substantial coding task in this repository — the mirror image of the Codex-Led Duo Loop above. This loop governs the implement-test-review-fix cycle; the branching, pull-request, and GO/NO-GO rules in "Change Workflow" above still apply on top of it for larger or riskier changes.

- Claude Code is the orchestrator and implementer: it understands and implements the task, runs the relevant tests and linters itself, fixes obvious issues, and then commits and pushes the change itself.
- Codex acts purely as an independent reviewer, invoked directly from Claude Code's own shell with `codex exec --sandbox read-only "<instruction>"`. This direct call is verified working; do not build a new API bridge, WSL setup, MCP server, or wrapper script for it. Pass the task context, constraints, and diff via stdin (`codex exec` appends piped stdin as a `<stdin>` block) rather than embedding a large diff directly in the quoted argument, to avoid shell-quoting and length issues.
- Codex reviews always run with `--sandbox read-only`: Codex must not modify any files or trigger external side effects (e.g. GitHub/API mutations). Do not include secrets or sensitive untracked content in the context passed to Codex.
- Give Codex the concrete task context, relevant constraints, and the actual `git diff` for the change, and have it check correctness, edge cases, regressions, security, and design issues.
- Claude Code critically evaluates every finding itself: fix valid findings; reject invalid or out-of-scope findings with a short stated reason instead of applying them blindly.
- After a substantive fix, rerun the relevant tests. Request another Codex review only when the round produced substantial changes.
- Cap the loop at a maximum of three Codex review rounds; stop earlier once Codex reports no further substantive findings.
- Small, obviously trivial changes do not need a Codex review.
- If `codex` is unreachable or fails, do not block delivery: report the problem transparently and continue with Claude Code's own review and testing instead.
- The user must not need to act as a go-between for Claude Code and Codex; Claude Code drives the whole loop itself.
- For changes that go through a pull request, add or update a compact `Codex Review` section in the PR description mirroring the existing `Claude Review` pattern: note the number of review rounds, Codex's substantive findings, what was accepted and changed, any substantive findings rejected with a short reason, and the final result (`no substantive open findings` or `open findings`).
- At the end of a task, report concisely: what was implemented, which tests ran, Codex's relevant findings, what was adopted, what was deliberately rejected (with reason), and the commit/push/PR status.

## Safety and Production

- Do not delete production data or history until integrity, backup, and restore have been verified.
- Do not change existing production functionality without explicit authorization.
- Preserve unrelated user changes and keep each change scoped to the task.
