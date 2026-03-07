# Copilot Conversation Pre-Warming

> Status: **Planned** | Priority: Low

Reduce repeated context-setup overhead for long Copilot sessions.

## Problem

`copilot -p` is stateless per call; each message starts fresh. When using the stateless history-injection approach, the AI re-reads repo context from scratch on every turn.

## Proposed Approach

On startup, send a system prompt to the Copilot CLI session that includes:
- Current repo name and language
- Key file structure (`/gate git` output)
- Active branch and last commit

This pre-warms the context so subsequent prompts don't need to re-establish it.

## Design

- Add `COPILOT_PREWARM=true` env var (default: `false`)
- On backend start, `copilot.py` sends a synthetic "system" message before accepting user input
- Prompt template configurable via `COPILOT_PREWARM_PROMPT` env var

## Caveats

- Copilot PTY session is stateful (`is_stateful=True`) — pre-warming only applies to the stateless Direct API backend path, or requires session restart to reset
- May consume Copilot token quota if sessions are frequently restarted
