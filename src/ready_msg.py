"""Shared helpers for building the AgentGate ready / info messages."""
import subprocess

from src.config import Settings, REPO_DIR


def _resolve_sha(settings: Settings) -> str:
    """Return the short git SHA for the current HEAD commit.

    Uses ``settings.bot.git_sha`` if set; otherwise queries git directly.
    Returns ``""`` silently on any error.
    """
    if settings.bot.git_sha:
        return settings.bot.git_sha
    try:
        result = subprocess.run(
            ["git", "-C", REPO_DIR, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def ai_label(settings: Settings) -> str:
    """Human-readable AI backend + model string."""
    cli = settings.ai.ai_cli
    model = settings.ai.ai_model
    if cli == "api" and settings.ai.direct.ai_provider:
        label = f"{cli}/{settings.ai.direct.ai_provider}"
    else:
        label = cli
    if model:
        label += f" ({model})"
    return label


def build_ready_message(settings: Settings, version: str, prefix: str, use_slash: bool = True) -> str:
    """Build the 🟢 Ready message shown on startup and by /gate info."""
    ai = ai_label(settings)
    tag = settings.bot.image_tag
    is_dev = bool(tag and tag != "latest")
    if is_dev:
        sha = _resolve_sha(settings)
        version_line = f"v{version}-dev-{sha}" if sha else f"v{version} `:{tag}`"
    else:
        version_line = f"v{version}" + (f" `:{tag}`" if tag else "")
    cmd = f"/{prefix}" if use_slash else prefix
    return (
        f"🟢 *AgentGate Ready* — {version_line}\n"
        f"📁 `{settings.github.github_repo}` | 🌿 `{settings.github.branch}`\n"
        f"🤖 AI: `{ai}`\n"
        f"Type `{cmd} help` for commands | `{cmd} info` for full status"
    )
