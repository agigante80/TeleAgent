# Phase 2: Automated GitHub Issue Operations

> Status: **Planned** | Priority: High | Last reviewed: 2026-03-18

Follow-up feature for automating GitHub issue creation and updates after Phase 1 manual migration is stable.

## Team Review

| Reviewer | Round | Score | Date | Notes |
|----------|-------|-------|------|-------|
| GateCode | 1 | 9/10 | 2026-03-18 | GateCode round 1: added concrete command/test/audit constraints; ready for security review. |
| GateSec  | - | -/10 | - | Mandatory security review before implementation. |
| GateDocs | - | -/10 | - | Pending documentation review. |

**Status**: ⏳ Planned
**Approved**: No

## Problem Statement

- Phase 1 exports markdown but still requires manual copy/paste to create issues.
- Manual posting does not scale and increases risk of title/label drift.
- There is no auditable automated issue CRUD path yet.

## Recommended Solution

- Add a single audited command path for GitHub issue CRUD through `gh`.
- Route all shell execution through `run_shell()` with allowlist enforcement.
- Reuse `GITHUB_REPO_TOKEN` with least-privilege scope (`issues:write`, `metadata:read`).
- Keep all issue body content in files/stdin (`--body-file`) to avoid shell interpolation risk.

## Implementation Scope

- Add `scripts/sync_github_issues.py` for idempotent create/update flows from `tmp/feature-issue-export/`.
- Support `--dry-run` (no writes), `--create-missing`, and `--update-existing` modes.
- Keep mapping in a checked-in machine-readable file (`tmp/feature-issue-export/issue-map.json`) generated from successful runs.
- Disallow free-form command execution; only explicit `gh issue create|edit|view|list` argument sets are permitted.
- Keep phase-1 `scripts/migrate_features.py --verify` as a hard preflight check before any write mode.

## Non-Goals

- No issue close/reopen/delete support in phase 2.
- No milestone/project/assignee automation in phase 2.
- No migration away from `GITHUB_REPO_TOKEN` in this slice.

## Security Review Scope (Required Before Build)

- Threat model update for command injection, token leakage, and auth scope creep.
- Verification that no new plaintext secret paths are introduced.
- Validation that all `gh` operations are redacted in logs and audit entries.
- GateSec score must be `>= 9/10` in this feature doc before implementation starts.

## Test Plan Requirements

- Unit tests for argument construction must assert exact argv arrays (no shell strings).
- Unit tests must cover malicious inputs in titles/body/labels and prove no command injection path.
- Integration tests (mocked subprocess) must validate create/update decision logic and idempotency.
- Negative tests must cover missing token, failed preflight parity check, and rejected unsupported flags.

## Acceptance Criteria

- [ ] Feature doc approved by GateCode, GateSec, and GateDocs.
- [ ] Security review completed with explicit mitigations recorded.
- [ ] Implementation PR references this doc and satisfies all listed mitigations.
- [ ] Tests cover command construction and untrusted markdown/body inputs.
- [ ] Write-mode runs are blocked unless phase-1 parity verification passes in the same execution context.
- [ ] Dry-run output is deterministic and includes proposed issue number/title/label diffs.
