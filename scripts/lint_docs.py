#!/usr/bin/env python3
"""Docs lint script — keeps roadmap and feature specs in sync.

Checks:
  1. Every feature spec (except _template.md) has a '> Status:' line.
  2. Every Implemented spec is NOT listed in docs/roadmap.md.
  3. Every roadmap feature link resolves to a real file.
  4. Every non-Implemented/non-Approved spec that has a feature file is in the roadmap.

Exit codes: 0 = all good, 1 = one or more violations found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FEATURES_DIR = Path("docs/features")
ROADMAP_FILE = Path("docs/roadmap.md")
TEMPLATE_NAME = "_template.md"

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

    # ── Report ────────────────────────────────────────────────────────────────
    for w in warnings:
        print(f"⚠  {w}")
    for e in errors:
        print(f"✗  {e}")

    if not errors and not warnings:
        print(f"✓  docs lint passed — {len(spec_files)} specs checked, roadmap consistent.")
        return 0

    print(
        f"\nResult: {len(errors)} error(s), {len(warnings)} warning(s) "
        f"across {len(spec_files)} specs."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
