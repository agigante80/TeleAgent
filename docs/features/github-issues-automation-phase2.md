# Phase 2: Automated GitHub Issue Operations

> Status: **Planned** | Priority: High | Last reviewed: 2026-03-18

Follow-up feature for automating GitHub issue creation and updates after Phase 1 manual migration is stable.

## Team Review

| Reviewer | Round | Score | Date | Notes |
|----------|-------|-------|------|-------|
| GateCode | - | -/10 | - | Pending implementation review. |
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

## Security Review Scope (Required Before Build)

- Threat model update for command injection, token leakage, and auth scope creep.
- Verification that no new plaintext secret paths are introduced.
- Validation that all `gh` operations are redacted in logs and audit entries.
- GateSec score must be `>= 9/10` in this feature doc before implementation starts.

## Acceptance Criteria

- [ ] Feature doc approved by GateCode, GateSec, and GateDocs.
- [ ] Security review completed with explicit mitigations recorded.
- [ ] Implementation PR references this doc and satisfies all listed mitigations.
- [ ] Tests cover command construction and untrusted markdown/body inputs.
