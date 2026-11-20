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
from unittest.mock import patch

import screen_ocr
import verify_report
import verify_rules as rules


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


class Whue9NormalizationTests(unittest.TestCase):
    def grounded(self, claim: str, quotes: list[str]) -> tuple[bool, str]:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.txt"
            speech = [line.removeprefix("> ") for line in quotes if "[画面]" not in line]
            screen = [line.removeprefix("> ") for line in quotes if "[画面]" in line]
            transcript.write_text("\n".join(speech), encoding="utf-8")
            if screen:
                transcript.with_name("screen.txt").write_text("\n".join(screen), encoding="utf-8")
            note = "## 主线讲了什么\n\n" + claim + "\n\n## 原文依据\n" + "\n".join(quotes)
            with patch.dict(os.environ, {"TFV_SCREEN_MODE": "slides"}):
                context = rules.build_context(transcript, note, job=True)
            self.assertEqual(len(context.valid_quotes), len(quotes), context.evidence_errors)
            _, passed, message = rules.c04c_grounding(context)
            return passed, message

    def test_original_claims_and_incorrect_values(self) -> None:
        fixture = ROOT / "evals/fixtures" / CORPUS / "whue9-normalization.json"
        for case in json.loads(fixture.read_text(encoding="utf-8")):
            with self.subTest(case=case["name"]):
                passed, message = self.grounded(case["claim"], case["quotes"])
                self.assertTrue(passed, message)
            for original, wrong, label in case["edits"]:
                with self.subTest(case=case["name"], altered=wrong):
                    claim = case["claim"].replace(original, wrong, 1)
                    self.assertNotEqual(claim, case["claim"])
                    passed, message = self.grounded(claim, case["quotes"])
                    self.assertFalse(passed, message)
                    self.assertIn(f"number '{label}'", message)

    def test_number_lists_do_not_supply_the_sum(self) -> None:
        _, values = rules.canonical_numbers("The engineers were between stages one and two.")
        for count, supported in ((1, True), (2, True), (3, False)):
            with self.subTest(count=count):
                claim = rules.NumericValue("number", rules.NumberRange(count, count), str(count))
                self.assertEqual(any(value.supports(claim) for value in values), supported)

    def test_compound_number_does_not_supply_its_components(self) -> None:
        _, values = rules.canonical_numbers("There were one hundred and two projects in the program.")
        for count, supported in ((102, True), (1, False), (2, False)):
            with self.subTest(count=count):
                claim = rules.NumericValue("number", rules.NumberRange(count, count), str(count))
                self.assertEqual(any(value.supports(claim) for value in values), supported)

    def test_calendar_year_does_not_match_a_count_or_percent(self) -> None:
        _, claims = rules.canonical_numbers("活动在 2025 年开始。")
        for quote in (
            "They invited 2025 engineers to the event.",
            "The figure grew by 2025%.",
            "They spent 2025 million dollars on the program.",
            "会上到了 2025 个工程师。",
        ):
            with self.subTest(quote=quote):
                _, values = rules.canonical_numbers(quote)
                self.assertFalse(any(value.supports(claims[0]) for value in values))

    def test_year_does_not_match_common_english_or_chinese_quantities(self) -> None:
        _, claims = rules.canonical_numbers("2025 年上半年")
        for unit in ("PRs", "repos", "repositories", "lines", "files", "agents", "teams",
                     "名工程师", "位员工", "条记录", "行代码", "篇文章", "倍", "种", "万", "亿", "多", "余"):
            with self.subTest(unit=unit):
                _, values = rules.canonical_numbers(f"we merged 2025 {unit}")
                self.assertFalse(any(value.supports(claims[0]) for value in values))

    def test_adjacent_count_needs_both_endpoints_in_the_same_range(self) -> None:
        for quote, expected in (
            ("four or five agents", True),
            ("four agents and five developers", False),
            ("twenty four or five hundred agents", False),
        ):
            with self.subTest(quote=quote):
                _, claims = rules.canonical_numbers("四五个智能体")
                _, values = rules.canonical_numbers(quote)
                self.assertTrue(claims)
                self.assertEqual(all(any(value.supports(claim) for value in values) for claim in claims), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
