"""Shared command registry — single source of truth for all bot commands."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

COMMANDS: list["CommandDef"] = []


@dataclass
class CommandDef:
    name: str
    handler_attr: str
    description: str
    platforms: set[str] = field(default_factory=lambda: {"telegram", "slack"})
    requires_args: bool = False
    destructive: bool = False


def register_command(
    name: str,
    description: str,
    *,
    platforms: set[str] | None = None,
    requires_args: bool = False,
    destructive: bool = False,
) -> Callable:
    """Decorator — register a command handler in the global COMMANDS list."""
    def decorator(fn: Callable) -> Callable:
        existing_names = {c.name for c in COMMANDS}
        if name in existing_names:
            # Idempotent on module reload: update the existing entry in place.
            for cmd in COMMANDS:
                if cmd.name == name:
                    cmd.handler_attr = fn.__name__
                    cmd.description = description
                    cmd.platforms = platforms or {"telegram", "slack"}
                    cmd.requires_args = requires_args
                    cmd.destructive = destructive
                    break
            return fn
        COMMANDS.append(CommandDef(
            name=name,
            handler_attr=fn.__name__,
            description=description,
            platforms=platforms or {"telegram", "slack"},
            requires_args=requires_args,
            destructive=destructive,
        ))
        return fn
    return decorator


def _validate_command_symmetry(telegram_adapter, slack_adapter) -> None:
    """Raise AttributeError if a shared command is missing on either adapter."""
    both = [c for c in COMMANDS if "telegram" in c.platforms and "slack" in c.platforms]
    for cmd in both:
        if not hasattr(telegram_adapter, cmd.handler_attr):
            raise AttributeError(
                f"Command {cmd.name!r} is registered for telegram but "
                f"{type(telegram_adapter).__name__} has no method {cmd.handler_attr!r}"
            )
        if not hasattr(slack_adapter, cmd.handler_attr):
            raise AttributeError(
                f"Command {cmd.name!r} is registered for slack but "
                f"{type(slack_adapter).__name__} has no method {cmd.handler_attr!r}"
            )
