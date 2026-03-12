"""Platform-agnostic helpers shared between Telegram and Slack bots."""
import asyncio
import time
from collections.abc import Awaitable, Callable

from src import history
from src.ai.adapter import AICLIBackend
from src.config import Settings


async def thinking_ticker(
    edit_fn: Callable[[str], Awaitable[None]],
    slow_threshold: int,
    update_interval: int,
    timeout_secs: int,
    warn_before_secs: int,
) -> None:
    """Background task: edits the 'Thinking…' placeholder with elapsed time.

    Sleeps for slow_threshold seconds first (quiet for fast responses).
    After that, edits every update_interval seconds.
    When timeout is set and remaining time <= warn_before_secs, adds a warning.
    Cancelled externally when the AI call completes or is timed out.
    """
    start = time.monotonic()
    await asyncio.sleep(slow_threshold)
    while True:
        elapsed = int(time.monotonic() - start)
        if timeout_secs > 0:
            remaining = timeout_secs - elapsed
            if remaining <= warn_before_secs:
                text = f"⏳ Still thinking… ({elapsed}s) — will cancel in {remaining}s"
            else:
                text = f"⏳ Still thinking… ({elapsed}s)"
        else:
            text = f"⏳ Still thinking… ({elapsed}s)"
        await edit_fn(text)
        await asyncio.sleep(update_interval)


async def build_prompt(
    text: str, chat_id: str, settings: Settings, backend: AICLIBackend
) -> str:
    """Build the AI prompt, injecting conversation history for stateless backends."""
    if backend.is_stateful:
        return text
    hist = (
        await history.get_history(chat_id) if settings.bot.history_enabled else []
    )
    return history.build_context(hist, text)


async def save_to_history(
    chat_id: str, user_msg: str, response: str, settings: Settings
) -> None:
    """Persist an exchange to conversation history (if enabled)."""
    if settings.bot.history_enabled:
        await history.add_exchange(chat_id, user_msg, response)


def is_allowed_slack(channel_id: str, user_id: str, settings: Settings) -> bool:
    """Auth check for Slack: optionally restrict by channel and/or user list."""
    cfg = settings.slack
    if cfg.slack_channel_id and channel_id != cfg.slack_channel_id:
        return False
    if cfg.allowed_users:
        return user_id in cfg.allowed_users
    return True
