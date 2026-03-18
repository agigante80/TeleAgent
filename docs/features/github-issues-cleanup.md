# Post-Migration Cleanup for Feature Tracking Docs

> Status: **Planned** | Priority: Medium | Last reviewed: 2026-03-18

Follow-up feature for retiring legacy docs-based tracking only after issue parity is verified.

## Team Review

| Reviewer | Round | Score | Date | Notes |
|----------|-------|-------|------|-------|
| GateCode | - | -/10 | - | Pending implementation review. |
| GateSec  | - | -/10 | - | Pending risk review for destructive cleanup steps. |
| GateDocs | - | -/10 | - | Pending documentation review. |

**Status**: ⏳ Planned
**Approved**: No

## Problem Statement

- `docs/roadmap.md` and legacy `docs/features/*.md` remain as temporary migration-era artifacts.
- Keeping both systems indefinitely risks drift and operator confusion.

## Recommended Solution

- Use `tmp/feature-issue-export/parity-report.json` as the cleanup gate.
- Remove `docs/roadmap.md` and only the migrated legacy docs after parity is verified.
- Perform cleanup in a dedicated PR with explicit file list and rollback notes.

## Acceptance Criteria

- [ ] Cleanup PR references verified parity report output.
- [ ] `docs/roadmap.md` removal approved in review.
- [ ] Removed feature docs each have matching GitHub issue references.
- [ ] README/docs instructions are updated to the final issue-centric workflow.
