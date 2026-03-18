# Post-Migration Cleanup for Feature Tracking Docs

> Status: **Implemented** | Priority: Medium | Last reviewed: 2026-03-18

Follow-up feature for retiring legacy docs-based tracking only after issue parity is verified.

## Team Review

| Reviewer | Round | Score | Date | Notes |
|----------|-------|-------|------|-------|
| GateCode | 1 | 9/10 | 2026-03-18 | GateCode round 1: added explicit cleanup gates, deterministic deletion inputs, and rollback/runbook constraints. |
| GateSec  | 1 | 9/10 | 2026-03-18 | GateSec round 1: added path-boundary enforcement, integrity chain, manifest validation, security considerations section, and expanded test/acceptance criteria. |
| GateDocs | 1 | 10/10 | 2026-03-18 | Docs review round 1: comprehensive and clear, adheres to all conventions. |

**Status**: ✅ Approved — round 1, all scores ≥ 9
**Approved**: Yes — ready to implement

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
- Every mapped issue exists in `agigante80/AgentGate`, is open, and carries expected migration labels (`type:feature`, `review:pending`, `priority:*`, `status:*`). Verification must be automated via `gh issue view` (or equivalent API call) — manual spot-checks alone are insufficient for the full set.
- No planned/unapproved feature docs are selected for deletion.
- Cleanup branch is based on latest `develop` and contains no non-doc changes.
- `parity-report.json` integrity hashes have been verified in the same run (the `--verify` gate above covers this).

## Implementation Steps

1. Regenerate and verify export artifacts:
   - Run `python scripts/migrate_features.py`.
   - Run `python scripts/migrate_features.py --verify` and capture success output in PR notes.
2. Build deletion candidate list from verified artifacts:
   - Derive candidates from `parity-report.json` + `issue-map.json` intersection.
   - Exclude this doc, the phase-2 automation doc, and any doc without approved migration parity.
3. Write a deterministic manifest at `tmp/feature-issue-export/cleanup-manifest.json` containing:
   - cleanup timestamp (UTC), commit SHA, and branch
   - `parity_report_sha256` — SHA-256 of the `parity-report.json` used as input (integrity chain)
   - files to delete (as relative paths within `docs/features/` or explicit `docs/roadmap.md`)
   - mapped issue numbers/URLs
4. Validate manifest before applying:
   - Every file path in the manifest must resolve within `docs/features/` or be exactly `docs/roadmap.md`. Reject entries that escape these boundaries (same `Path.resolve()` + `relative_to()` pattern used in `--verify`).
   - Deletion must be file-by-file from the manifest — no glob patterns, no `rm -rf`, no directory-level removal.
   - Verify issue existence via `gh issue view <number> --json state` for each mapped issue. Abort on any `404` or closed-state result.
5. Apply cleanup in one commit:
   - delete `docs/roadmap.md`
   - delete only manifest-listed migrated legacy docs
   - update remaining docs/README references to issue-centric tracking
6. Add rollback notes in PR description:
   - single-command rollback (`git revert <cleanup-commit-sha>`)
   - restored-file verification commands (`git diff --stat HEAD~1` to confirm only expected files restored)

## Non-Goals

- No edits to issue content/labels during cleanup.
- No automation redesign beyond already-approved phase-2 scope.
- No repository-wide docs reorganization unrelated to migration cleanup.
- No deletion of `docs/features/_template.md`, this doc, or the phase-2 automation doc — these are active artifacts.

## Security Considerations

- *Path boundary enforcement*: `cleanup-manifest.json` entries are untrusted input until validated. Every deletion path must be confined to `docs/features/` (or the explicit `docs/roadmap.md` exception). A tampered or manually-edited manifest listing paths like `src/main.py` or `../../etc/passwd` must cause an immediate abort.
- *Integrity chain*: The manifest must include the SHA-256 of the `parity-report.json` it was derived from. Reviewers verify this hash matches the report on disk — proving that the deletion set traces back to verified parity data.
- *No content exposure*: Error messages from manifest validation must not include file content — only paths and metadata (consistent with `--verify` error handling).
- *`gh` output redaction*: If `gh issue view` calls are made during precondition checks, all output must be passed through `SecretRedactor` before logging/display (the `GITHUB_REPO_TOKEN` could appear in error responses).
- *Atomic commit*: Cleanup must be a single commit so `git revert` is a single-command rollback. Multi-commit cleanup risks partial revert and orphaned state.

## Test Plan Requirements

- `python scripts/lint_docs.py` must pass after deletions.
- `python scripts/migrate_features.py --verify` must still pass after deletions.
- Sanity check that all surviving references to `docs/roadmap.md` are removed/updated.
- Manual spot-check of at least 3 deleted docs against mapped GitHub issues (title + labels + body parity).
- Regression test: manifest with a path escaping `docs/features/` (e.g., `src/main.py`) must be rejected before any file I/O.
- Regression test: manifest referencing a non-existent file must produce an error, not a silent skip.
- Verify that `parity_report_sha256` in the manifest matches the on-disk `parity-report.json` hash.

## Acceptance Criteria

- [x] Cleanup PR references successful parity verification output from the same commit lineage.
- [x] `tmp/feature-issue-export/cleanup-manifest.json` is present and matches deleted files exactly.
- [x] Manifest includes `parity_report_sha256` that matches the on-disk report.
- [x] `docs/roadmap.md` is removed.
- [x] Removed feature docs each have matching GitHub issue references in the manifest.
- [x] No manifest entry resolves outside `docs/features/` (except `docs/roadmap.md`).
- [x] Deletion is file-by-file from the manifest — no glob or directory removal.
- [x] README/docs instructions are updated to the final issue-centric workflow.
- [x] Rollback instructions are present and tested by reviewer via dry-run command inspection.
- [x] `_template.md`, this doc, and the phase-2 automation doc are confirmed not deleted.
