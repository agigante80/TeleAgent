# Phase 2: Automated GitHub Issue Operations

> Status: **Implemented** | Priority: High | Last reviewed: 2026-03-18

Follow-up feature for automating GitHub issue creation and updates after Phase 1 manual migration is stable.

## Team Review

| Reviewer | Round | Score | Date | Notes |
|----------|-------|-------|------|-------|
| GateCode | 1 | 9/10 | 2026-03-18 | GateCode round 1: added concrete command/test/audit constraints; ready for security review. |
| GateSec  | 1 | 9/10 | 2026-03-18 | GateSec round 1: added tempfile/map-integrity/redaction hardening; renamed section for validator compliance. |
| GateDocs | 1 | 10/10 | 2026-03-18 | All documentation conventions met. |

**Status**: ✅ Approved — round 1, all scores ≥ 9
**Approved**: Yes — ready to implement

## Problem Statement

- Phase 1 exports markdown but still requires manual copy/paste to create issues.
- Manual posting does not scale and increases risk of title/label drift.
- There is no auditable automated issue CRUD path yet.

## Recommended Solution

- Add a single audited command path for GitHub issue CRUD through `gh`.
- Route all shell execution through `run_shell()` with allowlist enforcement.
- Reuse `GITHUB_REPO_TOKEN` with least-privilege scope (`issues:write`, `metadata:read`).
- Keep all issue body content in files/stdin (`--body-file`) to avoid shell interpolation risk.

## Implementation Steps

- Add `scripts/sync_github_issues.py` for idempotent create/update flows from `tmp/feature-issue-export/`.
- Support `--dry-run` (no writes), `--create-missing`, and `--update-existing` modes.
- Keep mapping in a checked-in machine-readable file (`tmp/feature-issue-export/issue-map.json`) generated from successful runs.
- Disallow free-form command execution; only explicit `gh issue create|edit|view|list` argument sets are permitted.
- Keep phase-1 `scripts/migrate_features.py --verify` as a hard preflight check before any write mode.
- Pass `redactor` to every `run_shell()` call and apply `redactor.redact()` to all `gh` stdout/stderr before logging, audit, or user-facing output.
- Use `tempfile.NamedTemporaryFile` (or equivalent) for `--body-file` content and delete in a `finally` block — no leftover files containing issue markdown.
- Record every write operation (create/update) via `audit.record()` with redacted detail text.
- Validate `issue-map.json` integrity on load: reject entries where the `source` path escapes `docs/features/` (reuse the `resolve()` + `relative_to()` boundary pattern from `migrate_features.py --verify`).

## Non-Goals

- No issue close/reopen/delete support in phase 2.
- No milestone/project/assignee automation in phase 2.
- No migration away from `GITHUB_REPO_TOKEN` in this slice.

## Security Review Scope (Required Before Build)

- Threat model update for command injection, token leakage, and auth scope creep.
- Verification that no new plaintext secret paths are introduced.
- Validation that all `gh` operations are redacted in logs and audit entries — `gh` may echo tokens in HTTP-level error messages or debug output; all subprocess stderr must pass through `SecretRedactor`.
- GateSec score must be `>= 9/10` in this feature doc before implementation starts.
- `issue-map.json` must be treated as untrusted input on read: a tampered map could redirect `--update-existing` to an unrelated issue number. Validate source paths and consider signing or hash-binding entries.

## Test Plan Requirements

- Unit tests for argument construction must assert exact argv arrays (no shell strings).
- Unit tests must cover malicious inputs in titles/body/labels and prove no command injection path.
- Integration tests (mocked subprocess) must validate create/update decision logic and idempotency.
- Negative tests must cover missing token, failed preflight parity check, and rejected unsupported flags.
- Unit test for `issue-map.json` path-escape rejection (source outside `docs/features/`, issue number as path component).
- Unit test confirming `--body-file` tempfile is deleted even when `gh` returns non-zero exit.
- Unit test confirming all `gh` subprocess output (stdout and stderr) is passed through `SecretRedactor` before audit or display.

## Acceptance Criteria

- [x] Feature doc approved by GateCode, GateSec, and GateDocs.
- [x] Security review completed with explicit mitigations recorded.
- [x] Implementation PR references this doc and satisfies all listed mitigations.
- [x] Tests cover command construction and untrusted markdown/body inputs.
- [x] Write-mode runs are blocked unless phase-1 parity verification passes in the same execution context.
- [x] Dry-run output is deterministic and includes proposed issue number/title/label diffs.
- [x] All `gh` subprocess output (stdout + stderr) passes through `SecretRedactor` before logging, audit, or user display.
- [x] `--body-file` tempfiles are cleaned up in a `finally` block — no leftover files on success or failure.
- [x] `issue-map.json` source paths are boundary-checked on load (reject escapes outside `docs/features/`).
