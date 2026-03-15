"""Unit tests for CodexBackend — env isolation contract."""
import os
from unittest.mock import patch

from src.ai.codex import CodexBackend
from src.executor import _SECRET_ENV_KEYS


class TestCodexMakeCmd:
    """_make_cmd() must re-inject OPENAI_API_KEY and strip all other secret vars."""

    def test_openai_api_key_reinjected(self):
        backend = CodexBackend(api_key="sk-test-key-reinjected-1234567890ab")
        fake_env = {k: "should-be-stripped" for k in _SECRET_ENV_KEYS}
        with patch.dict(os.environ, fake_env, clear=False):
            _, env = backend._make_cmd("hello")
        assert env.get("OPENAI_API_KEY") == "sk-test-key-reinjected-1234567890ab"

    def test_other_secret_keys_stripped(self):
        backend = CodexBackend(api_key="sk-test-key-stripped-1234567890ab")
        other_secrets = {k: "should-be-gone" for k in _SECRET_ENV_KEYS if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, other_secrets, clear=False):
            _, env = backend._make_cmd("hello")
        for key in other_secrets:
            assert key not in env, f"{key} must be stripped from codex subprocess env"

    def test_non_secret_vars_preserved(self):
        backend = CodexBackend(api_key="sk-test-key-preserve-1234567890ab")
        with patch.dict(os.environ, {"NODE_PATH": "/usr/lib/node"}, clear=False):
            _, env = backend._make_cmd("hello")
        assert env.get("NODE_PATH") == "/usr/lib/node"
