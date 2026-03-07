# Test Coverage Gaps

> Status: **Ongoing** | Priority: Medium

CI enforces `--cov-fail-under=70`; current total is **86%** (236 tests). Remaining gaps:

## `bot.py`
- `build_app()` handler registration block
- Streaming error paths
- `cmd_info` uptime branches

## `main.py`
- Clone failure path
- SIGTERM teardown
- `asyncio.run` exception branch

## `ai/session.py`
- `TimeoutError` branch
- stdout drain inside stats-marker
- `_strip_stats` tail buffer

## `ai/direct.py`
- Provider-specific streaming branches
- Stream generator exception handling

## Approach
Each gap should have a dedicated test in the appropriate `tests/unit/` file. Use `MagicMock` and `AsyncMock` to avoid real network/subprocess calls.
