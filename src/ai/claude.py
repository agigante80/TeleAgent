"""
Claude CLI backend — non-interactive subprocess mode.
Each query spawns `claude -p <prompt> --dangerously-skip-permissions --output-format text`
as a subprocess. History is injected by the bot layer via build_prompt() (stateless pattern).
"""
import asyncio
import logging
import os
import shlex
from collections.abc import AsyncGenerator

from src.ai.adapter import AICLIBackend, SubprocessMixin
from src.executor import scrubbed_env
from src.registry import backend_registry

logger = logging.getLogger(__name__)

TIMEOUT = 300  # seconds — hard cap; Claude CLI agentic tasks can run long


@backend_registry.register("claude")
class ClaudeBackend(SubprocessMixin, AICLIBackend):
    """Stateless backend using Anthropic's Claude CLI.

    Each AgentGate message spawns a fresh ``claude -p <prompt>
    --dangerously-skip-permissions --output-format text`` subprocess.
    Claude CLI handles multi-step agentic execution within that single call
    (file edits, tool use, shell commands), but does NOT retain state across
    calls.  AgentGate injects conversation history via build_prompt()
    (is_stateful = False pattern).
    """

    is_stateful = False

    def __init__(self, api_key: str, model: str = "", opts: str = "") -> None:
        self._api_key = api_key
        self._model = model
        self._opts = opts

    def _make_cmd(self, prompt: str) -> tuple[list[str], dict]:
        env = {**scrubbed_env(), "ANTHROPIC_API_KEY": self._api_key}
        # Re-inject the GitHub token as GH_TOKEN so `gh` CLI and raw git
        # operations work in model shell commands. scrubbed_env() strips
        # GITHUB_REPO_TOKEN for safety.
        if github_token := os.environ.get("GITHUB_REPO_TOKEN"):
            env["GH_TOKEN"] = github_token
            env["GITHUB_TOKEN"] = github_token
        # --dangerously-skip-permissions: auto-approve all tool calls (file
        # reads, writes, shell commands). Docker container isolation is the
        # containment boundary — Claude CLI can only affect what is mounted
        # into the container.
        # --output-format text: force plain-text stdout so no JSON or ANSI UI
        # decorations bleed into the response captured by send() / stream().
        safety_flags = ["--dangerously-skip-permissions", "--output-format", "text"]
        user_opts = shlex.split(self._opts) if self._opts else []
        cmd = ["claude", "-p", prompt] + safety_flags + user_opts
        if self._model:
            cmd += ["--model", self._model]
        return cmd, env

    async def send(self, prompt: str) -> str:
        cmd, env = self._make_cmd(prompt)
        try:
            proc = await self._spawn(cmd, env)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
        except asyncio.TimeoutError:
            try:
                proc.kill()  # type: ignore[possibly-undefined]
                await proc.wait()  # reap zombie
            except Exception:
                pass
            return f"⚠️ Claude CLI timed out after {TIMEOUT}s."
        except Exception as exc:
            logger.exception("Claude CLI subprocess error")
            return f"⚠️ Claude CLI error: {exc}"
        if proc.returncode not in (0, None):
            err = stderr.decode().strip() or stdout.decode().strip()
            logger.error("claude CLI error (rc=%d): %s", proc.returncode, err)
            return f"⚠️ Claude CLI error (rc={proc.returncode}):\n{err}"
        return stdout.decode().strip()

    async def stream(self, prompt: str) -> AsyncGenerator[str, None]:
        cmd, env = self._make_cmd(prompt)
        try:
            proc = await self._spawn(cmd, env)
        except Exception as exc:
            logger.exception("Claude CLI stream error")
            yield f"⚠️ Claude CLI error: {exc}"
            return
        assert proc.stdout
        try:
            async for line in proc.stdout:
                yield line.decode()
        except Exception as exc:
            logger.exception("Claude CLI stream read error")
            yield f"\n⚠️ Claude CLI stream error: {exc}"
            return
        finally:
            await proc.wait()
        if proc.returncode not in (0, None):
            assert proc.stderr
            err = (await proc.stderr.read()).decode().strip()
            if err:
                logger.error("claude CLI stream error (rc=%d): %s", proc.returncode, err)
                yield f"\n⚠️ Claude CLI error (rc={proc.returncode}):\n{err}"
