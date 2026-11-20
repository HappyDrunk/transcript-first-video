"""Writer feedback, resumable stop, and bound C04c review through the public CLIs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_phase2e import NOTE, TRANSCRIPT
import render_reading_note


ROOT = Path(__file__).resolve().parents[1]
CLAIM = "stopping two centimeters below the rim"
BAD = NOTE.replace(CLAIM, "stopping 21.1 centimeters below the rim", 1)
HINT = "所链引文里没有这个词或数：补挂出处，或改正文"


class Phase4ReviewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.job = self.root / "job"
        self.job.mkdir()
        self.output = self.root / "reading.md"
        (self.job / "transcript.txt").write_text(TRANSCRIPT, encoding="utf-8")
        (self.job / "selection.md").write_bytes((ROOT / "evals/fixtures/usable_selection.md").read_bytes())
        (self.job / "status.json").write_text(json.dumps({
            "status": "transcript_ready", "expected_lang": "en", "duration_seconds": 120,
        }), encoding="utf-8")
        self.note(NOTE)

    def note(self, body):
        (self.job / "note.md").write_bytes(body.encode("utf-8"))

    def status(self):
        return json.loads((self.job / "status.json").read_text(encoding="utf-8"))

    def command(self, script, *args):
        result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *args],
                                cwd=ROOT, env=dict(os.environ, TFV_SCREEN_MODE="off"),
                                capture_output=True, encoding="utf-8", timeout=25)
        print(json.dumps({"args": args, "code": result.returncode, "stdout": result.stdout,
                          "stderr": result.stderr}, ensure_ascii=False))
        return result

    def submit(self, *args):
        return self.command("verify_note.py", "--job", str(self.job), "--with-coverage", "--json", *args)

    def render(self, required=True):
        args = ("--require-review",) if required else ()
        return self.command("render_reading_note.py", "--task-dir", str(self.job),
                            "--output", str(self.output), *args)

    def receipt(self, rows, *, result="clear", digest=None, followup=""):
        verifier = self.status()["verifier"]
        header = {"inputs": verifier["inputs"], "result": result,
                  "c04c_sha256": verifier.get("c04c_sha256") if digest is None else digest}
        (self.job / "review.md").write_text(
            f"<!-- tfv-review: {json.dumps(header, ensure_ascii=False)} -->\n\n"
            f"## C04c 告警裁定\n\n{rows}\n{followup}",
            encoding="utf-8",
        )

    def warning_draft(self, note=BAD):
        self.note(note)
        check = self.submit()
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        return json.loads(check.stdout)

    def break_quote(self, note, token):
        return note.replace("> [00:30] Snip the black", f"> [00:30] {token} the black", 1)

    def test_three_failed_drafts_stop_and_return_draft_and_issues_then_can_resume(self):
        for token in ("Preserve", "Replace", "Inspect"):
            self.note(self.break_quote(NOTE, token))
            self.assertNotEqual(self.submit().returncode, 0)
        status = self.status()
        self.assertEqual(status["status"], "needs_user_input")
        self.assertFalse(status["locked"])
        self.assertEqual(status["next_step"], "return-draft-and-issues")
        issues = (self.job / "issues.md").read_text(encoding="utf-8")
        self.assertIn("未通过检查 · 草稿", issues)
        self.assertIn("R04 FAIL", issues)
        self.assertIn(hashlib.sha256((self.job / "note.md").read_bytes()).hexdigest(), issues)
        self.output.write_bytes(b"prior formal reading copy")
        self.assertNotEqual(self.render().returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"prior formal reading copy")
        self.note(NOTE)
        self.assertNotEqual(self.submit().returncode, 0)
        self.assertEqual(self.submit("--resume").returncode, 0)
        self.assertTrue(self.status()["finished"])
        self.assertEqual(self.status()["repair_rounds"], 0)
        self.assertTrue(self.status().get("previous_attempts"))

    def test_second_repair_can_pass(self):
        for token in ("Preserve", "Inspect"):
            self.note(self.break_quote(NOTE, token))
            self.assertNotEqual(self.submit().returncode, 0)
        self.note(NOTE)
        self.assertEqual(self.submit().returncode, 0)
        self.assertEqual(self.status()["repair_rounds"], 2)
        self.receipt("无")
        self.assertEqual(self.render().returncode, 0)
        self.assertTrue(self.output.is_file())

    def test_writer_sees_located_warnings_and_all_linked_values_without_failure(self):
        note = BAD.replace("three days. ⏱ 01:00", "four days. ⏱ 01:00", 1)
        checked = self.warning_draft(note)
        findings = checked["c04c"]
        self.assertEqual([item["id"] for item in findings], ["C04c-001", "C04c-002"])
        self.assertEqual([item["term"] for item in findings], ["four", "21.1"])
        self.assertTrue(all(item["line"] > 0 and item["citations"] for item in findings))
        self.assertEqual(sum(HINT in message for message in checked["warnings"]), 2)
        self.assertIn("引文数值=", "\n".join(checked["warnings"]))
        self.assertTrue(checked["coverage"]["ok"])
        self.assertEqual(self.status()["repair_rounds"], 0)
        self.assertFalse(self.status()["finished"])
        self.assertNotEqual(self.render(False).returncode, 0)
        plain = self.command("verify_note.py", "--job", str(self.job), "--with-coverage")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertIn(HINT, plain.stderr)

    def test_review_must_cover_each_warning_with_exact_linked_numeric_evidence(self):
        self.warning_draft()
        good = "- C04c-001 | 21.1 | two centimeters below the rim | 误报"
        for row in ("", "无", good.replace("001", "002"), good + "\n" + good,
                    good.replace("21.1", "21"), good.replace("two centimeters below the rim", "four centimeters"),
                    good.replace("two centimeters below the rim", "below the rim"),
                    good.replace("two centimeters below the rim", "three days")):
            with self.subTest(row=row):
                self.receipt(row)
                self.assertNotEqual(self.render().returncode, 0)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.status()["repair_rounds"], 0)
        self.receipt(good, digest="0" * 64)
        self.assertNotEqual(self.render().returncode, 0)
        self.receipt(good.replace("误报", "真错"), result="changes")
        self.assertNotEqual(self.render().returncode, 0)
        self.assertFalse(self.output.exists())
        self.receipt(good)
        self.assertEqual(self.render().returncode, 0)
        self.assertTrue(self.output.is_file())

    def test_normal_conversion_preserves_original_chinese_with_no_warning(self):
        note = NOTE.replace(CLAIM, "stopping 两厘米 below the rim", 1)
        checked = self.warning_draft(note)
        self.assertEqual(checked["c04c"], [])
        self.receipt("无")
        rendered = self.render()
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn("两厘米", self.output.read_text(encoding="utf-8"))

    def test_warning_without_any_linked_number_requires_writer_to_repair_and_reviewer_to_confirm(self):
        wrong = NOTE.replace("loosen the soil with your fingers. ⏱ 00:00",
                             "loosen the soil with your 17 fingers. ⏱ 00:00", 1)
        self.warning_draft(wrong)
        self.receipt("- 待补 C04c-001", result="changes")
        self.assertNotEqual(self.render().returncode, 0)
        self.note(NOTE)
        self.assertNotEqual(self.render().returncode, 0)
        self.assertFalse(self.output.exists())
        receipt = self.job / "review.md"
        with receipt.open("a", encoding="utf-8") as file:
            file.write("- 已修 C04c-001 | loosen the soil with your fingers\n")
        fixed = self.render()
        self.assertEqual(fixed.returncode, 0, fixed.stderr)

    def test_review_revision_with_new_warning_does_not_use_an_old_row_by_number(self):
        self.warning_draft()
        self.receipt("- C04c-001 | 21.1 | two centimeters below the rim | 真错", result="changes")
        self.note(NOTE.replace("three days. ⏱ 01:00", "12 days. ⏱ 01:00", 1))
        self.assertNotEqual(self.render().returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.status()["repair_rounds"], 0)

    def test_same_sentence_distinct_values_get_distinct_warnings(self):
        result = self.warning_draft(NOTE.replace(CLAIM, "stopping 21.1 or 63 centimeters below the rim", 1))
        self.assertEqual([item["term"] for item in result["c04c"]], ["21.1", "63"])

    def test_repeated_claim_needs_its_own_final_warning_decision(self):
        first = self.warning_draft()
        self.receipt("- C04c-001 | 21.1 | two centimeters below the rim | 误报", result="changes")
        claim = first["c04c"][0]["claim"]
        self.note(BAD.replace(claim, f"{claim}\n\n{claim}", 1))
        result = self.render()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        verifier = self.status()["verifier"]
        self.assertEqual([row["id"] for row in verifier["c04c"]], ["C04c-001", "C04c-002"])
        with (self.job / "review.md").open("a", encoding="utf-8") as file:
            file.write(f'<!-- tfv-c04c-final: {verifier["c04c_sha256"]} -->\n')
            file.write("- 终稿 C04c-002 | 21.1 | two centimeters below the rim | 误报\n")
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.output.is_file())

    def test_concurrent_review_change_preserves_prior_reading_file(self):
        self.warning_draft()
        self.receipt("- C04c-001 | 21.1 | two centimeters below the rim | 误报")
        self.output.write_bytes(b"prior reading")
        original = render_reading_note.render_note

        def race(*args, **kw):
            rendered = original(*args, **kw)
            with (self.job / "review.md").open("a", encoding="utf-8") as receipt:
                receipt.write("\nChanged during rendering.\n")
            return rendered

        with patch.object(render_reading_note, "render_note", side_effect=race):
            with self.assertRaisesRegex(render_reading_note.RenderError, "changed during rendering"):
                render_reading_note.render_job(self.job, self.output, keep_frontmatter=False, require_review=True)
        self.assertEqual(self.output.read_bytes(), b"prior reading")


if __name__ == "__main__":
    unittest.main()
