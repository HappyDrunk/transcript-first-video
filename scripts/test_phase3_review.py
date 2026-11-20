#!/usr/bin/env python3
"""Freeze the bounded review correction after ordinary draft allowance is used."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_phase2e import NOTE, TRANSCRIPT


ROOT = Path(__file__).resolve().parents[1]
INITIAL_BAD = NOTE.replace("> [00:30] Snip the black", "> [00:30] Preserve the black", 1)
REVIEW_FIXED = NOTE.replace(
    "Protect the firm roots and let the new pot drain.",
    "Keep the firm roots and let the new pot drain.", 1,
)
REVIEW_BAD = REVIEW_FIXED.replace("## 翻车或别用", "## 使用限制", 1)
REVIEW_BAD_AGAIN = REVIEW_BAD.replace("Keep the firm roots", "Save the firm roots", 1)


class ReviewCorrectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.job = self.root / "task"
        self.job.mkdir()
        self.output = self.root / "reading.md"
        (self.job / "transcript.txt").write_bytes(TRANSCRIPT.encode("utf-8"))
        (self.job / "selection.md").write_bytes((ROOT / "evals/fixtures/usable_selection.md").read_bytes())
        (self.job / "status.json").write_text(json.dumps({
            "status": "transcript_ready", "expected_lang": "en", "duration_seconds": 120,
        }), encoding="utf-8")

    def status(self) -> dict:
        return json.loads((self.job / "status.json").read_text(encoding="utf-8"))

    def note(self, text: str) -> None:
        (self.job / "note.md").write_bytes(text.encode("utf-8"))

    def command(self, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *arguments],
            cwd=ROOT, env=dict(os.environ, TFV_SCREEN_MODE="off"),
            capture_output=True, encoding="utf-8", timeout=30,
        )
        print(json.dumps({"command": result.args, "exit": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr,
                          "status": self.status()}, ensure_ascii=False))
        return result

    def submit(self) -> tuple[int, dict]:
        result = self.command("verify_note.py", "--job", str(self.job), "--with-coverage", "--json")
        self.assertTrue(result.stdout, result)
        return result.returncode, json.loads(result.stdout)

    def render(self) -> subprocess.CompletedProcess[str]:
        return self.command("render_reading_note.py", "--task-dir", str(self.job), "--output", str(self.output))

    def ordinary_allowance_used(self, failures: int = 1) -> dict:
        self.note(INITIAL_BAD)
        for failure in range(1, failures + 1):
            code, result = self.submit()
            self.assertNotEqual(code, 0, result)
            self.assertTrue(any(reason.startswith("R04 FAIL:") for reason in result["reasons"]), result)
            status = self.status()
            self.assertEqual((status["edit_rounds"], status["repair_rounds"]), (1, failure), status)
            self.assertFalse(status.get("locked"), status)
        self.note(NOTE.replace("\n---\n", "\nrevision: ordinary draft two\n---\n", 1))
        code, result = self.submit()
        self.assertEqual(code, 0, result["reasons"])
        self.note(NOTE)
        code, result = self.submit()
        self.assertEqual(code, 0, result["reasons"])
        status = self.status()
        self.assertTrue(status["finished"], status)
        self.assertEqual((status["edit_rounds"], status["repair_rounds"]), (3, failures), status)
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])
        return status["verifier"]["inputs"]

    def review(self, inputs: dict) -> None:
        receipt = {"inputs": inputs, "result": "changes"}
        (self.job / "review.md").write_text(
            f"<!-- tfv-review: {json.dumps(receipt, ensure_ascii=False)} -->\n"
            "# 独立复核\n\n先记住一句话需调整表达，保持原有的根系处理与排水做法。\n",
            encoding="utf-8",
        )

    def first_review_check_fails(self, initial_failures: int) -> None:
        inputs = self.ordinary_allowance_used(initial_failures)
        self.review(inputs)
        self.note(REVIEW_BAD)
        result = self.render()
        self.assertNotEqual(result.returncode, 0, result)
        self.assertIn("C04a FAIL:", result.stdout + result.stderr)
        status = self.status()
        self.assertEqual(status["edit_rounds"], 3, status)
        self.assertEqual(status["repair_rounds"], initial_failures + 1, status)
        self.assertEqual(status.get("review_rounds"), 1, status)
        self.assertFalse(status.get("locked"), status)
        self.assertNotEqual(status["status"], "not_deposited", status)
        self.assertFalse(status["finished"], status)
        self.assertFalse(self.output.exists())

    def assert_review_correction_finishes(self, initial_failures: int) -> None:
        self.note(REVIEW_FIXED)
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.output.is_file(), result)
        self.assertIn("Keep the firm roots", self.output.read_text(encoding="utf-8"))
        self.assertNotIn("⏱", self.output.read_text(encoding="utf-8"))
        self.assertEqual((self.job / "note.md").read_bytes(), REVIEW_FIXED.encode("utf-8"))
        status = self.status()
        self.assertTrue(status["finished"], status)
        self.assertFalse(status.get("locked"), status)
        self.assertEqual(status["edit_rounds"], 3, status)
        self.assertEqual(status["repair_rounds"], initial_failures + 1, status)
        self.assertEqual(status.get("review_rounds"), 1, status)
        self.assertTrue(status["verifier"]["allowed"], status)
        self.assertTrue(status["coverage"]["allowed"], status)
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])
        self.assertEqual(status["verifier"]["inputs"]["note_file"], hashlib.sha256(REVIEW_FIXED.encode()).hexdigest())

    def test_review_failure_allows_one_bound_correction_and_reading_delivery(self) -> None:
        self.first_review_check_fails(initial_failures=1)
        self.assert_review_correction_finishes(initial_failures=1)

    def test_corrected_review_fixture_is_mechanically_valid_as_an_ordinary_first_draft(self) -> None:
        self.note(REVIEW_FIXED)
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.output.is_file())
        status = self.status()
        self.assertTrue(status["finished"], status)
        self.assertEqual((status["edit_rounds"], status["repair_rounds"]), (1, 0), status)
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])

    def test_second_review_failure_locks_the_task(self) -> None:
        self.first_review_check_fails(initial_failures=1)
        self.note(REVIEW_BAD_AGAIN)
        result = self.render()
        self.assertNotEqual(result.returncode, 0, result)
        self.assertIn("C04a FAIL:", result.stdout + result.stderr)
        status = self.status()
        self.assertEqual(status["edit_rounds"], 3, status)
        self.assertEqual(status["repair_rounds"], 3, status)
        self.assertEqual(status.get("review_rounds"), 1, status)
        self.assertTrue(status.get("locked"), status)
        self.assertEqual(status["status"], "not_deposited", status)
        self.assertFalse(status["finished"], status)
        self.assertFalse(self.output.exists())

        self.note(REVIEW_FIXED)
        result = self.render()
        self.assertNotEqual(result.returncode, 0, result)
        after = self.status()
        self.assertEqual((after["edit_rounds"], after["repair_rounds"]), (3, 3), after)
        self.assertTrue(after.get("locked"), after)
        self.assertFalse(self.output.exists())

    def test_first_review_failure_at_two_previous_failures_still_allows_the_bound_correction(self) -> None:
        self.first_review_check_fails(initial_failures=2)
        self.assert_review_correction_finishes(initial_failures=2)

    def test_unmarked_legacy_review_does_not_unlock_a_fourth_ordinary_draft(self) -> None:
        self.ordinary_allowance_used()
        (self.job / "review.md").write_text("# 旧复核记录\n\n建议调整开头表达。\n", encoding="utf-8")
        self.note(REVIEW_FIXED)
        result = self.render()
        self.assertNotEqual(result.returncode, 0, result)
        status = self.status()
        self.assertEqual(status["edit_rounds"], 4, status)
        self.assertEqual(status["repair_rounds"], 1, status)
        self.assertTrue(status.get("locked"), status)
        self.assertEqual(status["status"], "not_deposited", status)
        self.assertFalse(status["finished"], status)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
