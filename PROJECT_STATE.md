# PROJECT_STATE.md

## Current objective

Reduce Streamlit rerun latency without changing historical events, dashboard semantics, scanner behavior, or the Baseline/R2 architecture.

## Production status

DiGA Monitor is in production. The scheduler runs at 06:00, 09:00, 12:00, 15:00, and 18:00 in `Europe/Zurich`.

## Current architecture

- Scheduled DiGA monitoring runs produce monitoring data and historical artifacts.
- R2 is configured for new archives and checkpoints.
- All 369 historical events now carry embedded `snapshot_context`; the dashboard no longer performs a runtime lookup in `data/snapshots/`.
- A reproducible audit classified all 842 legacy snapshots into 35 unique monitored states and 807 redundant snapshots. The resulting retention plan contains 57 deduplicated legacy/event/checkpoint/boundary/baseline objects, all verified in R2.
- All 842 legacy JSON snapshots have been removed from the current tree while retaining `data/snapshots/.gitkeep`; no R2 object or historical Git object was changed.
- GitHub is the shared source of truth for code and project handoff state.
- Codex is the primary implementer and orchestrator. For substantial changes it invokes the authenticated local Claude Code CLI as a read-only reviewer with restricted tools and at most three review rounds.
- Dashboard inputs use content-addressed Streamlit caching: file-content signatures invalidate cached change events and scan history automatically on deployment changes.
- Notification recipients are resolved independently from message creation and Brevo Transactional Email API transport. Production uses the GitHub repository variable `DIGA_MONITOR_EMAIL_TO`; no recipient address is hardcoded in Python.

## Last completed work

Profiled and optimized the dashboard data path. Prepared the notification layer for externally configured single or multiple recipients while intentionally leaving newsletter subscriptions, signup, storage, and opt-in out of scope.

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
- Claude CLI 2.1.223 is authenticated; non-interactive `claude -p`, restricted read-only tools, workspace reads, and Codex output capture have been verified.
- Dashboard benchmark fixture: 31 change files (17,763,374 bytes), 369 events, 252 real events, 21 groups, and 162 rendered adjustments. The measured end-to-end warm rerun path improved from about 452 ms uncached to about 99 ms cached in the local benchmark harness.
- GitHub Actions run 33094466784: all 54 tests passed for the dashboard performance change.

## Open risks/blockers

- Historical Git objects remain available because no history rewrite was performed.
- Claude CLI currently uses its verified absolute Windows path because its directory is not in `PATH`.

## Next recommended step

Review and merge the notification-recipient configuration PR after tests and the read-only Claude review pass.

## Last updated

2026-08-27
