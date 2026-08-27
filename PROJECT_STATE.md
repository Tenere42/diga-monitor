# PROJECT_STATE.md

## Current objective

Remove the verified legacy snapshot archive from the current Git tree through a dedicated cleanup pull request, without rewriting Git history.

## Production status

DiGA Monitor is in production. The scheduler runs at 06:00, 09:00, 12:00, 15:00, and 18:00 in `Europe/Zurich`.

## Current architecture

- Scheduled DiGA monitoring runs produce monitoring data and historical artifacts.
- R2 is configured for new archives and checkpoints.
- All 369 historical events now carry embedded `snapshot_context`; the dashboard no longer performs a runtime lookup in `data/snapshots/`.
- A reproducible audit classified all 842 legacy snapshots into 35 unique monitored states and 807 redundant snapshots. The resulting retention plan contains 57 deduplicated legacy/event/checkpoint/boundary/baseline objects, all verified in R2.
- The cleanup branch removes all 842 legacy JSON snapshots from the current tree while retaining `data/snapshots/.gitkeep`; no R2 object or historical Git object is changed.
- GitHub is the shared source of truth for code and project handoff state.

## Last completed work

Merged PR #3 after verifying all retention, dashboard, restore, and runtime-independence requirements. Prepared a tree-only cleanup that removes the 842 legacy snapshot files while preserving the baseline, change events, R2 manifest, retention reports, and `.gitkeep`.

## Current branch / PR

- Branch: `codex/remove-legacy-snapshots`
- Pull request: pending
- Base: `main` at merge commit `e9471732eb1aebb42c1068d61402ce5157bf906d`
- Cleanup is not merged; no history rewrite has occurred

## Tests

- GitHub Actions run 33072662784: 48 tests passed and the hardened migration job completed successfully.
- Retention proof: 842/842 snapshots classified; 35 unique monitored states; 807 redundant snapshots; every unique state has a retained representative.
- R2: 57/57 retention objects verified by stored and calculated SHA-256, decompression, JSON parse, `created_at`, and source comparison.
- Restore integration: the R2 baseline object was restored to an isolated `data/baseline/current_snapshot.json` and loaded through the production loader with 79 entries.
- Cleanup verification: full tests plus explicit dashboard, scan/baseline, simulation/CLI, manifest, and restore checks are required before merge.

## Open risks/blockers

- Removing files from the current tree will not reduce historical Git object storage without a separate, explicitly approved history rewrite.
- The cleanup reduces fresh/current-tree checkouts by 29,555,828,327 bytes (27.526 GiB), but existing clones retain historical objects until normal Git maintenance or a separately approved history rewrite.

## Next recommended step

Review and merge the dedicated cleanup PR after its test suite succeeds. Do not perform a Git-history rewrite as part of this cleanup.

## Last updated

2026-08-27
