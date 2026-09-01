# PROJECT_STATE.md

## Current objective

No active implementation task is in flight. The DiGA Tracker rebrand, the
Railway migration of the public dashboard, and the production URL switch to
`https://www.diga-tracker.de` are complete in code/docs. One manual step
remains: setting the `DIGA_MONITOR_DASHBOARD_URL` GitHub repository variable
(see "Next recommended step"). Awaiting the next ChatGPT decision/spec
before starting new implementation work.

## Production status

DiGA Monitor is in production. The scheduler runs at 06:00, 09:00, 12:00, 15:00, and 18:00 in `Europe/Zurich`.

## Current architecture

- Scheduled DiGA monitoring runs produce monitoring data and historical artifacts.
- R2 is configured for new archives and checkpoints.
- All 369 historical events now carry embedded `snapshot_context`; the dashboard no longer performs a runtime lookup in `data/snapshots/`.
- A reproducible audit classified all 842 legacy snapshots into 35 unique monitored states and 807 redundant snapshots. The resulting retention plan contains 57 deduplicated legacy/event/checkpoint/boundary/baseline objects, all verified in R2.
- All 842 legacy JSON snapshots have been removed from the current tree while retaining `data/snapshots/.gitkeep`; no R2 object or historical Git object was changed.
- GitHub is the shared source of truth for code and project handoff state.
- The automatic GitHub Actions Claude PR review has been removed. Substantial changes use the local Gauntlet workflow: Codex implements, Claude Code orchestrates independent Claude-Critic reviews, and Claude Code performs Git plumbing. `scripts.claude_review` remains available as a manually invoked local review tool with API-key authentication, a redacted connectivity preflight, isolated Claude configuration, and read-only tools.
- Dashboard inputs use content-addressed Streamlit caching: file-content signatures invalidate cached change events and scan history automatically on deployment changes.
- Notification sender and recipients are resolved independently from message creation and Brevo Transactional Email API transport. Production uses `DIGA_MONITOR_EMAIL_FROM`, `DIGA_MONITOR_EMAIL_FROM_NAME`, and `DIGA_MONITOR_EMAIL_TO`; no email address is hardcoded in Python.
- Public notification identity is unified on **DiGA Tracker** (email subject, greeting, signature, and the `notify-test` simulation; the `TEST / SIMULATION` marker itself is unchanged).
- The dashboard link in notification emails is resolved by `resolve_dashboard_url()` in `src/notifications.py`: it prefers `DIGA_MONITOR_DASHBOARD_URL` (naming-consistent with the other `DIGA_MONITOR_EMAIL_*` variables) and falls back to the legacy `DASHBOARD_URL` variable for as long as that stays set — code-verified precedence, unchanged this session. No dashboard URL is hardcoded in source.
- **Railway is now the production dashboard hosting.** The public dashboard (`app.py`, Streamlit) is deployed on Railway from this repository's `main` branch (Railpack build; repo-based `railway.json` sets `deploy.startCommand`, `.python-version` pins the Python runtime — see commit `1370a7f`). **Streamlit Community Cloud is no longer the production host.**
- **Production public URL: `https://www.diga-tracker.de`.** The domain is verified and reachable; `diga-tracker.de` (bare/apex) redirects to `https://www.diga-tracker.de`. DNS itself is managed outside this repository (GoDaddy + Railway custom domain) and was not touched here.
- The `DIGA_MONITOR_DASHBOARD_URL` GitHub repository variable should be set to `https://www.diga-tracker.de` so production notification emails link to the new domain; as of this update it has not yet been set (Claude Code/Codex has no GitHub write credentials in this environment — see "Next recommended step"), so email links still resolve to whatever the legacy `DASHBOARD_URL` variable currently holds.

## Last completed work

Documented the production URL switch to `https://www.diga-tracker.de`
(Railway-hosted dashboard, verified and reachable; `diga-tracker.de`
redirects to the `www` host; Streamlit Community Cloud is no longer
production). Code precedence for `DIGA_MONITOR_DASHBOARD_URL` over the
legacy `DASHBOARD_URL` was re-verified and needed no change. Setting the
`DIGA_MONITOR_DASHBOARD_URL` GitHub repository variable itself remains a
manual step (see "Next recommended step") — no GitHub write credentials
are available in this environment. No R2, baseline, history, or
change-detection logic was touched; no test email was sent; no DNS change
was made.

Before that: prepared the repository for the Railway migration (commit
`1370a7f` on `main`, committed directly per the small/low-risk rule since
it only added deploy config/docs/tests and changed no monitoring, R2, or
email logic): added `railway.json` (`deploy.startCommand`:
`streamlit run app.py --server.address=0.0.0.0 --server.port=$PORT
--server.headless=true`) so Railway needs no manually maintained Start
Command, added `.python-version` (`3.11`) for a deterministic Railpack
build, added `tests/test_railway_config.py`, and documented the setup in
README.md. `requirements.txt` was already complete for `app.py` (its only
third-party import is `streamlit`).

Before that: merged branch `codex/rebrand-diga-tracker` → `main` (merge commit on top of
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
- Neither Claude Code nor Codex in this environment has GitHub API/UI write credentials (no `gh` CLI, no `GITHUB_TOKEN`, no authenticated browser session, no connected "Claude in Chrome"); setting repository variables, triggering `workflow_dispatch` runs, and opening/merging pull requests currently requires the user to act in the GitHub UI. Direct `git push`/local merge remains available and was used to land code/doc changes.
- `DIGA_MONITOR_DASHBOARD_URL` is not yet set as a GitHub Actions repository variable even though the production domain is now live; production notification emails still link to whatever the legacy `DASHBOARD_URL` variable currently holds until someone sets it (see "Next recommended step"). This is a configuration gap only — code precedence is already correct.

## Next recommended step

No code implementation work is pending. One manual GitHub step remains:

1. In the `Tenere42/diga-monitor` repository, go to
   `Settings > Secrets and variables > Actions > Variables` and set (or
   update) the repository variable `DIGA_MONITOR_DASHBOARD_URL` to
   `https://www.diga-tracker.de`. This is the only step needed to switch
   production notification emails to the new domain; everything else
   (Railway hosting, DNS, redirect, code precedence) is already in place.
2. Otherwise, await the next ChatGPT decision/spec, or a decision on closing
   PR #2 and pruning the fully-merged stale branches (including
   `codex/rebrand-diga-tracker`, already merged).

## Last updated

2026-08-29 (production URL switch to https://www.diga-tracker.de on Railway)
