# TeleAgent — Technical Status & Backlog

> Last updated: 2026-03-05

---

## 1. Project Overview

TeleAgent is a Telegram bot bridge that connects an AI CLI backend (GitHub Copilot, OpenAI Codex, or direct API) to a specific GitHub repository. Each project gets its own Docker container with a dedicated bot.

**Deployment model:** one Docker container per project, all config via env vars.

```
Telegram user
     │  /tarun <cmd> | free text
     ▼
 bot.py (python-telegram-bot)
     │
     ├─ shell commands → executor.py → subprocess in /repo
     ├─ git ops       → repo.py → gitpython
     └─ AI prompts    → ai/factory.py → backend (copilot | codex | api)
                                              │
                                         /repo (cloned GitHub project)
```

---

## 2. Current Architecture

### Source layout

```
src/
├── main.py          # entrypoint: validate env → clone → install deps → start bot
├── config.py        # pydantic-settings models + REPO_DIR / DB_PATH constants
├── bot.py           # Telegram handler class (_BotHandlers) + build_app()
├── executor.py      # shell command runner + output truncation
├── history.py       # aiosqlite conversation store (/data/history.db)
├── repo.py          # git clone, pull, status
├── runtime.py       # auto-detect and install Node/Python/Go deps
└── ai/
    ├── adapter.py   # AICLIBackend ABC (send, stream, clear_history, close, is_stateful)
    ├── factory.py   # create_backend(AIConfig) → concrete backend
    ├── copilot.py   # CopilotBackend — wraps CopilotSession PTY
    ├── session.py   # CopilotSession — pexpect PTY + thread/queue bridge to async
    ├── codex.py     # CodexBackend — asyncio subprocess, streaming via stdout
    └── direct.py    # DirectAPIBackend — OpenAI / Anthropic / Ollama native API
```

### Key design decisions

| Decision | Rationale |
|---|---|
| One container per project | Isolation, independent config, easy to kill/restart per project |
| pexpect PTY for Copilot | Copilot CLI is interactive-only; no programmatic API |
| Thread + SimpleQueue bridge | pexpect is sync; asyncio bridge via daemon thread + `queue.SimpleQueue` polled with `await asyncio.sleep(0.05)` |
| `is_stateful` flag on backends | Copilot (PTY) and DirectAPI manage their own history; Codex is stateless so `history.py` injects past exchanges as context |
| aiosqlite at `/data/history.db` | Persists across restarts via Docker named volume; per `chat_id` isolation |
| `_requires_auth` decorator | Single point of access control; wraps every handler method in `_BotHandlers` |
| `REPO_DIR` / `DB_PATH` in `config.py` | Single source of truth for mount paths; all modules import from here |

### Env var reference (`config.py`)

| Variable | Default | Class |
|---|---|---|
| `BRANCH` | `main` | `GitHubConfig` |
| `AI_CLI` | `copilot` | `AIConfig` |
| `BOT_CMD_PREFIX` | `ta` | `BotConfig` |
| `MAX_OUTPUT_CHARS` | `3000` | `BotConfig` |
| `HISTORY_ENABLED` | `true` | `BotConfig` |
| `STREAM_RESPONSES` | `true` | `BotConfig` |
| `STREAM_THROTTLE_SECS` | `1.0` | `BotConfig` |

### Bot commands (prefix = `ta` by default)

| Command | Handler | Description |
|---|---|---|
| `/tarun <cmd>` | `cmd_run` | Run shell command in `/repo`; destructive cmds require inline confirmation |
| `/tasync` | `cmd_sync` | `git pull` |
| `/tagit` | `cmd_git` | `git status --short -b` + `git log --oneline -3` |
| `/tastatus` | `cmd_status` | List active AI requests with elapsed time |
| `/taclear` | `cmd_clear` | Clear SQLite history + backend in-memory history |
| `/tainfo` | `cmd_info` | Repo, branch, AI backend, uptime, active tasks |
| `/tahelp` | `cmd_help` | Full command reference including app version |
| _any other text_ | `forward_to_ai` | Sent to AI backend; history injected if `!is_stateful` |

---

## 3. CI/CD Pipeline

### Unified workflow (`.github/workflows/ci-cd.yml`)

Single file; all jobs wired with `needs:` + `if:` conditions.

| Job | Runs on | What it does |
|---|---|---|
| `version` | all branches | Reads `VERSION`, builds version string (`X.Y.Z` on main, `X.Y.Z-dev-SHA` on develop) |
| `lint` | all branches | `ruff check src/` |
| `test` | all branches | `pytest` + `--cov=src --cov-fail-under=70` + uploads `coverage.xml` |
| `docker-publish` | `main`, `develop`, `v*` tags | Multi-platform (`amd64` + `arm64`) build → push to `ghcr.io` |
| `security-scan` | after `docker-publish` | Trivy SARIF upload to GitHub Security tab |
| `release` | `main` only, clean semver | Creates GitHub Release with auto-generated changelog |
| `summary` | always | Pipeline outcome table in Actions UI |

### Branch behaviour

| Branch | Docker tags | GitHub Release |
|---|---|---|
| `develop` | `:develop`, `:X.Y.Z-dev-SHA` | Never |
| `main` | `:latest`, `:main`, `:X.Y.Z` | Yes, when `VERSION` is clean semver |
| `v*` tag | `:latest`, `:X.Y.Z` | Yes |

> **`develop` always builds the Docker image** even if lint/tests fail, to catch Dockerfile issues early.
> **`main`** requires lint + tests to pass before building.

### Release flow

1. Work on `develop`; bump `VERSION` before merging
2. `git merge develop main && git push origin main`
3. CI auto-creates `ghcr.io/agigante80/teleagent:X.Y.Z` + GitHub Release

---

## 4. Test Coverage

As of v0.2.1 (165 tests, `pytest-cov>=5.0`):

| Module | Coverage |
|---|---|
| `src/executor.py` | 100% |
| `src/history.py` | 100% |
| `src/repo.py` | 100% |
| `src/runtime.py` | 88% |
| `src/ai/adapter.py` | 100% |
| `src/ai/codex.py` | 100% |
| `src/ai/factory.py` | 100% |
| `src/config.py` | 98% |
| `src/ai/session.py` | 79% |
| `src/ai/copilot.py` | 90% |
| `src/ai/direct.py` | 80% |
| `src/main.py` | 74% |
| `src/bot.py` | 73% |
| **TOTAL** | **84%** |

CI enforces `--cov-fail-under=70`.

---

## 5. Known Gaps & Technical Backlog

---

### 5.1 Remaining test coverage gaps

#### 5.1.1 `bot.py` — 73%, `main.py` — 74%

Remaining uncovered lines:
- `bot.py:52-72` — `build_app()` function body (handler registration)
- `bot.py:169-189` — `cmd_info` (uptime formatting branches)
- `main.py:73-82` — clone failure path + SIGTERM handler teardown

#### 5.1.2 `ai/session.py` — 79%

PTY streaming edge cases not yet reached:
- Lines 85–99 — timeout path inside `_sync_stream_to_queue` main loop
- Lines 109–111 — `PROMPT_RE` match with empty clean output
- Lines 132–135 — generic exception in `_sync_stream_to_queue`

---

### 5.2 npm packages not version-pinned (⚠️ Resolved — partially)

`@github/copilot@0.0.421` and `@openai/codex@0.111.0` are now pinned in the Dockerfile.
Dependabot monitors Docker but not npm globals; update manually when new versions ship.

---

### 5.3 No `/tarestart` command ✅ Implemented

`/tarestart` — calls `backend.close()` then re-initialises via `factory.create_backend()`.

---

### 5.4 `runtime.py` reinstalls on every restart ✅ Implemented

Sentinel file per manifest (SHA-256 hash of file content) written under `/data/.install_sentinels/`.
Install is skipped on subsequent starts if the manifest hasn't changed.

---

### 5.5 Docker `HEALTHCHECK` ✅ Added

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import src.config; import sys; sys.exit(0)"
```

---

## 6. Deployment Notes

### Running locally

```bash
cd /path/to/project-stack
docker compose up -d
docker compose logs -f
```

### Persistent repo (avoid re-cloning on restart)

Mount a local directory as `/repo` in `docker-compose.yml`:

```yaml
volumes:
  - /path/to/local/repo:/repo
```

Omit `GITHUB_REPO` from `.env` when using a bind mount — the clone step is skipped if `/repo/.git` already exists.

### Adding a second project

```bash
mkdir /path/to/another-stack
cp /path/to/project-stack/.env /path/to/another-stack/.env
cp /path/to/project-stack/docker-compose.yml /path/to/another-stack/docker-compose.yml
# Edit .env: new TG_BOT_TOKEN, new GITHUB_REPO
cd /path/to/another-stack && docker compose up -d
```

Each stack is fully independent. Create separate Telegram bots via BotFather (one bot token per project).

---

## 7. Dependency Notes

| Dependency | Version pin | Why |
|---|---|---|
| `python-telegram-bot` | `>=21` | Async-native; `Application` builder pattern |
| `pydantic-settings` | `>=2` | `BaseSettings` with alias support |
| `aiosqlite` | `>=0.20` | Async SQLite for history |
| `pexpect` | `>=4.9` | PTY interaction with Copilot CLI |
| `gitpython` | `>=3.1` | Repo clone/pull |
| `openai` | `>=1.0` | Direct API + streaming |
| `anthropic` | `>=0.28` | Anthropic direct API |
| `ollama` | `>=0.1` | Ollama local API |
| `pytest-cov` | `>=5.0` | Coverage reporting in CI |
| Node.js | LTS (NodeSource) | Required by Copilot CLI and Codex CLI |
| `@github/copilot` (npm) | latest | Copilot CLI — **not** `@githubnext/github-copilot-cli` (deprecated) |
| `@openai/codex` (npm) | latest | OpenAI Codex CLI |
| Go | 1.22.4 | Runtime auto-detection for Go projects |
