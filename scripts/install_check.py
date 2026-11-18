#!/usr/bin/env python3
"""Check that an installed transcript-first-video skill is complete."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# These paths let the check work on a copied source directory that has no .git.
# In a checkout, git's tracked-file list also catches files added in later releases.
FALLBACK_FILES = (
    "scripts/claim_ground_check.py",
    "scripts/coverage_check.py",
    "scripts/install_check.py",
    "scripts/knowledge_note.py",
    "scripts/quality_gate.py",
    "scripts/render_reading_note.py",
    "scripts/run_evidence.py",
    "scripts/screen_ocr.py",
    "scripts/smoke.sh",
    "scripts/test_claim_ground_check.py",
    "scripts/test_coverage_check.py",
    "scripts/test_gate.py",
    "scripts/test_no_overfit.py",
    "scripts/test_regressions.py",
    "scripts/verify_note.py",
    "scripts/verify_report.py",
    "scripts/verify_rules.py",
    "scripts/x_host.py",
    "scripts/youtube_host.py",
    "references/delivery-format.md",
    "references/host-delivery.md",
    "references/note-examples.md",
    "references/pitfalls.md",
    "references/rules.md",
)


def required_files(root: Path) -> list[str]:
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        ).stdout.strip()
        if Path(top).resolve() != root.resolve():
            return list(FALLBACK_FILES)
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "scripts", "references"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        tracked = [name for name in result.stdout.split("\0") if name]
        files = set(tracked)
        files.add("scripts/install_check.py")
        return sorted(files)
    except (OSError, subprocess.SubprocessError):
        return list(FALLBACK_FILES)


def skill_version(root: Path) -> str:
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        ).stdout.strip()
        if Path(top).resolve() != root.resolve():
            raise subprocess.CalledProcessError(1, "git rev-parse --show-toplevel")
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        commit = result.stdout.strip()
        if commit:
            return commit
    except (OSError, subprocess.SubprocessError):
        pass
    version_file = root / "VERSION"
    if version_file.is_file():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version
    return "unknown"


def main() -> int:
    print(f"skill_version: {skill_version(ROOT)}")
    missing = [name for name in required_files(ROOT) if not (ROOT / name).is_file()]
    if missing:
        print("Missing required installation files:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1
    print("Installation check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
