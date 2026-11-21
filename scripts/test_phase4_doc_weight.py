#!/usr/bin/env python3
"""RED contracts for Phase 4 documentation weight and role separation."""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import install_check
import verify_rules

ROOT = Path(__file__).resolve().parents[1]
WRITER_REQUIRED = ("SKILL.md", "references/delivery-format.md", "references/rules.md")


def read_text(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def h2_section(document, heading):
    lines = document.splitlines(keepends=True)
    in_fence = False
    start = None
    for index, line in enumerate(lines):
        if line.startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        if start is None:
            if line.rstrip("\n") == heading:
                start = index
        elif line.startswith("## "):
            return "".join(lines[start:index])
    return "" if start is None else "".join(lines[start:])


class DocWeightTests(unittest.TestCase):
    def test_writer_required_files_lf_and_within_30kb_cap(self):
        sizes = {}
        for relative in WRITER_REQUIRED:
            raw = (ROOT / relative).read_bytes()
            self.assertNotIn(b"\r", raw, relative)
            raw.decode("utf-8")
            sizes[relative] = len(raw)
        total = sum(sizes.values())
        details = ", ".join(f"{name}={size}" for name, size in sizes.items())
        self.assertLessEqual(total, 30_720, f"{details}; total={total}")

    def test_review_guide_exists_lf_and_within_8kb_cap(self):
        path = ROOT / "references/review-guide.md"
        self.assertTrue(path.is_file(), path)
        raw = path.read_bytes()
        self.assertNotIn(b"\r", raw)
        document = raw.decode("utf-8")
        self.assertLessEqual(len(raw), 8_192)
        for heading in ("## Independent semantic review", "### 独立复核回执与计轮", "### C04c 告警裁定"):
            self.assertIn(heading, document)

    def test_gitattributes_pins_role_docs_to_lf(self):
        files = [*WRITER_REQUIRED, "references/review-guide.md"]
        result = subprocess.run(
            ["git", "check-attr", "-z", "text", "eol", "--", *files],
            cwd=ROOT, capture_output=True, check=True,
        )
        fields = result.stdout.decode("utf-8").split("\0")[:-1]
        attributes = {(path, name): value for path, name, value in zip(
            fields[::3], fields[1::3], fields[2::3], strict=True,
        )}
        unpinned = [path for path in files if
                    (attributes[path, "text"], attributes[path, "eol"]) != ("set", "lf")]
        self.assertEqual(unpinned, [], ".gitattributes must pin role docs to LF")

    def test_skill_canonical_role_lines_and_run_step_paths(self):
        skill = read_text("SKILL.md")
        writer = "<!-- tfv-writer-required: SKILL.md, references/delivery-format.md, references/rules.md -->"
        reviewer = "<!-- tfv-reviewer-required: references/review-guide.md -->"
        self.assertEqual(skill.count(writer), 1)
        self.assertEqual(skill.count(reviewer), 1)
        run = h2_section(skill, "## Run")
        positions = [run.find(f"\n{number}. ") for number in range(1, 11)]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        step_three = run.split("\n3. ", 1)[1].split("\n4. ", 1)[0]
        self.assertIn("references/rules.md", step_three)
        self.assertIn("references/delivery-format.md", step_three)
        step_seven = run.split("\n7. ", 1)[1].split("\n8. ", 1)[0]
        self.assertIn("references/review-guide.md", step_seven)
        self.assertNotIn("references/rules.md", step_seven)

    def test_delivery_format_excerpt_section_limit_and_plain_contrast_verbatim(self):
        delivery = read_text("references/delivery-format.md")
        section = h2_section(delivery, "## 范例节选")
        self.assertTrue(section.strip())
        self.assertLessEqual(len(section.encode("utf-8")), 5_120)
        self.assertIn("通俗版合成片段", section)
        note = read_text("evals/fixtures/delivery-examples/synthetic-cold-dough/note.md")
        pieces = (
            "## 先记住一句话\n先让面团在冰箱里慢慢发起，取出回温，再检查面团和成品。",
            "> [!note] 术语：低温发酵（cold fermentation）\n> 让面团在较冷的环境里慢慢发起，便于安排发面时间。（Claude 补充，非视频内容）",
            "## 今天立刻动手一步\n把冷藏和回温的开始时间写到你今天的备料单上。（改写讲者做法） ⏱ 01:10 ⏱ 03:20",
        )
        for piece in pieces:
            self.assertIn(piece, note)
            self.assertIn(piece, section)

    def test_writer_required_docs_exclude_forbidden_substrings(self):
        forbidden = ("x_host.py", "FX_TWITTER_API", "Twitter", "language.txt", "R01–R17", "R01 到 R17")
        failures = []
        for relative in WRITER_REQUIRED:
            for number, line in enumerate(read_text(relative).splitlines(), 1):
                for token in forbidden:
                    if token in line:
                        failures.append(f"{relative}:{number}: {token}: {line}")
        self.assertEqual(failures, [])

    def test_rules_index_table_matches_active_rules_and_excludes_review_guide(self):
        verify_ids = set()
        for function in verify_rules.RULES:
            match = re.match(r"^([rc]\d+[a-z]?)_", function.__name__)
            self.assertIsNotNone(match, function.__name__)
            rule_id = match.group(1)
            verify_ids.add(rule_id[0].upper() + rule_id[1:])
        coverage = read_text("scripts/coverage_check.py")
        self.assertIn("C02", coverage)
        self.assertIn("S01", coverage)
        rules = read_text("references/rules.md")
        table_ids = []
        for line in rules.splitlines():
            if not line.startswith("|"):
                continue
            first = line.split("|", 2)[1].strip().strip("`")
            if first in ("Rule", "规则") or re.fullmatch(r"[-:]+", first):
                continue
            table_ids.append(first)
        self.assertEqual(len(table_ids), len(set(table_ids)), table_ids)
        self.assertEqual(set(table_ids), verify_ids | {"C02", "S01"})
        self.assertNotIn("## Independent semantic review", rules)
        self.assertNotIn("### C04c 告警裁定", rules)

    def test_skill_preserves_required_run_phrases_and_youtube_description(self):
        skill = read_text("SKILL.md")
        frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", skill, re.DOTALL)
        self.assertIsNotNone(frontmatter)
        description = next(line for line in frontmatter.group(1).splitlines()
                           if line.startswith("description:"))
        for phrase in ("YouTube", "summarize", "extract", "needs-transcript", "通读"):
            self.assertIn(phrase, description)
        self.assertNotIn("Twitter", description)
        self.assertNotIn("X/", description)
        run = h2_section(skill, "## Run")
        lowered = run.lower()
        self.assertIn("steps, conditions, and claims within the cited evidence", lowered)
        self.assertIn("retained lists and cases", lowered)
        self.assertIn("explain essential terms at first use", lowered)
        step_one = run.split("\n1. ", 1)[1].split("\n2. ", 1)[0]
        self.assertIn("--group base", step_one)
        self.assertIn("--group screen", step_one)
        self.assertNotIn("on demand", step_one.lower())
        self.assertNotIn("按需", step_one.lower())

    def test_install_check_requires_review_guide_not_synthetic_examples(self):
        self.assertIn("references/review-guide.md", install_check.FALLBACK_FILES)
        self.assertNotIn("references/synthetic-examples.md", install_check.FALLBACK_FILES)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            for relative in (*install_check.FALLBACK_FILES, "SKILL.md"):
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            command = [sys.executable, str(destination / "scripts/install_check.py")]
            complete = subprocess.run(command, cwd=destination, capture_output=True, text=True)
            self.assertEqual(complete.returncode, 0, complete.stdout + complete.stderr)
            (destination / "references/review-guide.md").unlink()
            missing = subprocess.run(command, cwd=destination, capture_output=True, text=True)
            self.assertNotEqual(missing.returncode, 0, missing.stdout + missing.stderr)
            self.assertIn("references/review-guide.md", missing.stderr)

    def test_readme_marks_delivery_examples_as_test_fixtures(self):
        readme = read_text("README.md")
        self.assertIn("evals/fixtures/delivery-examples/", readme)
        self.assertNotIn("four synthetic examples", readme)
        self.assertNotIn("四个示例", readme)
        self.assertRegex(readme, re.compile(r"test fixture|测试夹具", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
