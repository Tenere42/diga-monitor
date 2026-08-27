# PROJECT_STATE.md

## Current objective

Complete verification of the expanded legacy-history retention set in PR #3, then decide whether `data/snapshots/*.json` may be removed from the current tree without rewriting Git history.

## Production status

DiGA Monitor is in production. The scheduler runs at 06:00, 09:00, 12:00, 15:00, and 18:00 in `Europe/Zurich`.

## Current architecture

- Scheduled DiGA monitoring runs produce monitoring data and historical artifacts.
- R2 is configured for new archives and checkpoints.
- All 369 historical events now carry embedded `snapshot_context`; the dashboard no longer performs a runtime lookup in `data/snapshots/`.
- A reproducible audit classified all 842 legacy snapshots into 36 unique monitored states and 806 redundant snapshots. The resulting retention plan contains 58 deduplicated legacy/event/checkpoint/boundary/baseline objects.
- Legacy snapshots remain in `data/snapshots/`; this work did not delete or rewrite them.
- GitHub is the shared source of truth for code and project handoff state.

## Last completed work

Resolved the review findings: all 842 snapshots are covered by a committed monitored-state report, simulations and CLI runtime no longer depend on `data/snapshots/`, the full 369-event dashboard comparison is a committed test, restore now loads an isolated operational baseline through the production snapshot loader, and the migration workflow no longer has write permission or direct-push capability.

## Current branch / PR

- Branch: `codex/legacy-history-cleanup-prep`
- Pull request: #3
- Latest audit decision: pending final GO/NO-GO review; no deletion has occurred

## Tests

- Local targeted tests: 9 passed, including the complete 369-event / 22-group historical dashboard equivalence test.
- Retention proof: 842/842 snapshots classified; 36 unique monitored states; 806 redundant snapshots; every unique state has a retained representative.
- R2: existing 44-object manifest remains verified; expanded 58-object plan awaits the branch workflow run.
- Restore integration: implemented and unit-tested against an isolated `data/baseline/current_snapshot.json`; live R2 execution awaits the branch workflow run.

## Open risks/blockers

- All 842 full snapshots / 27.526 GiB still remain in the Git tree; this PR intentionally does not delete them.
- Fourteen additional objects in the expanded 58-object plan still require live R2 upload and verification before deletion can be approved.
- Removing files from the current tree will not reduce historical Git object storage without a separate, explicitly approved history rewrite.
- Final cleanup still requires review and GO/NO-GO approval of PR #3 and its manifest.

## Next recommended step

Run the hardened migration workflow on the PR branch, commit the resulting 58-object manifest, and issue the final GO/NO-GO decision for a separate cleanup PR.

## Last updated

2026-08-27
