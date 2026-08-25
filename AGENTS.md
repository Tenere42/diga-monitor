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
→ Pull Request
→ Claude Code independent review
→ Codex fixes findings
→ tests
→ ChatGPT GO/NO-GO
→ merge to main
```

- Do not implement larger or riskier changes directly on `main`; use a dedicated branch and pull request.
- Run all relevant tests before merging.
- Codex executes required Git and shell commands itself. The user must not need to run manual Git or PowerShell commands.
- Prefer the direct GitHub Connector for GitHub operations.
- Prefer direct connectors and APIs; use local PowerShell or CLI workarounds only when necessary.

## Safety and Production

- Do not delete production data or history until integrity, backup, and restore have been verified.
- Do not change existing production functionality without explicit authorization.
- Preserve unrelated user changes and keep each change scoped to the task.
