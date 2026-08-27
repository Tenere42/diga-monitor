# PROJECT_STATE.md

## Current objective

Complete verification of the expanded legacy-history retention set in PR #3, then decide whether `data/snapshots/*.json` may be removed from the current tree without rewriting Git history.

## Production status

DiGA Monitor is in production. The scheduler runs at 06:00, 09:00, 12:00, 15:00, and 18:00 in `Europe/Zurich`.

## Current architecture

- Scheduled DiGA monitoring runs produce monitoring data and historical artifacts.
- R2 is configured for new archives and checkpoints.
- All 369 historical events now carry embedded `snapshot_context`; the dashboard no longer performs a runtime lookup in `data/snapshots/`.
- A reproducible audit classified all 842 legacy snapshots into 35 unique monitored states and 807 redundant snapshots. The resulting retention plan contains 57 deduplicated legacy/event/checkpoint/boundary/baseline objects, all verified in R2.
- Legacy snapshots remain in `data/snapshots/`; this work did not delete or rewrite them.
- GitHub is the shared source of truth for code and project handoff state.

## Last completed work

Resolved the review findings: all 842 snapshots are covered by a committed monitored-state report, simulations and CLI runtime no longer depend on `data/snapshots/`, the full 369-event dashboard comparison is a committed golden-projection test, restore loaded an isolated operational baseline through the production snapshot loader, and the migration workflow no longer has write permission or direct-push capability.

## Current branch / PR

- Branch: `codex/legacy-history-cleanup-prep`
- Pull request: #3
- Latest audit decision: pending final GO/NO-GO review; no deletion has occurred

## Tests

- GitHub Actions run 33072662784: 48 tests passed and the hardened migration job completed successfully.
- Retention proof: 842/842 snapshots classified; 35 unique monitored states; 807 redundant snapshots; every unique state has a retained representative.
- R2: 57/57 retention objects verified by stored and calculated SHA-256, decompression, JSON parse, `created_at`, and source comparison.
- Restore integration: the R2 baseline object was restored to an isolated `data/baseline/current_snapshot.json` and loaded through the production loader with 79 entries.

## Open risks/blockers

- All 842 full snapshots / 27.526 GiB still remain in the Git tree; this PR intentionally does not delete them.
- Removing files from the current tree will not reduce historical Git object storage without a separate, explicitly approved history rewrite.
- Final cleanup still requires review and GO/NO-GO approval of PR #3 and its 57-object manifest.

## Next recommended step

Review the final 57-object manifest and issue the GO/NO-GO decision for merging PR #3 and a separate cleanup PR.

## Last updated

2026-08-27
