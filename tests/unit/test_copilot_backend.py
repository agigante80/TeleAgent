"""Unit tests for src/ai/copilot.py — CopilotBackend."""
from unittest.mock import AsyncMock, MagicMock, patch


def _make_backend():
    with patch("src.ai.session.CopilotSession") as MockSession:
        from src.ai.copilot import CopilotBackend
        backend = CopilotBackend()
        backend._session = MagicMock()
        return backend


class TestCopilotBackend:
    async def test_send_delegates_to_session(self):
        """send() delegates to CopilotSession.send() (line 20)."""
        from src.ai.copilot import CopilotBackend
        with patch("src.ai.copilot.CopilotSession") as MockSession:
            backend = CopilotBackend()
            mock_session = MagicMock()
            mock_session.send = AsyncMock(return_value="hello world")
            backend._session = mock_session

            result = await backend.send("test prompt")

        assert result == "hello world"
        mock_session.send.assert_awaited_once_with("test prompt")

    def test_close_delegates_to_session(self):
        """close() calls session.close() (line 27)."""
        from src.ai.copilot import CopilotBackend
        with patch("src.ai.copilot.CopilotSession") as MockSession:
            backend = CopilotBackend()
            mock_session = MagicMock()
            backend._session = mock_session

            backend.close()

        mock_session.close.assert_called_once()
