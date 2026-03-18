# Post-Migration Cleanup for Feature Tracking Docs

> Status: **Planned** | Priority: Medium | Last reviewed: 2026-03-18

Follow-up feature for retiring legacy docs-based tracking only after issue parity is verified.

## Team Review

| Reviewer | Round | Score | Date | Notes |
|----------|-------|-------|------|-------|
| GateCode | 1 | 9/10 | 2026-03-18 | GateCode round 1: added explicit cleanup gates, deterministic deletion inputs, and rollback/runbook constraints. |
| GateSec  | - | -/10 | - | Pending risk review for destructive cleanup steps. |
| GateDocs | - | -/10 | - | Pending documentation review. |

**Status**: ⏳ Planned
**Approved**: No

## Problem Statement

- `docs/roadmap.md` and legacy `docs/features/*.md` remain as temporary migration-era artifacts.
- Keeping both systems indefinitely risks drift and operator confusion.
- Cleanup is inherently destructive and must not run unless migration parity and issue mapping are verified against live GitHub issues.

## Recommended Solution

- Treat cleanup as a dedicated, reviewable PR with no unrelated changes.
- Use `tmp/feature-issue-export/parity-report.json` and `tmp/feature-issue-export/issue-map.json` as hard gates.
- Remove `docs/roadmap.md` and only migrated feature docs that are proven to have matching GitHub issues.
- Keep a deterministic deletion manifest in-repo so reviewers can verify exactly what was removed.
- Include explicit rollback instructions tied to commit SHA and deleted file list.

## Preconditions (Must Be True Before Cleanup)

- `python scripts/migrate_features.py --verify` passes in the same working tree/commit targeted for cleanup.
- `tmp/feature-issue-export/issue-map.json` exists, parses successfully, and has one entry per migrated doc scheduled for deletion.
- Every mapped issue exists in `agigante80/AgentGate`, is open, and carries expected migration labels (`type:feature`, `review:pending`, `priority:*`, `status:*`).
- No planned/unapproved feature docs are selected for deletion.
- Cleanup branch is based on latest `develop` and contains no non-doc changes.

## Implementation Steps

1. Regenerate and verify export artifacts:
   - Run `python scripts/migrate_features.py`.
   - Run `python scripts/migrate_features.py --verify` and capture success output in PR notes.
2. Build deletion candidate list from verified artifacts:
   - Derive candidates from `parity-report.json` + `issue-map.json` intersection.
   - Exclude this doc, the phase-2 automation doc, and any doc without approved migration parity.
3. Write a deterministic manifest at `tmp/feature-issue-export/cleanup-manifest.json` containing:
   - cleanup timestamp (UTC), commit SHA, and branch
   - files to delete
   - mapped issue numbers/URLs
4. Apply cleanup in one commit:
   - delete `docs/roadmap.md`
   - delete only manifest-listed migrated legacy docs
   - update remaining docs/README references to issue-centric tracking
5. Add rollback notes in PR description:
   - single-command rollback (`git revert <cleanup-commit-sha>`)
   - restored-file verification commands

## Non-Goals

- No edits to issue content/labels during cleanup.
- No automation redesign beyond already-approved phase-2 scope.
- No repository-wide docs reorganization unrelated to migration cleanup.

## Test Plan Requirements

- `python scripts/lint_docs.py` must pass after deletions.
- `python scripts/migrate_features.py --verify` must still pass after deletions.
- Sanity check that all surviving references to `docs/roadmap.md` are removed/updated.
- Manual spot-check of at least 3 deleted docs against mapped GitHub issues (title + labels + body parity).

## Acceptance Criteria

- [ ] Cleanup PR references successful parity verification output from the same commit lineage.
- [ ] `tmp/feature-issue-export/cleanup-manifest.json` is present and matches deleted files exactly.
- [ ] `docs/roadmap.md` is removed.
- [ ] Removed feature docs each have matching GitHub issue references in the manifest.
- [ ] README/docs instructions are updated to the final issue-centric workflow.
- [ ] Rollback instructions are present and tested by reviewer via dry-run command inspection.
