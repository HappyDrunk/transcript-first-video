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

import verify_report


ROOT = Path(__file__).resolve().parents[1]
CORPUS = "phase3-c04c"


class ConferenceC04cTests(unittest.TestCase):
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
