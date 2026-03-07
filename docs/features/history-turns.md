# Context Window Control (`HISTORY_TURNS`)

> Status: **Planned** | Priority: Low

Cap how many past exchanges are injected for stateless AI backends.

## Usage

```
HISTORY_TURNS=5          # env var (default: 10)
/gate context 5          # adjust live without restart
/gate context            # show current value
```

## Design

- `HISTORY_TURNS` env var added to `BotConfig` (default `10`)
- `history.build_context()` accepts a `limit` parameter (already takes `limit` — just wire it)
- `/gate context <n>` stores override in-memory for the session; `/gate info` shows current value
- Useful for reducing token costs when using paid API backends

## Files to Change

- `src/config.py` — add `history_turns: int = 10` to `BotConfig`
- `src/history.py` — verify `build_context(limit=...)` is already respected
- `src/bot.py` — add `cmd_context` subcommand and in-memory override
- `src/platform/slack.py` — matching handler
