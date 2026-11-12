#!/usr/bin/env python3
"""Phase 1A status lifecycle regressions. No network or model calls."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"


class Phase1AStatusTests(unittest.TestCase):
    def _job(self, root: Path) -> Path:
        job = root / "job"
        job.mkdir()
        transcript = (FIXTURES / "usable_en_timed_transcript.txt").read_text(encoding="utf-8")
        note = (FIXTURES / "usable_en_note.md").read_text(encoding="utf-8")
        (job / "transcript.txt").write_text(transcript, encoding="utf-8")
        note = note.replace("evals/fixtures/usable_en_timed_transcript.txt", "transcript.txt")
        (job / "note.md").write_text(note, encoding="utf-8")
        (job / "selection.md").write_bytes((FIXTURES / "usable_selection.md").read_bytes())
        (job / "status.json").write_text(
            json.dumps({"status": "transcript_ready", "duration_seconds": 120}),
            encoding="utf-8",
        )
        return job

    def _run(self, script: str, job: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), "--job", str(job), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

    def test_verify_and_coverage_set_finished_and_later_verify_failure_clears_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(Path(tmp))
            verify = self._run("verify_note.py", job)
            self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
            coverage = self._run("coverage_check.py", job)
            self.assertEqual(coverage.returncode, 0, coverage.stdout + coverage.stderr)
            status_path = job / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertTrue((status.get("verifier") or {}).get("allowed"))
            self.assertTrue((status.get("verifier") or {}).get("at"))
            self.assertTrue((status.get("verifier") or {}).get("skill_version"))
            self.assertTrue(status.get("finished"))

            (job / "note.md").write_text("bad note", encoding="utf-8")
            verify = self._run("verify_note.py", job)
            self.assertNotEqual(verify.returncode, 0)
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertFalse(status["finished"])
            self.assertTrue(status["verifier"]["reasons"])

    def test_third_failed_verify_locks_job_and_coverage_failure_counts_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = self._job(Path(tmp))
            (job / "note.md").write_text("bad note", encoding="utf-8")
            outcomes = [self._run("verify_note.py", job) for _ in range(2)]
            self.assertTrue(all(result.returncode != 0 for result in outcomes))
            (job / "selection.md").unlink()
            coverage = self._run("coverage_check.py", job)
            self.assertNotEqual(coverage.returncode, 0)
            status = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["repair_rounds"], 3)
            self.assertTrue(
                any(reason.startswith("S01 FAIL:") for reason in status["failure_lines"]), status,
            )
            self.assertEqual(status["status"], "not_deposited")
            locked_verify = self._run("verify_note.py", job)
            self.assertNotEqual(locked_verify.returncode, 0)
            self.assertIn("未交：已超过 2 轮", locked_verify.stdout + locked_verify.stderr)
            locked_coverage = self._run("coverage_check.py", job)
            self.assertNotEqual(locked_coverage.returncode, 0)
            self.assertIn("未交：已超过 2 轮", locked_coverage.stdout + locked_coverage.stderr)


if __name__ == "__main__":
    unittest.main()
