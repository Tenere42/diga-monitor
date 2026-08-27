# PROJECT_STATE.md

## Current objective

Maintain the production DiGA Monitor with GitHub as source of truth and use the Codex-Claude CLI Duo Loop for independent read-only review of larger, risky, or architecture-relevant changes.

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

## Last completed work

Merged the verified tree-only legacy snapshot cleanup and established the local Codex-Claude Duo Loop for future substantial changes. The loop does not require the Claude GitHub Action or GitHub OIDC/WIF.

## Current branch / PR

- Branch: `main`
- Legacy cleanup merge: `e5c96da083a818cc9009d1b6dab6acb3d83b665e`
- No Git-history rewrite has occurred.

## Tests

- GitHub Actions run 33072662784: 48 tests passed and the hardened migration job completed successfully.
- Retention proof: 842/842 snapshots classified; 35 unique monitored states; 807 redundant snapshots; every unique state has a retained representative.
- R2: 57/57 retention objects verified by stored and calculated SHA-256, decompression, JSON parse, `created_at`, and source comparison.
- Restore integration: the R2 baseline object was restored to an isolated `data/baseline/current_snapshot.json` and loaded through the production loader with 79 entries.
- Cleanup verification passed before merge, including dashboard, scan/baseline, simulation/CLI, manifest, and restore checks.
- Claude CLI 2.1.223 is authenticated; non-interactive `claude -p`, restricted read-only tools, workspace reads, and Codex output capture have been verified.

## Open risks/blockers

- Historical Git objects remain available because no history rewrite was performed.
- Claude CLI currently uses its verified absolute Windows path because its directory is not in `PATH`.

## Next recommended step

Use the documented Duo Loop on the next larger or riskier change; continue handling small, obviously low-risk changes without mandatory Claude review.

## Last updated

2026-08-27
