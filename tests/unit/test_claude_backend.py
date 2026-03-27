"""
Tests for ClaudeBackend (src/ai/claude.py).
All subprocess I/O is fully mocked — no real claude process is spawned.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.claude import ClaudeBackend, TIMEOUT
from src.executor import _SECRET_ENV_KEYS


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
        b = ClaudeBackend(api_key="k", model="claude-sonnet-4-6", opts="--debug")
        assert b._api_key == "k"
        assert b._model == "claude-sonnet-4-6"
        assert b._opts == "--debug"

    def test_not_stateful(self):
        assert ClaudeBackend(api_key="k").is_stateful is False


# ── _make_cmd ─────────────────────────────────────────────────────────────────

class TestMakeCmd:
    def test_default_cmd_has_skip_permissions_flag(self):
        b = ClaudeBackend(api_key="k")
        cmd, _ = b._make_cmd("hello")
        assert "--dangerously-skip-permissions" in cmd

    def test_default_cmd_has_output_format_text(self):
        """Explicit text output prevents JSON/ANSI UI decorations in captured response."""
        b = ClaudeBackend(api_key="k")
        cmd, _ = b._make_cmd("hello")
        assert "--output-format" in cmd
        idx = cmd.index("--output-format")
        assert cmd[idx + 1] == "text"

    def test_prompt_in_cmd(self):
        b = ClaudeBackend(api_key="k")
        cmd, _ = b._make_cmd("my prompt")
        assert "-p" in cmd
        assert "my prompt" in cmd

    def test_env_contains_api_key_when_provided(self):
        b = ClaudeBackend(api_key="sk-ant-test")
        _, env = b._make_cmd("hello")
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-test"

    def test_env_omits_api_key_when_empty(self):
        """OAuth mode: ANTHROPIC_API_KEY must NOT appear in subprocess env."""
        b = ClaudeBackend(api_key="")
        _, env = b._make_cmd("hello")
        assert "ANTHROPIC_API_KEY" not in env

    def test_env_does_not_contain_other_secrets(self):
        """scrubbed_env() must have stripped other AgentGate secrets from the env."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-secret", "SLACK_BOT_TOKEN": "xoxb-secret"}):
            b = ClaudeBackend(api_key="sk-ant-test")
            _, env = b._make_cmd("hello")
        assert "OPENAI_API_KEY" not in env
        assert "SLACK_BOT_TOKEN" not in env

    def test_model_flag_added_when_set(self):
        b = ClaudeBackend(api_key="k", model="claude-sonnet-4-6")
        cmd, _ = b._make_cmd("hi")
        assert "--model" in cmd
        assert "claude-sonnet-4-6" in cmd

    def test_model_flag_absent_when_empty(self):
        b = ClaudeBackend(api_key="k")
        cmd, _ = b._make_cmd("hi")
        assert "--model" not in cmd

    def test_custom_opts_appended(self):
        b = ClaudeBackend(api_key="k", opts="--max-turns 5")
        cmd, _ = b._make_cmd("hi")
        assert "--dangerously-skip-permissions" in cmd
        assert "--max-turns" in cmd
        assert "5" in cmd

    def test_custom_opts_parsed_with_shlex(self):
        b = ClaudeBackend(api_key="k", opts="--max-turns 10 --verbose")
        cmd, _ = b._make_cmd("hi")
        assert "--max-turns" in cmd
        assert "--verbose" in cmd

    def test_github_token_reinjected(self):
        with patch.dict(os.environ, {"GITHUB_REPO_TOKEN": "ghp_test123"}):
            b = ClaudeBackend(api_key="k")
            _, env = b._make_cmd("hello")
        assert env["GH_TOKEN"] == "ghp_test123"
        assert env["GITHUB_TOKEN"] == "ghp_test123"


# ── send() ─────────────────────────────────────────────────────────────────────

class TestSend:
    async def test_send_success(self):
        b = ClaudeBackend(api_key="k")
        proc = _make_proc(stdout=b"Hello from Claude")
        with patch.object(b, "_spawn", return_value=proc):
            result = await b.send("hello")
        assert result == "Hello from Claude"

    async def test_send_error(self):
        b = ClaudeBackend(api_key="k")
        proc = _make_proc(stdout=b"", stderr=b"auth error", returncode=1)
        with patch.object(b, "_spawn", return_value=proc):
            result = await b.send("hello")
        assert "⚠️" in result
        assert "auth error" in result

    async def test_send_timeout(self):
        b = ClaudeBackend(api_key="k")
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
        b = ClaudeBackend(api_key="k")
        proc = _make_proc(stdout=b"line1\nline2\n")
        with patch.object(b, "_spawn", return_value=proc):
            chunks = [c async for c in b.stream("hello")]
        assert "".join(chunks).strip() == "line1\nline2"

    async def test_stream_error_appended(self):
        b = ClaudeBackend(api_key="k")
        proc = _make_proc(stdout=b"partial", stderr=b"stream error", returncode=1)
        with patch.object(b, "_spawn", return_value=proc):
            chunks = [c async for c in b.stream("hello")]
        full = "".join(chunks)
        assert "⚠️" in full
        assert "stream error" in full


# ── clear_history ──────────────────────────────────────────────────────────────

class TestClearHistory:
    def test_clear_history_does_not_raise(self):
        b = ClaudeBackend(api_key="k")
        b.clear_history()  # no-op inherited from AICLIBackend — must not raise
