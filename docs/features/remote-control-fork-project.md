# Remote Control Fork Project (`gate fork`)

> Status: **Planned** | Priority: Medium | Last reviewed: 2026-03-15

Allow AgentGate to manage, cherry-pick from, and interact with a second "fork" GitHub
repository alongside the primary `GITHUB_REPO`. Enables cross-repo code promotion workflows
without leaving the chat interface.

---

## Team Review

> Managed automatically by the team review process — see `docs/guides/feature-review-process.md`.
> To start a review, ask any team member: `dev Please start a feature review of docs/features/remote-control-fork-project.md`

| Reviewer | Round | Score | Date | Notes |
|----------|-------|-------|------|-------|
| GateCode | 1 | -/10 | - | Pending |
| GateSec  | 1 | 6/10  | 2026-03-15 | GateSec R1: 7 security gaps found — see findings below |
| GateDocs | 1 | -/10 | - | Pending |

**Status**: ⏳ Pending review
**Approved**: No — requires all scores ≥ 9/10 in the same round

---

### GateSec R1 Findings (2026-03-15)

Seven security and design gaps identified. All fixed inline in this commit except F3
(open question — needs team decision).

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| F1 | 🔴 High | `run_shell()` hardcodes `cwd=REPO_DIR` — fork commands would execute in the wrong directory. No `cwd` parameter exists. | ✅ Fixed: added Step 2 (`executor.py` refactoring), Files table updated, test added |
| F2 | 🔴 High | Token fallback leaks primary PAT cross-org — `FORK_GITHUB_TOKEN` silently fell back to `GITHUB_REPO_TOKEN` with no org-boundary check. An attacker-controlled fork repo would receive the primary repo's credentials. | ✅ Fixed: added `FORK_SAME_ORG` gate (default `false`); fallback only when explicitly opted in |
| F3 | 🟡 Medium | Cross-repo cherry-pick mechanism unspecified — `git cherry-pick <sha>` only works on locally reachable commits. Spec didn't explain how fork commits become reachable in `REPO_DIR`. | ✅ Fixed: added "Cross-repo cherry-pick mechanism" section with remote-add/fetch/pick flow |
| F4 | 🟡 Medium | `gate fork cherry-pick` not marked destructive — modifies `REPO_DIR` working tree but wasn't flagged for confirmation dialog. | ✅ Fixed: added `destructive=True` note, confirmation requirement, acceptance criterion |
| F5 | 🟡 Medium | No audit logging — fork operations (especially cherry-pick) had no audit trail. | ✅ Fixed: added audit requirement in Architecture Notes + test |
| F6 | 🟢 Low | `FORK_REPO` not validated at startup — no format check; malformed values could produce confusing errors downstream. | ✅ Fixed: added `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` validation in Step 1 |
| F7 | 🟢 Low | `register_command` signature wrong in code example — used `help=` kwarg but actual decorator uses positional `description` param. | ✅ Fixed: corrected Step 4 code example |

---

## ⚠️ Prerequisite Questions

> Answer these before writing a single line of code.

1. **Scope** — Both Telegram and Slack (fork management is platform-agnostic).
2. **Backend** — Applies to all AI backends; fork clone/push is shell-level, not AI-level.
3. **Stateful vs stateless** — No interaction with history injection; fork operations are
   discrete shell commands.
4. **Breaking change?** — No existing env vars renamed or removed. New `FORK_*` vars are
   additive with safe defaults (empty = disabled).
5. **New dependency?** — No new pip packages. Uses `git` (already present in container).
6. **Persistence** — Fork repo cloned to a new directory under `/data/fork/` (separate from
   `REPO_DIR = /repo`). No new DB tables needed.
7. **Auth** — `FORK_GITHUB_TOKEN` (PAT with repo scope). May reuse `GITHUB_REPO_TOKEN` if
   fork is in the same org; separate token recommended for cross-org forks.
8. **Prerequisite** — `modular-plugin-architecture.md` must be implemented first. The
   registry pattern (`backend_registry`, `platform_registry`) and `Services` dataclass
   introduced there are the extension points this feature builds on (e.g., `RepoService`
   will be extended to support a second repo target).

---

## Problem Statement

1. **Cross-repo cherry-pick is manual** — developers must leave the chat, clone a fork
   locally, cherry-pick commits, and push. There is no chat-native workflow for this.
2. **No visibility into fork divergence** — no command to show how far a fork has drifted
   from the upstream without external tooling.
3. **Promotion pipelines require shell access** — moving a fix from a fork to the primary
   repo (or vice versa) today requires manual git operations outside AgentGate.

Affected: Telegram and Slack users managing multi-repo projects (e.g., open-source
maintainers with a private fork or a staging fork).

---

## Current Behaviour (as of v`0.20.x`)

| Layer | Location | Current behaviour |
|-------|----------|-------------------|
| Config | `src/config.py` (`GitHubConfig`) | Only `GITHUB_REPO`, `GITHUB_REPO_TOKEN`, `BRANCH` — single-repo only |
| Repo ops | `src/repo.py` | `clone()`, `pull()`, `push()` all operate on `REPO_DIR` only |
| Services | `src/services.py` | `RepoService` wraps a single `REPO_DIR`; `NullRepoService` for no-op |
| Bot | `src/bot.py` | No `gate fork` command |
| Slack | `src/platform/slack.py` | No `fork` subcommand |

> **Key gap**: `src/repo.py` and `RepoService` are hardcoded to a single directory.
> The registry and `Services` patterns from `modular-plugin-architecture` provide the
> extension points, but the second-repo wiring does not exist yet.

---

## Design Space

### Axis 1 — Where to clone the fork

#### Option A — `/data/fork/` (fixed path) *(recommended)*

Clone the fork to a fixed `/data/fork/` directory (a `FORK_DIR` constant in `config.py`,
analogous to `REPO_DIR`).

**Pros:**
- Simple. No user configuration for the clone path.
- Volume-persisted between restarts (same `/data` volume).

**Cons:**
- Only one fork at a time per container (acceptable given one-container-per-project model).

**Recommendation: Option A** — matches the single-project deployment model; complexity
is low and the constraint is documented.

---

#### Option B — `FORK_DIR` env var (user-configurable path)

Let the user specify the clone path via `FORK_DIR`.

**Pros:**
- Flexible.

**Cons:**
- More surface area; path traversal risk if not validated.

---

### Axis 2 — How to expose fork commands

#### Option A — Subcommands of `gate fork` *(recommended)*

`gate fork clone`, `gate fork pull`, `gate fork diff`, `gate fork cherry-pick <sha>`.

**Pros:**
- Namespaced; no collision with existing `gate` commands.
- Natural grouping.

**Cons:**
- Slightly deeper command tree.

**Recommendation: Option A** — consistent with how `gate sync` / `gate run` are structured.

---

## Recommended Solution

- **Axis 1**: Option A — fixed `FORK_DIR = /data/fork/`
- **Axis 2**: Option A — `gate fork <subcommand>`

New commands:
- `gate fork clone` — clone `FORK_REPO` into `FORK_DIR`
- `gate fork pull` — pull latest in `FORK_DIR`
- `gate fork diff` — show commits in fork not in primary (or vice versa)
- `gate fork cherry-pick <sha>` — cherry-pick a commit from the fork into `REPO_DIR`
  (**destructive** — modifies primary working tree; must trigger confirmation dialog)

`ForkRepoService` will be a second `RepoService` instance registered via the existing
`Services` dataclass, added in `modular-plugin-architecture`.

### Cross-repo cherry-pick mechanism

`git cherry-pick` only works on commits reachable from a local ref. To cherry-pick from
the fork into the primary repo:

1. Add the fork as a named remote in `REPO_DIR`: `git remote add fork <fork-url>`
2. Fetch the fork: `git fetch fork`
3. Cherry-pick: `git cherry-pick <sha>`
4. Do **not** remove the remote afterwards (speeds up subsequent picks).

The fork remote URL must use the same credential-embedding pattern as the primary clone
(token in HTTPS URL). The remote-add and fetch steps must redact the URL from output.

---

## Architecture Notes

- **Prerequisite**: `modular-plugin-architecture` must be merged before implementation.
  `RepoService`, `Services`, and `registry.py` are all required extension points.
- **`REPO_DIR` and `DB_PATH`** — always import from `src/config.py`. Add `FORK_DIR` there.
- **`run_shell()` refactoring required** — `executor.run_shell()` currently hardcodes
  `cwd=str(REPO_DIR)` (line 54 of `executor.py`). Fork commands (`clone`, `pull`, `diff`)
  need to execute in `FORK_DIR`. Add an optional `cwd: str | None = None` parameter that
  defaults to `REPO_DIR`. All existing callers are unaffected; fork handlers pass
  `cwd=str(FORK_DIR)`.
- **Platform symmetry** — every `gate fork *` command in `src/bot.py` must have a mirrored
  handler in `src/platform/slack.py`.
- **Auth guard** — all Telegram handlers must use `@_requires_auth`; Slack handlers must
  call `self._is_allowed(channel, user)`.
- **`sanitize_git_ref`** — always use `executor.sanitize_git_ref(sha)` before interpolating
  any user-supplied SHA into a `git cherry-pick` command.
- **Destructive flag** — `gate fork cherry-pick` modifies the primary working tree and must
  be registered with `destructive=True` so that `is_destructive()` triggers the confirmation
  dialog. `gate fork clone` and `gate fork pull` operate only on `FORK_DIR` and are
  non-destructive.
- **Secret redaction** — `FORK_GITHUB_TOKEN` must be included in `ForkConfig.secret_values()`
  (not `GitHubConfig`) so the redactor scrubs it from output automatically. The
  `_collect_secrets()` function in `redact.py` auto-discovers sub-configs via Pydantic
  `model_fields`, so adding `fork: ForkConfig` to `Settings` is sufficient — no manual
  edit to `_KNOWN_SUBCONFIGS` is needed.
- **Audit logging** — all fork operations must call `audit.record()` with action
  `fork_clone`, `fork_pull`, `fork_diff`, or `fork_cherry_pick`. Cherry-pick must log
  the target SHA. Follow the existing pattern in `bot.py` / `slack.py`.

---

## Config Variables

| Env var | Type | Default | Description |
|---------|------|---------|-------------|
| `FORK_REPO` | `str` | `""` | Fork repository in `owner/repo` format. Empty = feature disabled. Validated at startup: must match `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` or be empty. |
| `FORK_GITHUB_TOKEN` | `str` | `""` | PAT with repo scope for the fork. Falls back to `GITHUB_REPO_TOKEN` *only* if `FORK_SAME_ORG=true` (see below). |
| `FORK_BRANCH` | `str` | `"main"` | Default branch to track in the fork. |
| `FORK_SAME_ORG` | `bool` | `false` | When `true`, allows `FORK_GITHUB_TOKEN` to fall back to `GITHUB_REPO_TOKEN`. When `false` (default), an empty `FORK_GITHUB_TOKEN` disables fork auth — clone will fail for private repos. This prevents accidentally sending the primary token to a cross-org remote. |

---

## Implementation Steps

### Step 1 — `src/config.py`: add `ForkConfig` and `FORK_DIR`

```python
FORK_DIR: Final[str] = "/data/fork"

class ForkConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    fork_repo: str = Field("", env="FORK_REPO")
    fork_github_token: str = Field("", env="FORK_GITHUB_TOKEN")
    fork_branch: str = Field("main", env="FORK_BRANCH")
    fork_same_org: bool = Field(False, env="FORK_SAME_ORG")

    def secret_values(self) -> list[str]:
        return [v for v in [self.fork_github_token] if v]
```

Add `fork: ForkConfig` to `Settings`. Add startup validation in `_validate_config()`
that `FORK_REPO` matches `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` or is empty.

---

### Step 2 — `src/executor.py`: add optional `cwd` parameter to `run_shell()`

```python
async def run_shell(cmd: str, max_chars: int, redactor=None, cwd: str | None = None) -> str:
    effective_cwd = cwd if cwd is not None else str(REPO_DIR)
    proc = await asyncio.create_subprocess_shell(
        cmd, cwd=effective_cwd, ...
    )
```

All existing callers pass no `cwd` and are unaffected.

---

### Step 3 — `src/services.py`: add `ForkRepoService`

Instantiate a second `RepoService(FORK_DIR)` in `main.py` and expose it as
`Services.fork_repo`. Bots check `services.fork_repo is not None` before dispatching fork
commands.

---

### Step 4 — `src/bot.py`: add `cmd_fork`

```python
@register_command("fork", "Manage the fork repo (clone/pull/diff/cherry-pick)",
                  platforms={"telegram", "slack"})
@_requires_auth
async def cmd_fork(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ...
```

Note: `cherry-pick` subcommand must check `is_destructive()` and trigger confirmation.
All subcommands must call `audit.record()`.

---

### Step 5 — `src/platform/slack.py`: mirror `cmd_fork`

Add `"fork": self.cmd_fork` to the dispatch table in `_dispatch()`. The `cmd_fork`
handler parses subcommands from `args[0]`. Cherry-pick must trigger the confirmation
dialog (Block Kit Actions). All subcommands must call `audit.record()`.

---

### Step 6 — `src/main.py`: initialise `ForkRepoService`

Only instantiate if `settings.fork.fork_repo` is non-empty.

---

## Files to Create / Change

| File | Action | Summary of change |
|------|--------|-------------------|
| `src/config.py` | **Edit** | Add `ForkConfig`, `FORK_DIR`, wire into `Settings`, startup validation |
| `src/executor.py` | **Edit** | Add optional `cwd` parameter to `run_shell()` |
| `src/services.py` | **Edit** | Add `ForkRepoService`; expose via `Services.fork_repo` |
| `src/bot.py` | **Edit** | Add `cmd_fork` with subcommand dispatch |
| `src/platform/slack.py` | **Edit** | Mirror `cmd_fork` for Slack; add to dispatch table |
| `src/main.py` | **Edit** | Conditionally init `ForkRepoService` |
| `README.md` | **Edit** | Add `FORK_*` env var rows, `gate fork` commands table |
| `.env.example` | **Edit** | Add commented `FORK_REPO`, `FORK_GITHUB_TOKEN`, `FORK_BRANCH`, `FORK_SAME_ORG` |
| `docker-compose.yml.example` | **Edit** | Add commented `FORK_*` entries |
| `docs/features/remote-control-fork-project.md` | **Edit** | Status → `Implemented` on merge |
| `docs/roadmap.md` | **Edit** | Mark item done; add follow-up if any |

---

## Dependencies

| Package | Status | Notes |
|---------|--------|-------|
| `git` | ✅ Already in container | Used via `run_shell()` in `executor.py` |

---

## Test Plan

### `tests/unit/test_fork.py` (new file)

| Test | What it checks |
|------|----------------|
| `test_fork_disabled_when_no_repo` | `FORK_REPO=""` → `cmd_fork` returns "not configured" |
| `test_fork_clone_runs_git` | `gate fork clone` shells `git clone` with correct URL |
| `test_fork_cherry_pick_sanitizes_ref` | Invalid SHA → `sanitize_git_ref` returns `None` → error |
| `test_fork_config_secret_values` | `ForkConfig.secret_values()` includes token, excludes empty |
| `test_fork_token_redacted_in_output` | `FORK_GITHUB_TOKEN` value does not appear in `run_shell()` output |
| `test_fork_clone_url_redacted` | Clone URL with embedded token is redacted from user-visible output |
| `test_fork_cherry_pick_destructive` | `cherry-pick` triggers confirmation dialog before executing |
| `test_fork_repo_validation` | Invalid `FORK_REPO` format rejected at startup |
| `test_fork_token_no_fallback_cross_org` | `FORK_SAME_ORG=false` + empty token → clone fails for private repos |
| `test_fork_token_fallback_same_org` | `FORK_SAME_ORG=true` + empty token → uses `GITHUB_REPO_TOKEN` |
| `test_fork_run_shell_cwd` | Fork commands execute with `cwd=FORK_DIR`, not `REPO_DIR` |
| `test_fork_audit_logged` | All fork operations produce an audit record |

### `tests/unit/test_executor.py` additions

| Test | What it checks |
|------|----------------|
| `test_run_shell_default_cwd` | No `cwd` → runs in `REPO_DIR` (backward compat) |
| `test_run_shell_custom_cwd` | `cwd=FORK_DIR` → runs in `FORK_DIR` |

### `tests/unit/test_bot.py` additions

| Test | What it checks |
|------|----------------|
| `test_cmd_fork_auth` | Unauthenticated user is rejected |
| `test_cmd_fork_no_config` | `FORK_REPO` unset → informative message returned |

---

## Documentation Updates

### `README.md`

Add `FORK_REPO`, `FORK_GITHUB_TOKEN`, `FORK_BRANCH` rows to the env var table.
Add `gate fork clone/pull/diff/cherry-pick` rows to the commands table.

### `.env.example` and `docker-compose.yml.example`

Add commented `FORK_*` entries under the GitHub section.

### `.github/copilot-instructions.md`

Add note: `ForkRepoService` is the second `RepoService` instance in `Services`; enabled
only when `FORK_REPO` is set.

---

## Edge Cases and Open Questions

1. **Token fallback** — ~~if `FORK_GITHUB_TOKEN` is empty, fall back to `GITHUB_REPO_TOKEN`.
   Is this safe?~~ *Resolved*: fallback is gated behind `FORK_SAME_ORG=true` (default
   `false`). When `false`, an empty `FORK_GITHUB_TOKEN` means no auth — clone will fail
   for private repos. This prevents accidentally sending the primary repo's PAT to a
   cross-org remote controlled by a different party.

2. **Cherry-pick conflicts** — what happens if `git cherry-pick` exits non-zero (merge
   conflict)? `run_shell()` captures output including the conflict markers; surface them to
   the user and abort with `git cherry-pick --abort`. Do not auto-resolve.

3. **Divergence display** — `gate fork diff` should show a bounded output (max N commits).
   Use `HISTORY_TURNS`-style cap or a new `FORK_DIFF_LIMIT` var?

4. **`gate restart` interaction** — if a `git cherry-pick` is in progress, `gate restart`
   will interrupt it. The working tree will be in a conflicted state. Document this in the
   help text for `gate fork cherry-pick`.

5. **Slack thread scope** — fork status messages should reply in-thread when invoked from a
   thread, consistent with other commands.

6. **OQ: single fork limit** — the one-container-per-project model means one fork per
   deployment. If users need multiple forks, they would need multiple containers.
   Document this as a known limitation.

7. **Cross-repo cherry-pick mechanism** — cherry-picking across repos requires adding the
   fork as a git remote in `REPO_DIR` and fetching. The remote URL embeds the fork token
   and must be redacted from all output. See "Cross-repo cherry-pick mechanism" in
   Recommended Solution for the full flow.

8. **`FORK_DIR` must not be user-configurable** — the hardcoded `/data/fork/` path avoids
   path traversal. Do not expose as an env var without strict validation.

---

## Acceptance Criteria

- [ ] All implementation steps above are complete.
- [ ] `pytest tests/ -v --tb=short` passes with no failures.
- [ ] `ruff check src/` reports no new issues.
- [ ] `README.md` updated (env vars, commands — both Telegram and Slack sections).
- [ ] `.env.example` and `docker-compose.yml.example` updated with `FORK_*` entries.
- [ ] `FORK_REPO=""` (default) leaves existing behaviour 100% unchanged.
- [ ] `sanitize_git_ref` is used for every user-supplied SHA in fork commands.
- [ ] `FORK_GITHUB_TOKEN` is included in `ForkConfig.secret_values()`.
- [ ] `run_shell()` accepts optional `cwd` parameter; all existing callers unaffected.
- [ ] `gate fork cherry-pick` is registered as `destructive=True` and triggers confirmation.
- [ ] Token fallback is gated behind `FORK_SAME_ORG=true`; default `false` prevents cross-org leakage.
- [ ] Fork clone URL with embedded token is redacted from all user-visible output.
- [ ] All fork operations are audit-logged.
- [ ] `FORK_REPO` format validated at startup (`owner/repo` pattern or empty).
- [ ] Cherry-pick conflicts are surfaced to user and aborted (`--abort`), never auto-resolved.
- [ ] Feature works on both Telegram and Slack.
- [ ] `docs/roadmap.md` entry is marked done (✅) on merge.
- [ ] `docs/features/remote-control-fork-project.md` status → `Implemented` on merge.
- [ ] `.github/copilot-instructions.md` updated.
- [ ] `VERSION` bumped (MINOR) on `develop` before merge to `main`.

---

## Version Bump

**Expected bump**: MINOR → `0.Y+1.0` (new commands and env vars, safe defaults, no removals).

---

## Roadmap Update

```markdown
| 2.15 | ✅ Remote control fork project — `gate fork` subcommands for cross-repo cherry-pick | [→ features/remote-control-fork-project.md](features/remote-control-fork-project.md) |
```
