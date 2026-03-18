from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_module():
    script_path = Path("scripts/cleanup_feature_tracking_docs.py")
    spec = importlib.util.spec_from_file_location("cleanup_feature_tracking_docs", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_parity_report(path: Path, *, payload: dict[str, object] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if payload is None:
        payload = {
            "schema_version": 2,
            "source_count": 0,
            "export_count": 0,
            "items": [],
        }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validate_manifest_rejects_path_escape_before_deleting(tmp_path, monkeypatch):
    module = _load_module()
    features_dir = tmp_path / "docs" / "features"
    output_dir = tmp_path / "tmp" / "feature-issue-export"
    features_dir.mkdir(parents=True)
    _write_parity_report(output_dir / "parity-report.json")

    outside = tmp_path / "src" / "main.py"
    outside.parent.mkdir(parents=True)
    outside.write_text("print('x')\n", encoding="utf-8")

    manifest_path = output_dir / "cleanup-manifest.json"
    _write_manifest(
        manifest_path,
        {
            "schema_version": 1,
            "parity_report_sha256": _hash_file(output_dir / "parity-report.json"),
            "files_to_delete": [outside.as_posix()],
            "issue_map": [],
        },
    )

    unlinked = {"count": 0}
    original_unlink = Path.unlink

    def _tracking_unlink(self, *args, **kwargs):
        unlinked["count"] += 1
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _tracking_unlink)

    with pytest.raises(module.CleanupError, match="escapes features dir"):
        module.apply_manifest(manifest_path, features_dir=features_dir, output_dir=output_dir)

    assert unlinked["count"] == 0


def test_validate_manifest_rejects_nonexistent_file(tmp_path):
    module = _load_module()
    features_dir = tmp_path / "docs" / "features"
    output_dir = tmp_path / "tmp" / "feature-issue-export"
    features_dir.mkdir(parents=True)
    _write_parity_report(output_dir / "parity-report.json")

    missing = tmp_path / "docs" / "features" / "missing.md"
    manifest_path = output_dir / "cleanup-manifest.json"
    _write_manifest(
        manifest_path,
        {
            "schema_version": 1,
            "parity_report_sha256": _hash_file(output_dir / "parity-report.json"),
            "files_to_delete": [missing.as_posix()],
            "issue_map": [{"source": missing.as_posix(), "issue_number": 1, "issue_url": "https://example.com/1"}],
        },
    )

    with pytest.raises(module.CleanupError, match="does not exist"):
        module.validate_manifest(manifest_path, features_dir=features_dir, output_dir=output_dir)


def test_validate_manifest_rejects_parity_hash_mismatch(tmp_path):
    module = _load_module()
    features_dir = tmp_path / "docs" / "features"
    output_dir = tmp_path / "tmp" / "feature-issue-export"
    features_dir.mkdir(parents=True)
    _write_parity_report(output_dir / "parity-report.json")

    target = features_dir / "x.md"
    target.write_text("# x\n", encoding="utf-8")

    manifest_path = output_dir / "cleanup-manifest.json"
    _write_manifest(
        manifest_path,
        {
            "schema_version": 1,
            "parity_report_sha256": "0" * 64,
            "files_to_delete": [target.as_posix()],
            "issue_map": [{"source": target.as_posix(), "issue_number": 1, "issue_url": "https://example.com/1"}],
        },
    )

    with pytest.raises(module.CleanupError, match="parity_report_sha256 mismatch"):
        module.validate_manifest(manifest_path, features_dir=features_dir, output_dir=output_dir)
