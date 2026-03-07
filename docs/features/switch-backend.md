# Hot-Swap AI Backend (`/gate switch`)

> Status: **Planned** | Priority: Medium

Switch the active AI backend at runtime without restarting the container.

## Usage

```
/gate switch copilot
/gate switch codex
/gate switch api
```

## Design

`cmd_restart` already tears down and recreates the backend object. This extends it to accept a target backend name and temporarily override `AI_CLI` for the session.

- State stored in memory only — reverts to `AI_CLI` env var on container restart
- Visible in `/gate info` output ("AI: codex (overridden, default: copilot)")
- History is NOT cleared on switch — useful for continuity with stateless backends

## Files to Change

- `src/bot.py` — add `cmd_switch` subcommand
- `src/platform/slack.py` — add matching handler
- `src/ai/factory.py` — accept explicit `ai_cli` parameter override
