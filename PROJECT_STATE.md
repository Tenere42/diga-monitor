# PROJECT_STATE.md

## Current objective

Use API-key-only authentication for automated Claude Code reviews without relying on personal OAuth state.

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

Replaced personal OAuth and GitHub federation dependencies in automated Claude reviews with the repository secret/environment variable `ANTHROPIC_API_KEY`, a fail-closed API connectivity check, and an isolated read-only local review wrapper.

## Current branch / PR

- Branch: `codex/notification-recipient-config`
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

## Open risks/blockers

- Historical Git objects remain available because no history rewrite was performed.
- The `ANTHROPIC_API_KEY` environment variable is not currently available in the local Codex process. A live local connectivity check and PR #5 review must remain skipped until the GitHub repository secret exists.

## Next recommended step

Add the GitHub repository Actions secret `ANTHROPIC_API_KEY`, then rerun the Claude PR Review workflow for PR #5.

## Last updated

2026-08-29
