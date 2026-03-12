"""
Tests for thinking_ticker() in src/platform/common.py.
Uses patched asyncio.sleep to avoid real waiting.

_clock is passed directly to thinking_ticker (injectable parameter) so tests
don't need to patch any module-level names at all.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.platform.common import thinking_ticker


def _make_sleep_counter(cancel_after: int):
    """Return a fake asyncio.sleep that raises CancelledError after N calls."""
    call_count = [0]

    async def fake_sleep(secs):
        call_count[0] += 1
        if call_count[0] > cancel_after:
            raise asyncio.CancelledError

    return fake_sleep


def _make_clock(*monotonic_values):
    """Return a callable that steps through monotonic_values, repeating the last."""
    values_iter = iter(monotonic_values)

    def clock():
        try:
            return next(values_iter)
        except StopIteration:
            return monotonic_values[-1]

    return clock


async def _run_ticker(edit_fn, slow_threshold, update_interval, timeout_secs,
                      warn_before_secs, cancel_after_sleeps, monotonic_values):
    fake_sleep = _make_sleep_counter(cancel_after_sleeps)
    clock = _make_clock(*monotonic_values)
    with patch("src.platform.common.asyncio.sleep", side_effect=fake_sleep):
        task = asyncio.create_task(
            thinking_ticker(edit_fn, slow_threshold, update_interval,
                            timeout_secs, warn_before_secs, _clock=clock)
        )
        try:
            await task
        except asyncio.CancelledError:
            pass


async def test_ticker_fires_after_threshold():
    """edit_fn is called exactly once after the threshold sleep."""
    edit_fn = AsyncMock()
    # Flow with cancel_after=1:
    #   sleep(threshold)[call 1] → edit → sleep(update)[call 2 > 1 → cancel]
    await _run_ticker(edit_fn, slow_threshold=15, update_interval=30,
                      timeout_secs=360, warn_before_secs=60,
                      cancel_after_sleeps=1,
                      monotonic_values=[0.0, 20.0])
    assert edit_fn.call_count == 1


async def test_ticker_cancelled_before_threshold_yields_zero_edits():
    """Cancellation on the first (threshold) sleep → edit_fn never called."""
    edit_fn = AsyncMock()
    # cancel_after=0: first sleep immediately raises CancelledError
    await _run_ticker(edit_fn, slow_threshold=15, update_interval=30,
                      timeout_secs=360, warn_before_secs=60,
                      cancel_after_sleeps=0,
                      monotonic_values=[0.0])
    edit_fn.assert_not_called()


async def test_ticker_updates_at_interval():
    """After threshold, edit_fn is called once per update_interval sleep."""
    edit_fn = AsyncMock()
    # cancel_after=3: sleep(threshold)[1] → edit → sleep[2] → edit → sleep[3] → edit
    #                → sleep[4 > 3 → cancel]  → 3 edits
    await _run_ticker(edit_fn, slow_threshold=15, update_interval=30,
                      timeout_secs=360, warn_before_secs=60,
                      cancel_after_sleeps=3,
                      monotonic_values=[0.0, 30.0, 60.0, 90.0])
    assert edit_fn.call_count == 3


async def test_ticker_sends_warning_near_timeout():
    """Warning text appears when remaining time <= warn_before_secs."""
    edit_fn = AsyncMock()
    # elapsed=310s, timeout=360s, remaining=50s ≤ 60s → warning expected
    await _run_ticker(edit_fn, slow_threshold=0, update_interval=30,
                      timeout_secs=360, warn_before_secs=60,
                      cancel_after_sleeps=1,
                      monotonic_values=[0.0, 310.0])
    assert edit_fn.call_count >= 1
    last_text = edit_fn.call_args_list[-1][0][0]
    assert "will cancel in" in last_text


async def test_ticker_no_warning_when_timeout_zero():
    """When timeout_secs=0, warning text never appears."""
    edit_fn = AsyncMock()
    await _run_ticker(edit_fn, slow_threshold=0, update_interval=30,
                      timeout_secs=0, warn_before_secs=60,
                      cancel_after_sleeps=1,
                      monotonic_values=[0.0, 9999.0])
    assert edit_fn.call_count >= 1
    for c in edit_fn.call_args_list:
        assert "will cancel in" not in c[0][0]


async def test_ticker_zero_threshold_fires_immediately():
    """When slow_threshold=0, edit_fn fires right after the zero-second sleep."""
    edit_fn = AsyncMock()
    await _run_ticker(edit_fn, slow_threshold=0, update_interval=30,
                      timeout_secs=0, warn_before_secs=60,
                      cancel_after_sleeps=1,
                      monotonic_values=[0.0, 0.0])
    assert edit_fn.call_count == 1
