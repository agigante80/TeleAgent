# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository

**Owner**: `agigante80` | **Repo**: `agigante80/AgentGate` | **Branches**: `main` (production), `develop` (active development)

## Commands

```bash
# Lint
ruff check src/

# Lint docs (checks env var coverage in README, .env.example, docker-compose.yml.example)
python scripts/lint_docs.py

# Run all tests
pytest tests/ -v --tb=short

# Single test file
pytest tests/unit/test_bot.py -v

# Single test
pytest tests/unit/test_bot.py::TestPrefix::test_default_prefix -v

# Coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run locally
pip install -r requirements.txt && pip install -r requirements-dev.txt
python -m src.main
```

## Architecture

AgentGate is an async Python bot (Telegram or Slack) that acts as a gateway to pluggable AI backends. Each deployment is one Docker container per project repo.

### Startup flow (`src/main.py`)

Validate config -> clone GitHub repo -> auto-install deps -> init SQLite history/audit DBs -> build `Services` dataclass -> create AI backend -> start bot -> send Ready message -> write `/tmp/healthy`.

### Config (`src/config.py`)

Pydantic `BaseSettings` split into sub-configs: `TelegramConfig`, `SlackConfig`, `GitHubConfig`, `AIConfig`, `BotConfig`, `VoiceConfig`, `StorageConfig`, `LogConfig`. All values from env vars. Every sub-config implements `secret_values() -> list[str]` for dynamic secret redaction. Module-level `REPO_DIR` and `DB_PATH` constants -- always import these instead of hardcoding paths.

### AI backends (`src/ai/`)

- **`adapter.py`**: `AICLIBackend` ABC with `send()`, `stream()`, `clear_history()`, `close()`, and `is_stateful` flag. `SubprocessMixin` for backends that spawn child processes.
- **Stateless** (history injected via `build_prompt()`): `CopilotBackend`, `CodexBackend`, `GeminiBackend`, `ClaudeBackend`
- **Stateful** (maintains native message list): `DirectAPIBackend` (OpenAI/Anthropic/Ollama)
- **`claude.py`**: Stateless `ClaudeBackend` -- spawns `claude -p <prompt> --dangerously-skip-permissions --output-format text`. Requires `ANTHROPIC_API_KEY`.
- **`factory.py`**: Selects backend via `AI_CLI` env var. Backends registered with `@backend_registry.register("key")` and lazy-loaded via `_load_backends()`.

### Platform layer (`src/platform/`)

- `common.py`: Shared helpers -- `build_prompt()`, `save_to_history()`, `thinking_ticker()`
- `bot.py`: Telegram bot with `@_requires_auth` decorator on all handlers
- `slack.py`: Slack bot using `slack-bolt[async]` Socket Mode

Platform selected by `PLATFORM` env var (default `telegram`).

### Registry system (`src/registry.py`)

Generic `Registry[T]` with four instances: `backend_registry`, `platform_registry`, `storage_registry`, `audit_registry`. Register with `@registry.register("key")`, instantiate with `registry.create("key", ...)`.

### Command registry (`src/commands/registry.py`)

`@register_command(name, help)` decorator. `_validate_command_symmetry()` asserts every Telegram command has a Slack mirror -- CI fails if one platform is missing.

### Other key modules

- **`executor.py`**: `run_shell()` runs in `REPO_DIR`, `is_destructive()` keyword-checks, `sanitize_git_ref()` validates user input before git commands
- **`redact.py`**: `SecretRedactor` scrubs outgoing text of known tokens/patterns
- **`history.py`**: `ConversationStorage` ABC with `SQLiteStorage`. `build_context()` prepends history for stateless backends. `HISTORY_TURNS` controls injection count (default 10)
- **`audit.py`**: `AuditLog` ABC with `SQLiteAuditLog`. Exception-swallowing design. Callers must redact before recording
- **`services.py`**: `Services` dataclass bundles `ShellService`, `RepoService`, `AuditLog`. Constructed once in `main.py`
- **`runtime.py`**: Auto-detects and installs deps from `package.json`/`pyproject.toml`/`requirements.txt`/`go.mod`

## Key Conventions

- **Secret redaction**: Always pass `SecretRedactor` to `run_shell()` and call `redactor.redact()` on any text going back to users.
- **Git ref safety**: Always use `executor.sanitize_git_ref(ref)` before interpolating user input into git commands.
- **Adding an AI backend**: Subclass `AICLIBackend`, set `is_stateful`, implement `send()`, decorate with `@backend_registry.register("key")`, add to `_load_backends()` in `factory.py`.
- **New config values**: Add to appropriate sub-config in `src/config.py`. Must implement `secret_values()`.
- **New bot commands**: Implement `cmd_<name>` in both `bot.py` and `slack.py` with `@register_command()`. Symmetry is enforced by CI.
- **Auth guards**: Telegram handlers use `@_requires_auth`. Slack handlers call `self._is_allowed()` early.
- **Docker paths**: Always use `REPO_DIR` and `DB_PATH` from `src/config.py`.
- **System prompt file**: `SYSTEM_PROMPT_FILE` must NOT point inside `REPO_DIR` (enforced in `factory.py`).

## Testing

- **`pytest.ini`**: `asyncio_mode = auto` -- no `@pytest.mark.asyncio` needed on async tests.
- **`conftest.py`**: Autouse fixture strips real credentials so tests never hit live services.
- **Layout**: `tests/unit/` (pure logic), `tests/contract/` (backend interface compliance), `tests/integration/` (history DB, factory).
- **Fixtures**: Use `MagicMock(spec=SettingsSubclass)` with direct attribute setting. See `_make_settings()` / `_make_update()` patterns in test files.

## CI/CD (`.github/workflows/ci-cd.yml`)

Single pipeline: `version` -> `lint` + `test` (parallel) -> `docker-publish` + `security-scan` -> `release` -> `summary`. On `develop`: publishes `:develop` Docker tag. On `main`: version-bump check, publishes `:latest`, creates GitHub Release. Multi-platform builds (amd64 + arm64).
