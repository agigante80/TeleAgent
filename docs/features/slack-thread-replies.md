# Slack: Thread Reply Mode (`SLACK_THREAD_REPLIES`)

> Status: **Planned** | Priority: **High** | Last reviewed: 2026-01-01

All bot responses currently go to the channel root level. In multi-agent conversations,
this quickly becomes noisy and hard to follow. This feature introduces an opt-in thread
reply mode: when enabled, the bot always replies inside a thread anchored to the message
that triggered it.

---

## ⚠️ Prerequisite Questions

1. **Scope** — Slack-only. Telegram threads work differently and are out of scope.
2. **Backend** — All AI backends (`copilot`, `codex`, `api`). The change is in the Slack
   delivery layer, not the AI backend.
3. **Stateful vs stateless** — Not relevant. Thread context (`thread_ts`) is plumbed at
   the delivery layer.
4. **Breaking change?** — No. Default is `false` (opt-in). Existing deployments are unaffected.
   **MINOR** bump.
5. **New dependency?** — No. `thread_ts` is a standard Slack API field supported by `slack-bolt`.
6. **Persistence** — No new DB table. `thread_ts` is extracted from the triggering event
   and passed through the request lifecycle.
7. **Auth** — No new secrets. `chat:write` (already required) covers threaded posts.
8. **Prefix command replies** — Should prefix commands (e.g. `dev git`) also reply in thread?
   Proposed: yes, when `SLACK_THREAD_REPLIES=true`, all bot output goes into the thread.

---

## Problem Statement

1. **Channel noise.** In a multi-agent deployment, each user message triggers up to three bot
   responses plus potential delegation messages, all posted at channel root. A busy team channel
   becomes unreadable very quickly.

2. **Lost context.** Without threads, there is no visual grouping between a user's question
   and the agents' responses. Readers have to scroll and correlate manually.

3. **No opt-in grouping.** Teams that want clean channel history have no way to configure
   bots to stay inside threads. All responses currently go to root.

---

## Current Behaviour (as of v0.9.x)

| Layer | Location | Current behaviour |
|-------|----------|-------------------|
| `_send()` helper | `src/platform/slack.py:106` | Calls `say(text)` — always posts to channel root |
| `_stream_to_slack()` | `src/platform/slack.py:120` | `say(_THINKING)` — posts thinking placeholder to channel root |
| `_run_ai_pipeline()` | `src/platform/slack.py:201` | `say(_THINKING)` for non-streaming — channel root |
| Prefix commands | `src/platform/slack.py:various` | All `say()` calls go to channel root |
| `_on_message()` | `src/platform/slack.py:250` | Extracts `channel` and `text`, but not `thread_ts` |
| Config | `src/config.py` (`SlackConfig`) | No `slack_thread_replies` field |

> **Key gap**: The triggering event's `thread_ts` (or `ts` as root anchor) is never extracted
> and never passed to any delivery call. Every `say()` call defaults to channel root.

---

## Design Space

### Axis 1 — When to use thread replies

#### Option A — Always thread *(opt-out config)*

Thread replies are always on unless `SLACK_THREAD_REPLIES=false`.

**Pros:**
- Cleanest default for multi-agent setups.

**Cons:**
- Breaking change for existing single-agent deployments where users expect channel-root responses.
- Channel-root responses are the Slack norm for many bots.

---

#### Option B — Never thread *(status quo)*

Thread replies are always off.

**Cons:**
- Multi-agent conversations remain noisy.

---

#### Option C — Opt-in via env var *(recommended)*

`SLACK_THREAD_REPLIES=true` (default `false`). Existing deployments are unaffected.

```python
# In SlackConfig:
slack_thread_replies: bool = Field(False, env="SLACK_THREAD_REPLIES")
```

**Pros:**
- Non-breaking: default preserves current behaviour.
- Per-agent control (each bot has its own `.env` file).

**Cons:**
- Must set per-agent — cannot be set globally across all bots at once.

**Recommendation: Option C** — opt-in is the only safe default for an existing deployment.

---

### Axis 2 — Which `thread_ts` to use for replies

When a user posts in a channel (not a thread), their message has a `ts` and no `thread_ts`.
When a user posts inside an existing thread, their message has both `ts` (the reply's own ts)
and `thread_ts` (the root message's ts).

#### Option A — Always use the triggering message's `ts` as root

Every bot response starts its own thread. If the user replies in a thread, the bot creates
a new nested sub-thread.

**Pros:**
- Simple: always one value to track.

**Cons:**
- If the user is already in a thread, the bot creates a new sub-thread instead of continuing.
- Confusing for multi-turn thread conversations.

---

#### Option B — Use `thread_ts` if present, else `ts` *(recommended)*

```python
# From the Slack event:
thread_ts = event.get("thread_ts") or event.get("ts")
```

If the triggering message is already in a thread, continue that thread. Otherwise, start a new
thread anchored to the triggering message.

**Pros:**
- Natural: bot follows the existing thread if there is one.
- Multi-turn thread conversations work correctly.

**Cons:**
- Slightly more complex than always using `ts`, but the logic is one line.

**Recommendation: Option B** — this is the standard Slack threading pattern.

---

### Axis 3 — Thread scope for prefix commands and delegation messages

#### Option A — Thread replies only for AI responses

Prefix commands (`dev git`, `dev run`, etc.) still reply to channel root.

**Cons:**
- Inconsistent UX: AI responses are in thread, command output is at root.

---

#### Option B — Thread replies for all bot output *(recommended)*

When `SLACK_THREAD_REPLIES=true`, ALL bot output — AI responses, prefix command output,
delegation messages, error messages — goes into the thread.

**Pros:**
- Consistent UX: everything stays in one thread.
- Delegation messages (see `slack-agent-delegation.md`) also go into thread, keeping context.

**Cons:**
- Command output in a thread is slightly less visible, but this is the intended trade-off.

**Recommendation: Option B** — consistent threading is the more useful behaviour.

---

## Recommended Solution

- **Axis 1**: Option C — opt-in via `SLACK_THREAD_REPLIES=true`
- **Axis 2**: Option B — use `thread_ts` if present, else `ts`
- **Axis 3**: Option B — all bot output goes into thread when enabled

**End-to-end flow:**

```
Channel root:
  User: "dev what does main.py do?"                         (ts=T1, no thread_ts)

Thread under T1 (if SLACK_THREAD_REPLIES=true):
  GateCode: ⏳ Thinking...                                  (thread_ts=T1)
  GateCode: ⏳ Still working on it...                       (edit of thinking msg)
  GateCode: "main.py is the entry point. It validates..."   (NEW message, thread_ts=T1)

  [delegation msg posted to thread:]
  "sec Please review main.py for security issues."           (thread_ts=T1)

Thread under T1:
  GateSec: ⏳ Thinking...                                    (thread_ts=T1)
  GateSec: "I found two issues: ..."                        (NEW message, thread_ts=T1)
```

All conversation stays inside the thread under T1. The channel root only has the original
user message, keeping the channel clean.

---

## Architecture Notes

- **`thread_ts` must be threaded through the entire call chain** — from `_on_message()` (where
  it is extracted) through `_run_ai_pipeline()`, `_stream_to_slack()`, `_send()`, `_edit()`,
  all prefix command handlers, and any delegation message posts. This is the main implementation
  complexity.
- **`say()` shorthand vs `client.chat_postMessage()`** — `say()` does not support `thread_ts`
  directly. Use `client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=...)` for
  threaded posts, or pass `thread_ts` as a keyword arg to `say()` if the bolt version supports it.
  Verify with `slack-bolt` docs; prefer `client.chat_postMessage` for explicit control.
- **Delegation messages** — posts from `_run_ai_pipeline()` after sentinel extraction (see
  `slack-agent-delegation.md`) must also use `thread_ts` when thread mode is enabled.
- **Platform symmetry** — thread replies are Slack-only; no change to `src/bot.py`.
- **`asyncio_mode = auto`** — tests remain `async def test_*` without decorator.
- **`REPO_DIR` and `DB_PATH`** — not involved in this feature.

---

## Config Variables

| Env var | Type | Default | Description |
|---------|------|---------|-------------|
| `SLACK_THREAD_REPLIES` | `bool` | `False` | When `true`, all bot output (AI responses, command output, delegation messages) is posted as a thread reply to the triggering message. |

> **Naming convention**: `SLACK_` prefix. Default `False` is the safe opt-in value — existing
> deployments are unaffected.

---

## Implementation Steps

### Step 1 — `src/config.py`: add config field

```python
# In SlackConfig:
slack_thread_replies: bool = Field(False, env="SLACK_THREAD_REPLIES")
```

---

### Step 2 — `src/platform/slack.py`: extract `thread_ts` in `_on_message()`

```python
async def _on_message(self, event: dict, say, client) -> None:
    channel = event.get("channel", "")
    user = event.get("user", "")
    text = (event.get("text") or "").strip()
    bot_id = event.get("bot_id", "")
    # Extract thread context
    thread_ts = event.get("thread_ts") or event.get("ts") if self._settings.slack.slack_thread_replies else None
    ...
    # Pass thread_ts through to pipeline and dispatch
    await self._run_ai_pipeline(say, client, mention_text or text, channel, thread_ts=thread_ts)
```

---

### Step 3 — `src/platform/slack.py`: update `_run_ai_pipeline()` signature

```python
async def _run_ai_pipeline(
    self, say, client, text: str, channel: str, *, thread_ts: str | None = None
) -> None:
    ...
    if self._settings.bot.stream_responses:
        response = await self._stream_to_slack(say, client, channel, prompt, thread_ts=thread_ts)
    else:
        resp = await client.chat_postMessage(
            channel=channel,
            text=_THINKING,
            **({"thread_ts": thread_ts} if thread_ts else {}),
        )
        ts = resp["ts"]
        ...
        await client.chat_postMessage(
            channel=channel,
            text=response or "_(empty response)_",
            **({"thread_ts": thread_ts} if thread_ts else {}),
        )
```

---

### Step 4 — `src/platform/slack.py`: update `_stream_to_slack()` signature

```python
async def _stream_to_slack(
    self, say, client, channel: str, prompt: str, *, thread_ts: str | None = None
) -> str:
    resp = await client.chat_postMessage(
        channel=channel,
        text=_THINKING,
        **({"thread_ts": thread_ts} if thread_ts else {}),
    )
    ts = resp["ts"]
    ...
    await client.chat_postMessage(
        channel=channel,
        text=final or "_(empty response)_",
        **({"thread_ts": thread_ts} if thread_ts else {}),
    )
```

---

### Step 5 — `src/platform/slack.py`: update `_dispatch()` and prefix command handlers

All prefix command handlers that call `say()` must use `thread_ts` when available:

```python
async def _dispatch(
    self, sub: str, args: list[str], say, client, channel: str,
    *, thread_ts: str | None = None
) -> None:
    ...

# Each command handler uses a helper:
async def _reply(self, client, channel: str, text: str, thread_ts: str | None) -> None:
    await client.chat_postMessage(
        channel=channel,
        text=text,
        **({"thread_ts": thread_ts} if thread_ts else {}),
    )
```

---

### Step 6 — `src/platform/slack.py`: thread_ts for trusted bot messages

When trusted bots send messages, extract `thread_ts` the same way:

```python
# In _on_message(), trusted bot path:
thread_ts = event.get("thread_ts") or event.get("ts") if self._settings.slack.slack_thread_replies else None
await self._dispatch(sub, args, say, client, channel, thread_ts=thread_ts)
```

---

## Files to Create / Change

| File | Action | Summary of change |
|------|--------|-------------------|
| `src/config.py` | **Edit** | Add `slack_thread_replies: bool = False` to `SlackConfig` |
| `src/platform/slack.py` | **Edit** | Extract `thread_ts` in `_on_message()`; thread `thread_ts` through `_run_ai_pipeline()`, `_stream_to_slack()`, `_dispatch()`, and all `say()` / `chat_postMessage()` calls |
| `tests/unit/test_slack_bot.py` | **Edit** | Add `slack_thread_replies` to `_make_settings()`; add thread mode tests |
| `docs/roadmap.md` | **Edit** | Mark feature done on completion |
| `docs/features/slack-thread-replies.md` | **Edit** | Change status to `Implemented` after merge |

---

## Dependencies

| Package | Status | Notes |
|---------|--------|-------|
| `slack-bolt[async]` | ✅ Already installed | `thread_ts` is a standard Slack API field; no new SDK needed |

---

## Test Plan

### `tests/unit/test_slack_bot.py` additions

| Test | What it checks |
|------|----------------|
| `test_thread_replies_disabled_by_default` | With default config, `say()` is called without `thread_ts` |
| `test_thread_reply_uses_event_ts` | With `SLACK_THREAD_REPLIES=true`, non-thread message → reply uses `event.ts` as `thread_ts` |
| `test_thread_reply_continues_existing_thread` | With `SLACK_THREAD_REPLIES=true`, message in thread → reply uses `event.thread_ts` |
| `test_thread_reply_stream` | Streaming path also posts thinking and final with `thread_ts` |
| `test_thread_reply_prefix_command` | Prefix command (`dev git`) reply uses `thread_ts` when enabled |
| `test_thread_reply_delegation` | Delegation messages (if `slack-agent-delegation.md` implemented) also use `thread_ts` |
| `test_thread_ts_propagation` | `thread_ts` extracted in `_on_message()` reaches `_run_ai_pipeline()` |

---

## Documentation Updates

### `README.md`

Add to environment variables table:
```markdown
| `SLACK_THREAD_REPLIES` | `false` | Reply in a thread anchored to the triggering message. Keeps channels clean in multi-agent setups. |
```

### `docs/guides/multi-agent-slack.md`

Add a **Thread Reply Mode** section:
- Explain `SLACK_THREAD_REPLIES=true`
- Show example `.env` snippet
- Describe interaction with delegation messages
- Note: works alongside `slack-final-response-new-message.md` (final response posted in thread)

### `docs/roadmap.md`

Mark this feature as done (✅) when merged to `main`.

---

## Version Bump

New env var with safe default `false`. Existing deployments are unaffected.

**Expected bump**: `MINOR` → `0.10.0` (coordinate with `slack-final-response-new-message.md`
and `slack-agent-delegation.md` — all three can ship together)

---

## Edge Cases and Open Questions

1. **`say()` vs `client.chat_postMessage()` for `thread_ts`** — The `say()` shorthand in
   `slack-bolt` accepts keyword arguments that are forwarded to `chat_postMessage`, including
   `thread_ts`. However, for clarity and explicit control, prefer `client.chat_postMessage()`
   in all paths where `thread_ts` is involved.

2. **Thinking placeholder in thread** — The ⏳ placeholder and its streaming edits must all
   use the same `thread_ts`. Since `_edit()` uses `chat_update(ts=...)` (updating the thinking
   message itself), it does not need `thread_ts` — it already references the specific message.
   Only the **initial** `chat_postMessage` for ⏳ needs `thread_ts`.

3. **`gate restart` interaction** — No persistent state. `gate restart` is unaffected.

4. **Delegations in thread** — See `slack-agent-delegation.md` Edge Case 5. When both features
   are enabled, delegation messages must carry the same `thread_ts`. The `_extract_delegations()`
   call in `_run_ai_pipeline()` must have access to `thread_ts` to pass to `chat_postMessage`.

5. **First message in a DM or group DM** — DMs and MPIMs support threads. The same logic
   applies: use `thread_ts` from the event if present, else `ts`. `is_allowed_slack()` already
   gates DM access; no additional auth work needed.

6. **Confirmation dialogs (Block Kit actions)** — The `confirm_run` / `cancel_run` Block Kit
   action handlers also call `say()`. If thread mode is enabled, these should also reply in
   thread. The action event contains `container.message_ts` which can serve as `thread_ts`.
   This is a stretch goal for v1; document as a known limitation.

7. **`SLACK_THREAD_REPLIES` per-agent** — Each agent has its own `.env` file, so the setting
   is already per-agent. One agent can be thread-mode while another is channel-root. This is
   intentional.

---

## Acceptance Criteria

- [ ] All implementation steps above are complete.
- [ ] `pytest tests/ -v --tb=short` passes with no failures or errors.
- [ ] `ruff check src/` reports no new linting issues.
- [ ] `README.md` is updated (env var table).
- [ ] `docs/guides/multi-agent-slack.md` updated with Thread Reply Mode section.
- [ ] `docs/roadmap.md` entry is marked done (✅).
- [ ] `docs/features/slack-thread-replies.md` status changed to `Implemented`.
- [ ] `VERSION` file bumped.
- [ ] Default (`SLACK_THREAD_REPLIES=false`) preserves existing channel-root behaviour (regression test).
- [ ] With `SLACK_THREAD_REPLIES=true`, all bot output (AI, commands, errors) goes into thread.
- [ ] Message already in a thread → bot continues that thread (uses `event.thread_ts`).
- [ ] Message at channel root → bot starts a new thread (uses `event.ts`).
