#!/usr/bin/env python3
"""Check the paired regressions from the post-merge new-video trial."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import verify_report


ROOT = Path(__file__).resolve().parents[1]
CORPUS = "phase2e-new-video"


class NewVideoTests(unittest.TestCase):
    def test_paired_samples(self) -> None:
        bad = ROOT / "evals/adversarial" / CORPUS
        good = ROOT / "evals/good" / CORPUS
        names = {path.name for path in bad.glob("*.md")}
        self.assertTrue(names)
        self.assertEqual(names, {path.name for path in good.glob("*.md")})
        with patch.dict(os.environ, {"TFV_SCREEN_MODE": "off"}):
            for name in sorted(names):
                for folder, expected in ((bad, "FAIL"), (good, "PASS")):
                    path = folder / name
                    with self.subTest(sample=path.relative_to(ROOT).as_posix()):
                        text = path.read_text(encoding="utf-8")
                        kind, rule = verify_report.expect_of(text)
                        self.assertEqual(kind, expected)
                        verified, covered = verify_report.check_sample(text)
                        print(json.dumps({
                            "sample": path.relative_to(ROOT).as_posix(),
                            "expect": kind,
                            "expected_rule": rule,
                            "verify": verified,
                            "coverage": covered,
                        }, ensure_ascii=False, sort_keys=True))
                        if expected == "PASS":
                            self.assertTrue(verified["allowed"], verified["reasons"])
                            self.assertTrue(covered["ok"], covered["reasons"])
                        else:
                            failed = verify_report.failed_ids(verified) | verify_report.failed_ids(covered)
                            self.assertIn(rule, failed, verified["reasons"] + covered["reasons"])


if __name__ == "__main__":
    unittest.main()
