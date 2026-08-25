# PROJECT_STATE.md

## Current objective

Safely migrate and verify the legacy history in `data/snapshots/` against R2, then reduce local and Git storage without losing production data or auditability.

## Production status

DiGA Monitor is in production. The scheduler runs at 06:00, 09:00, 12:00, 15:00, and 18:00 in `Europe/Zurich`.

## Current architecture

- Scheduled DiGA monitoring runs produce monitoring data and historical artifacts.
- R2 is configured for new archives and checkpoints.
- Legacy snapshots remain in `data/snapshots/` pending migration and verification.
- GitHub is the shared source of truth for code and project handoff state.

## Last completed work

R2 storage for new archives/checkpoints was established. The latest audit found that the legacy history still requires migration and verification before deletion. The Claude PR review workflow was configured with GitHub OIDC and Anthropic Workload Identity Federation.

## Current branch / PR

- Branch: `main`
- Pull request: none
- Latest audit decision: **NO-GO** for immediate deletion of the legacy history

## Tests

- R2 setup and the latest storage audit are complete.
- This documentation-only workflow setup requires content and diff verification; no production code tests are affected.
- Migration integrity, backup completeness, and restore capability must be tested before any legacy deletion.

## Open risks/blockers

- Approximately 842 full snapshots / approximately 27.5 GiB remain in the Git tree according to the latest audit.
- 367 historical events have no `snapshot_context`.
- Legacy history has not yet been fully migrated and verified in R2.
- Do not delete `data/snapshots/` until integrity, backup, and restore are verified.

## Next recommended step

Design and execute a reversible legacy migration and verification plan for R2, including event-to-snapshot reconciliation, integrity checks, backup confirmation, and a restore test. Return to ChatGPT for GO/NO-GO before removing local or Git history.

## Last updated

2026-08-25
