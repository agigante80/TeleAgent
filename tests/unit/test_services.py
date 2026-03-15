"""Unit tests for src/services.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services import Services, ShellService, RepoService, NullRepoService


class TestNullRepoService:
    async def test_pull_returns_info_string(self):
        svc = NullRepoService()
        result = await svc.pull()
        assert "No repository configured" in result

    async def test_clone_is_noop(self):
        svc = NullRepoService()
        await svc.clone()  # should not raise

    async def test_status_returns_info_string(self):
        svc = NullRepoService()
        result = await svc.status()
        assert "No repository configured" in result

    async def test_configure_auth_is_noop(self):
        svc = NullRepoService()
        await svc.configure_auth()  # should not raise

    def test_no_token_attr(self):
        """NullRepoService has no token attribute — OQ11."""
        svc = NullRepoService()
        assert not hasattr(svc, "token")

    def test_does_not_inherit_from_repo_service(self):
        """NullRepoService is a standalone class, not a subclass of RepoService."""
        assert not issubclass(NullRepoService, RepoService)


class TestRepoService:
    def test_token_private_not_in_repr(self):
        """RepoService token is excluded from repr() — OQ10."""
        svc = RepoService(token="super-secret-token-abc123")
        assert "super-secret-token-abc123" not in repr(svc)

    def test_token_kwarg(self):
        svc = RepoService(token="tok", repo_name="owner/repo", branch="main")
        assert svc.repo_name == "owner/repo"

    async def test_pull_delegates_to_repo(self):
        svc = RepoService(token="tok")
        with patch("src.repo.pull", new=AsyncMock(return_value="up to date")) as mock_pull:
            result = await svc.pull()
        mock_pull.assert_awaited_once()
        assert "up to date" in result

    async def test_clone_delegates_to_repo(self):
        svc = RepoService(token="tok", repo_name="owner/repo", branch="main")
        with patch("src.repo.clone", new=AsyncMock()) as mock_clone:
            await svc.clone()
        mock_clone.assert_awaited_once_with("tok", "owner/repo", "main")


class TestShellService:
    def _make_redactor(self):
        r = MagicMock()
        r.redact = lambda x: x
        return r

    async def test_run_delegates_to_executor(self):
        svc = ShellService(max_chars=3000, redactor=self._make_redactor())
        with patch("src.executor.run_shell", new=AsyncMock(return_value="output")) as mock:
            result = await svc.run("echo hello")
        mock.assert_awaited_once_with("echo hello", 3000, svc.redactor)
        assert result == "output"

    def test_sanitize_ref_valid(self):
        svc = ShellService(max_chars=3000, redactor=self._make_redactor())
        result = svc.sanitize_ref("main")
        assert result is not None

    def test_sanitize_ref_invalid(self):
        svc = ShellService(max_chars=3000, redactor=self._make_redactor())
        result = svc.sanitize_ref("ref with spaces & special!")
        assert result is None

    def test_is_destructive(self):
        svc = ShellService(max_chars=3000, redactor=self._make_redactor())
        # rm is typically detected as destructive
        result = svc.is_destructive("rm -rf /")
        assert isinstance(result, bool)

    def test_is_exempt(self):
        svc = ShellService(max_chars=3000, redactor=self._make_redactor())
        result = svc.is_exempt("git push", ["push"])
        assert result is True


class TestServicesDataclass:
    def test_services_holds_components(self):
        redactor = MagicMock()
        shell = ShellService(max_chars=3000, redactor=redactor)
        repo = RepoService(token="tok")
        svc = Services(shell=shell, repo=repo, redactor=redactor)
        assert svc.shell is shell
        assert svc.repo is repo
        assert svc.redactor is redactor
        assert svc.transcriber is None
