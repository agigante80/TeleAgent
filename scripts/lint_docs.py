#!/usr/bin/env python3
"""Docs lint script — keeps roadmap, feature specs, and config documentation in sync.

Checks:
  1. Every feature spec (except _template.md) has a '> Status:' line.
  2. Every Implemented spec is NOT listed in docs/roadmap.md.
  3. Every roadmap feature link resolves to a real file.
  4. Every non-Implemented/non-Approved spec that has a feature file is in the roadmap.
  5. Every env var defined in src/config.py is documented in README.md.

Exit codes: 0 = all good, 1 = one or more violations found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FEATURES_DIR = Path("docs/features")
ROADMAP_FILE = Path("docs/roadmap.md")
CONFIG_FILE = Path("src/config.py")
README_FILE = Path("README.md")
TEMPLATE_NAME = "_template.md"

# Nested BaseSettings fields on Settings / AIConfig — not direct env vars.
_NESTED_CONFIG_FIELDS = {
    "telegram", "github", "log", "bot", "ai", "voice", "slack", "audit",
    "copilot", "codex", "direct", "model_config",
}

# Statuses that mean the feature is fully shipped — must NOT appear in roadmap.
IMPLEMENTED_STATUSES = {"implemented"}

# Statuses that mean the feature is planned/in-progress — MUST appear in roadmap.
ROADMAP_REQUIRED_STATUSES = {"planned", "proposed", "approved"}

STATUS_RE = re.compile(r"^>\s*Status:\s*\*{0,2}(.+?)\*{0,2}\s*[|$]", re.IGNORECASE | re.MULTILINE)
ROADMAP_LINK_RE = re.compile(r"\(features/([^)]+\.md)\)")


def extract_status(text: str) -> str | None:
    """Return the raw status string from a spec, or None if not found."""
    m = STATUS_RE.search(text)
    if not m:
        return None
    # Strip any remaining bold markers and extra whitespace
    return m.group(1).replace("*", "").replace("✅", "").strip().lower()


def extract_config_env_vars() -> set[str]:
    """Parse src/config.py and return the set of env var names it declares.

    Three sources:
    - ``alias="VAR_NAME"`` → explicit env var alias
    - ``env="VAR_NAME"`` inside Field() → explicit env override
    - Plain field declaration (no alias/env) → field_name.upper()

    Nested BaseSettings sub-config fields (telegram, bot, ai, …) are skipped.
    """
    if not CONFIG_FILE.is_file():
        return set()

    text = CONFIG_FILE.read_text()
    env_vars: set[str] = set()

    # 1. Explicit alias="VAR" or env="VAR"
    env_vars.update(re.findall(r'alias="([A-Z][A-Z0-9_]+)"', text))
    env_vars.update(re.findall(r'\benv="([A-Z][A-Z0-9_]+)"', text))

    # 2. Plain field declarations — 4-space-indented, no alias/env on the same line
    for m in re.finditer(r"^    ([a-z]\w*)\s*:", text, re.MULTILINE):
        name = m.group(1)
        if name in _NESTED_CONFIG_FIELDS:
            continue
        line_end = text.find("\n", m.start())
        line = text[m.start():line_end]
        if 'alias="' not in line and 'env="' not in line:
            env_vars.add(name.upper())

    return env_vars


def check_config_coverage(readme_text: str) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for env vars missing from README.md."""
    env_vars = extract_config_env_vars()
    if not env_vars:
        return [], []

    errors: list[str] = []
    for var in sorted(env_vars):
        if f"`{var}`" not in readme_text and var not in readme_text:
            errors.append(
                f"[CONFIG DRIFT] {var} is defined in src/config.py but not documented in README.md"
            )
    return errors, []


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not FEATURES_DIR.is_dir():
        print(f"ERROR: {FEATURES_DIR} not found — run from the repo root.", file=sys.stderr)
        return 1
    if not ROADMAP_FILE.is_file():
        print(f"ERROR: {ROADMAP_FILE} not found — run from the repo root.", file=sys.stderr)
        return 1

    roadmap_text = ROADMAP_FILE.read_text()
    roadmap_linked_files = set(ROADMAP_LINK_RE.findall(roadmap_text))

    readme_text = README_FILE.read_text() if README_FILE.is_file() else ""

    spec_files = sorted(
        f for f in FEATURES_DIR.glob("*.md") if f.name != TEMPLATE_NAME
    )

    # ── Check 1: every spec has a '> Status:' line ──────────────────────────
    spec_statuses: dict[str, str] = {}
    for spec in spec_files:
        text = spec.read_text()
        status = extract_status(text)
        if status is None:
            errors.append(
                f"[MISSING STATUS] {spec}: no '> Status:' line found. "
                "Add '> Status: **Planned** | Priority: ... | Last reviewed: ...' near the top."
            )
        else:
            spec_statuses[spec.name] = status

    # ── Check 2: Implemented specs must NOT be in roadmap ───────────────────
    for spec_name, status in spec_statuses.items():
        is_implemented = any(s in status for s in IMPLEMENTED_STATUSES)
        if is_implemented and spec_name in roadmap_linked_files:
            errors.append(
                f"[STALE ROADMAP] features/{spec_name} is Implemented but still "
                "listed in docs/roadmap.md — remove the roadmap row."
            )

    # ── Check 3: every roadmap link resolves to a real file ─────────────────
    for linked_name in sorted(roadmap_linked_files):
        linked_path = FEATURES_DIR / linked_name
        if not linked_path.is_file():
            errors.append(
                f"[BROKEN LINK] docs/roadmap.md links to features/{linked_name} "
                "but the file does not exist."
            )

    # ── Check 4: Planned/Proposed/Approved specs must be in roadmap ─────────
    for spec_name, status in spec_statuses.items():
        needs_roadmap = any(s in status for s in ROADMAP_REQUIRED_STATUSES)
        if needs_roadmap and spec_name not in roadmap_linked_files:
            warnings.append(
                f"[MISSING ROADMAP ENTRY] features/{spec_name} has status '{status}' "
                "but is not listed in docs/roadmap.md — add a roadmap row."
            )

    # ── Check 5: every config.py env var is documented in README.md ─────────
    cfg_errors, cfg_warnings = check_config_coverage(readme_text)
    errors.extend(cfg_errors)
    warnings.extend(cfg_warnings)

    # ── Report ────────────────────────────────────────────────────────────────
    for w in warnings:
        print(f"⚠  {w}")
    for e in errors:
        print(f"✗  {e}")

    if not errors and not warnings:
        print(f"✓  docs lint passed — {len(spec_files)} specs checked, roadmap consistent, README config coverage complete.")
        return 0

    print(
        f"\nResult: {len(errors)} error(s), {len(warnings)} warning(s) "
        f"across {len(spec_files)} specs."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
