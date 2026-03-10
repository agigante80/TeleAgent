# Multi-Agent Architecture on Slack

> Status: **Planned** | Priority: Medium

## Overview

Run multiple AgentGate instances simultaneously, each configured as a distinct AI agent with
its own persona, model, command prefix, and skill set — all connected to a single Slack
workspace. Users interact by mentioning the agent's unique prefix (e.g. `dev run`, `sec scan`,
`docs explain`).

---

## How Copilot Agents Work

### What Is a "Copilot Agent"?

In GitHub Copilot's model, an **agent** is a Copilot CLI process that is:

1. **Scoped** — given a working directory and an optional set of skills or tools.
2. **Instructed** — either by system-level skills files (`.md` or `.yml` in the skills directory)
   that define persona, constraints, and context, or by flags passed directly to the `copilot` CLI
   (`AI_CLI_OPTS`).
3. **Isolated** — each invocation of `copilot -p <prompt> [opts]` is stateless; AgentGate
   provides conversation continuity by prepending history from SQLite.

### Copilot Skills Directory

`COPILOT_SKILLS_DIRS` tells Copilot where to find skill definition files. A skill file is a
Markdown or YAML file that narrows the agent's persona, adds domain knowledge, or restricts
what it will do. Examples:

```
skills/
  security-agent.md     # Persona: "You are a security analyst..."
  devops-agent.md       # Persona: "You focus on CI/CD and infra..."
  docs-agent.md         # Persona: "You write clear, accurate documentation..."
```

Copilot reads all files in the directory and incorporates them into its system context before
responding. This is the primary mechanism for giving an agent a "profile" without touching code.

### Per-Agent Config Surface in AgentGate

| Env Var | Effect | Agent-specific? |
|---------|--------|-----------------|
| `BOT_CMD_PREFIX` | Trigger word in Slack (e.g. `gate`, `dev`, `sec`) | ✅ Yes |
| `COPILOT_SKILLS_DIRS` | Path to skills directory mounted into container | ✅ Yes |
| `AI_MODEL` | Which model the agent uses (e.g. `gpt-4o`, `claude-3-5-sonnet`) | ✅ Yes |
| `AI_CLI_OPTS` | Raw flags passed to `copilot -p` (replaces `--allow-all`) | ✅ Yes |
| `AI_CLI` | Backend selector: `copilot` \| `codex` \| `api` | ✅ Yes |
| `AI_API_KEY` | API key for the backend | ✅ Yes (per key) |
| `GITHUB_REPO` | Which repo the agent is aware of | ✅ Yes |
| `SLACK_BOT_TOKEN` | Slack bot credential (one per Slack app) | ✅ Yes |
| `SLACK_APP_TOKEN` | Socket Mode app token (one per Slack app) | ✅ Yes |
| `SLACK_CHANNEL_ID` | Restrict agent to a specific channel (optional) | Optional |

> **Key constraint:** Each Slack App / bot token is tied to one OAuth install. To have N
> agents in the same workspace, you create N separate Slack Apps in the
> [Slack API console](https://api.slack.com/apps), each with its own `SLACK_BOT_TOKEN` and
> `SLACK_APP_TOKEN`. All apps are installed in the same workspace and invited to the same channel.

---

## Multi-Agent Architecture

```
Slack Workspace
└── #agentgate (channel)
    ├── @DevAgent     ← "dev <cmd>"   → AgentGate container A (Copilot + dev skills)
    ├── @SecAgent     ← "sec <cmd>"   → AgentGate container B (API/Claude + security skills)
    └── @DocsAgent    ← "docs <cmd>"  → AgentGate container C (API/GPT-4o + docs skills)
```

All three containers share:
- The same GitHub repo (bind-mounted or cloned from the same `GITHUB_REPO`)
- The same SQLite volume path structure (`/data/history.db`) — but each in its **own** Docker
  volume so histories are isolated per agent

Each container has:
- Its own Slack App (separate bot user, separate tokens)
- Its own `BOT_CMD_PREFIX`
- Its own skills directory mounted at `/skills`
- Its own AI backend / model config

### Sequence: User Types `sec scan src/executor.py`

```
User  →  Slack
         Slack  →  @SecAgent (Socket Mode WebSocket)
                   SlackBot._on_message() → prefix match: "sec"
                   _handle_run("sec scan src/executor.py")
                   executor.run_shell("scan src/executor.py") ← runs in REPO_DIR
                   or forwards to AI with security persona injected via skills
         @SecAgent  →  AI backend (prompt + history)
         AI response  →  Slack (streamed)
User  ←  Slack (streamed reply from @SecAgent)
```

---

## Pros and Cons

### Pros

| Benefit | Detail |
|---------|--------|
| **Specialisation** | Each agent has deep, narrow expertise — no prompt dilution from competing domains |
| **Parallel context** | Two agents can answer in the same thread simultaneously (dev + sec, for example) |
| **Independent scaling** | High-load agents can run on larger hardware without affecting others |
| **Model flexibility** | Dev agent on Copilot (free), Sec agent on Claude Sonnet, Docs agent on GPT-4o |
| **Audit isolation** | Each agent has its own history DB — separate conversation logs per persona |
| **Prefix clarity** | Users know exactly which agent they're addressing (`sec scan` vs `docs explain`) |
| **Cost control** | Route cheap queries to cheaper models; expensive (long context) to premium models |

### Cons

| Drawback | Detail |
|----------|--------|
| **N Slack Apps to manage** | Each agent = one Slack App registration; more OAuth tokens, more configuration surface |
| **Resource overhead** | N Docker containers, N repo clones (or shared volume with care), N history DBs |
| **Slack workspace noise** | N bot users appear in workspace member list and every channel they join |
| **Skills file maintenance** | Skills files must be kept in sync with actual agent capabilities |
| **No cross-agent awareness** | Agents don't see each other's history — if you need collaborative context, inject it manually |
| **Prefix collision risk** | If a user forgets the right prefix, a wrong agent answers silently |

---

## Recommended Agents for AgentGate Project

For a team working on the **AgentGate repo itself**, three agents cover the full development
lifecycle:

### Agent 1 — `@GateCode` (Developer Agent)

**Purpose:** Day-to-day coding assistant, PR reviews, architecture questions, refactoring.
**Prefix:** `dev`
**Backend:** `AI_CLI=copilot`, `AI_MODEL=claude-sonnet-4-5` (or GPT-4o)
**Skills persona:** "You are a senior Python engineer working on AgentGate. Focus on clean
async Python, Pydantic, and testability. Always run ruff and pytest before suggesting code
changes."

```
Skills file: skills/dev-agent.md
---
# Developer Agent — AgentGate

You are a senior Python developer with deep expertise in:
- Async Python (asyncio, aiofiles, asyncpg)
- Pydantic v2 and pydantic-settings
- Telegram Bot API (python-telegram-bot)
- Slack Bolt async
- Docker and Docker Compose
- pytest and coverage

When asked to write code, always:
1. Follow the existing module structure in src/
2. Add or update tests in tests/unit/ or tests/integration/
3. Run `ruff check src/` mentally before answering
4. Prefer surgical changes — don't rewrite working code

The repo is AgentGate (github.com/agigante80/AgentGate).
```

---

### Agent 2 — `@GateSec` (Security Agent)

**Purpose:** Security review, red/blue team analysis, dependency audits, secret scanning.
**Prefix:** `sec`
**Backend:** `AI_CLI=api`, `AI_PROVIDER=anthropic`, `AI_MODEL=claude-opus-4-5`
**Rationale:** Claude Opus has stronger reasoning for adversarial thinking; Anthropic's
Constitutional AI makes it better at nuanced security risk assessment.

```
Skills file: skills/sec-agent.md
---
# Security Agent — AgentGate

You are a security engineer conducting red team / blue team analysis.

When reviewing code:
- Identify injection vectors (shell, prompt injection)
- Check for secret exposure (env vars logged, printed, or leaked)
- Verify authentication gates on every handler
- Review Docker attack surface (capabilities, user, exposed ports)
- Flag OWASP Top 10 equivalents for Telegram/Slack bots

When asked to think like an attacker:
- Model threat actors: script kiddie, insider threat, nation-state
- Identify C2 patterns (this project's architecture is Telegram C2 — be aware)
- Suggest detection IOCs for blue teamers

Always conclude with a risk rating: LOW / MEDIUM / HIGH / CRITICAL.
```

---

### Agent 3 — `@GateDocs` (Documentation Agent)

**Purpose:** Write and update docs, create feature specs, explain code to new contributors.
**Prefix:** `docs`
**Backend:** `AI_CLI=api`, `AI_PROVIDER=openai`, `AI_MODEL=gpt-4o`
**Rationale:** GPT-4o is fast and cost-effective for text-heavy tasks with no code execution.

```
Skills file: skills/docs-agent.md
---
# Documentation Agent — AgentGate

You are a technical writer and developer advocate.

Your jobs:
- Write and update docs/features/*.md spec files
- Explain architecture clearly for new contributors
- Create README sections, docker-compose examples, and env var tables
- Keep language concise: prefer tables and bullet points over prose
- Match the existing tone: direct, no fluff, code-first

Format rules:
- Feature docs: Status line, Overview, Env vars, Design, Files to Change, Open Questions
- Always include a pros/cons table when presenting options
- Docker Compose examples must be fully working (no placeholders left blank)
```

---

## Setup: Step-by-Step

### Step 1 — Create Slack Apps (repeat for each agent)

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Name: `GateCode` (or `GateSec`, `GateDocs`)
3. Enable **Socket Mode** → generate an App-Level Token (`xapp-...`) → scope: `connections:write`
4. **Event Subscriptions** → Subscribe to bot events: `message.channels`, `message.groups`
5. **OAuth & Permissions** → Bot Token Scopes: `channels:history`, `chat:write`, `files:read`, `app_mentions:read`
6. Install to workspace → copy `Bot User OAuth Token` (`xoxb-...`)
7. **Invite the bot** to your target channel: `/invite @GateCode`

Repeat for `GateSec` and `GateDocs`.

### Step 2 — Create Skills Files

```bash
mkdir -p skills
# Paste skills/dev-agent.md, skills/sec-agent.md, skills/docs-agent.md
# (content from examples above)
```

### Step 3 — Create `.env` Files

```bash
# .env.dev
PLATFORM=slack
SLACK_BOT_TOKEN=xoxb-dev-...
SLACK_APP_TOKEN=xapp-dev-...
SLACK_CHANNEL_ID=C0123456789        # your #agentgate channel ID
BOT_CMD_PREFIX=dev
GITHUB_REPO=agigante80/AgentGate
GITHUB_REPO_TOKEN=ghp_...
AI_CLI=copilot
AI_MODEL=claude-sonnet-4-5

# .env.sec
PLATFORM=slack
SLACK_BOT_TOKEN=xoxb-sec-...
SLACK_APP_TOKEN=xapp-sec-...
SLACK_CHANNEL_ID=C0123456789
BOT_CMD_PREFIX=sec
GITHUB_REPO=agigante80/AgentGate
GITHUB_REPO_TOKEN=ghp_...
AI_CLI=api
AI_PROVIDER=anthropic
AI_API_KEY=sk-ant-...
AI_MODEL=claude-opus-4-5
COPILOT_SKILLS_DIRS=/skills

# .env.docs
PLATFORM=slack
SLACK_BOT_TOKEN=xoxb-docs-...
SLACK_APP_TOKEN=xapp-docs-...
SLACK_CHANNEL_ID=C0123456789
BOT_CMD_PREFIX=docs
GITHUB_REPO=agigante80/AgentGate
GITHUB_REPO_TOKEN=ghp_...
AI_CLI=api
AI_PROVIDER=openai
AI_API_KEY=sk-...
AI_MODEL=gpt-4o
COPILOT_SKILLS_DIRS=/skills
```

### Step 4 — Docker Compose (Multi-Agent)

```yaml
# docker-compose.multi-agent.yml

services:

  # ── Developer Agent ──────────────────────────────────────────────────────────
  dev:
    image: ghcr.io/agigante80/agentgate:latest
    restart: unless-stopped
    env_file: .env.dev
    volumes:
      - repo_dev:/repo
      - data_dev:/data
      - ./skills/dev-agent.md:/skills/dev-agent.md:ro
    labels:
      agentgate.agent: dev

  # ── Security Agent ──────────────────────────────────────────────────────────
  sec:
    image: ghcr.io/agigante80/agentgate:latest
    restart: unless-stopped
    env_file: .env.sec
    volumes:
      - repo_sec:/repo
      - data_sec:/data
      - ./skills/sec-agent.md:/skills/sec-agent.md:ro
    labels:
      agentgate.agent: sec

  # ── Documentation Agent ─────────────────────────────────────────────────────
  docs:
    image: ghcr.io/agigante80/agentgate:latest
    restart: unless-stopped
    env_file: .env.docs
    volumes:
      - repo_docs:/repo
      - data_docs:/data
      - ./skills/docs-agent.md:/skills/docs-agent.md:ro
    labels:
      agentgate.agent: docs

volumes:
  repo_dev:
  data_dev:
  repo_sec:
  data_sec:
  repo_docs:
  data_docs:
```

```bash
# Launch all three agents
docker compose -f docker-compose.multi-agent.yml up -d

# Check status
docker compose -f docker-compose.multi-agent.yml ps

# Tail a specific agent's logs
docker compose -f docker-compose.multi-agent.yml logs -f sec
```

### Step 5 — Verify

In your Slack channel, each bot posts its 🟢 Ready message on startup. Test each:

```
dev what's the architecture of the history module?
sec review src/executor.py for injection vulnerabilities
docs write a one-paragraph overview of the Slack integration
```

---

## Channel Strategy Options

| Strategy | Setup | Best For |
|----------|-------|----------|
| **Single channel, all agents** | All `SLACK_CHANNEL_ID` = same channel | Small team, easy discovery |
| **Dedicated channels per agent** | `#agentgate-dev`, `#agentgate-sec`, `#agentgate-docs` | Clear separation, less noise |
| **Shared + specialised** | Main `#agentgate` for general + private channels for sensitive security queries | Balanced |

For AgentGate itself: **single `#agentgate` channel** is recommended. Three bots with distinct
prefixes are easy to distinguish and the cross-pollination (seeing `sec` flag what `dev` just
wrote) is valuable.

---

## Open Questions

1. **Shared repo volume?** All agents cloning the same repo wastes disk and network. A read-only
   shared bind-mount for the source tree + separate writable `/data` volumes per agent would be
   cleaner. Risk: one agent's `gate run` could affect another's working dir.

2. **Agent routing?** Could a "router agent" (prefix: `gate`) auto-classify the query and
   delegate to the right agent? Requires an extra LLM call per message but would eliminate
   prefix memorisation burden.

3. **Cross-agent history?** Today each agent's history is isolated. A shared `history.db`
   (with `agent_id` column) would let a meta-agent see all conversations, but raises privacy
   and locking concerns.

4. **Cost accounting?** With N agents and N API keys, tracking spend per agent requires either
   separate API keys or per-request logging not yet in AgentGate.

5. **Skills hot-reload?** Skills files are read by Copilot at subprocess spawn time. No restart
   needed to change a skill — just edit the file. Confirm this holds for `api` backend (where
   the system prompt would need to be re-read on each request).
