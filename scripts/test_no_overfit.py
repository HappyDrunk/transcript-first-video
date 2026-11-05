#!/usr/bin/env python3
"""Fail if scripts/ or SKILL.md contains retired or eval-set tokens.

The patterns live in evals/overfit_blacklist.txt, one per line. This file
does not contain them. Matching is case-insensitive. CJK patterns have no
case, and the same flag is harmless for them. SKILL.md is the instruction
file injected with the skill. The receipt under evals/results/ is not scanned.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
BLACKLIST = ROOT / "evals" / "overfit_blacklist.txt"
INSTRUCTION_FILES = (
    ROOT / "SKILL.md",
    ROOT / "references" / "note-examples.md",
)
_SKIP_PARTS = {"__pycache__"}
_SKIP_NAMES = {"test_no_overfit.py", "overfit_blacklist.txt"}


def load_patterns(path: Path = BLACKLIST) -> list[str]:
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns


def compile_blacklist(patterns: list[str]) -> re.Pattern[str]:
    if not patterns:
        raise ValueError(f"no patterns in {BLACKLIST}")
    body = "|".join(f"(?:{re.escape(pattern)})" for pattern in patterns)
    return re.compile(body, re.IGNORECASE)


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def scan_text(path: Path, text: str, pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for match in pattern.finditer(text):
        line_no = text.count("\n", 0, match.start()) + 1
        hits.append(f"{_display(path)}:{line_no}: {match.group(0)}")
    return hits


def scan_file(path: Path, pattern: re.Pattern[str]) -> list[str]:
    if not path.is_file():
        return [f"missing {_display(path)}"]
    return scan_text(path, path.read_text(encoding="utf-8", errors="replace"), pattern)


def scan_tree(root: Path, pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if _SKIP_PARTS.intersection(path.parts) or path.name in _SKIP_NAMES:
            continue
        if path.suffix == ".pyc":
            continue
        hits.extend(scan_file(path, pattern))
    return hits


class NoOverfitTests(unittest.TestCase):
    def test_blacklist_lives_outside_scripts(self) -> None:
        self.assertTrue(BLACKLIST.is_file(), BLACKLIST)
        self.assertNotIn("scripts", BLACKLIST.resolve().relative_to(ROOT.resolve()).parts)
        self.assertGreaterEqual(len(load_patterns()), 7)

    def test_scripts_tree_has_no_blacklist_tokens(self) -> None:
        hits = scan_tree(SCRIPTS, compile_blacklist(load_patterns()))
        self.assertEqual(hits, [], "\n".join(hits))

    def test_skill_has_no_blacklist_tokens(self) -> None:
        self.assertTrue(INSTRUCTION_FILES)
        pattern = compile_blacklist(load_patterns())
        hits: list[str] = []
        for path in INSTRUCTION_FILES:
            self.assertTrue(path.is_file(), path)
            hits.extend(scan_file(path, pattern))
        self.assertEqual(hits, [], "\n".join(hits))

    def test_eval_leak_token_is_banned(self) -> None:
        patterns = load_patterns()
        self.assertIn("Robert Moses", patterns)
        self.assertIn("gold_sha256", patterns)
        pattern = compile_blacklist(patterns)
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "SKILL.md"
            sample.write_text("The talk hangs on Robert Moses.\n", encoding="utf-8")
            hits = scan_file(sample, pattern)
        self.assertEqual(len(hits), 1)
        self.assertIn("Robert Moses", hits[0])

    def test_scanner_flags_a_token_from_the_list(self) -> None:
        token = load_patterns()[0]
        pattern = compile_blacklist(load_patterns())
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "sample.py"
            sample.write_text(f"label = {token!r}\n", encoding="utf-8")
            hits = scan_tree(Path(tmp), pattern)
        self.assertEqual(len(hits), 1)
        self.assertIn(token, hits[0])


if __name__ == "__main__":
    result = unittest.main(exit=False)
    sys.exit(0 if result.result.wasSuccessful() else 1)
