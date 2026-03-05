"""
Tests for CopilotSession (src/ai/session.py).
All pexpect I/O is fully mocked — no real process is spawned.
"""
from __future__ import annotations

import queue
import re
from unittest.mock import MagicMock, patch, PropertyMock

import pexpect
import pytest

from src.ai.session import CopilotSession, PROMPT_RE, _strip_ansi


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_child(before_text: str = "response text", expect_idx: int = 0) -> MagicMock:
    """Return a mock pexpect.spawn child that looks alive."""
    child = MagicMock(spec=pexpect.spawn)
    child.isalive.return_value = True
    child.before = before_text
    child.expect.return_value = expect_idx
    return child


# ── _strip_ansi ───────────────────────────────────────────────────────────────

def test_strip_ansi_removes_escape_sequences():
    assert _strip_ansi("\x1b[32mhello\x1b[0m") == "hello"


def test_strip_ansi_passthrough_plain_text():
    assert _strip_ansi("plain text") == "plain text"


# ── _spawn ────────────────────────────────────────────────────────────────────

class TestSpawn:
    def test_spawn_success_returns_child(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = _make_child(expect_idx=0)
        with patch("pexpect.spawn", return_value=child):
            session = CopilotSession()
            result = session._spawn()
        assert result is child

    def test_spawn_auth_failure_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = _make_child(expect_idx=1)
        with patch("pexpect.spawn", return_value=child):
            session = CopilotSession()
            with pytest.raises(RuntimeError, match="auth failed"):
                session._spawn()

    def test_spawn_timeout_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = _make_child(expect_idx=2)
        with patch("pexpect.spawn", return_value=child):
            session = CopilotSession()
            with pytest.raises(RuntimeError, match="auth failed"):
                session._spawn()

    def test_spawn_passes_model_arg(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = _make_child(expect_idx=0)
        with patch("pexpect.spawn", return_value=child) as mock_spawn:
            CopilotSession(model="gpt-4o")._spawn()
        args = mock_spawn.call_args
        assert "--model" in args[0][1]
        assert "gpt-4o" in args[0][1]


# ── _ensure ───────────────────────────────────────────────────────────────────

class TestEnsure:
    def test_spawns_when_no_child(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = _make_child(expect_idx=0)
        session = CopilotSession()
        with patch.object(session, "_spawn", return_value=child) as mock_spawn:
            result = session._ensure()
        assert result is child
        mock_spawn.assert_called_once()

    def test_reuses_alive_child(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = _make_child(expect_idx=0)
        session = CopilotSession()
        session._child = child
        with patch.object(session, "_spawn") as mock_spawn:
            result = session._ensure()
        assert result is child
        mock_spawn.assert_not_called()

    def test_respawns_dead_child(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        dead_child = _make_child()
        dead_child.isalive.return_value = False
        new_child = _make_child()
        session = CopilotSession()
        session._child = dead_child
        with patch.object(session, "_spawn", return_value=new_child):
            result = session._ensure()
        assert result is new_child


# ── _sync_send ────────────────────────────────────────────────────────────────

class TestSyncSend:
    def test_sends_and_returns_response(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = _make_child(before_text="  the answer  ")
        session = CopilotSession()
        with patch.object(session, "_ensure", return_value=child):
            result = session._sync_send("What is 2+2?")
        assert result == "the answer"
        child.sendline.assert_called_once_with("What is 2+2?")

    def test_timeout_resets_child_and_returns_warning(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = MagicMock()
        child.expect.side_effect = pexpect.TIMEOUT(30)
        session = CopilotSession()
        with patch.object(session, "_ensure", return_value=child):
            result = session._sync_send("prompt")
        assert "timed out" in result
        assert session._child is None

    def test_eof_resets_child_and_returns_warning(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = MagicMock()
        child.expect.side_effect = pexpect.EOF("eof")
        session = CopilotSession()
        with patch.object(session, "_ensure", return_value=child):
            result = session._sync_send("prompt")
        assert "ended" in result
        assert session._child is None

    def test_exception_resets_child_and_returns_warning(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = MagicMock()
        child.expect.side_effect = RuntimeError("boom")
        session = CopilotSession()
        with patch.object(session, "_ensure", return_value=child):
            result = session._sync_send("prompt")
        assert "error" in result.lower()
        assert session._child is None


# ── _sync_stream_to_queue ─────────────────────────────────────────────────────

class TestSyncStreamToQueue:
    def test_streams_chunks_and_sends_sentinel(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = MagicMock()
        # Simulate two chunks then a prompt terminator
        child.read_nonblocking.side_effect = [
            "hello ",
            "world\n> ",
            pexpect.TIMEOUT("t"),
        ]
        session = CopilotSession()
        q: queue.SimpleQueue = queue.SimpleQueue()
        with patch.object(session, "_ensure", return_value=child):
            session._sync_stream_to_queue("prompt", q)

        items = []
        while not q.empty():
            items.append(q.get_nowait())
        assert None in items  # sentinel present
        combined = "".join(i for i in items if i is not None)
        assert "hello" in combined or "world" in combined

    def test_eof_sends_sentinel(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.ai.session.REPO_DIR", tmp_path)
        child = MagicMock()
        child.read_nonblocking.side_effect = pexpect.EOF("eof")
        session = CopilotSession()
        q: queue.SimpleQueue = queue.SimpleQueue()
        with patch.object(session, "_ensure", return_value=child):
            session._sync_stream_to_queue("prompt", q)
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        assert None in items


# ── close ─────────────────────────────────────────────────────────────────────

class TestClose:
    def test_close_kills_alive_child(self):
        child = MagicMock()
        child.isalive.return_value = True
        session = CopilotSession()
        session._child = child
        session.close()
        child.sendline.assert_called_once_with("/exit")
        child.close.assert_called_once()
        assert session._child is None

    def test_close_noop_when_no_child(self):
        session = CopilotSession()
        session.close()  # must not raise
        assert session._child is None
