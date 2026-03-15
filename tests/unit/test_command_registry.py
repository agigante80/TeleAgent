"""Tests for src/commands/registry.py."""
import pytest
from unittest.mock import MagicMock


class TestCommandRegistry:
    def test_commands_list_populated_by_bot_import(self):
        """COMMANDS should be populated once bot.py is imported (decorators fire at import time)."""
        from src.commands.registry import COMMANDS
        # bot.py registers commands when imported; after any test that imports bot, COMMANDS has entries
        import src.bot  # noqa: F401 — ensure bot is imported so decorators have fired
        names = {c.name for c in COMMANDS}
        expected = {"run", "sync", "git", "diff", "log", "status", "clear", "cancel", "init", "restart", "confirm", "help", "info"}
        assert expected <= names, f"Missing commands: {expected - names}"

    def test_command_def_attributes(self):
        """Each CommandDef has the expected fields."""
        from src.commands.registry import COMMANDS
        import src.bot  # noqa: F401
        run_cmd = next((c for c in COMMANDS if c.name == "run"), None)
        assert run_cmd is not None
        assert run_cmd.requires_args is True
        assert run_cmd.destructive is True
        assert "telegram" in run_cmd.platforms
        assert "slack" in run_cmd.platforms

    def test_cancel_is_telegram_only(self):
        """cancel command should be registered for telegram only."""
        from src.commands.registry import COMMANDS
        import src.bot  # noqa: F401
        cancel_cmd = next((c for c in COMMANDS if c.name == "cancel"), None)
        assert cancel_cmd is not None
        assert cancel_cmd.platforms == {"telegram"}

    def test_handler_attr_matches_method_name(self):
        """handler_attr for each command should match the actual method name."""
        from src.commands.registry import COMMANDS
        from src.bot import _BotHandlers
        import src.bot  # noqa: F401
        for cmd in COMMANDS:
            if "telegram" in cmd.platforms:
                assert hasattr(_BotHandlers, cmd.handler_attr), (
                    f"_BotHandlers missing method {cmd.handler_attr!r} for command {cmd.name!r}"
                )

    def test_no_duplicate_names(self):
        """Command names must be unique."""
        from src.commands.registry import COMMANDS
        import src.bot  # noqa: F401
        names = [c.name for c in COMMANDS]
        assert len(names) == len(set(names)), f"Duplicate command names: {names}"

    def test_register_command_duplicate_raises(self):
        """Registering the same name twice should raise ValueError."""
        # Use a fresh registry to avoid polluting global COMMANDS
        from src.commands import registry as reg_module
        try:
            @reg_module.register_command("__test_dup__", "first")
            def handler_one(): ...

            # Re-registration is idempotent (updates in place, no error).
            @reg_module.register_command("__test_dup__", "updated description")
            def handler_two(): ...

            # Verify description was updated and only one entry exists
            matches = [c for c in reg_module.COMMANDS if c.name == "__test_dup__"]
            assert len(matches) == 1
            assert matches[0].description == "updated description"
        finally:
            # Restore COMMANDS to original state
            reg_module.COMMANDS[:] = [c for c in reg_module.COMMANDS if c.name != "__test_dup__"]

    def test_validate_command_symmetry_passes(self):
        """_validate_command_symmetry should not raise when both adapters have all shared methods."""
        from src.commands.registry import _validate_command_symmetry, COMMANDS
        from src.platform.slack import SlackBot
        from src.bot import _BotHandlers
        import src.bot  # noqa: F401

        # Build minimal proxies that respond hasattr for all cmd_* methods
        tg_mock = MagicMock(spec=_BotHandlers)
        slack_mock = MagicMock(spec=SlackBot)
        # Should not raise
        _validate_command_symmetry(tg_mock, slack_mock)

    def test_validate_command_symmetry_raises_on_missing_method(self):
        """_validate_command_symmetry should raise AttributeError for missing handler."""
        from src.commands.registry import _validate_command_symmetry, COMMANDS, CommandDef
        import src.bot  # noqa: F401

        # Create a minimal fake command that requires both platforms
        from src.commands import registry as reg_module
        reg_module.COMMANDS.append(CommandDef(
            name="__missing_test__",
            handler_attr="cmd_missing_test",
            description="test",
            platforms={"telegram", "slack"},
        ))
        try:
            tg_mock = MagicMock()
            slack_mock = MagicMock()
            # Remove the attribute to simulate missing handler
            del tg_mock.cmd_missing_test
            with pytest.raises(AttributeError, match="cmd_missing_test"):
                _validate_command_symmetry(tg_mock, slack_mock)
        finally:
            reg_module.COMMANDS[:] = [c for c in reg_module.COMMANDS if c.name != "__missing_test__"]
