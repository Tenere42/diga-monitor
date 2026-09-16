# PROJECT_STATE.md

## Current objective

Phase B (mobile-first public homepage) is implemented locally on
`codex/ui-redesign-black-white`, starting exactly from the approved Phase A commit
`40888b3f675a9977156cadb5c1e3e8dff9365110`. It is not merged or deployed.
No protected monitoring/storage/subscriber/configuration/data files changed.

### Phase B validation / handoff — 2026-09-16

- Default route: compact desktop links/native mobile menu, requested hero copy
  and anchor CTAs, four KPIs, five newest existing DiGA/date groups, explanation,
  one existing signup form, and existing privacy footer. No JavaScript/framework,
  new search/filter chips, duplicate signup widgets or invented legal content.
- `?view=changes` contains the original full filter/group/detail experience.
  Privacy and confirmation routes preserve their readiness gate and behavior.
- KPI source: tracked `data/baseline/current_snapshot.json`, persisted by the
  existing monitor workflow. `directory_metrics.active_count` excludes removed
  and unknown entries and equals permanent + provisional; the other market
  cards use `status_counts.permanent` and `status_counts.provisional`.
  The read-only adapter validates all aggregates against existing
  `calculate_directory_metrics` semantics; missing/inconsistent input is
  unavailable, not zero. Cached summary is keyed by snapshot content signature.
- Inspected snapshot: 2026-09-15 19:24 UTC (21:24 Berlin), 80 total entries,
  62 active = 50 permanent + 12 provisional, 18 removed, 0 unknown. UI shows the
  snapshot's date explicitly and makes no live-data claim.
- Fourth KPI: deduplicated displayed adjustments in 30 Berlin calendar days,
  today included. For 2026-09-16: Aug 18–Sep 16, 15 adjustments. Counts are
  calculated from the unchanged full-dashboard grouping; no market status is
  inferred from change history. The homepage uses the full dashboard's default
  date eligibility (dated records on/after tracking start).
- Before/after comparison: 380 stored events, 263 eligible events, 25 groups,
  173 displayed adjustments; ordering/grouping, four date filters and every price
  analysis match Phase A. Existing business helpers/cache/legal functions are
  unchanged. Newsletter changes are limited to its heading and scroll anchor.
- Full suite: 186 tests, 184 pass, the same two pre-existing failures expecting
  369 historical events instead of 380. No protected fixtures were edited.
  New tests cover market semantics/inconsistency/unavailability/cache refresh,
  recent order/limit/date boundaries/escaping, routes, one form and mocked signup.
  No real Brevo request or signup occurred.
- Codex self-review (Claude unavailable): corrected a preview edge case that
  could include undated/pre-tracking records; added a default-filter equivalence
  test. Removed empty manufacturer markup. No business-logic or protected-file
  changes, duplicated forms, color-only cues, new generated selectors or scope
  expansion found. Mobile styling uses owned classes and the Phase A tokens.
- Browser access was denied earlier; actual rendering and menu/anchor/focus/
  overflow behavior remain unverified at 320/375/390/430/768/1440px. AppTest only
  verifies server/widget behavior. Visual review is required before deployment.
- Sandbox network remains disabled; no further connectivity debugging or push
  attempted. Publish the local commit externally when ready. Main untouched.

### Phase A validation / handoff — 2026-09-16

- Central CSS tokens, a presentation-only `src/ui.py`, and a light monochrome
  Streamlit theme replace scattered colored/OS-dark-mode presentation rules.
- Newsletter functions, business helpers, cache inputs, routes and render order
  were compared against the starting commit; behavioral code is unchanged.
  Full current-data comparison: 380 raw events, 263 eligible events, 25 groups,
  173 displayed adjustments; ordering/grouping and four date-filter cases match.
- The starting main suite has two pre-existing failures: historical tests expect
  369 events, but current data contains 380. Protected fixtures and existing
  tests were not changed to conceal this mismatch.
- Nine new presentation/Streamlit AppTest checks pass, including mocked signup,
  consent, reruns/result persistence and existing legal routes. No real Brevo
  request or signup was performed. Full suite: 169 tests, 167 pass, the same
  two baseline historical-count failures, no new failures.
- Claude was unavailable per task instruction. Codex self-review checked the
  protected-file boundary, unchanged business/newsletter logic, CSS hooks,
  non-color semantics, branding and Phase A scope. An obsolete native CSS hook
  and an overly broad text-color rule were removed during review.
- Browser access to the local preview was denied. Actual mobile/desktop
  rendering, overflow, keyboard focus and touch targets still need visual
  review at 320/375/390/430/768/1440px before Phase B. AppTest is not a visual test.
- The older production/configuration notes below are historical context, not a
  fresh verification of Railway settings or repository variables.

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

- Active implementation branch: `codex/ui-redesign-black-white` (Phase A + B;
  not merged or deployed).
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

Review the Phase B homepage visually before planning Phase C. Resolve the two
pre-existing historical-test count expectations in a separate, authorized
data/test-maintenance task; this presentation change deliberately leaves them
untouched. Do not merge or deploy this branch without a subsequent decision.

The following production URL configuration follow-up is retained from the
earlier handoff and was not re-verified during Phase A:

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

2026-09-16 (Phase B homepage; production unchanged)
