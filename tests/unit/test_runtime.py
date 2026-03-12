"""Unit tests for runtime.py — dependency detection."""
import hashlib
import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path

import src.runtime as runtime_module


class TestInstallDeps:
    async def test_no_manifest_returns_message(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runtime_module, "REPO_DIR", tmp_path)
        monkeypatch.setattr(runtime_module, "_SENTINEL_DIR", tmp_path / ".sentinels")
        result = await runtime_module.install_deps()
        assert "No known package manifest" in result

    async def test_detects_package_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runtime_module, "REPO_DIR", tmp_path)
        monkeypatch.setattr(runtime_module, "_SENTINEL_DIR", tmp_path / ".sentinels")
        (tmp_path / "package.json").write_text("{}")
        with patch("asyncio.create_subprocess_exec") as mock_proc:
            mock_proc.return_value = AsyncMock(
                communicate=AsyncMock(return_value=(b"ok", b"")),
                returncode=0,
            )
            result = await runtime_module.install_deps()
        assert "npm" in result

    async def test_detects_pyproject_toml(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runtime_module, "REPO_DIR", tmp_path)
        monkeypatch.setattr(runtime_module, "_SENTINEL_DIR", tmp_path / ".sentinels")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
        with patch("asyncio.create_subprocess_exec") as mock_proc:
            mock_proc.return_value = AsyncMock(
                communicate=AsyncMock(return_value=(b"ok", b"")),
                returncode=0,
            )
            result = await runtime_module.install_deps()
        assert "pip" in result

    async def test_failed_install_marked_with_x(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runtime_module, "REPO_DIR", tmp_path)
        monkeypatch.setattr(runtime_module, "_SENTINEL_DIR", tmp_path / ".sentinels")
        (tmp_path / "requirements.txt").write_text("nonexistent-pkg==0.0.0")
        with patch("asyncio.create_subprocess_exec") as mock_proc:
            mock_proc.return_value = AsyncMock(
                communicate=AsyncMock(return_value=(b"error output", b"")),
                returncode=1,
            )
            result = await runtime_module.install_deps()
        assert "❌" in result

    async def test_cached_manifest_skips_install(self, tmp_path, monkeypatch):
        """When sentinel exists, install is skipped (lines 34-36)."""
        monkeypatch.setattr(runtime_module, "REPO_DIR", tmp_path)
        sentinel_dir = tmp_path / ".sentinels"
        monkeypatch.setattr(runtime_module, "_SENTINEL_DIR", sentinel_dir)
        sentinel_dir.mkdir(parents=True, exist_ok=True)
        manifest = tmp_path / "requirements.txt"
        manifest.write_text("requests==2.0.0")
        # Create the sentinel so install is skipped
        h = hashlib.sha256(manifest.read_bytes()).hexdigest()[:16]
        (sentinel_dir / f"requirements.txt.{h}.ok").touch()
        with patch("asyncio.create_subprocess_exec") as mock_proc:
            result = await runtime_module.install_deps()
        mock_proc.assert_not_called()
        assert "cached" in result

    async def test_successful_install_removes_old_sentinels(self, tmp_path, monkeypatch):
        """After a successful install, old sentinel files for the same marker are deleted (line 49)."""
        monkeypatch.setattr(runtime_module, "REPO_DIR", tmp_path)
        sentinel_dir = tmp_path / ".sentinels"
        monkeypatch.setattr(runtime_module, "_SENTINEL_DIR", sentinel_dir)
        sentinel_dir.mkdir(parents=True, exist_ok=True)
        manifest = tmp_path / "requirements.txt"
        manifest.write_text("requests==2.0.0")
        # Plant a stale sentinel with a different hash
        old_sentinel = sentinel_dir / "requirements.txt.deadbeef0000dead.ok"
        old_sentinel.touch()
        with patch("asyncio.create_subprocess_exec") as mock_proc:
            mock_proc.return_value = AsyncMock(
                communicate=AsyncMock(return_value=(b"ok", b"")),
                returncode=0,
            )
            await runtime_module.install_deps()
        assert not old_sentinel.exists()
