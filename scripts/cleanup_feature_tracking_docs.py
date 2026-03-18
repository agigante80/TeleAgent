#!/usr/bin/env python3
"""Generate and apply post-migration cleanup for legacy feature tracking docs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent


def _load_verify_parity_report():
    script_path = _SCRIPT_DIR / "migrate_features.py"
    spec = importlib.util.spec_from_file_location("migrate_features", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load migrate_features.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    verify_fn = getattr(module, "verify_parity_report", None)
    if not callable(verify_fn):
        raise RuntimeError("migrate_features.py does not expose verify_parity_report")
    return verify_fn


verify_parity_report = _load_verify_parity_report()

ISSUE_MAP_SCHEMA_VERSION = 1
CLEANUP_MANIFEST_SCHEMA_VERSION = 1
REQUIRED_LABELS = {"type:feature", "review:pending"}
SOURCE_DOC_RE = re.compile(r"^- Source doc:\s*`([^`]+)`\s*$", re.MULTILINE)
DEFAULT_KEEP_SOURCES = {
    "docs/features/github-issues-migration.md",
    "docs/features/github-issues-automation-phase2.md",
    "docs/features/github-issues-cleanup.md",
}


class CleanupError(RuntimeError):
    """Raised when cleanup preconditions or operations fail."""


@dataclass(frozen=True)
class IssueRef:
    issue_number: int
    url: str


@dataclass(frozen=True)
class CleanupInputs:
    parity_sources: set[str]
    issue_map: dict[str, IssueRef]
    files_to_delete: list[str]
    parity_report_sha256: str


class _TokenRedactor:
    def __init__(self, token: str) -> None:
        self._token = token

    def redact(self, text: str) -> str:
        if not text:
            return text
        redacted = text
        if self._token:
            redacted = redacted.replace(self._token, "[REDACTED]")
        redacted = re.sub(r"gh[pors]_[A-Za-z0-9]{20,}", "[REDACTED]", redacted)
        redacted = re.sub(r"github_pat_[A-Za-z0-9_]{20,}", "[REDACTED]", redacted)
        return redacted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, default=Path("docs/features"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/feature-issue-export"))
    parser.add_argument("--repo", default="agigante80/AgentGate")
    parser.add_argument("--manifest-path", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="delete files from a validated manifest")
    parser.add_argument(
        "--keep-source",
        action="append",
        default=[],
        help="source docs to preserve even if parity+issue mapping exists",
    )
    return parser.parse_args()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_parity_sources(features_dir: Path, output_dir: Path) -> set[str]:
    errors = verify_parity_report(features_dir, output_dir)
    if errors:
        formatted = "\n".join(f"- {error}" for error in errors)
        raise CleanupError(f"parity verification failed:\n{formatted}")

    report_path = output_dir / "parity-report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CleanupError(f"unable to read parity report: {exc}") from exc

    items = report.get("items") if isinstance(report, dict) else None
    if not isinstance(items, list):
        raise CleanupError("invalid parity report: `items` must be a list")

    sources: set[str] = set()
    features_root = features_dir.resolve()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("source"), str):
            raise CleanupError(f"invalid parity report item at index {index}: missing `source`")
        source = item["source"]
        resolved = Path(source).resolve()
        try:
            resolved.relative_to(features_root)
        except ValueError as exc:
            raise CleanupError(f"source path escapes features dir: {source}") from exc
        sources.add(Path(source).as_posix())

    return sources


def _run_gh_json(argv: list[str], *, token: str, redactor: _TokenRedactor) -> object:
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    proc = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    stdout = redactor.redact(proc.stdout)
    stderr = redactor.redact(proc.stderr)
    if proc.returncode != 0:
        raise CleanupError(f"gh command failed: {' '.join(argv)} :: {stderr.strip() or stdout.strip()}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CleanupError(f"gh returned malformed JSON: {' '.join(argv)}") from exc


def _extract_source_doc(body: str) -> str | None:
    match = SOURCE_DOC_RE.search(body)
    if not match:
        return None
    return Path(match.group(1)).as_posix()


def _has_required_label_set(labels: list[str]) -> bool:
    if not REQUIRED_LABELS.issubset(set(labels)):
        return False
    has_priority = any(label.startswith("priority:") for label in labels)
    has_status = any(label.startswith("status:") for label in labels)
    return has_priority and has_status


def _fetch_issue_map(*, repo: str, token: str, parity_sources: set[str]) -> dict[str, IssueRef]:
    redactor = _TokenRedactor(token)
    payload = _run_gh_json(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--label",
            "type:feature",
            "--limit",
            "500",
            "--json",
            "number",
        ],
        token=token,
        redactor=redactor,
    )
    if not isinstance(payload, list):
        raise CleanupError("gh issue list returned non-list payload")

    issue_map: dict[str, IssueRef] = {}
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("number"), int):
            continue
        number = item["number"]
        issue = _run_gh_json(
            [
                "gh",
                "issue",
                "view",
                "--repo",
                repo,
                str(number),
                "--json",
                "number,state,url,body,labels",
            ],
            token=token,
            redactor=redactor,
        )
        if not isinstance(issue, dict):
            raise CleanupError(f"invalid issue payload for #{number}")

        state = issue.get("state")
        if state != "OPEN":
            raise CleanupError(f"mapped issue #{number} is not open")

        labels_payload = issue.get("labels")
        labels: list[str] = []
        if isinstance(labels_payload, list):
            for label in labels_payload:
                if isinstance(label, dict) and isinstance(label.get("name"), str):
                    labels.append(label["name"])
        if not _has_required_label_set(labels):
            raise CleanupError(f"mapped issue #{number} missing required migration labels")

        body = issue.get("body") if isinstance(issue.get("body"), str) else ""
        source = _extract_source_doc(body)
        if source is None:
            continue
        if source not in parity_sources:
            continue

        if source in issue_map:
            raise CleanupError(f"duplicate issue mapping for source {source}")

        url = issue.get("url") if isinstance(issue.get("url"), str) else ""
        issue_map[source] = IssueRef(issue_number=number, url=url)

    missing = sorted(parity_sources - set(issue_map.keys()))
    if missing:
        raise CleanupError(
            "unable to map all parity sources to open issues via Source Spec marker: "
            + ", ".join(missing)
        )

    return issue_map


def _write_issue_map(path: Path, issue_map: dict[str, IssueRef]) -> None:
    items = [
        {"source": source, "issue_number": ref.issue_number}
        for source, ref in sorted(issue_map.items())
    ]
    payload = {"schema_version": ISSUE_MAP_SCHEMA_VERSION, "items": items}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_cleanup_inputs(args: argparse.Namespace) -> CleanupInputs:
    parity_sources = _load_parity_sources(args.features_dir, args.output_dir)
    token = os.environ.get("GITHUB_REPO_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if not token:
        raise CleanupError("missing required env var: GITHUB_REPO_TOKEN (or GH_TOKEN)")

    issue_map = _fetch_issue_map(repo=args.repo, token=token, parity_sources=parity_sources)

    keep_sources = set(DEFAULT_KEEP_SOURCES)
    keep_sources.update(Path(value).as_posix() for value in args.keep_source)

    docs_to_delete = sorted(
        source for source in issue_map if source not in keep_sources and source != "docs/features/_template.md"
    )
    files_to_delete = ["docs/roadmap.md", *docs_to_delete]

    report_path = args.output_dir / "parity-report.json"
    return CleanupInputs(
        parity_sources=parity_sources,
        issue_map=issue_map,
        files_to_delete=files_to_delete,
        parity_report_sha256=_sha256_file(report_path),
    )


def _manifest_path(args: argparse.Namespace) -> Path:
    if args.manifest_path is not None:
        return args.manifest_path
    return args.output_dir / "cleanup-manifest.json"


def _write_manifest(path: Path, *, args: argparse.Namespace, inputs: CleanupInputs) -> None:
    payload = {
        "schema_version": CLEANUP_MANIFEST_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "branch": _git_output(["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit_sha": _git_output(["rev-parse", "HEAD"]),
        "parity_report_sha256": inputs.parity_report_sha256,
        "files_to_delete": inputs.files_to_delete,
        "issue_map": [
            {
                "source": source,
                "issue_number": ref.issue_number,
                "issue_url": ref.url,
            }
            for source, ref in sorted(inputs.issue_map.items())
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_output(argv: list[str]) -> str:
    proc = subprocess.run(
        ["git", *argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise CleanupError(f"git command failed: {' '.join(argv)} :: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CleanupError(f"invalid cleanup manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise CleanupError("invalid cleanup manifest: top-level JSON must be an object")
    return data


def _validate_manifest_file_list(*, manifest: dict[str, object], features_dir: Path) -> list[Path]:
    files_raw = manifest.get("files_to_delete")
    if not isinstance(files_raw, list) or not all(isinstance(value, str) for value in files_raw):
        raise CleanupError("invalid cleanup manifest: `files_to_delete` must be a list of strings")

    features_root = features_dir.resolve()
    allowed_roadmap = Path("docs/roadmap.md").resolve()
    resolved_paths: list[Path] = []
    seen: set[Path] = set()

    for value in files_raw:
        if any(ch in value for ch in "*?[]"):
            raise CleanupError(f"invalid cleanup manifest path contains glob characters: {value}")
        candidate = Path(value)
        resolved = candidate.resolve()

        if resolved == allowed_roadmap:
            pass
        else:
            try:
                resolved.relative_to(features_root)
            except ValueError as exc:
                raise CleanupError(f"cleanup manifest path escapes features dir: {value}") from exc

        if resolved in seen:
            raise CleanupError(f"duplicate cleanup manifest path: {value}")
        if not resolved.exists():
            raise CleanupError(f"cleanup manifest path does not exist: {value}")
        if not resolved.is_file():
            raise CleanupError(f"cleanup manifest path is not a file: {value}")

        seen.add(resolved)
        resolved_paths.append(resolved)

    return resolved_paths


def _validate_manifest_issue_map(manifest: dict[str, object]) -> dict[str, IssueRef]:
    entries = manifest.get("issue_map")
    if not isinstance(entries, list):
        raise CleanupError("invalid cleanup manifest: `issue_map` must be a list")

    issue_map: dict[str, IssueRef] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CleanupError(f"invalid cleanup manifest issue_map entry at index {index}")
        source = entry.get("source")
        number = entry.get("issue_number")
        url = entry.get("issue_url")
        if (
            not isinstance(source, str)
            or not isinstance(number, int)
            or isinstance(number, bool)
            or not isinstance(url, str)
        ):
            raise CleanupError(
                f"invalid cleanup manifest issue_map entry at index {index}: malformed fields"
            )
        source_key = Path(source).as_posix()
        if source_key in issue_map:
            raise CleanupError(f"invalid cleanup manifest: duplicate issue_map source {source_key}")
        issue_map[source_key] = IssueRef(issue_number=number, url=url)

    return issue_map


def validate_manifest(manifest_path: Path, *, features_dir: Path, output_dir: Path) -> list[Path]:
    manifest = _load_manifest(manifest_path)

    schema = manifest.get("schema_version")
    if schema != CLEANUP_MANIFEST_SCHEMA_VERSION:
        raise CleanupError(
            "invalid cleanup manifest: unsupported schema_version "
            f"{schema!r}"
        )

    expected_hash = manifest.get("parity_report_sha256")
    if not isinstance(expected_hash, str):
        raise CleanupError("invalid cleanup manifest: `parity_report_sha256` must be a string")

    actual_hash = _sha256_file(output_dir / "parity-report.json")
    if expected_hash != actual_hash:
        raise CleanupError(
            "cleanup manifest parity_report_sha256 mismatch: "
            f"expected {expected_hash}, got {actual_hash}"
        )

    issue_map = _validate_manifest_issue_map(manifest)
    resolved_paths = _validate_manifest_file_list(manifest=manifest, features_dir=features_dir)
    mapped_sources = {Path(source).resolve() for source in issue_map}
    roadmap_path = Path("docs/roadmap.md").resolve()

    for resolved in resolved_paths:
        if resolved == roadmap_path:
            continue
        if resolved not in mapped_sources:
            raise CleanupError(
                f"manifest deletion target has no mapped issue: {resolved.as_posix()}"
            )

    return resolved_paths


def apply_manifest(manifest_path: Path, *, features_dir: Path, output_dir: Path) -> list[str]:
    resolved_paths = validate_manifest(manifest_path, features_dir=features_dir, output_dir=output_dir)

    deleted: list[str] = []
    for path in resolved_paths:
        path.unlink()
        deleted.append(path.as_posix())
    return deleted


def run_cleanup(args: argparse.Namespace) -> int:
    manifest_path = _manifest_path(args)

    inputs = _build_cleanup_inputs(args)
    _write_issue_map(args.output_dir / "issue-map.json", inputs.issue_map)
    _write_manifest(manifest_path, args=args, inputs=inputs)

    print(f"wrote issue map: {(args.output_dir / 'issue-map.json').as_posix()}")
    print(f"wrote cleanup manifest: {manifest_path.as_posix()}")

    resolved = validate_manifest(manifest_path, features_dir=args.features_dir, output_dir=args.output_dir)
    print(f"validated cleanup manifest ({len(resolved)} files)")

    if not args.apply:
        print("dry-run complete (no files deleted; rerun with --apply)")
        return 0

    deleted = apply_manifest(manifest_path, features_dir=args.features_dir, output_dir=args.output_dir)
    print(f"cleanup complete (deleted={len(deleted)})")
    for path in deleted:
        print(f"deleted {path}")
    return 0


def main() -> int:
    try:
        return run_cleanup(parse_args())
    except CleanupError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
