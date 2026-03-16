# Gemini CLI Backend

> Status: **Planned** | Priority: Medium | Last reviewed: 2026-03-11

Add `AI_CLI=gemini` as a first-class backend, backed by Google's official
[Gemini CLI](https://github.com/google-gemini/gemini-cli) (`@google/gemini-cli`).
This enables AgentGate to use Gemini 2.5 Pro (and future Gemini models) via a
dedicated Google AI Studio API key, with no OpenAI/Anthropic dependency.

---

## ⚠️ Prerequisite Questions

> Answer these before writing a single line of code. A wrong assumption costs 10× more to fix than a clarification takes.

1. **Scope** — Both platforms. `GeminiBackend` is called identically by both `src/bot.py` (Telegram) and `src/platform/slack.py` (Slack). No platform-specific changes are required beyond registering the backend in `factory.py`.
2. **Backend** — New `gemini` backend only. No changes to existing `copilot`, `codex`, or `api` backend behaviour.
3. **Stateful vs stateless** — **Stateless** (`is_stateful = False`). Mirrors `CopilotBackend`: each call spawns a fresh `gemini --non-interactive -p "prompt"` subprocess. History is injected via `build_prompt()` in `platform/common.py`.
4. **Breaking change?** — No. `AI_CLI` defaults to `copilot`; adding `gemini` as a valid value is purely additive. Existing deployments are unaffected.
5. **New dependency?** — Yes, but npm-only. `@google/gemini-cli` must be installed globally in the Docker image (`npm install -g @google/gemini-cli`). Node.js is already present in the container. No new Python pip package.
6. **Persistence** — No new DB table or file. History is handled by the existing SQLite history layer.
7. **Auth** — New: `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) env var is required. No interactive browser auth is supported in headless/Docker mode.
8. **Interactive auth guard** — The Gemini CLI will hang indefinitely if invoked without `--non-interactive` and no API key is set. **Always use `--non-interactive`**. Validate that `GEMINI_API_KEY` is non-empty in `_validate_config()` when `AI_CLI=gemini`.

---

## Background

Google released the **Gemini CLI** in June 2025 (Apache 2.0, open source).

Key facts relevant to AgentGate:

| Property | Value |
|----------|-------|
| Install | `npm install -g @google/gemini-cli` |
| Binary | `gemini` |
| Non-interactive invocation | `gemini --non-interactive -p "prompt"` |
| Auth (API key) | `GEMINI_API_KEY` or `GOOGLE_API_KEY` env var |
| Auth (OAuth, free tier) | Interactive browser login — **not suitable for Docker/headless** |
| Free-tier quota | Gemini 2.5 Pro · 60 req/min · 1 000 req/day (personal Google account) |
| Paid quota | Higher limits via API key from [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| Context window | 1 million tokens |
| Exit codes | 0 = success · 1 = general error · 42 = invalid input · 53 = turn limit exceeded |
| ANSI stripping | Automatic when stdout is not a TTY (i.e. piped — always the case in subprocess mode) |
| License | Apache 2.0 |
| GitHub | https://github.com/google-gemini/gemini-cli |
| Docs | https://google-gemini.github.io/gemini-cli/ |

The CLI supports both interactive REPL mode and a non-interactive single-prompt
mode. AgentGate uses the non-interactive mode, mirroring how `CopilotBackend`
and `CodexBackend` work today.

### Critical flag clarification

The Gemini CLI has **two distinct flags** that are often confused:

| Flag | Purpose | Required for AgentGate? |
|------|---------|------------------------|
| `--non-interactive` | Disables interactive prompts (auth dialogs, confirmations). Enables headless/scripted use. | ✅ **Yes — always** |
| `--yolo` | Auto-approves Gemini's **built-in tool calls** (web search, shell exec, file writes). Separate from interactive mode. | ⚠️ Optional — only if tool use is enabled |

**Do not conflate them.** A subprocess run with only `--yolo` will still hang waiting for auth input if no API key is set. Always use `--non-interactive` for headless execution.

---

## Usage (env vars)

```env
AI_CLI=gemini
GEMINI_API_KEY=AIza...          # from https://aistudio.google.com/app/apikey
AI_MODEL=gemini-2.5-pro         # optional — omit to use CLI default
AI_CLI_OPTS=                    # optional verbatim extra flags passed to gemini
```

`GOOGLE_API_KEY` is accepted as an alternative to `GEMINI_API_KEY` by the CLI
itself, but `GEMINI_API_KEY` is preferred for clarity in AgentGate `.env` files.

> ⚠️ **API key required for Docker.** The free personal-account flow requires a
> browser for first-time OAuth. Use an API key from Google AI Studio for all
> container deployments.

No other config changes are needed. All existing `BotConfig`, `VoiceConfig`, and
platform settings remain unchanged.

---

## Behaviour

- **Stateless** (`is_stateful = False`) — same pattern as `CopilotBackend`.
  AgentGate injects the last 10 history exchanges via `build_prompt()` (called
  by `forward_to_ai` in `bot.py` / `slack.py`) before each call.
- **Streaming** — stdout is read line-by-line and yielded to the Telegram/Slack
  streaming handler. Throttled by `STREAM_THROTTLE_SECS` as usual.
- **ANSI codes** — automatically stripped by the Gemini CLI when stdout is a pipe
  (which is always the case in `asyncio.create_subprocess_exec`). No manual
  stripping needed in AgentGate code.
- **Model selection** — if `AI_MODEL` is set, pass it via `--model <value>`.
  The shorthand is `-m`. If unset, the CLI uses its own default.
- **Extra opts** — `AI_CLI_OPTS` is split with `shlex` and appended after the
  mandatory safety flags (`--non-interactive --no-tools`), exactly as an additive
  extension. The safety flags cannot be removed via `AI_CLI_OPTS`. To enable
  Gemini's built-in tool use deliberately, set `AI_CLI_OPTS=--yolo`.
- **Timeout** — `send()` applies a 180s hard timeout (same as `CopilotSession`)
  to prevent the process hanging if the API is unavailable.
- **Tool use / MCP** — `--no-tools` is included in the default safety flags
  alongside `--non-interactive`. Gemini's built-in tools (web search, shell
  execution, file writes) bypass AgentGate's `SHELL_ALLOWLIST`, `is_destructive()`,
  confirmation dialogs, and audit logging entirely — they must be disabled by
  default. If an operator deliberately wants tool use, they can set
  `AI_CLI_OPTS=--yolo` (auto-approves tool calls); `--non-interactive` and
  `--no-tools` remain prepended and cannot be overridden via `AI_CLI_OPTS`.
- **Working directory** — `SubprocessMixin._spawn()` runs in `REPO_DIR` (`/repo`),
  so Gemini can access project files via the `@filename` syntax.
- **`clear_history()`** — no-op (inherited from `AICLIBackend` base class).
  The backend is stateless; history is injected into each prompt by the bot layer.

---

## Current Behaviour (as of v0.7.x)

| Layer | Location | Current behaviour |
|-------|----------|-------------------|
| Backend factory | `src/ai/factory.py` | `ai_cli` accepts `"copilot"`, `"codex"`, `"api"` only; raises `ValueError` for any other value |
| `AIConfig` | `src/config.py` (`AIConfig`) | `ai_cli: Literal["copilot", "codex", "api"] = "copilot"` — `"gemini"` is not a valid value |
| Dockerfile | `Dockerfile` | Node.js is installed; `@github/copilot-cli` and `@openai/codex` are added; `@google/gemini-cli` is absent |

> **Key gap**: `AI_CLI=gemini` currently raises a validation error at startup. No Gemini-flavoured subprocess backend exists. All three current backends (copilot, codex, api) are fully implemented and stable — this feature adds a fourth without modifying any existing path.

---

## Architecture Notes

> **Read before touching code.** These are non-obvious constraints specific to this feature.

- **`is_stateful = False`** — `GeminiBackend` must be stateless, mirroring `CopilotBackend`. History context is injected by `build_prompt()` in `platform/common.py`; the backend never manages its own history.
- **`SubprocessMixin`** — use `SubprocessMixin` from `src/ai/adapter.py` to run the subprocess in `REPO_DIR`. Study `CopilotBackend` as the reference implementation.
- **`--non-interactive` and `--no-tools` are mandatory safety flags** — always prepend both; `AI_CLI_OPTS` is additive (not replacing). Without `--non-interactive` the CLI hangs on auth dialogs in Docker. Without `--no-tools`, Gemini's built-in shell/file/web tools bypass `SHELL_ALLOWLIST`, `is_destructive()`, confirmation dialogs, and audit logging entirely.
- **Exit code handling** — exit code 0 = success; 1 = general error; 42 = invalid input; 53 = turn limit exceeded. Map non-zero codes to user-facing error messages (don't silently return empty output).
- **API key validation** — when `AI_CLI=gemini`, `GEMINI_API_KEY` must be non-empty. Add a check in `_validate_config()` in `src/main.py` — same pattern as the Telegram/Slack token checks.
- **Timeout interaction** — if the AI response feedback feature (`docs/features/ai-response-feedback.md`) is implemented first, the platform-layer timeout replaces the internal 180s timeout. Coordinate: do not add a new internal `asyncio.wait_for()` inside `GeminiBackend` if the platform already wraps it.
- **`REPO_DIR` and `DB_PATH`** — import from `src/config.py`; never hardcode paths.
- **`asyncio_mode = auto`** — all `async def test_*` functions run without `@pytest.mark.asyncio`.

---

## Architecture

### New file: `src/ai/gemini.py`

```python
"""
Gemini CLI backend — non-interactive subprocess mode.
Each query spawns `gemini --non-interactive -p <prompt>` as a subprocess.
History is injected by the bot layer via build_prompt() (stateless pattern).
"""
import asyncio
import logging
import shlex
from collections.abc import AsyncGenerator

from src.ai.adapter import AICLIBackend, SubprocessMixin
from src.executor import scrubbed_env
from src.registry import backend_registry

logger = logging.getLogger(__name__)

TIMEOUT = 180  # seconds — same as CopilotSession


@backend_registry.register("gemini")
class GeminiBackend(SubprocessMixin, AICLIBackend):
    """Stateless backend using Google's official Gemini CLI."""

    is_stateful = False

    def __init__(self, api_key: str, model: str = "", opts: str = "") -> None:
        self._api_key = api_key
        self._model = model
        self._opts = opts

    def _make_cmd(self, prompt: str) -> tuple[list[str], dict]:
        env = {**scrubbed_env(), "GEMINI_API_KEY": self._api_key}
        # Always prepend safety flags — never allow AI_CLI_OPTS to override them.
        # --non-interactive: prevents auth dialogs and interactive prompts in headless mode.
        # --no-tools: disables Gemini's built-in shell exec, file writes, and web search, which
        #   would otherwise bypass AgentGate's SHELL_ALLOWLIST, is_destructive() checks,
        #   confirmation dialogs, and audit logging entirely.
        safety_flags = ["--non-interactive", "--no-tools"]
        extra = safety_flags + (shlex.split(self._opts) if self._opts else [])
        cmd = ["gemini", "-p", prompt] + extra
        if self._model:
            cmd += ["--model", self._model]
        return cmd, env

    async def send(self, prompt: str) -> str:
        cmd, env = self._make_cmd(prompt)
        try:
            proc = await self._spawn(cmd, env)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
        except asyncio.TimeoutError:
            try:
                proc.kill()  # type: ignore[possibly-undefined]
                await proc.wait()  # reap zombie — prevent defunct gemini processes
            except Exception:
                pass
            return f"⚠️ Gemini timed out after {TIMEOUT}s."
        except Exception as exc:
            logger.exception("Gemini subprocess error")
            return f"⚠️ Gemini error: {exc}"
        if proc.returncode not in (0, None):
            err = stderr.decode().strip() or stdout.decode().strip()
            rc = proc.returncode
            suffix = {42: " (invalid input)", 53: " (turn limit exceeded)"}.get(rc, "")
            logger.error("gemini CLI error (rc=%d%s): %s", rc, suffix, err)
            return f"⚠️ Gemini error (rc={rc}{suffix}):\n{err}"
        return stdout.decode().strip()

    async def stream(self, prompt: str) -> AsyncGenerator[str, None]:
        cmd, env = self._make_cmd(prompt)
        try:
            proc = await self._spawn(cmd, env)
        except Exception as exc:
            logger.exception("Gemini stream error")
            yield f"⚠️ Gemini error: {exc}"
            return
        assert proc.stdout
        try:
            async for line in proc.stdout:
                yield line.decode()
        except Exception as exc:
            logger.exception("Gemini stream read error")
            yield f"\n⚠️ Gemini stream error: {exc}"
            return
        finally:
            await proc.wait()
        if proc.returncode not in (0, None):
            assert proc.stderr
            err = (await proc.stderr.read()).decode().strip()
            rc = proc.returncode
            suffix = {42: " (invalid input)", 53: " (turn limit exceeded)"}.get(rc, "")
            if err:
                logger.error("gemini CLI stream error (rc=%d%s): %s", rc, suffix, err)
                yield f"\n⚠️ Gemini error (rc={rc}{suffix}):\n{err}"
```

---

## Files to Create / Change

| File | Change | Notes |
|------|--------|-------|
| `src/ai/gemini.py` | **New** — `GeminiBackend` class (see above) | ~75 lines |
| `src/ai/factory.py` | Add `gemini` branch + `_load_backends()` entry | ~10 lines |
| `src/config.py` | Extend `AIConfig`: `ai_cli` Literal + `gemini_api_key` field + `secret_values()` | 4 lines |
| `src/executor.py` | Add `GEMINI_API_KEY`, `GOOGLE_API_KEY` to `_SECRET_ENV_KEYS` | 2 lines |
| `src/redact.py` | Add Google API key regex (`AIza...`) to `_SECRET_PATTERNS` | 1 line |
| `Dockerfile` | Add `npm install -g @google/gemini-cli` (Node.js **already present**) | 1 line |
| `README.md` | Add `gemini` to `AI_CLI` row; add `GEMINI_API_KEY` row (×2 — Telegram + Slack sections) | ~4 lines |
| `tests/unit/test_gemini_backend.py` | **New** — unit tests (see below) | ~80 lines |
| `tests/contract/test_backends_contract.py` | Add `GeminiBackend` to `ALL_BACKENDS` | ~5 lines |
| `tests/integration/test_factory.py` | Add factory test for `AI_CLI=gemini` | ~10 lines |

---

## Step-by-Step Implementation

### Step 1 — `src/config.py`

In `AIConfig`, make two changes:

```python
# Before:
ai_cli: Literal["copilot", "codex", "api"] = "copilot"

# After:
ai_cli: Literal["copilot", "codex", "api", "gemini"] = "copilot"
```

Add after the existing `ai_cli_opts` field:

```python
gemini_api_key: str = ""   # GEMINI_API_KEY — falls back to AI_API_KEY if empty
```

The `gemini_api_key` field reads from `GEMINI_API_KEY` (Pydantic auto-maps field
name to env var in uppercase). The factory falls back to `ai_api_key` (`AI_API_KEY`)
so users who already have a generic key set don't need a duplicate.

Also update `AIConfig.secret_values()` to include the new key so `SecretRedactor`
scrubs it from all outgoing text (AI responses, error messages, shell output):

```python
# Before:
def secret_values(self) -> list[str]:
    return [v for v in [self.ai_api_key, self.codex.codex_api_key] if v]

# After:
def secret_values(self) -> list[str]:
    return [v for v in [
        self.ai_api_key,
        self.codex.codex_api_key,
        self.gemini_api_key,   # ← add — prevents GEMINI_API_KEY leaking in logs/responses
    ] if v]
```

> ⚠️ **Critical**: if `gemini_api_key` is not in `secret_values()`, the key will
> pass through `SecretRedactor` unredacted in every AI response and error message.
> This is not protected by the pattern-based `_SECRET_PATTERNS` alone (which only
> covers the `AIza...` regex — see Step 2b below).

### Step 2b — `src/executor.py` and `src/redact.py` (secret protection)

#### `src/executor.py` — extend `_SECRET_ENV_KEYS`

Add `GEMINI_API_KEY` and `GOOGLE_API_KEY` to the denylist so `scrubbed_env()`
strips them before passing environment to any subprocess. Without this, any
subprocess spawned by AgentGate (shell commands, executor runs) can read these
keys from the environment even though `GeminiBackend._make_cmd()` only re-injects
`GEMINI_API_KEY` for its own subprocess.

```python
# Before:
_SECRET_ENV_KEYS: frozenset[str] = frozenset({
    "TG_BOT_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "GITHUB_REPO_TOKEN",
    "AI_API_KEY",
    "CODEX_API_KEY",
    "WHISPER_API_KEY",
    "OPENAI_API_KEY",
})

# After — add both Google key names (CLI accepts either):
_SECRET_ENV_KEYS: frozenset[str] = frozenset({
    "TG_BOT_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "GITHUB_REPO_TOKEN",
    "AI_API_KEY",
    "CODEX_API_KEY",
    "WHISPER_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",   # ← add (F2)
    "GOOGLE_API_KEY",   # ← add (F6) — Gemini CLI also accepts this alternative name
})
```

#### `src/redact.py` — extend `_SECRET_PATTERNS`

Add a pattern for Google AI Studio API keys (prefix `AIza`, 39 characters total)
so that any key that appears in AI output or error messages is pattern-matched and
redacted even if it was not captured in `secret_values()`:

```python
# Add to _SECRET_PATTERNS list (after the Anthropic key line):
re.compile(r"AIza[0-9A-Za-z_\-]{35}"),  # Google API key (AI Studio / GCP)
```

> ℹ️ Google API keys always start with `AIza` followed by exactly 35 alphanumeric,
> underscore, or hyphen characters (39 chars total). This pattern is stable across
> all current Google API key types including AI Studio keys.

### Step 3 — `src/ai/gemini.py`

Create the file with the implementation shown in the Architecture section above.

### Step 4 — `src/ai/factory.py`

Two changes are required:

**1. Add the `gemini` branch** before the final `raise ValueError`:

```python
    if ai.ai_cli == "gemini":
        from src.ai.gemini import GeminiBackend
        return GeminiBackend(
            api_key=ai.gemini_api_key or ai.ai_api_key,
            model=ai.ai_model,
            opts=ai.ai_cli_opts,
        )
```

**2. Add `src.ai.gemini` to `_load_backends()`** so the registry decorator fires:

```python
# Before:
def _load_backends() -> None:
    _module_file_exists("src.ai.copilot") and __import__("src.ai.copilot")
    _module_file_exists("src.ai.codex") and __import__("src.ai.codex")
    _module_file_exists("src.ai.direct") and __import__("src.ai.direct")

# After:
def _load_backends() -> None:
    _module_file_exists("src.ai.copilot") and __import__("src.ai.copilot")
    _module_file_exists("src.ai.codex") and __import__("src.ai.codex")
    _module_file_exists("src.ai.direct") and __import__("src.ai.direct")
    _module_file_exists("src.ai.gemini") and __import__("src.ai.gemini")   # ← add
```

Without this, the `@backend_registry.register("gemini")` decorator in `gemini.py`
never fires and `backend_registry.create("gemini", ...)` raises `KeyError`.

### Step 5 — `Dockerfile`

Node.js is **already installed** in the base image via the NodeSource block. Only
add the Gemini CLI global install, alongside the existing Copilot and Codex lines:

```dockerfile
# Before (existing lines):
# GitHub Copilot CLI — pinned version (update via Dependabot)
RUN npm install -g @github/copilot@1.0.5

# OpenAI Codex CLI — pinned version (update via Dependabot)
RUN npm install -g @openai/codex@0.111.0

# After — add:
# Google Gemini CLI — pinned version (update via Dependabot)
RUN npm install -g @google/gemini-cli@<latest-version>
```

> ⚠️ **Pin the version.** Find the latest version with `npm show @google/gemini-cli
> version` and hardcode it. Dependabot will keep it updated (it already tracks npm
> packages for this project via `docs/features/npm-dependabot.md`).

> ℹ️ **No Docker size impact.** Node.js is already ~200 MB in the image for Copilot
> and Codex CLIs. Adding `@google/gemini-cli` adds only ~50–100 MB (the npm
> package itself). The optional build-arg approach is unnecessary here.

### Step 6 — `README.md`

Two tables must be updated (Telegram section ≈ line 158, Slack section ≈ line 447):

**`AI_CLI` row** — extend the allowed values:
```markdown
# Before:
| `AI_CLI` | `copilot` | `copilot` \| `codex` \| `api` |

# After:
| `AI_CLI` | `copilot` | `copilot` \| `codex` \| `api` \| `gemini` |
```

**Add `GEMINI_API_KEY` row** — insert after the `COPILOT_GITHUB_TOKEN` row:
```markdown
| `GEMINI_API_KEY` | — | API key for the `gemini` backend (from [AI Studio](https://aistudio.google.com/app/apikey)). Falls back to `AI_API_KEY` if unset. |
```

**Update `AI_CLI_OPTS` description** — add the Gemini default:
```markdown
# Before:
... (Copilot: `--allow-all`; Codex: `--approval-mode full-auto`) ...

# After:
... (Copilot: `--allow-all`; Codex: `--approval-mode full-auto`; Gemini: `--non-interactive`) ...
```

### Step 7 — Tests

#### `tests/unit/test_gemini_backend.py` (new file)

```python
"""
Tests for GeminiBackend (src/ai/gemini.py).
All subprocess I/O is fully mocked — no real gemini process is spawned.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.gemini import GeminiBackend, TIMEOUT


# ── Helpers ────────────────────────────────────────────────────────────────────

class _AsyncIter:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


def _make_proc(stdout: bytes = b"output", stderr: bytes = b"", returncode: int = 0) -> AsyncMock:
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.stderr.read = AsyncMock(return_value=stderr)
    proc.wait = AsyncMock()
    lines = stdout.splitlines(keepends=True)
    proc.stdout.__aiter__ = MagicMock(return_value=_AsyncIter(lines))
    return proc


# ── Construction ───────────────────────────────────────────────────────────────

class TestConstruction:
    def test_stores_fields(self):
        b = GeminiBackend(api_key="k", model="gemini-2.5-pro", opts="--debug")
        assert b._api_key == "k"
        assert b._model == "gemini-2.5-pro"
        assert b._opts == "--debug"

    def test_not_stateful(self):
        assert GeminiBackend(api_key="k").is_stateful is False


# ── _make_cmd ─────────────────────────────────────────────────────────────────

class TestMakeCmd:
    def test_default_cmd_has_non_interactive(self):
        b = GeminiBackend(api_key="k")
        cmd, _ = b._make_cmd("hello")
        assert "--non-interactive" in cmd

    def test_default_cmd_has_no_tools(self):
        b = GeminiBackend(api_key="k")
        cmd, _ = b._make_cmd("hello")
        assert "--no-tools" in cmd

    def test_prompt_in_cmd(self):
        b = GeminiBackend(api_key="k")
        cmd, _ = b._make_cmd("my prompt")
        assert "-p" in cmd
        assert "my prompt" in cmd

    def test_env_does_not_contain_other_secrets(self):
        """scrubbed_env() must have stripped other AgentGate secrets from the env."""
        import os
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-secret", "SLACK_BOT_TOKEN": "xoxb-secret"}):
            b = GeminiBackend(api_key="AIzaXYZ")
            _, env = b._make_cmd("hello")
        assert "OPENAI_API_KEY" not in env
        assert "SLACK_BOT_TOKEN" not in env

    def test_env_contains_api_key(self):
        b = GeminiBackend(api_key="AIzaXYZ")
        _, env = b._make_cmd("hello")
        assert env["GEMINI_API_KEY"] == "AIzaXYZ"

    def test_model_flag_added_when_set(self):
        b = GeminiBackend(api_key="k", model="gemini-2.5-pro")
        cmd, _ = b._make_cmd("hi")
        assert "--model" in cmd
        assert "gemini-2.5-pro" in cmd

    def test_model_flag_absent_when_empty(self):
        b = GeminiBackend(api_key="k")
        cmd, _ = b._make_cmd("hi")
        assert "--model" not in cmd

    def test_custom_opts_appended_after_safety_flags(self):
        """Safety flags are always prepended; custom opts are additive, not replacing."""
        b = GeminiBackend(api_key="k", opts="--yolo")
        cmd, _ = b._make_cmd("hi")
        assert "--non-interactive" in cmd  # always present
        assert "--no-tools" in cmd          # always present
        assert "--yolo" in cmd              # user opts appended

    def test_custom_opts_parsed_with_shlex(self):
        b = GeminiBackend(api_key="k", opts="--debug --sandbox")
        cmd, _ = b._make_cmd("hi")
        assert "--debug" in cmd
        assert "--sandbox" in cmd
        assert "--non-interactive" in cmd  # still present — safety flag not replaced
        assert "--no-tools" in cmd          # still present — safety flag not replaced


# ── send() ─────────────────────────────────────────────────────────────────────

class TestSend:
    async def test_send_success(self):
        b = GeminiBackend(api_key="k")
        proc = _make_proc(stdout=b"Hello from Gemini")
        with patch.object(b, "_spawn", return_value=proc):
            result = await b.send("hello")
        assert result == "Hello from Gemini"

    async def test_send_error_rc1(self):
        b = GeminiBackend(api_key="k")
        proc = _make_proc(stdout=b"", stderr=b"auth error", returncode=1)
        with patch.object(b, "_spawn", return_value=proc):
            result = await b.send("hello")
        assert "⚠️" in result
        assert "auth error" in result

    async def test_send_error_rc42_invalid_input(self):
        b = GeminiBackend(api_key="k")
        proc = _make_proc(stdout=b"", stderr=b"bad prompt", returncode=42)
        with patch.object(b, "_spawn", return_value=proc):
            result = await b.send("hello")
        assert "invalid input" in result

    async def test_send_error_rc53_turn_limit(self):
        b = GeminiBackend(api_key="k")
        proc = _make_proc(stdout=b"", stderr=b"rate limit", returncode=53)
        with patch.object(b, "_spawn", return_value=proc):
            result = await b.send("hello")
        assert "turn limit" in result

    async def test_send_timeout(self):
        b = GeminiBackend(api_key="k")
        proc = AsyncMock()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        proc.kill = AsyncMock()
        with patch.object(b, "_spawn", return_value=proc):
            result = await b.send("hello")
        assert f"{TIMEOUT}s" in result
        assert "⚠️" in result


# ── stream() ───────────────────────────────────────────────────────────────────

class TestStream:
    async def test_stream_yields_lines(self):
        b = GeminiBackend(api_key="k")
        proc = _make_proc(stdout=b"line1\nline2\n")
        with patch.object(b, "_spawn", return_value=proc):
            chunks = [c async for c in b.stream("hello")]
        assert "".join(chunks).strip() == "line1\nline2"

    async def test_stream_error_appended(self):
        b = GeminiBackend(api_key="k")
        proc = _make_proc(stdout=b"partial", stderr=b"stream error", returncode=1)
        with patch.object(b, "_spawn", return_value=proc):
            chunks = [c async for c in b.stream("hello")]
        full = "".join(chunks)
        assert "⚠️" in full
        assert "stream error" in full


# ── clear_history ──────────────────────────────────────────────────────────────

class TestClearHistory:
    def test_clear_history_does_not_raise(self):
        b = GeminiBackend(api_key="k")
        b.clear_history()  # no-op inherited from AICLIBackend — must not raise
```

#### `tests/contract/test_backends_contract.py` — additions

Add to the imports and `ALL_BACKENDS` list:

```python
# Add to imports:
from src.ai.gemini import GeminiBackend

# Add make_ helper:
def make_gemini():
    return GeminiBackend(api_key="test-key", model="gemini-2.5-pro")

# Add to ALL_BACKENDS:
ALL_BACKENDS = [
    pytest.param(make_copilot, id="copilot"),
    pytest.param(make_codex, id="codex"),
    pytest.param(make_direct, id="direct"),
    pytest.param(make_gemini, id="gemini"),  # ← ADD THIS
]

# Add to TestAdapterContract:
def test_gemini_is_not_stateful(self):
    assert make_gemini().is_stateful is False
```

#### `tests/integration/test_factory.py` — addition

```python
def test_creates_gemini_backend(self, monkeypatch):
    monkeypatch.setenv("AI_CLI", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTest")
    cfg = AIConfig()
    backend = create_backend(cfg)
    assert isinstance(backend, GeminiBackend)
    assert backend._api_key == "AIzaTest"

def test_gemini_falls_back_to_ai_api_key(self, monkeypatch):
    monkeypatch.setenv("AI_CLI", "gemini")
    monkeypatch.setenv("AI_API_KEY", "fallback-key")
    # GEMINI_API_KEY not set
    cfg = AIConfig()
    backend = create_backend(cfg)
    assert backend._api_key == "fallback-key"

def test_gemini_model_passed_through(self, monkeypatch):
    monkeypatch.setenv("AI_CLI", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("AI_MODEL", "gemini-2.0-flash")
    cfg = AIConfig()
    backend = create_backend(cfg)
    assert backend._model == "gemini-2.0-flash"
```

---

## Open Questions / Risks

| # | Question | Status | Notes |
|---|----------|--------|-------|
| 1 | **`--non-interactive` flag stability** | ✅ Confirmed | Documented in official headless.md. Stable across versions. Use alongside `-p`. |
| 2 | **`--yolo` flag** | ⚠️ Optional | Auto-approves built-in tool calls (web search, shell). Separate from non-interactive mode. Only needed if Gemini tool use is desired; keep disabled by default. |
| 3 | **ANSI codes in output** | ✅ Non-issue | CLI auto-strips ANSI when stdout is not a TTY. `asyncio.create_subprocess_exec` always pipes stdout. |
| 4 | **Streaming is buffered or progressive?** | 🔍 Verify at impl | Test whether `gemini -p "…" --non-interactive` streams progressively or buffers. If buffered, only `send()` is meaningful; `stream()` can delegate to `send()`. |
| 5 | **Built-in tool calls interfere with executor?** | ✅ Resolved — disabled by default | `--no-tools` is prepended as a mandatory safety flag. Gemini's built-in tools (web search, shell exec, file writes) would bypass `SHELL_ALLOWLIST`, `is_destructive()`, confirmation dialogs, and audit logging. Operators who want tool use must set `AI_CLI_OPTS=--yolo` explicitly. |
| 6 | **Trailing footer?** | 🔍 Verify at impl | Copilot CLI appends `Total usage est: …` which `CopilotSession` strips. Check whether Gemini CLI appends similar metadata and strip if needed. |
| 7 | **Turn limit (rc=53)** | ✅ Documented | Exit code 53 = turn limit exceeded. Handled in `send()` and `stream()` with labelled error messages. |
| 8 | **`GOOGLE_API_KEY` vs `GEMINI_API_KEY`** | ✅ Clarified | Both accepted by the CLI. AgentGate uses `GEMINI_API_KEY` field (reads `GEMINI_API_KEY` env var) for clarity; `GOOGLE_API_KEY` works as a silent fallback if the CLI prefers it. |

---

## Pros and Cons vs. Existing Backends

| | `AI_CLI=gemini` | `AI_CLI=copilot` | `AI_CLI=codex` | `AI_CLI=api` (OpenAI) |
|-|-----------------|-------------------|----------------|----------------------|
| **Free tier** | ✅ 1 000 req/day (personal account) | ✅ GitHub Copilot subscription | ❌ Pay-per-token | ❌ Pay-per-token |
| **Paid tier** | ✅ API key from AI Studio | — | OpenAI billing | OpenAI / Anthropic billing |
| **Model** | Gemini 2.5 Pro (1M ctx) | GPT-4o / Claude (varies) | o3/o4 | Any OpenAI/Anthropic |
| **Context window** | 1M tokens | ~128K tokens | ~200K (o3) | Up to 200K |
| **Stateful/Stateless** | Stateless (history injected) | Stateless | Stateless | Stateful (native) |
| **Docker image impact** | ✅ Node.js already installed | ⚠️ Needs `gh` CLI + auth | ✅ Node.js already installed | ✅ Pure Python |
| **Streaming** | ✅ (verify progressiveness) | ✅ | ✅ | ✅ |
| **Privacy** | Data sent to Google | Data sent to GitHub/OpenAI | Data sent to OpenAI | Data sent to provider |
| **Offline** | ❌ | ❌ | ❌ | ❌ (unless Ollama) |
| **Built-in tools** | ⚠️ Web search, shell (disable recommended) | ✅ Code-focused tools | ✅ Code-focused | ❌ (none via CLI) |

---

## Dependencies

| Package | Status | Notes |
|---------|--------|-------|
| `@google/gemini-cli` | ❌ New (npm global) | Add `RUN npm install -g @google/gemini-cli@<version>` to `Dockerfile`. Pin to a specific version to avoid surprise breakage. |
| `subprocess`, `asyncio`, `shlex`, `os` | ✅ stdlib | Already used by `copilot.py` and `codex.py`. |
| No new pip packages | ✅ Pure Python | `GeminiBackend` uses only existing stdlib and project modules. |

> **Rule**: Node.js is already installed in the Docker image (required for Copilot and Codex CLIs). Adding `@google/gemini-cli` does not change the base image or Python deps — it is one additional `npm install -g` line in the `Dockerfile`.

---

## Test Plan

The detailed test implementations are embedded in the Architecture section (`tests/unit/test_gemini_backend.py`, `tests/contract/test_backends_contract.py`, `tests/integration/test_factory.py`). Summary:

### `tests/unit/test_gemini_backend.py` (new file)

| Test | What it checks |
|------|----------------|
| `test_not_stateful` | `GeminiBackend.is_stateful == False` |
| `test_default_cmd_has_non_interactive` | `--non-interactive` always present in subprocess args |
| `test_default_cmd_has_no_tools` | `--no-tools` always present — Gemini's built-in tools disabled by default |
| `test_prompt_in_cmd` | Prompt passed as `-p <value>` |
| `test_env_does_not_contain_other_secrets` | `scrubbed_env()` strips other AgentGate secrets from subprocess env |
| `test_env_contains_api_key` | `GEMINI_API_KEY` is re-injected in subprocess env |
| `test_model_flag_added_when_set` | `--model <value>` added when `AI_MODEL` is non-empty |
| `test_model_flag_absent_when_empty` | No `--model` flag when `AI_MODEL` is empty |
| `test_custom_opts_appended_after_safety_flags` | Safety flags always prepended; opts are additive, not replacing |
| `test_custom_opts_parsed_with_shlex` | Custom opts parsed correctly; `--non-interactive` and `--no-tools` still present |
| `test_send_success` | Exit code 0 returns stdout as a string |
| `test_send_error_rc1` | Exit code 1 returns a user-facing error message |
| `test_send_error_rc42_invalid_input` | Exit code 42 returns "invalid input" message |
| `test_send_error_rc53_turn_limit` | Exit code 53 returns "turn limit exceeded" message |
| `test_send_timeout` | `asyncio.TimeoutError` returns timeout message; subprocess killed + waited |
| `test_stream_yields_lines` | `stream()` yields stdout lines progressively |
| `test_stream_error_appended` | Non-zero exit code appended to stream output |
| `test_clear_history_does_not_raise` | `clear_history()` is a no-op that does not raise |

### `tests/contract/test_backends_contract.py` additions

| Test | What it checks |
|------|----------------|
| `test_gemini_is_not_stateful` | `GeminiBackend` satisfies `AICLIBackend` contract with `is_stateful = False` |

### `tests/integration/test_factory.py` additions

| Test | What it checks |
|------|----------------|
| `test_creates_gemini_backend` | `create_backend()` with `AI_CLI=gemini` returns `GeminiBackend` instance |
| `test_gemini_falls_back_to_ai_api_key` | If `GEMINI_API_KEY` unset but `AI_API_KEY` set, backend uses the fallback |
| `test_gemini_model_passed_through` | `AI_MODEL` value reaches `GeminiBackend` constructor |

### Coverage note

Run `pytest tests/ --cov=src --cov-report=term-missing` after implementation. Target: 100% branch coverage on `GeminiBackend.send()` and `stream()`, including all non-zero exit code branches. The timeout branch requires a mock that stalls indefinitely.

---

## Documentation Updates

### `README.md`

1. **`AI_CLI` row** — extend the accepted values to include `gemini`:
   ```markdown
   | `AI_CLI` | `copilot` | AI backend to use. Options: `copilot`, `codex`, `api`, `gemini`. |
   ```
2. **New env var row** in the AI configuration table:
   ```markdown
   | `GEMINI_API_KEY` | `""` | API key for the Gemini CLI backend (`AI_CLI=gemini`). Get one from [aistudio.google.com](https://aistudio.google.com/app/apikey). |
   ```
3. **Features bullet list** — add:
   > 🤖 **Gemini CLI backend** — use Google Gemini 2.5 Pro (1M token context) via `AI_CLI=gemini`.

### `.github/copilot-instructions.md`

Add `GeminiBackend` to the backends description in the AI backend section:
> `gemini.py` — stateless `GeminiBackend` (`is_stateful = False`). Spawns `gemini --non-interactive -p <prompt>` per call. Requires `GEMINI_API_KEY`.

### `docker-compose.yml.example`

Add a commented-out Gemini block:
```yaml
# Gemini CLI backend (alternative to copilot)
# AI_CLI=gemini
# GEMINI_API_KEY=AIza...
# AI_MODEL=gemini-2.5-pro
```

### `docs/roadmap.md`

This feature is not currently listed. Add it to the Features table:
```markdown
| 2.10 | Gemini CLI backend — `AI_CLI=gemini` using Google Gemini 2.5 Pro | [→ features/gemini-cli-backend.md](features/gemini-cli-backend.md) |
```
After merge to `main`, mark it done (✅).

### `docs/features/gemini-cli-backend.md`

Change `Status: **Planned**` → `Status: **Implemented**` on merge to `main`. Add `Implemented in: v0.8.0`.

---

## Version Bump

Consult `docs/versioning.md` for the full decision guide. Quick reference:

| This feature… | Bump |
|---------------|------|
| Adds a new backend option (`AI_CLI=gemini`) with a safe default (existing default `copilot` unchanged) | **MINOR** |
| Adds `GEMINI_API_KEY` env var (no existing var renamed/removed) | **MINOR** |
| Modifies `Dockerfile` (one new `npm install` line) | **MINOR** |

**Expected bump for this feature**: `MINOR` → `0.8.0` (from current `0.7.3`)

> Bump `VERSION` on `develop` _before_ the merge PR to `main`. Never edit `VERSION` directly on `main`.

---

## Roadmap Update

When this feature is complete, update `docs/roadmap.md`:

```markdown
| 2.10 | ✅ Gemini CLI backend — `AI_CLI=gemini` using Google Gemini 2.5 Pro (1M token context) | [→ features/gemini-cli-backend.md](features/gemini-cli-backend.md) |
```

Potential stretch goal: streaming progressiveness verification (Open Questions item 4) — if Gemini CLI buffers output rather than streaming progressively, a `stream()`-via-`send()` fallback mode may be worth documenting.

---

## Acceptance Criteria

> The feature is **done** when ALL of the following are true.

- [ ] All implementation steps above are complete.
- [ ] `pytest tests/ -v --tb=short` passes with no failures or errors.
- [ ] `ruff check src/` reports no new linting issues.
- [ ] `README.md` is updated: `AI_CLI` values include `gemini`; `GEMINI_API_KEY` row added.
- [ ] `docker-compose.yml.example` has the commented Gemini block.
- [ ] `.github/copilot-instructions.md` updated with `GeminiBackend` description.
- [ ] `docs/roadmap.md` entry added and marked done (✅).
- [ ] `docs/features/gemini-cli-backend.md` status changed to `Implemented` on merge to `main`.
- [ ] `VERSION` file bumped to `0.8.0` on `develop` before merge to `main`.
- [ ] `AI_CLI=gemini` end-to-end: a message reaches the Gemini CLI subprocess and the response is returned to the user in both Telegram and Slack.
- [ ] `--non-interactive` and `--no-tools` are always included in the subprocess command (cannot be accidentally omitted by `AI_CLI_OPTS`).
- [ ] `GEMINI_API_KEY` missing triggers a clear error at startup (not a silent hang).
- [ ] All non-zero exit codes (1, 42, 53) return user-facing error messages (not empty strings or tracebacks).
- [ ] Subprocess is killed *and waited* on timeout (no zombie `gemini` processes).
- [ ] `GEMINI_API_KEY` is in `AIConfig.secret_values()` — verified by checking `SecretRedactor` scrubs it from output.
- [ ] `GEMINI_API_KEY` and `GOOGLE_API_KEY` are in `_SECRET_ENV_KEYS` — verified by checking `scrubbed_env()` strips them.
- [ ] Google API key regex (`AIza[0-9A-Za-z_-]{35}`) is in `_SECRET_PATTERNS` in `redact.py`.
- [ ] `GeminiBackend._make_cmd()` uses `scrubbed_env()` (not `os.environ`) — verified by the `test_env_does_not_contain_other_secrets` test.
- [ ] `@backend_registry.register("gemini")` decorator present on `GeminiBackend`; `src.ai.gemini` listed in `_load_backends()`.
- [ ] Existing backends (`copilot`, `codex`, `api`) are unaffected — no regression.
- [ ] Contract test (`test_backends_contract.py`) passes with `GeminiBackend` included.
- [ ] Edge cases in the Open Questions section above are resolved and either handled or documented.
- [ ] PR is merged to `develop` first; CI is green; then merged to `main`.

