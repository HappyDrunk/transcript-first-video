#!/usr/bin/env python3
"""Exercise the C04c bad/good pairs recovered from the Phase 3 conference trial."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import screen_ocr
import verify_report


ROOT = Path(__file__).resolve().parents[1]
CORPUS = "phase3-c04c"


class ConferenceC04cTests(unittest.TestCase):
    def test_screen_writer_places_a_physical_boundary_between_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary)
            screenshot = staged / "frame-000001.png"
            screenshot.touch()
            frame = screen_ocr.Frame(screenshot, 205)
            raw = [
                (screen_ocr.Line("Left row one", 50, 20, 100, 24), True),
                (screen_ocr.Line("Right title part one", 300, 25, 150, 40), True),
                (screen_ocr.Line("Left uncertain row", 50, 70, 120, 20), False),
                (screen_ocr.Line("Right title part two", 300, 75, 150, 40), True),
            ]
            refs = screen_ocr._write_evidence(staged, [frame], [raw], filter_watermarks=True,
                                              slide_groups=[[frame]])
            rows = (staged / "screen.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(rows, [
                "[03:25][画面] Left row one",
                "[03:25][画面?] Left uncertain row",
                "",
                "[03:25][画面] Right title part one",
                "[03:25][画面] Right title part two",
            ])
            self.assertEqual(refs, {screenshot.name: [1, 2, 4, 5]})

    def test_paired_samples(self) -> None:
        good = ROOT / "evals/good" / CORPUS
        bad = ROOT / "evals/adversarial" / CORPUS
        samples = {path.name for path in good.glob("*.md")}
        self.assertTrue(samples)
        self.assertEqual(samples, {path.name for path in bad.glob("*.md")})
        environment = os.environ.copy()
        environment.pop("TFV_SCREEN_MODE", None)
        for sample in sorted(samples):
            for folder, expected in ((good, "PASS"), (bad, "FAIL")):
                path = folder / sample
                with self.subTest(sample=path.relative_to(ROOT).as_posix()), tempfile.TemporaryDirectory() as temporary:
                    job = Path(temporary) / "job"
                    shutil.copytree(ROOT / "evals/fixtures" / CORPUS, job)
                    shutil.copyfile(path, job / "note.md")
                    command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/verify_note.py"),
                               "--job", str(job), "--with-coverage", "--json"]
                    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                                            encoding="utf-8", timeout=30)
                    print(json.dumps({"sample": path.relative_to(ROOT).as_posix(), "command": command,
                                      "exit": result.returncode, "stdout": result.stdout,
                                      "stderr": result.stderr}, ensure_ascii=False), flush=True)
                    expected_kind, expected_rule = verify_report.expect_of(path.read_text(encoding="utf-8"))
                    self.assertEqual((expected_kind, expected_rule), (expected, None if expected == "PASS" else "C04c"))
                    output = json.loads(result.stdout)
                    self.assertTrue(output["coverage"]["ok"], output["coverage"]["reasons"])
                    failures = {item["id"]: item["message"] for item in output["rules"] if not item["ok"]}
                    self.assertEqual(set(failures), set() if expected == "PASS" else {"C04c"}, failures)
                    self.assertEqual(result.returncode == 0, expected == "PASS", output["reasons"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
