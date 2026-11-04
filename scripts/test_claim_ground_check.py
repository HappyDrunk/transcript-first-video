#!/usr/bin/env python3
"""Counts API for claim_ground_check. Synthetic fixture notes only.

No gold notes. No language model. Asserts unsupported_count and sentences.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import claim_ground_check as ground

QUOTE = (
    "Export the overnight file before standup and delete the duplicate tab "
    "before you email anyone."
)
GROUNDED = (
    "Export the overnight file before standup and delete the duplicate tab."
)
OTHER_QUOTE = (
    "Stop the feed because the soil stayed wet for three days after watering."
)
CAUSAL = "Stop the feed because the soil stayed wet."
LOOSE = "Acme moved 42 pallets because demand spiked overnight in the east warehouse."


def _note(*sections: tuple[str, str, str]) -> str:
    lines = [
        "---",
        'title: "fixture"',
        'video_id: "vidfixture"',
        "---",
        "",
    ]
    for heading, prose, quote in sections:
        lines.extend([f"## {heading}", "", prose, ""])
        if quote:
            lines.extend([f"> {quote}", ""])
    return "\n".join(lines)


class ClaimGroundCountTests(unittest.TestCase):
    def test_script_uses_pathlib_and_has_no_drive_root_write(self) -> None:
        source = Path(ground.__file__).read_text(encoding="utf-8")
        self.assertIn("from pathlib import Path", source)
        self.assertNotIn('Path("C:', source)
        self.assertNotIn("Path('C:", source)
        self.assertNotIn("C:\\", source)
        self.assertNotIn("C:/", source)
        self.assertNotIn("E:/", source)
        self.assertNotIn("E:\\", source)

    def test_counts_api_on_synthetic_fixtures(self) -> None:
        grounded = _note(
            ("问题与做法", GROUNDED, QUOTE),
            ("完整怎么做", "本节不适用：原文没有分步骤。", ""),
            ("翻车或别用", CAUSAL, OTHER_QUOTE),
            ("今天立刻动手一步", "转写未给出可以今天执行的一步。", QUOTE),
        )
        loose = _note(
            ("问题与做法", LOOSE, QUOTE),
            ("完整怎么做", "The count is 42.", OTHER_QUOTE),
            ("翻车或别用", "本节不适用：原文没有别用边界。", ""),
            ("今天立刻动手一步", GROUNDED, QUOTE),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grounded_path = root / "grounded.md"
            loose_path = root / "loose.md"
            grounded_path.write_text(grounded, encoding="utf-8")
            loose_path.write_text(loose, encoding="utf-8")

            held = ground.check_file(grounded_path)
            missed = ground.check_file(loose_path)

        for row in (held, missed):
            self.assertEqual(set(row), {"file", "sentences", "unsupported_count", "sections"})
            self.assertIsInstance(row["unsupported_count"], int)
            self.assertIsInstance(row["sentences"], int)
            self.assertGreater(row["sentences"], 0)
            self.assertLessEqual(row["unsupported_count"], row["sentences"])

        self.assertEqual(held["unsupported_count"], 0)
        self.assertGreaterEqual(held["sentences"], 4)
        self.assertEqual(missed["unsupported_count"], 2)
        problem = missed["sections"]["问题与做法"]
        self.assertEqual(problem["unsupported_sentences"], 1)
        self.assertGreaterEqual(problem["issue_kinds"].get("number", 0), 1)
        self.assertGreaterEqual(problem["issue_kinds"].get("proper", 0), 1)
        steps = missed["sections"]["完整怎么做"]
        self.assertEqual(steps["unsupported_sentences"], 1)
        self.assertGreaterEqual(steps["issue_kinds"].get("number", 0), 1)
        self.assertEqual(steps["n_quotes"], 1)
        self.assertEqual(missed["sections"]["今天立刻动手一步"]["unsupported_sentences"], 0)

    def test_summary_json_is_counts_only(self) -> None:
        note = _note(("问题与做法", LOOSE, QUOTE))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note_path = root / "A_v03_r1.md"
            note_path.write_text(
                note.replace('video_id: "vidfixture"', 'video_id: "abc123"'),
                encoding="utf-8",
            )
            jobs = root / "jobs" / "youtube_abc123"
            jobs.mkdir(parents=True)
            (jobs / "transcript.txt").write_text(QUOTE + "\n", encoding="utf-8")
            out = root / "summary.json"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = ground.main(
                    [
                        str(root),
                        "--jobs-root",
                        str(root / "jobs"),
                        "--quiet",
                        "--out",
                        str(out),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertNotIn(LOOSE, buf.getvalue())
            payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(
            set(payload),
            {"n_files", "total_unsupported", "total_sentences", "per_file"},
        )
        self.assertEqual(payload["n_files"], 1)
        self.assertEqual(payload["total_unsupported"], 1)
        self.assertGreaterEqual(payload["total_sentences"], 1)
        blob = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(LOOSE, blob)
        self.assertNotIn("Acme", blob)
        self.assertNotIn("gold", blob.casefold())


if __name__ == "__main__":
    unittest.main()
