# PROJECT_STATE.md

## Current objective

No active implementation task is in flight. The DiGA Tracker rebrand and
configurable dashboard URL have been merged. Awaiting the next ChatGPT
decision/spec before starting new implementation work. The public domain
`https://diga-tracker.de` is not yet live; see "Next recommended step".

## Production status

DiGA Monitor is in production. The scheduler runs at 06:00, 09:00, 12:00, 15:00, and 18:00 in `Europe/Zurich`.

## Current architecture

- Scheduled DiGA monitoring runs produce monitoring data and historical artifacts.
- R2 is configured for new archives and checkpoints.
- All 369 historical events now carry embedded `snapshot_context`; the dashboard no longer performs a runtime lookup in `data/snapshots/`.
- A reproducible audit classified all 842 legacy snapshots into 35 unique monitored states and 807 redundant snapshots. The resulting retention plan contains 57 deduplicated legacy/event/checkpoint/boundary/baseline objects, all verified in R2.
- All 842 legacy JSON snapshots have been removed from the current tree while retaining `data/snapshots/.gitkeep`; no R2 object or historical Git object was changed.
- GitHub is the shared source of truth for code and project handoff state.
- Codex is the primary implementer and orchestrator. For substantial changes it invokes Claude Code through `scripts.claude_review`, which requires `ANTHROPIC_API_KEY`, passes a redacted connectivity preflight, isolates Claude from personal OAuth state, and grants read-only tools for at most three review rounds.
- Dashboard inputs use content-addressed Streamlit caching: file-content signatures invalidate cached change events and scan history automatically on deployment changes.
- Notification sender and recipients are resolved independently from message creation and Brevo Transactional Email API transport. Production uses `DIGA_MONITOR_EMAIL_FROM`, `DIGA_MONITOR_EMAIL_FROM_NAME`, and `DIGA_MONITOR_EMAIL_TO`; no email address is hardcoded in Python.
- Public notification identity is unified on **DiGA Tracker** (email subject, greeting, signature, and the `notify-test` simulation; the `TEST / SIMULATION` marker itself is unchanged).
- The dashboard link in notification emails is resolved by `resolve_dashboard_url()` in `src/notifications.py`: it prefers `DIGA_MONITOR_DASHBOARD_URL` (production target `https://diga-tracker.de`, naming-consistent with the other `DIGA_MONITOR_EMAIL_*` variables) and falls back to the legacy `DASHBOARD_URL` variable (e.g. the current Streamlit hosting URL) for as long as that stays set. No dashboard URL is hardcoded in source.

## Last completed work

Merged branch `codex/rebrand-diga-tracker` → `main` (merge commit on top of
`9aafc42`): unified the public notification identity on "DiGA Tracker" and
made the public dashboard URL configuration-driven via the new
`DIGA_MONITOR_DASHBOARD_URL` variable (legacy `DASHBOARD_URL` kept as a
documented technical fallback). Scope confined to branding strings, the
dashboard-URL resolver, `.env.example`, the DiGA Monitor workflow, README,
and tests; no R2, baseline, history, or change-detection logic was touched.

**Claude Review — deliberately overridden:** the Claude PR Review run for
this branch authenticated successfully via the API-key preflight and failed
exclusively with "Credit balance is too low," producing no substantive
findings to accept or reject. GitHub Actions unit tests for the branch
(`R2 Connectivity Check`, `mode=tests`) passed per the user's direct report.
The user explicitly decided to override the review-gate for this PR given
(a) the auth preflight worked, (b) the only failure was insufficient
Anthropic API credit, (c) tests were green, and (d) the change was scoped to
branding/dashboard-URL configuration only. Codex/Claude performed an
explicit self-review of the final diff instead (branding-string sweep,
dashboard-URL fallback order, workflow/env-var wiring, test coverage) and
found no issues before merging.

Previously: merged PR #5 (`codex/notification-recipient-config` → `main`,
commit `5c95bde68c54f01583ffb4fac62c0d8d2e06886f`): production Brevo sender
configuration and API-key-authenticated Claude review. 77/77 tests passed
before merge; the final Claude review rerun authenticated successfully and
produced no new findings, but failed exclusively with "Credit balance is too
low" and was consciously overridden for the merge.

## Current branch / PR

- Branch: `main` (no active implementation branch or open work-in-progress PR).
- `codex/rebrand-diga-tracker` is merged into `main` and is a candidate for deletion, pending confirmation.
- Branches `codex/legacy-history-cleanup-prep`, `codex/notification-recipient-config`, `codex/remove-legacy-snapshots`, and `infra/claude-github-review` are fully merged (0 commits ahead of `main`) and are candidates for deletion, pending confirmation.
- Open PR #2 ("Test Claude PR review end to end", branch `test/claude-review-e2e`) is explicitly marked "Do not merge" in its description — a harmless one-sentence `PROJECT_STATE.md` change used only to validate the Claude PR review workflow, GitHub OIDC, and Anthropic Workload Identity Federation end to end. It remains open and untouched.
- Legacy cleanup merge: `e5c96da083a818cc9009d1b6dab6acb3d83b665e`
- No Git-history rewrite has occurred.

## Tests

- GitHub Actions run 33072662784: 48 tests passed and the hardened migration job completed successfully.
- Retention proof: 842/842 snapshots classified; 35 unique monitored states; 807 redundant snapshots; every unique state has a retained representative.
- R2: 57/57 retention objects verified by stored and calculated SHA-256, decompression, JSON parse, `created_at`, and source comparison.
- Restore integration: the R2 baseline object was restored to an isolated `data/baseline/current_snapshot.json` and loaded through the production loader with 79 entries.
- Cleanup verification passed before merge, including dashboard, scan/baseline, simulation/CLI, manifest, and restore checks.
- Claude CLI 2.1.223 is installed. Automated authentication no longer uses its stored personal OAuth account; it requires `ANTHROPIC_API_KEY` and an isolated temporary config directory.
- Dashboard benchmark fixture: 31 change files (17,763,374 bytes), 369 events, 252 real events, 21 groups, and 162 rendered adjustments. The measured end-to-end warm rerun path improved from about 452 ms uncached to about 99 ms cached in the local benchmark harness.
- GitHub Actions run 33094466784: all 54 tests passed for the dashboard performance change.
- GitHub Actions run 33252731862: all 74 tests passed for the API-key-only Claude review integration.
- No Python interpreter is available in this session's local environment, so `tests/` could not be re-run locally this session; test status above reflects the last GitHub Actions runs prior to the PR #5 merge. Rely on GitHub Actions for the authoritative result on the next change.
- `R2 Connectivity Check` (`mode=tests`, i.e. `python -m unittest discover -s tests`) on `codex/rebrand-diga-tracker` passed per the user's direct report before the rebrand merge; the exact run was not independently re-verified via the GitHub API in this session due to the unauthenticated rate limit (see below).

## Open risks/blockers

- Historical Git objects remain available because no history rewrite was performed.
- `ANTHROPIC_API_KEY` remains intentionally unavailable to the local Codex process; GitHub Actions now supplies it exclusively from the repository secret.
- No Python interpreter is installed in this session's local environment; local test/lint execution is not currently possible here.
- Several remote branches are fully merged into `main` and unused; deletion has not been requested or performed.
- Neither Claude Code nor Codex in this environment has GitHub API/UI write credentials (no `gh` CLI, no `GITHUB_TOKEN`, no authenticated browser session); triggering `workflow_dispatch` runs and opening/merging pull requests currently requires the user to click the corresponding GitHub UI buttons. Direct `git push`/local merge remains available and was used to land this change.
- `DIGA_MONITOR_DASHBOARD_URL` is not yet set as a GitHub Actions repository variable, so the dashboard link in production email still falls back to the legacy `DASHBOARD_URL` value until someone sets it (see "Next recommended step").
- The domain `https://diga-tracker.de` is not yet configured at the registrar (GoDaddy) or pointed at Streamlit; no DNS or Streamlit custom-domain change has been made.

## Next recommended step

No code implementation work is pending. Remaining steps are manual/external:

1. In GitHub, set the repository variable `DIGA_MONITOR_DASHBOARD_URL` to
   `https://diga-tracker.de` under `Settings > Secrets and variables >
   Actions > Variables` (once the domain is live; until then the legacy
   `DASHBOARD_URL` fallback keeps working).
2. At the registrar (GoDaddy), point `diga-tracker.de` at the Streamlit
   deployment (custom domain / CNAME per Streamlit's instructions), then
   configure the custom domain in Streamlit Community Cloud. Not done yet;
   explicitly out of scope for this change per the user's instruction.
3. Otherwise, await the next ChatGPT decision/spec, or a decision on closing
   PR #2 and pruning the fully-merged stale branches.

## Last updated

2026-08-29 (DiGA Tracker rebrand merge)
