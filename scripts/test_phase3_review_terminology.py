"""Regression fixtures for the Task instructions, separate from the renderer."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals/fixtures/phase3-review-terminology"
HEADING = "## 未解释的术语和基础词"
EMPTY = "已逐节查过，没有"
ROW_FORMAT = "词 | 首次出现的小节 | 原句"


def sections(markdown):
    current = None
    contents = {}
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = line
            contents[current] = []
        elif current is not None and line.strip():
            contents[current].append(line)
    return contents


def follows_reference(note, receipt, expected_terms):
    """Compare against the hand-listed fixture evidence, without guessing terms."""
    rows = sections(receipt).get(HEADING)
    if not expected_terms:
        return rows == [EMPTY]
    note_sections = sections(note)
    expected_rows = []
    for term, section, original in expected_terms:
        assert term in original and original in note_sections[f"## {section}"]
        expected_rows.append(f"- {term} | {section} | {original}")
    return rows == expected_rows


class TerminologyInstructionsTests(unittest.TestCase):
    def test_task_prompt_requires_a_located_section_and_an_explicit_empty_result(self):
        rules = (ROOT / "references/rules.md").read_text(encoding="utf-8")
        review = rules.split("## Independent semantic review", 1)[1]
        for requirement in (HEADING, ROW_FORMAT, EMPTY):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, review)

    def test_review_examples_match_the_reference_findings(self):
        findings = (
            ("QMF", "登记输入", "先在 QMF 表里登记队列的负责人。"),
            ("跳线表", "检查连接", "接着查看跳线表，确认编号与设备一致。"),
        )
        for note, receipt, terms, expected in (
            ("unexplained-note.md", "bad-missing-section.md", findings, False),
            ("unexplained-note.md", "bad-false-empty.md", findings, False),
            ("unexplained-note.md", "good-complete.md", findings, True),
            ("plain-note.md", "good-empty.md", (), True),
        ):
            with self.subTest(receipt=receipt):
                self.assertEqual(
                    follows_reference(
                        (FIXTURES / note).read_text(encoding="utf-8"),
                        (FIXTURES / receipt).read_text(encoding="utf-8"),
                        terms,
                    ),
                    expected,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
