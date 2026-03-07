# Split AIConfig into Per-Backend Sub-Configs

> Status: **Planned** | Priority: Low (long-term architecture)

## Problem

`src/config.py` `AIConfig` contains fields for Copilot, Codex, and Direct API in a flat struct. Adding a new backend adds noise to every other backend's namespace (e.g., `copilot_model` appears alongside `ai_base_url` even when `AI_CLI=codex`).

## Proposed Design

```python
class CopilotConfig(BaseSettings):
    copilot_github_token: str = ""
    copilot_model: str = ""

class CodexConfig(BaseSettings):
    codex_model: str = "o3"

class DirectAPIConfig(BaseSettings):
    ai_provider: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = ""

class AIConfig(BaseSettings):
    ai_cli: Literal["copilot", "codex", "api"] = "copilot"
    ai_cli_opts: str = ""
    copilot: CopilotConfig = CopilotConfig()
    codex: CodexConfig = CodexConfig()
    direct: DirectAPIConfig = DirectAPIConfig()
```

## Migration

All env var names stay the same (pydantic-settings reads them into nested models transparently). Only internal attribute access paths change (`settings.ai.copilot_model` → `settings.ai.copilot.copilot_model`).

Update all callers in `ai/copilot.py`, `ai/codex.py`, `ai/direct.py`, and `factory.py`.
