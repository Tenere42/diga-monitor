# PROJECT_STATE.md

## Current objective

No active implementation task is in flight. PR #5 (production Brevo sender
and API-key-authenticated Claude review) has been merged. Awaiting the next
ChatGPT decision/spec before starting new implementation work.

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

## Last completed work

Merged PR #5 (`codex/notification-recipient-config` → `main`, commit
`5c95bde68c54f01583ffb4fac62c0d8d2e06886f`): production Brevo sender
configuration and API-key-authenticated Claude review. 77/77 tests passed
before merge; the final Claude review rerun authenticated successfully and
produced no new findings, but failed exclusively with "Credit balance is too
low" and was consciously overridden for the merge.

## Current branch / PR

- Branch: `main` (no active implementation branch or open work-in-progress PR).
- Local `main` was 468 commits behind `origin/main` at the start of this session; it has been fast-forwarded and now matches `origin/main` exactly.
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

## Open risks/blockers

- Historical Git objects remain available because no history rewrite was performed.
- `ANTHROPIC_API_KEY` remains intentionally unavailable to the local Codex process; GitHub Actions now supplies it exclusively from the repository secret.
- No Python interpreter is installed in this session's local environment; local test/lint execution is not currently possible here.
- Several remote branches are fully merged into `main` and unused; deletion has not been requested or performed.

## Next recommended step

No implementation work is pending. Await the next ChatGPT decision/spec, or a
decision on closing PR #2 and pruning the fully-merged stale branches.

## Last updated

2026-08-29
