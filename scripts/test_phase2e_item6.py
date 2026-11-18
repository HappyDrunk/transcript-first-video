#!/usr/bin/env python3
"""Cover the failures from the first formal Phase 2E item 6 attempt."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_render_reading_note import NOTE, SELECTION, TRANSCRIPT, write_job


ROOT = Path(__file__).resolve().parents[1]
CONFERENCE = ROOT / "evals/fixtures/delivery-examples/synthetic-cold-chain"
CONFERENCE_HEAD = """\
---
title: 冷藏货物怎样记录温度
source: https://example.invalid/videos/cold-chain
channel: 沿海冷运会
published: 2026-06-18
type: 大会
caption_kind: manual
skill_version: fixture
transcript_path: transcript.txt
tags: [video-note]
---

## 先记住一句话
运输中记录货物周围的温度，超过上限就通知司机。

## 这场在谈什么、谁
沿海冷运会的大会演讲发布于 2026-06-18，适合负责冷藏运输和处理超温情况的人。

## 发布或主张了什么
把温度记录器放在货物旁边，运输中记录温度，超过 5°C 就通知司机。 ⏱ 00:48
"""
CONFERENCE_GROUP = "## 有证据的 / 只是说法"
CONFERENCE_DEMO = "台上的记录器显示 3.8 度。 ⏱ 02:11"
CONFERENCE_CASE = "加装记录器并在报警时通知司机后，超温的箱子少了。 ⏱ 03:02"
CONFERENCE_TAIL = """\
### 只是口头声称
演讲者计划下一季把提醒扩展到更多路线。 ⏱ 03:36

## 可复用做法
先明确温度上限，再约定超温后通知谁。 ⏱ 00:48

## 翻车或别用
台上只展示了案例的汇总数据。要核对个别路线的情况，还需要看对应的运输记录。 ⏱ 03:02

## 今天立刻动手一步
在你负责的一类货物的检查单上写明温度上限和超温联系人。（改写讲者做法） ⏱ 00:48

本文略去｜赞助口播（00:00–00:48）

## 原文依据
"""
# The original acceptance failed because the final second was marked as omitted
# even though an evidence quote continued into it.
SHORT_TAIL_SELECTION = SELECTION.replace("01:01:00", "01:00:26")
SHORT_TAIL_NOTE = NOTE.replace("01:01:00", "01:00:26")
FINAL_CUE = TRANSCRIPT.splitlines()[-1].partition("] ")[2]
BAD_NOTE = SHORT_TAIL_NOTE.replace("字幕写作 `seed pouches`", "字幕写作 `absent caption spelling`").rstrip()
BAD_NOTE += f" {FINAL_CUE}\n"
MONTH_LINE = "[08:16][画面] JUL 15 · FIRST INSTRUCTIONS"
TRANSLATED_QUOTES = (
    ("成本按「每个来源」（per source）计算。 ⏱ 01:36", "[01:36][画面] Cost per source"),
    ("套餐叫「大披萨加饮料」（Large pizza + drink）。 ⏱ 09:52", "[09:52][画面] Large pizza + drink"),
    ("图中标记为「在其中一根轴上退步」（fell back on one）。 ⏱ 09:28", "[09:28][画面] fell back on one"),
)


class Phase2EItem6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)

    def command(self, script: str, *args: str, screen: bool = False) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, TFV_SCREEN_MODE="slides" if screen else "off")
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *args],
            cwd=ROOT, env=env, capture_output=True, encoding="utf-8", timeout=30,
        )

    def status(self, job: Path) -> dict:
        return json.loads((job / "status.json").read_text(encoding="utf-8"))

    def verify(self, job: Path, *options: str, screen: bool = False) -> tuple[int, dict]:
        result = self.command("verify_note.py", "--job", str(job), "--json", *options, screen=screen)
        self.assertTrue(result.stdout, result)
        return result.returncode, json.loads(result.stdout)

    def set_note(self, job: Path, text: str) -> None:
        (job / "note.md").write_text(text, encoding="utf-8")

    def bad_job(self) -> Path:
        job = self.root / "both-fail"
        write_job(job)
        self.set_note(job, BAD_NOTE)
        (job / "selection.md").write_text(SHORT_TAIL_SELECTION, encoding="utf-8")
        status = self.status(job)
        status["duration_seconds"] = 3626
        (job / "status.json").write_text(json.dumps(status), encoding="utf-8")
        return job

    def test_joint_check_reports_both_failures_then_accepts_one_repair(self) -> None:
        job = self.bad_job()
        code, result = self.verify(job, "--with-coverage")
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["allowed"], result)
        self.assertTrue(any(reason.startswith("C04d FAIL:") for reason in result["reasons"]), result)
        self.assertTrue(any(reason.startswith("S01 FAIL: quote [01:00:07] uses or crosses an omitted")
                            for reason in result["reasons"]), result)
        status = self.status(job)
        self.assertFalse(status["finished"], status)
        self.assertFalse(status["verifier"]["allowed"], status)
        self.assertFalse(status["coverage"]["allowed"], status)
        self.assertEqual(status["edit_rounds"], 1, status)
        self.assertEqual(status["repair_rounds"], 1, status)
        self.assertFalse(status.get("locked"), status)

        merged_selection = SHORT_TAIL_SELECTION.replace(
            "01:00:07–01:00:25", "01:00:07–01:00:26",
        ).rsplit("01:00:25–01:00:26", 1)[0]
        (job / "selection.md").write_text(merged_selection, encoding="utf-8")
        repaired_note = BAD_NOTE.replace("`absent caption spelling`", "`seed pouches`").replace(
            "、会后提醒（01:00:25–01:00:26）", "",
        )
        self.set_note(job, repaired_note)
        code, result = self.verify(job, "--with-coverage")
        self.assertEqual(code, 0, result)
        self.assertTrue(result["allowed"], result)
        status = self.status(job)
        self.assertTrue(status["finished"], status)
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])
        self.assertEqual(status["edit_rounds"], 2, status)
        self.assertEqual(status["repair_rounds"], 1, status)

        self.set_note(job, repaired_note.replace("收好种子前", "收种子之前"))
        code, result = self.verify(job, "--with-coverage")
        self.assertNotEqual(code, 0, result)
        self.assertFalse(result["allowed"], result)
        status = self.status(job)
        self.assertFalse(status["finished"], status)
        self.assertTrue(status["locked"], status)
        self.assertEqual(status["status"], "not_deposited", status)
        self.assertEqual(status["edit_rounds"], 3, status)
        self.assertEqual(status["repair_rounds"], 1, status)

    def test_joint_check_keeps_the_failed_submission_limit(self) -> None:
        job = self.bad_job()
        for failed_submissions in (1, 2, 3):
            code, result = self.verify(job, "--with-coverage")
            self.assertNotEqual(code, 0, result)
            self.assertFalse(result["allowed"], result)
            status = self.status(job)
            self.assertEqual(status["edit_rounds"], 1, status)
            self.assertEqual(status["repair_rounds"], failed_submissions, status)
            self.assertEqual(bool(status.get("locked")), failed_submissions == 3, status)
        self.assertEqual(status["status"], "not_deposited", status)
        self.assertIn("未交：已超过 2 轮", result["reasons"])

        code, result = self.verify(job, "--with-coverage")
        self.assertNotEqual(code, 0, result)
        self.assertIn("未交：已超过 2 轮", result["reasons"])
        self.assertEqual(self.status(job), status)

    def test_renderer_lists_both_failures_without_creating_reading_copy(self) -> None:
        job = self.bad_job()
        output = self.root / "reading.md"
        result = self.command("render_reading_note.py", "--task-dir", str(job), "--output", str(output))
        self.assertNotEqual(result.returncode, 0, result)
        self.assertFalse(output.exists(), result)
        diagnostics = result.stdout + result.stderr
        self.assertIn("C04d FAIL:", diagnostics)
        self.assertIn("S01 FAIL: quote [01:00:07] uses or crosses an omitted", diagnostics)
        status = self.status(job)
        self.assertEqual(status["edit_rounds"], 1, status)
        self.assertEqual(status["repair_rounds"], 1, status)
        self.assertFalse(status["finished"], status)

    def conference_job(self, name: str, claims: tuple[str, ...] = (), screen: tuple[str, ...] = ()) -> tuple[Path, str]:
        job = self.root / name
        job.mkdir()
        for name in ("transcript.txt", "selection.md", "status.json"):
            shutil.copyfile(CONFERENCE / name, job / name)
        speech = (job / "transcript.txt").read_text(encoding="utf-8").splitlines()[1:]
        note = "\n\n".join((
            CONFERENCE_HEAD.rstrip(), *claims, CONFERENCE_GROUP,
            f"### 演示过或给出数据\n{CONFERENCE_DEMO}", CONFERENCE_CASE, CONFERENCE_TAIL.rstrip(),
        )) + "\n" + "".join(f"> {line}\n" for line in speech)
        if screen:
            (job / "screen.txt").write_text("\n".join(screen) + "\n", encoding="utf-8")
            note = note.rstrip() + "\n" + "".join(f"> {line}\n" for line in screen)
        self.set_note(job, note)
        return job, note

    def test_screen_month_supports_chinese_month_and_day(self) -> None:
        for month in ("JUL", "July"):
            with self.subTest(month=month):
                job, _ = self.conference_job(
                    month, ("幻灯片上写着，7 月 15 日开始写第一份说明。 ⏱ 08:16",),
                    (MONTH_LINE.replace("JUL", month),),
                )
                code, result = self.verify(job, screen=True)
                self.assertEqual(code, 0, result["reasons"])

    def test_quoted_chinese_translations_use_the_parenthesized_original(self) -> None:
        claims, excerpts = zip(*TRANSLATED_QUOTES)
        job, note = self.conference_job("translations", claims, excerpts)
        code, result = self.verify(job, screen=True)
        self.assertEqual(code, 0, result["reasons"])

        # The original false positives appeared together in C04c's quoted-name
        # report. A no-evidence parenthesis must not erase that check.
        bad_note = note.replace("（per source）", "（per location）", 1)
        bad_note = bad_note.replace("（Large pizza + drink）", "（Large pizza + cake）", 1)
        bad_note = bad_note.replace("（fell back on one）", "（fell back on all axes）", 1)
        self.set_note(job, bad_note)
        code, result = self.verify(job, screen=True)
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any(reason.startswith("C04c FAIL:") for reason in result["reasons"]), result)

    def test_month_evidence_does_not_support_other_values_or_names(self) -> None:
        for name, claim, unsupported in (
            ("wrong-month", "幻灯片上写着，9 月 15 日发出货物。", "number '9'"),
            ("wrong-count", "幻灯片上写着，发出 7 个箱子。", "number '7'"),
            ("wrong-name", "发货公司名为「虚造机构」。", "name '虚造机构'"),
        ):
            with self.subTest(case=name):
                job, _ = self.conference_job(name, (f"{claim} ⏱ 08:16",), (MONTH_LINE,))
                code, result = self.verify(job, screen=True)
                self.assertNotEqual(code, 0, result)
                reasons = "\n".join(reason for reason in result["reasons"] if reason.startswith("C04c FAIL:"))
                self.assertIn(unsupported, reasons)

    def test_conference_evidence_can_use_step_headings(self) -> None:
        job, note = self.conference_job("steps")
        middle = re.compile(r"(## 有证据的 / 只是说法\n).*?(?=### 只是口头声称)", re.DOTALL)
        steps = (
            f"\n### 检查读数\n{CONFERENCE_DEMO}\n\n"
            f"### 对照加装前后的记录\n{CONFERENCE_CASE}\n\n"
        )
        step_note, count = middle.subn(lambda match: match[1] + steps, note, count=1)
        self.assertEqual(count, 1)
        self.set_note(job, step_note)
        code, result = self.verify(job)
        self.assertEqual(code, 0, result["reasons"])

        self.set_note(job, step_note.replace("### 只是口头声称", "### 以后怎么做"))
        code, result = self.verify(job)
        self.assertNotEqual(code, 0, result)
        self.assertTrue(any(reason.startswith("C04a FAIL:") for reason in result["reasons"]), result)


if __name__ == "__main__":
    unittest.main()
