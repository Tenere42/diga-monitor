# PROJECT_STATE.md

## Current objective

Review the verified legacy-history migration in PR #3, then decide whether `data/snapshots/*.json` may be removed from the current tree without rewriting Git history.

## Production status

DiGA Monitor is in production. The scheduler runs at 06:00, 09:00, 12:00, 15:00, and 18:00 in `Europe/Zurich`.

## Current architecture

- Scheduled DiGA monitoring runs produce monitoring data and historical artifacts.
- R2 is configured for new archives and checkpoints.
- All 369 historical events now carry embedded `snapshot_context`; the dashboard no longer performs a runtime lookup in `data/snapshots/`.
- A durable R2 audit manifest covers 44 deduplicated legacy/event/checkpoint/boundary/baseline objects.
- Legacy snapshots remain in `data/snapshots/`; this work did not delete or rewrite them.
- GitHub is the shared source of truth for code and project handoff state.

## Last completed work

Backfilled 367 historical event contexts without changing before/after values, verified identical historical dashboard grouping/output without the legacy directory, migrated and byte-verified 44 required objects in R2, and completed an isolated historical restore. The manifest records 44/44 successful SHA-256, decompression, JSON, `created_at`, and legacy-source comparisons.

## Current branch / PR

- Branch: `codex/legacy-history-cleanup-prep`
- Pull request: #3
- Latest audit decision: pending final GO/NO-GO review; no deletion has occurred

## Tests

- GitHub Actions: 46 tests passed.
- Historical dashboard comparison: 369 events, 22 groups before/after, identical after excluding storage-only embedded context.
- R2: 44/44 objects verified twice; 171,323,927 compressed bytes and 1,440,899,885 uncompressed bytes represented in the manifest.
- Restore: historical object downloaded, decompressed, SHA-256 checked, JSON parsed, and restored in an isolated temporary directory.

## Open risks/blockers

- All 842 full snapshots / 27.526 GiB still remain in the Git tree; this PR intentionally does not delete them.
- Only the 44-object minimal retention set is migrated and verified in R2; the other Legacy snapshots are classified as redundant full-scan archives, not individually copied.
- Removing files from the current tree will not reduce historical Git object storage without a separate, explicitly approved history rewrite.
- Final cleanup still requires review and GO/NO-GO approval of PR #3 and its manifest.

## Next recommended step

Review PR #3 and the persisted manifest, then issue the final GO/NO-GO decision for a separate cleanup PR that removes only `data/snapshots/*.json` from the current tree.

## Last updated

2026-08-27
