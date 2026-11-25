#!/usr/bin/env python3
"""Keep formatting cleanup from consuming a note's content-repair budget."""

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
SCREEN_LINE = "[01:44][画面] mattpocock/skills"
SCREEN_NOTE = NOTE.replace(
    "## 翻车或别用\n", "画面给出了仓库路径。 ⏱ 01:44\n\n## 翻车或别用\n", 1,
) + f"> {SCREEN_LINE}\n"


class SubmissionFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def job(self, note: str = NOTE) -> Path:
        job = self.root / "task"
        job.mkdir()
        (job / "note.md").write_bytes(note.encode("utf-8"))
        (job / "transcript.txt").write_bytes(TRANSCRIPT.encode("utf-8"))
        (job / "screen.txt").write_bytes((SCREEN_LINE + "\n").encode("utf-8"))
        (job / "selection.md").write_bytes((ROOT / "evals/fixtures/usable_selection.md").read_bytes())
        (job / "status.json").write_text(json.dumps({
            "status": "transcript_ready", "duration_seconds": 120, "expected_lang": "en",
            "screen_ocr": {"mode": "slides", "state": "ready", "sha256": hashlib.sha256((SCREEN_LINE + "\n").encode()).hexdigest()},
        }), encoding="utf-8")
        return job

    def status(self, job: Path) -> dict:
        return json.loads((job / "status.json").read_text(encoding="utf-8"))

    def command(self, script: str, *arguments: str, mode: str = "slides") -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *arguments],
            cwd=ROOT, env=dict(os.environ, TFV_SCREEN_MODE=mode),
            capture_output=True, encoding="utf-8", timeout=30,
        )
        print(json.dumps({"command": result.args, "screen_mode": mode, "exit": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr}, ensure_ascii=False))
        return result

    def verify(self, job: Path, mode: str = "slides") -> tuple[int, dict]:
        result = self.command("verify_note.py", "--job", str(job), "--json", mode=mode)
        self.assertTrue(result.stdout, result)
        return result.returncode, json.loads(result.stdout)

    def assert_passes_without_repair(self, job: Path, expected_note: str) -> dict:
        code, result = self.verify(job)
        self.assertEqual(code, 0, result["reasons"])
        self.assertTrue(result["allowed"], result)
        self.assertEqual((job / "note.md").read_bytes(), expected_note.encode("utf-8"))
        status = self.status(job)
        self.assertEqual(status["repair_rounds"], 0, status)
        self.assertEqual(status["edit_rounds"], 1, status)
        self.assertEqual(status["verifier"]["inputs"]["note_file"], hashlib.sha256(expected_note.encode()).hexdigest())
        return status

    def test_missing_speech_separator_is_written_back_before_first_submission(self) -> None:
        unformatted = NOTE.replace("> [00:30] Snip", "> [00:30]Snip", 1)
        self.assertNotEqual(unformatted, NOTE)
        self.assert_passes_without_repair(self.job(unformatted), NOTE)

    def test_missing_screen_tag_separator_is_written_back(self) -> None:
        # The real screen row was already valid in slides mode. This variant
        # checks cleanup and write-back, not a claim about that historical failure.
        unformatted = SCREEN_NOTE.replace("> [01:44][画面] mattpocock/skills", "> [01:44][画面]mattpocock/skills", 1)
        self.assert_passes_without_repair(self.job(unformatted), SCREEN_NOTE)

    def test_structural_fullwidth_timestamp_colon_is_written_back(self) -> None:
        unformatted = NOTE.replace("> [00:30] Snip", "> [00：30] Snip", 1)
        self.assert_passes_without_repair(self.job(unformatted), NOTE)

    def test_actual_screen_row_passes_when_slides_are_enabled(self) -> None:
        self.assert_passes_without_repair(self.job(SCREEN_NOTE), SCREEN_NOTE)

    def test_explicit_off_does_not_become_a_formatting_success(self) -> None:
        job = self.job(SCREEN_NOTE)
        code, result = self.verify(job, "off")
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any(reason.startswith("R04 FAIL:") for reason in result["reasons"]), result)
        self.assertEqual(self.status(job)["repair_rounds"], 1)
        self.assertEqual((job / "note.md").read_bytes(), SCREEN_NOTE.encode("utf-8"))

    def test_changed_quote_text_is_refused_and_counts_as_a_failure(self) -> None:
        changed = NOTE.replace("> [00:30] Snip the black", "> [00:30] Preserve the black", 1)
        job = self.job(changed)
        code, result = self.verify(job)
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any(reason.startswith("R04 FAIL:") for reason in result["reasons"]), result)
        self.assertEqual((job / "note.md").read_bytes(), changed.encode("utf-8"))
        self.assertEqual(self.status(job)["repair_rounds"], 1)
        self.assertEqual(self.status(job)["edit_rounds"], 1)

    def test_format_cleanup_cannot_replace_changed_words_with_the_source(self) -> None:
        changed = NOTE.replace("> [00:30] Snip the black", "> [00:30] Preserve the black", 1)
        unformatted = changed.replace("> [00:30] Preserve", "> [00:30]Preserve", 1)
        job = self.job(unformatted)
        code, result = self.verify(job)
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any(reason.startswith("R04 FAIL:") for reason in result["reasons"]), result)
        self.assertEqual((job / "note.md").read_bytes(), changed.encode("utf-8"))
        self.assertEqual(self.status(job)["repair_rounds"], 1)
        self.assertEqual(self.status(job)["edit_rounds"], 1)

    def test_format_only_change_after_content_failure_does_not_add_an_edit(self) -> None:
        changed = NOTE.replace("> [00:30] Snip the black", "> [00:30] Preserve the black", 1)
        job = self.job(changed)
        code, result = self.verify(job)
        self.assertNotEqual(code, 0, result)
        self.assertEqual(self.status(job)["edit_rounds"], 1)
        (job / "note.md").write_bytes(changed.replace("> [00:30] Preserve", "> [00:30]Preserve", 1).encode("utf-8"))
        code, result = self.verify(job)
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any(reason.startswith("R04 FAIL:") for reason in result["reasons"]), result)
        self.assertEqual(self.status(job)["edit_rounds"], 1)
        self.assertEqual(self.status(job)["repair_rounds"], 1)
        self.assertEqual((job / "note.md").read_bytes(), changed.encode("utf-8"))

    def test_renderer_checks_and_renders_the_cleaned_note_in_one_run(self) -> None:
        unformatted = NOTE.replace("> [00:30] Snip", "> [00:30]Snip", 1)
        job = self.job(unformatted)
        reading = self.root / "reading.md"
        result = self.command("render_reading_note.py", "--task-dir", str(job), "--output", str(reading))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(reading.is_file(), result)
        self.assertEqual((job / "note.md").read_bytes(), NOTE.encode("utf-8"))
        status = self.status(job)
        self.assertTrue(status["finished"], status)
        self.assertEqual(status["repair_rounds"], 0, status)
        self.assertEqual(status["edit_rounds"], 1, status)
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])
        self.assertEqual(status["verifier"]["inputs"]["note_file"], hashlib.sha256(NOTE.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
