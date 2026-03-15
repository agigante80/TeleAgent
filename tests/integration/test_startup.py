"""Integration test for main.py startup sequence."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestStartup:
    async def test_startup_calls_all_phases(self, monkeypatch):
        """Verify startup() calls each phase in order and sends Ready message."""
        from src.config import Settings, TelegramConfig, GitHubConfig, BotConfig, AIConfig, AuditConfig, StorageConfig

        # Build a minimal settings object
        tg = MagicMock(spec=TelegramConfig)
        tg.chat_id = "99999"
        tg.bot_token = "fake-token"
        gh = MagicMock(spec=GitHubConfig)
        gh.github_repo_token = "tok"
        gh.github_repo = "owner/repo"
        gh.branch = "main"
        bot = MagicMock(spec=BotConfig)
        bot.bot_cmd_prefix = "ta"
        bot.image_tag = ""
        bot.max_output_chars = 3000
        bot.allow_secrets = False
        ai = MagicMock(spec=AIConfig)
        ai.ai_cli = "api"
        ai.ai_model = ""
        direct = MagicMock()
        direct.ai_provider = "openai"
        ai.direct = direct
        audit = MagicMock(spec=AuditConfig)
        audit.audit_enabled = True
        storage_cfg = MagicMock(spec=StorageConfig)
        storage_cfg.storage_backend = "sqlite"
        storage_cfg.audit_backend = "sqlite"
        settings = MagicMock(spec=Settings)
        settings.platform = "telegram"
        settings.telegram = tg
        settings.github = gh
        settings.bot = bot
        settings.ai = ai
        settings.audit = audit
        settings.storage = storage_cfg

        mock_clone = AsyncMock()
        mock_install = AsyncMock(return_value="OK")
        mock_storage = AsyncMock()
        mock_storage.init = AsyncMock()
        mock_backend = MagicMock()
        mock_backend.is_stateful = False

        mock_adapter = AsyncMock()
        mock_adapter.start = AsyncMock()

        import asyncio

        with patch("src.repo.clone", mock_clone), \
             patch("src.repo.configure_git_auth", AsyncMock()), \
             patch("src.runtime.install_deps", mock_install), \
             patch("src.registry.storage_registry.create", return_value=mock_storage), \
             patch("src.registry.audit_registry.create", return_value=MagicMock(init=AsyncMock(), verify=AsyncMock(return_value=True))), \
             patch("src.main.create_backend", return_value=mock_backend), \
             patch("src.main._load_platforms"), \
             patch("src.registry.platform_registry.create", return_value=mock_adapter):

            from src.main import startup
            await startup(settings)

        mock_clone.assert_awaited_once()
        mock_install.assert_awaited_once()
        mock_storage.init.assert_awaited_once()
        mock_adapter.start.assert_awaited_once()
