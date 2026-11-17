#!/usr/bin/env python3
"""Freeze failures from the second formal Phase 2E item 6 attempt."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_render_reading_note import SELECTION, write_job


ROOT = Path(__file__).resolve().parents[1]
CONFERENCE = ROOT / "evals/fixtures/delivery-examples/synthetic-cold-chain"
INSERT_BEFORE = "## 有证据的 / 只是说法"
# Complete evidence excerpts from the second formal attempt's note.md and screen.txt.
STORES = "[00:34] Domino's. As you all know, they have 20 plus thousand stores, 90 plus markets."
ANTHOLOGY = (
    "[02:06] Here is like the six steps that we use, not just with Domino's, but with other "
    "customers as well. We start off with kickoff, followed by anthology, benchmarks, first agent, iterating, and handing off."
)
EMAILS = (
    "[05:45] Step three is finding out benchmarks and emails. Now Now, these steps can be "
    "interchangeable slightly, but essentially you're trying to figure out what you can run offline "
    "emails on and what you can run online emails on."
)
ONTOLOGY = "[02:08][画面] Ontology"
EVALS = "[05:44][画面] and evals"
COMPLETED = "[08:16][画面] Completed"
PERCENT = "[08:16][画面] 100%"
VERSION = "[09:28][画面] v10· 87%"
TABLE = "[08:16][画面] V1'S MISTAKES, BY REASON → WHERE THE FIX GOES"


class Phase2EItem6RerunTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def verify(self, job: Path, *, with_coverage: bool = False) -> tuple[int, dict]:
        args = [sys.executable, "-X", "utf8", str(ROOT / "scripts/verify_note.py"), "--job", str(job), "--json"]
        if with_coverage:
            args.append("--with-coverage")
        result = subprocess.run(
            args, cwd=ROOT, env=dict(os.environ, TFV_SCREEN_MODE="slides"),
            capture_output=True, encoding="utf-8", timeout=30,
        )
        self.assertTrue(result.stdout, result)
        return result.returncode, json.loads(result.stdout)

    def conference(
        self, name: str, passage: str, *, speech: tuple[str, ...] = (),
        screen: tuple[str, ...] = (), screen_quotes: tuple[str, ...] | None = None,
    ) -> Path:
        job = self.work / name
        shutil.copytree(CONFERENCE, job)
        transcript = job / "transcript.txt"
        raw = transcript.read_text(encoding="utf-8").splitlines()
        transcript.write_text("\n".join(sorted((*raw, *speech))) + "\n", encoding="utf-8")
        if screen:
            (job / "screen.txt").write_text("\n".join(screen) + "\n", encoding="utf-8")
        if screen_quotes is None:
            screen_quotes = screen
        note_path = job / "note.md"
        note = note_path.read_text(encoding="utf-8").replace(INSERT_BEFORE, passage + "\n\n" + INSERT_BEFORE, 1)
        quotes = "".join(f"> {line}\n" for line in (*speech, *screen_quotes))
        note_path.write_text(note.rstrip() + "\n" + quotes, encoding="utf-8")
        return job

    def assert_fails_rule(self, job: Path, rule: str, phrase: str) -> None:
        code, result = self.verify(job)
        self.assertNotEqual(code, 0, result)
        reasons = [reason for reason in result["reasons"] if reason.startswith(f"{rule} FAIL:")]
        self.assertIn(phrase, "\n".join(reasons), result)

    def assert_passes(self, job: Path) -> None:
        code, result = self.verify(job)
        self.assertEqual(code, 0, result["reasons"])
        self.assertTrue(result["allowed"], result)

    def test_caption_errors_are_refused_in_prose(self) -> None:
        cases = (
            ("anthology", "讲者把第二步说成 anthology，字幕也写成 anthology，但幻灯片上写的是 Ontology。 ⏱ 02:06 ⏱ 02:08",
             "Ontology", ANTHOLOGY, ONTOLOGY),
            ("emails", "讲者口头把评测说成 emails，字幕也写成 emails，但幻灯片上写的是 evals。 ⏱ 05:44 ⏱ 05:45",
             "evals", EMAILS, EVALS),
        )
        for incorrect, sentence, correct, speech, screen in cases:
            with self.subTest(incorrect=incorrect):
                passage = f"{sentence}\n\n> [!warning] 字幕更正\n> 字幕写作 {incorrect}，实为 {correct}。"
                job = self.conference(incorrect, passage, speech=(speech,), screen=(screen,))
                self.assert_fails_rule(job, "C04d", incorrect)

    def test_caption_errors_are_allowed_in_marked_blocks_and_end_evidence(self) -> None:
        passage = """\
先把采集用的概念写清楚，再为上线前后准备评测。 ⏱ 02:06 ⏱ 02:08 ⏱ 05:44 ⏱ 05:45

> [!warning] 字幕更正
> 字幕写作 anthology，实为 Ontology。
> 字幕写作 emails，实为 evals。

> [!note] 术语：Ontology
> 这里指采集需要用到的概念，原字幕写成 anthology。

> [!tip] 类比（Claude 补充）
> 像出门前看钥匙带没带，上线前也得先检查。
> 不成立的地方：评测有单独的规则，原字幕的 emails 是识别错误。
"""
        job = self.conference("only-marked", passage, speech=(ANTHOLOGY, EMAILS), screen=(ONTOLOGY, EVALS))
        self.assert_passes(job)

    def test_translated_store_count_matches_twenty_plus_thousand(self) -> None:
        job = self.conference("stores", "达美乐有两万多家店（20 plus thousand stores）。 ⏱ 00:34", speech=(STORES,))
        self.assert_passes(job)

    def test_translated_version_number_matches_v10(self) -> None:
        job = self.conference("version", "第 10 版（v10）的准确率是 87%。 ⏱ 09:28", screen=(VERSION,))
        self.assert_passes(job)

    def test_version_label_cannot_support_a_count_or_a_different_version(self) -> None:
        for name, sentence, unsupported in (
            ("count", "这里有 10 家门店。", "10"),
            ("wrong-version", "第 12 版的准确率是 87%。", "12"),
        ):
            with self.subTest(case=name):
                job = self.conference(name, f"{sentence} ⏱ 09:28", screen=(VERSION,))
                self.assert_fails_rule(job, "C04c", unsupported)

    def test_parenthesized_original_can_join_adjacent_screen_lines(self) -> None:
        job = self.conference(
            "completion", "表格填完了（Completed 100%）。 ⏱ 08:16",
            screen=(COMPLETED, PERCENT), screen_quotes=(PERCENT, COMPLETED),
        )
        self.assert_passes(job)

    def test_parenthesized_original_requires_adjacent_quoted_trusted_lines_at_one_time(self) -> None:
        later = PERCENT.replace("08:16", "08:24")
        uncertain = PERCENT.replace("画面]", "画面?]")
        cases = (
            ("different-time", (COMPLETED, later), (COMPLETED, later), " ⏱ 08:24"),
            ("separated", (COMPLETED, TABLE, PERCENT), (COMPLETED, PERCENT), ""),
            ("not-quoted", (COMPLETED, PERCENT), (COMPLETED,), ""),
            ("uncertain", (COMPLETED, uncertain), (COMPLETED, PERCENT), ""),
        )
        for name, screen, quotes, link in cases:
            with self.subTest(case=name):
                passage = f"表格填完了（Completed 100%）。 ⏱ 08:16{link}"
                job = self.conference(name, passage, screen=screen, screen_quotes=quotes)
                self.assert_fails_rule(job, "C04c", "Completed 100%")

    def test_screen_selection_rows_are_auxiliary_to_timed_coverage(self) -> None:
        job = self.work / "screen-selection"
        write_job(job)
        (job / "screen.txt").write_text(TABLE + "\n", encoding="utf-8")
        selection_path = job / "selection.md"
        code, control = self.verify(job, with_coverage=True)
        self.assertEqual(code, 0, control["reasons"])
        for decision in ("留", "略"):
            with self.subTest(decision=decision):
                line = f"08:16 | [画面] 第一版的错误归因表 | {decision} | 单独判断画面独有信息\n"
                lines = SELECTION.splitlines(keepends=True)
                lines.insert(2, line)
                selection_path.write_text("".join(lines), encoding="utf-8")
                code, result = self.verify(job, with_coverage=True)
                self.assertEqual(code, 0, result["reasons"])
                self.assertTrue(result["allowed"], result)
                self.assertEqual(result["coverage"], control["coverage"])


if __name__ == "__main__":
    unittest.main()
