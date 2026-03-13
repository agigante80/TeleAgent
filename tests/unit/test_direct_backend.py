"""Unit tests for ai/direct.py — DirectAPIBackend."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.ai.direct import DirectAPIBackend


def _make_backend(provider="openai", api_key="sk-test", model="gpt-4o"):
    return DirectAPIBackend(provider=provider, api_key=api_key, model=model)


class TestSend:
    async def test_openai_send_returns_content(self):
        backend = _make_backend("openai")
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Hello!"
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        backend._openai_client = mock_client

        result = await backend.send("Hi")

        assert result == "Hello!"
        assert backend._messages[-1] == {"role": "assistant", "content": "Hello!"}

    async def test_anthropic_send_returns_content(self):
        backend = _make_backend("anthropic", model="claude-3-5-sonnet-20241022")
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Anthropic reply")]
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        backend._anthropic_client = mock_client

        result = await backend.send("Hello")

        assert result == "Anthropic reply"

    async def test_unknown_provider_raises(self):
        backend = _make_backend("unknown")
        with pytest.raises(ValueError, match="Unknown AI_PROVIDER"):
            await backend.send("hi")

    async def test_ollama_uses_openai_client(self):
        backend = _make_backend("ollama", model="llama3")
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Ollama response"
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        backend._openai_client = mock_client

        result = await backend.send("test")
        assert result == "Ollama response"

    async def test_messages_accumulate_across_calls(self):
        backend = _make_backend("openai")
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "reply"
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        backend._openai_client = mock_client

        await backend.send("first")
        await backend.send("second")

        roles = [m["role"] for m in backend._messages]
        assert roles == ["user", "assistant", "user", "assistant"]


class TestClearHistory:
    def test_clear_history_resets_messages(self):
        backend = _make_backend()
        backend._messages = [{"role": "user", "content": "test"}]
        backend.clear_history()
        assert backend._messages == []

    def test_is_stateful_flag(self):
        assert DirectAPIBackend.is_stateful is True


class TestStream:
    async def test_openai_stream_yields_chunks(self):
        backend = _make_backend("openai")

        async def fake_stream():
            for chunk in ["Hello", " world"]:
                event = MagicMock()
                event.choices = [MagicMock()]
                event.choices[0].delta.content = chunk
                yield event

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=fake_stream())
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client = MagicMock()
        mock_client.chat.completions.stream = MagicMock(return_value=mock_ctx)
        backend._openai_client = mock_client

        chunks = []
        async for chunk in backend.stream("test"):
            chunks.append(chunk)

        assert chunks == ["Hello", " world"]
        assert backend._messages[-1]["content"] == "Hello world"


class TestSystemPrompt:
    def test_system_prompt_stored(self):
        backend = DirectAPIBackend(provider="openai", api_key="sk-test", model="gpt-4o", system_prompt="You are a helpful assistant.")
        assert backend._system_prompt == "You are a helpful assistant."

    def test_no_system_prompt_by_default(self):
        backend = _make_backend()
        assert backend._system_prompt == ""

    def test_build_messages_prepends_system(self):
        backend = DirectAPIBackend(provider="openai", api_key="sk-test", model="gpt-4o", system_prompt="You are a security expert.")
        backend._messages = [{"role": "user", "content": "hello"}]
        msgs = backend._build_messages()
        assert msgs[0] == {"role": "system", "content": "You are a security expert."}
        assert msgs[1] == {"role": "user", "content": "hello"}

    def test_build_messages_without_system_prompt(self):
        backend = _make_backend()
        backend._messages = [{"role": "user", "content": "hello"}]
        msgs = backend._build_messages()
        assert msgs == [{"role": "user", "content": "hello"}]

    async def test_openai_send_includes_system_message(self):
        backend = DirectAPIBackend(provider="openai", api_key="sk-test", model="gpt-4o", system_prompt="Be concise.")
        backend._messages = [{"role": "user", "content": "test"}]
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "short reply"
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        backend._openai_client = mock_client

        await backend._openai_send()

        call_kwargs = mock_client.chat.completions.create.call_args
        messages_sent = call_kwargs.kwargs["messages"]
        assert messages_sent[0]["role"] == "system"
        assert messages_sent[0]["content"] == "Be concise."

    async def test_anthropic_send_includes_system_param(self):
        backend = DirectAPIBackend(provider="anthropic", api_key="sk-test", model="claude-3-5-sonnet-20241022", system_prompt="Be helpful.")
        backend._messages = [{"role": "user", "content": "test"}]
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="reply")]
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        backend._anthropic_client = mock_client

        await backend._anthropic_send()

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs.get("system") == "Be helpful."

    async def test_anthropic_send_no_system_param_when_empty(self):
        backend = _make_backend("anthropic")
        backend._messages = [{"role": "user", "content": "test"}]
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="reply")]
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        backend._anthropic_client = mock_client

        await backend._anthropic_send()

        call_kwargs = mock_client.messages.create.call_args
        assert "system" not in call_kwargs.kwargs


# ── Client lazy-init ──────────────────────────────────────────────────────────

class TestClientLazyInit:
    def test_openai_client_created_on_first_call(self):
        """_get_openai_client() lazily imports and creates AsyncOpenAI."""
        backend = _make_backend("openai", api_key="sk-test")
        mock_client = MagicMock()
        with patch("src.ai.direct.AsyncOpenAI", return_value=mock_client, create=True):
            # Temporarily remove cached client so the branch runs
            backend._openai_client = None
            from openai import AsyncOpenAI  # noqa: ensure module available
            with patch("src.ai.direct.DirectAPIBackend._get_openai_client") as _:
                pass  # just ensure the import path works
        # Direct path: patch openai inside the method
        backend._openai_client = None
        fake_openai_class = MagicMock(return_value=mock_client)
        import sys
        import types
        fake_mod = types.ModuleType("openai")
        fake_mod.AsyncOpenAI = fake_openai_class
        original = sys.modules.get("openai")
        sys.modules["openai"] = fake_mod
        try:
            result = backend._get_openai_client()
        finally:
            if original is not None:
                sys.modules["openai"] = original
            else:
                del sys.modules["openai"]
        assert result is mock_client
        fake_openai_class.assert_called_once_with(api_key="sk-test")

    def test_anthropic_client_created_on_first_call(self):
        """_get_anthropic_client() lazily imports and creates AsyncAnthropic."""
        backend = _make_backend("anthropic", api_key="sk-ant-test")
        backend._anthropic_client = None
        mock_client = MagicMock()
        fake_anthropic_class = MagicMock(return_value=mock_client)
        import sys
        import types
        fake_mod = types.ModuleType("anthropic")
        fake_mod.AsyncAnthropic = fake_anthropic_class
        original = sys.modules.get("anthropic")
        sys.modules["anthropic"] = fake_mod
        try:
            result = backend._get_anthropic_client()
        finally:
            if original is not None:
                sys.modules["anthropic"] = original
            else:
                del sys.modules["anthropic"]
        assert result is mock_client
        fake_anthropic_class.assert_called_once_with(api_key="sk-ant-test")

    def test_anthropic_client_cached_on_second_call(self):
        """_get_anthropic_client() returns the same instance on repeated calls."""
        backend = _make_backend("anthropic")
        first = MagicMock()
        backend._anthropic_client = first
        result = backend._get_anthropic_client()
        assert result is first


# ── Anthropic stream ──────────────────────────────────────────────────────────

class TestAnthropicStream:
    async def test_anthropic_stream_yields_chunks(self):
        """_anthropic_stream yields chunks from stream.text_stream."""
        backend = _make_backend("anthropic", model="claude-3-5-sonnet-20241022")
        backend._messages = [{"role": "user", "content": "hello"}]

        async def _fake_text_stream():
            for chunk in ["Hello", ", ", "world"]:
                yield chunk

        mock_stream = MagicMock()
        mock_stream.text_stream = _fake_text_stream()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.messages.stream = MagicMock(return_value=mock_ctx)
        backend._anthropic_client = mock_client

        chunks = []
        async for chunk in backend._anthropic_stream():
            chunks.append(chunk)

        assert chunks == ["Hello", ", ", "world"]


class TestOpenAIClientBaseUrl:
    def test_openai_client_includes_base_url_when_set(self):
        """_get_openai_client() passes base_url kwarg when base_url is non-empty (line 74)."""
        import sys
        import types
        backend = DirectAPIBackend(
            provider="openai", api_key="sk-test", model="gpt-4o",
            base_url="http://localhost:11434/v1"
        )
        backend._openai_client = None
        mock_client = MagicMock()
        fake_openai_class = MagicMock(return_value=mock_client)
        fake_mod = types.ModuleType("openai")
        fake_mod.AsyncOpenAI = fake_openai_class
        original = sys.modules.get("openai")
        sys.modules["openai"] = fake_mod
        try:
            result = backend._get_openai_client()
        finally:
            if original is not None:
                sys.modules["openai"] = original
            else:
                del sys.modules["openai"]
        call_kwargs = fake_openai_class.call_args[1]
        assert call_kwargs.get("base_url") == "http://localhost:11434/v1"


class TestAnthropicStreamWithSystemPrompt:
    async def test_anthropic_stream_sends_system_param_when_set(self):
        """_anthropic_stream includes system kwarg when system_prompt is set (line 127)."""
        backend = DirectAPIBackend(
            provider="anthropic", api_key="sk-ant", model="claude-3-5-sonnet-20241022",
            system_prompt="Be concise."
        )
        backend._messages = [{"role": "user", "content": "hello"}]

        async def _fake_text_stream():
            yield "response"

        mock_stream = MagicMock()
        mock_stream.text_stream = _fake_text_stream()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.messages.stream = MagicMock(return_value=mock_ctx)
        backend._anthropic_client = mock_client

        chunks = [c async for c in backend._anthropic_stream()]

        assert chunks == ["response"]
        call_kwargs = mock_client.messages.stream.call_args[1]
        assert call_kwargs.get("system") == "Be concise."
