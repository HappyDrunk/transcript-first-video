#!/usr/bin/env python3
"""Check ready task evidence when the caller omitted the screen-mode variable."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_phase2e_w10 import NOTE, ROOT, SCREEN_LINE, SCREEN_NOTE, TRANSCRIPT


ENV_KEY = "TFV_SCREEN_MODE"


class TaskScreenModeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def job(self, name: str = "task", *, grouped: bool = False, missing_slide: bool = False) -> Path:
        job = self.root / name
        job.mkdir()
        (job / "note.md").write_bytes(SCREEN_NOTE.encode("utf-8"))
        (job / "transcript.txt").write_bytes(TRANSCRIPT.encode("utf-8"))
        selection = (ROOT / "evals/fixtures/usable_selection.md").read_text(encoding="utf-8")
        screen = SCREEN_LINE + "\n"
        if grouped:
            screen = "[00:00][幻灯片 1] frame-000001.png\n[00:00][画面] Root inspection\n"
            screen += f"[01:44][幻灯片 2] frame-000002.png\n{SCREEN_LINE}\n"
            selection += "\n00:00 | [幻灯片 1] 根系检查 | 留 | 保留操作方法\n"
            if not missing_slide:
                selection += "01:44 | [幻灯片 2] 仓库路径 | 留 | 画面给出准确路径\n"
        (job / "screen.txt").write_bytes(screen.encode("utf-8"))
        (job / "selection.md").write_bytes(selection.encode("utf-8"))
        screen_status = {"mode": "slides", "state": "ready", "sha256": hashlib.sha256(screen.encode()).hexdigest()}
        if grouped:
            screen_status["slide_count"] = 2
        (job / "status.json").write_text(json.dumps({
            "status": "transcript_ready", "duration_seconds": 120, "expected_lang": "en",
            "screen_ocr": screen_status,
        }), encoding="utf-8")
        return job

    def status(self, job: Path) -> dict:
        return json.loads((job / "status.json").read_text(encoding="utf-8"))

    def set_status(self, job: Path, status: dict) -> None:
        (job / "status.json").write_text(json.dumps(status), encoding="utf-8")

    def command(self, script: str, *arguments: str, mode: str | None = None) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.pop(ENV_KEY, None)
        if mode is not None:
            environment[ENV_KEY] = mode
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *arguments],
            cwd=ROOT, env=environment, capture_output=True, encoding="utf-8", timeout=30,
        )
        print(json.dumps({"command": result.args, "screen_variable_present": ENV_KEY in environment,
                          "screen_variable_value": environment.get(ENV_KEY), "exit": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr}, ensure_ascii=False))
        return result

    def verify(self, job: Path, *, joint: bool = False, mode: str | None = None) -> tuple[int, dict]:
        options = ["--job", str(job), "--json"]
        if joint:
            options.append("--with-coverage")
        result = self.command("verify_note.py", *options, mode=mode)
        self.assertTrue(result.stdout, result)
        return result.returncode, json.loads(result.stdout)

    def assert_no_repair(self, job: Path) -> dict:
        status = self.status(job)
        self.assertEqual(status["repair_rounds"], 0, status)
        self.assertEqual(status["edit_rounds"], 1, status)
        self.assertEqual((job / "note.md").read_bytes(), SCREEN_NOTE.encode("utf-8"))
        self.assertEqual(status["verifier"]["inputs"]["screen"], hashlib.sha256((job / "screen.txt").read_bytes()).hexdigest())
        return status

    def test_unset_environment_uses_ready_slides_for_direct_verify(self) -> None:
        job = self.job()
        code, result = self.verify(job)
        self.assertEqual(code, 0, result["reasons"])
        self.assertTrue(result["allowed"], result)
        self.assert_no_repair(job)

    def test_joint_submission_uses_the_same_ready_screen_fingerprint_for_both_gates(self) -> None:
        job = self.job(grouped=True)
        code, result = self.verify(job, joint=True)
        self.assertEqual(code, 0, result["reasons"])
        self.assertTrue(result["allowed"], result)
        status = self.assert_no_repair(job)
        self.assertTrue(status["finished"], status)
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])
        self.assertEqual(status["verifier"]["inputs"]["slide_count"], 2)

    def test_direct_coverage_still_requires_each_ready_slide(self) -> None:
        job = self.job(grouped=True, missing_slide=True)
        result = self.command("coverage_check.py", "--job", str(job), "--json")
        self.assertTrue(result.stdout, result)
        checked = json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, checked)
        self.assertFalse(checked["ok"], checked)
        reasons = "\n".join(reason for reason in checked["reasons"] if reason.startswith("S01 FAIL:"))
        self.assertRegex(reasons, r"幻灯片\s*2\b")
        self.assertEqual(self.status(job)["repair_rounds"], 1)

    def test_renderer_uses_ready_slides_without_an_environment_override(self) -> None:
        job = self.job(grouped=True)
        reading = self.root / "reading.md"
        result = self.command("render_reading_note.py", "--task-dir", str(job), "--output", str(reading))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(reading.is_file(), result)
        status = self.assert_no_repair(job)
        self.assertTrue(status["finished"], status)
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])
        self.assertEqual(status["verifier"]["inputs"]["slide_count"], 2)

    def test_explicit_off_and_empty_string_keep_their_existing_behavior(self) -> None:
        for name, mode in (("off", "off"), ("empty", "")):
            with self.subTest(mode=mode):
                job = self.job(name)
                code, result = self.verify(job, mode=mode)
                self.assertNotEqual(code, 0, result)
                self.assertTrue(any(reason.startswith("R04 FAIL:") for reason in result["reasons"]), result)
                self.assertEqual(self.status(job)["repair_rounds"], 1)
                self.assertEqual((job / "note.md").read_bytes(), SCREEN_NOTE.encode("utf-8"))

    def test_nonready_missing_or_mismatched_screen_cannot_enable_task_mode(self) -> None:
        for name, change in (
            ("fallback", {"state": "fallback"}), ("pending", {"state": "pending"}),
            ("wrong-hash", {"sha256": "0" * 64}), ("no-hash", {"sha256": None}),
            ("unknown-mode", {"mode": "unsupported"}), ("missing-file", {}),
        ):
            with self.subTest(case=name):
                job = self.job(name)
                status = self.status(job)
                status["screen_ocr"].update(change)
                self.set_status(job, status)
                if name == "missing-file":
                    (job / "screen.txt").unlink()
                code, result = self.verify(job)
                self.assertNotEqual(code, 0, result)
                self.assertTrue(any(reason.startswith("R04 FAIL:") for reason in result["reasons"]), result)
                self.assertEqual(self.status(job)["repair_rounds"], 1)
                # On the same invalid context, speech-only text remains usable
                # and its accepted fingerprints must not acquire a screen source.
                (job / "note.md").write_bytes(NOTE.encode("utf-8"))
                code, result = self.verify(job, joint=True)
                self.assertEqual(code, 0, result["reasons"])
                status = self.status(job)
                self.assertNotIn("screen", status["verifier"]["inputs"])
                self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])

    def test_speech_only_task_without_materials_is_unchanged(self) -> None:
        job = self.job()
        (job / "note.md").write_bytes(NOTE.encode("utf-8"))
        (job / "screen.txt").unlink()
        status = self.status(job)
        status.pop("screen_ocr")
        self.set_status(job, status)
        code, result = self.verify(job, joint=True)
        self.assertEqual(code, 0, result["reasons"])
        self.assertTrue(result["allowed"], result)
        status = self.status(job)
        self.assertEqual(status["repair_rounds"], 0)
        self.assertEqual(status["edit_rounds"], 1)
        self.assertNotIn("screen", status["verifier"]["inputs"])
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])

    def test_unset_environment_also_uses_a_ready_nameplate_task(self) -> None:
        job = self.job()
        status = self.status(job)
        status["screen_ocr"]["mode"] = "nameplate"
        self.set_status(job, status)
        code, result = self.verify(job, joint=True)
        self.assertEqual(code, 0, result["reasons"])
        self.assertTrue(result["allowed"], result)
        status = self.assert_no_repair(job)
        self.assertTrue(status["finished"], status)
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])
        self.assertNotIn("slide_count", status["verifier"]["inputs"])


if __name__ == "__main__":
    unittest.main()
