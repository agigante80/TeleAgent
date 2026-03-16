"""
Tests for CodexBackend (src/ai/codex.py).
All subprocess I/O is fully mocked — no real codex process is spawned.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.codex import CodexBackend


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_proc(stdout: bytes = b"output", stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.stderr.read = AsyncMock(return_value=stderr)
    proc.wait = AsyncMock()
    # Make proc.stdout async-iterable yielding lines
    lines = stdout.splitlines(keepends=True)
    proc.stdout.__aiter__ = MagicMock(return_value=aiter_from_list(lines))
    return proc


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


def aiter_from_list(items):
    return _AsyncIter(items)


# ── Construction ──────────────────────────────────────────────────────────────

class TestConstruction:
    def test_stores_api_key_and_model(self):
        backend = CodexBackend(api_key="sk-test", model="o3")
        assert backend._api_key == "sk-test"
        assert backend._model == "o3"

    def test_default_model(self):
        backend = CodexBackend(api_key="sk-test")
        assert backend._model == "gpt-5.3-codex"

    def test_not_stateful(self):
        assert CodexBackend(api_key="k").is_stateful is False


# ── _make_cmd ─────────────────────────────────────────────────────────────────

class TestMakeCmd:
    def test_includes_prompt_and_model(self):
        backend = CodexBackend(api_key="sk-x", model="o4")
        cmd, env = backend._make_cmd("hello world")
        assert "codex" in cmd
        assert "hello world" in cmd
        assert "--model" in cmd
        assert "o4" in cmd

    def test_env_contains_api_key(self):
        backend = CodexBackend(api_key="sk-test")
        _, env = backend._make_cmd("prompt")
        assert env["OPENAI_API_KEY"] == "sk-test"

    def test_default_opts_uses_full_auto(self):
        backend = CodexBackend(api_key="sk-x")
        cmd, _ = backend._make_cmd("prompt")
        assert "--approval-mode" in cmd
        assert "full-auto" in cmd
        assert "auto" not in [c for c in cmd if c not in ("--approval-mode", "full-auto")]

    def test_custom_opts_replaces_full_auto(self):
        backend = CodexBackend(api_key="sk-x", opts="--approval-mode auto-edit")
        cmd, _ = backend._make_cmd("prompt")
        assert "auto-edit" in cmd
        assert "full-auto" not in cmd

    def test_custom_opts_passthrough(self):
        backend = CodexBackend(api_key="sk-x", opts="--search --add-dir /extra")
        cmd, _ = backend._make_cmd("prompt")
        assert "--search" in cmd
        assert "--add-dir" in cmd
        assert "/extra" in cmd
        assert "full-auto" not in cmd


# ── send ─────────────────────────────────────────────────────────────────────

class TestSend:
    async def test_returns_stdout_on_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.codex.REPO_DIR", tmp_path)
        proc = _make_proc(stdout=b"Hello from codex\n")
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            backend = CodexBackend(api_key="sk-x")
            result = await backend.send("hi")
        assert result == "Hello from codex"

    async def test_returns_error_on_non_zero_exit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.codex.REPO_DIR", tmp_path)
        proc = _make_proc(stdout=b"", stderr=b"rate limited", returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            backend = CodexBackend(api_key="sk-x")
            result = await backend.send("hi")
        assert "error" in result.lower() or "Codex" in result
        assert "rate limited" in result

    async def test_uses_stdout_as_error_when_stderr_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.codex.REPO_DIR", tmp_path)
        proc = _make_proc(stdout=b"some output", stderr=b"", returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            backend = CodexBackend(api_key="sk-x")
            result = await backend.send("hi")
        assert "some output" in result


# ── stream ────────────────────────────────────────────────────────────────────

class TestStream:
    async def test_yields_lines(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.codex.REPO_DIR", tmp_path)
        proc = _make_proc(stdout=b"line1\nline2\n", returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            backend = CodexBackend(api_key="sk-x")
            chunks = [c async for c in backend.stream("prompt")]
        assert any("line1" in c for c in chunks)
        assert any("line2" in c for c in chunks)

    async def test_appends_error_on_non_zero_exit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.codex.REPO_DIR", tmp_path)
        proc = _make_proc(stdout=b"partial\n", stderr=b"crash", returncode=2)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            backend = CodexBackend(api_key="sk-x")
            chunks = [c async for c in backend.stream("prompt")]
        full = "".join(chunks)
        assert "crash" in full or "error" in full.lower()
