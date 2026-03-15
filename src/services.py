"""Service container — injected into platform adapters at startup."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.redact import SecretRedactor
    from src.transcriber import Transcriber


@dataclass
class ShellService:
    """Thin wrapper around executor.run_shell with injected configuration."""
    max_chars: int
    redactor: "SecretRedactor"

    async def run(self, cmd: str) -> str:
        from src import executor
        return await executor.run_shell(cmd, self.max_chars, self.redactor)

    def is_destructive(self, cmd: str) -> bool:
        from src import executor
        return executor.is_destructive(cmd)

    def is_exempt(self, cmd: str, keywords: list[str]) -> bool:
        from src import executor
        return executor.is_exempt(cmd, keywords)

    def sanitize_ref(self, ref: str) -> str | None:
        from src import executor
        return executor.sanitize_git_ref(ref)

    async def summarize_if_long(self, text: str, backend) -> str:
        from src import executor
        return await executor.summarize_if_long(text, self.max_chars, backend)


@dataclass
class RepoService:
    """Wraps src/repo.py. A fork can replace this with NullRepoService."""
    token: str = field(repr=False)  # excluded from repr() — not part of public interface
    repo_name: str = ""
    branch: str = "main"

    async def clone(self) -> None:
        from src import repo
        await repo.clone(self.token, self.repo_name, self.branch)

    async def pull(self) -> str:
        from src import repo
        return await repo.pull()

    async def status(self) -> str:
        from src import repo
        return await repo.status()

    async def configure_auth(self) -> None:
        from src import repo
        await repo.configure_git_auth(self.token)


class NullRepoService:
    """No-op repo service for forks that manage their own source directory.

    Does NOT inherit from RepoService — has no token attribute at all (OQ11).
    Implements the same duck-typed interface as RepoService.
    """
    async def clone(self) -> None:
        pass

    async def pull(self) -> str:
        return "ℹ️ No repository configured."

    async def status(self) -> str:
        return "ℹ️ No repository configured."

    async def configure_auth(self) -> None:
        pass


@dataclass
class Services:
    """Service container injected into platform adapters at startup."""
    shell: ShellService
    repo: RepoService
    redactor: "SecretRedactor"
    transcriber: "Transcriber | None" = field(default=None)
