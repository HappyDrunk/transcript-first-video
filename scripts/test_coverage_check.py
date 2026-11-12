#!/usr/bin/env python3
"""Coverage and single-note contract tests. No network or model calls."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import coverage_check as cov
import verify_note
from verify_report import ADVERSARIAL, check_sample, failed_ids

ROOT = Path(__file__).resolve().parents[1]
ARCS = [
    (30, "Export the overnight file before the standup meeting starts today."),
    (90, "Name the owner of that file before anyone else opens the folder."),
    (150, "Keep one backup copy on the side desk and do not mail the original."),
    (330, "Delete the duplicate tab before the email goes to the whole team."),
    (420, "Stop adding columns once the sheet already answers the question."),
    (630, "Stop the feed when the soil stayed wet for three full days."),
    (720, "Mark the pot that stayed wet so the next watering skips it."),
    (930, "Write the limit down before the next person opens the shared board."),
    (1020, "Read the limit aloud once before the group leaves the room."),
    (1140, "Close the board only after the limit is written where people look."),
]
DURATION = 1200
NO_ADDITIONAL_CASE = "本节没有补充中间部分之外的情况。"
FRONT = """---
title: 合成示例
source: https://example.invalid/videos/fixture
channel: 合成课堂
published: 2026-01-01
type: {kind}
caption_kind: manual
skill_version: fixture
transcript_path: {path}
tags: [video-note]
---"""


def _clock(stamp: int) -> str:
    return f"{stamp // 60:02d}:{stamp % 60:02d}"


def _transcript(rows: list[tuple[int, str]]) -> str:
    return "".join(f"[{_clock(stamp)}] {speech}\n" for stamp, speech in rows)


def _selection(duration: int, boundaries: list[int], omitted_from: int | None = None) -> str:
    return "".join(
        f"{_clock(start)}–{_clock(end)} | 内容 | "
        f"{'略' if omitted_from is not None and start >= omitted_from else '留'} | 供核对素材取舍\n"
        for start, end in zip(boundaries, [*boundaries[1:], duration], strict=True)
    )


def _article(
    middle: str,
    rows: list[tuple[int, str]],
    *,
    kind: str = "讲座",
    lead: str = "先检查方法，再记录结果。",
    action: str = "检查状态后写下结果。（改写讲者做法） ⏱ 00:30",
    omitted: str = "无",
    path: str = "transcript.txt",
) -> str:
    evidence = "".join(f"> [{_clock(stamp)}] {speech}\n" for stamp, speech in rows)
    return (
        f"{FRONT.format(kind=kind, path=path)}\n\n"
        f"## 先记住一句话\n\n{lead}\n\n"
        "## 这场在谈什么、谁\n\n讲者介绍操作顺序。\n\n"
        f"{middle.rstrip()}\n\n"
        f"## 可复用做法\n\n{NO_ADDITIONAL_CASE}\n\n"
        f"## 翻车或别用\n\n{NO_ADDITIONAL_CASE}\n\n"
        f"## 今天立刻动手一步\n\n{action}\n\n"
        f"本文略去｜{omitted}\n\n## 原文依据\n{evidence}"
    )


def _arc_note(rows: list[tuple[int, str]], *, omitted: str = "无") -> str:
    middle = "## 主线论点\n\n" + "\n\n".join(
        f"{speech} ⏱ {_clock(stamp)}" for stamp, speech in rows
    )
    action = f"{rows[0][1]} ⏱ {_clock(rows[0][0])}"
    return _article(middle, rows, action=action, omitted=omitted)


def _write_job(
    job: Path, note: str, transcript: str, selection: str | None, duration: int | None,
) -> Path:
    job.mkdir(parents=True)
    (job / "transcript.txt").write_text(transcript, encoding="utf-8")
    (job / "note.md").write_text(note, encoding="utf-8")
    (job / "status.json").write_text(
        json.dumps({"status": "transcript_ready", "expected_lang": "en", "duration_seconds": duration}),
        encoding="utf-8",
    )
    if selection is not None:
        (job / "selection.md").write_text(selection, encoding="utf-8")
    return job


def _check_note(job: Path) -> dict:
    return verify_note.verify(
        job / "transcript.txt", (job / "note.md").read_text(encoding="utf-8"), expected_lang="en",
    )


def _c04_reasons(result: dict) -> set[str]:
    return {rule for rule in failed_ids(result) if rule.startswith("C04")}


class CoverageCheckTests(unittest.TestCase):
    def _check(
        self,
        indexes: list[int],
        *,
        rows: list[tuple[int, str]] = ARCS,
        duration: int = DURATION,
        boundaries: list[int] | None = None,
        omitted_from: int | None = None,
    ) -> dict:
        selected = [rows[index] for index in indexes]
        selection = _selection(duration, boundaries or [0, *(stamp for stamp, _ in rows[1:])], omitted_from)
        omitted = f"旁支（{_clock(omitted_from)}–{_clock(duration)}）" if omitted_from is not None else "无"
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp) / "job", _arc_note(selected, omitted=omitted),
                             _transcript(rows), selection, duration)
            return cov.check_job(job)

    def test_script_reads_only_and_calls_no_model(self) -> None:
        source = Path(cov.__file__).read_text(encoding="utf-8")
        self.assertIn("from pathlib import Path", source)
        self.assertNotIn("import openai", source)
        self.assertNotIn("anthropic", source)
        self.assertNotIn('Path("C:', source)
        self.assertNotIn("Path('C:", source)
        self.assertNotIn("C:\\", source)
        self.assertNotIn("C:/", source)

    def test_thin_stub_fails_quartiles_and_depth(self) -> None:
        result = self._check([0])
        self.assertFalse(result["ok"])
        self.assertEqual(failed_ids(result), {"C02", "S01"}, result["reasons"])
        self.assertEqual(result["quartiles"], [0])

    def test_spread_without_depth_still_fails(self) -> None:
        result = self._check([0, 3, 5, 7])
        self.assertFalse(result["ok"])
        self.assertEqual(failed_ids(result), {"S01"}, result["reasons"])
        self.assertEqual(result["quartiles"], [0, 1, 2, 3])

    def test_full_arc_note_passes(self) -> None:
        result = self._check(list(range(10)))
        self.assertTrue(result["ok"], result["reasons"])
        self.assertTrue(result["long"])
        self.assertEqual(result["quartiles"], [0, 1, 2, 3])
        self.assertEqual(result["warnings"], [])

    def test_nine_of_ten_passes_and_eight_fails(self) -> None:
        passed = self._check(list(range(9)))
        failed = self._check(list(range(8)))
        self.assertTrue(passed["ok"], passed["reasons"])
        self.assertFalse(failed["ok"])
        self.assertEqual(failed_ids(failed), {"S01"}, failed["reasons"])

    def test_selection_needs_at_least_three_covered_units(self) -> None:
        result = self._check([0, 3, 5, 7], boundaries=[0, 600])
        self.assertFalse(result["ok"])
        self.assertEqual(failed_ids(result), {"S01"}, result["reasons"])

    def test_unstamped_quotes_use_segments(self) -> None:
        # No clocks in transcript text; the real timed sidecar places the quotes.
        rows = [ARCS[i] for i in (0, 3, 5, 7)]
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(
                Path(tmp) / "job", _arc_note(rows), "\n".join(speech for _, speech in rows) + "\n",
                _selection(DURATION, [0, 300, 600, 900]), DURATION,
            )
            (job / "segments.json").write_text(
                json.dumps([{"start": stamp, "end": stamp + 4, "text": speech} for stamp, speech in rows]),
                encoding="utf-8",
            )
            result = cov.check_job(job)
        self.assertTrue(result["ok"], result["reasons"])
        self.assertEqual(result["quartiles"], [0, 1, 2, 3])

    def test_short_video_still_checks_selection_and_skips_quartiles(self) -> None:
        result = self._check([0, 1, 2], rows=ARCS[:3], duration=180)
        self.assertTrue(result["ok"], result["reasons"])
        self.assertFalse(result["long"])
        self.assertEqual(result["quartiles"], [])

    def test_omitted_duration_warning_does_not_loosen_thresholds(self) -> None:
        # Three retained units; duration is exactly half, then just over half.
        rows = [
            (0, ARCS[0][1]), (40, ARCS[1][1]), (80, ARCS[2][1]),
            (210, "Thanks for coming to today's recording. Remember to follow our channel."),
        ]
        for end, warns in [(140, False), (139, True)]:
            with self.subTest(retained_seconds=end):
                result = self._check([0, 1, 2], rows=rows, duration=280, boundaries=[0, 40, 80, end], omitted_from=end)
                self.assertTrue(result["ok"], result["reasons"])
                self.assertEqual(bool(result["warnings"]), warns, result["warnings"])
                self.assertEqual(result["quartiles"], [])

    def test_cli_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, indexes, expected in (("thin", [0], 1), ("full", list(range(10)), 0)):
                job = _write_job(root / name, _arc_note([ARCS[i] for i in indexes]), _transcript(ARCS),
                                 _selection(DURATION, [0, *(stamp for stamp, _ in ARCS[1:])]), DURATION)
                run = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/coverage_check.py"), "--job", str(job), "--json"],
                    capture_output=True, encoding="utf-8", check=False,
                )
                self.assertEqual(run.returncode, expected, run.stdout + run.stderr)
                self.assertEqual(json.loads(run.stdout)["ok"], expected == 0)


class DeliveryContractTests(unittest.TestCase):
    def _check_delivery(
        self, middle: str, *, quote: str = "Check the status before recording the result.", kind: str = "讲座",
    ) -> set[str]:
        rows = [
            (0, "The speaker first explains how the team writes down the expected result."),
            (30, quote),
            (60, "Keep the status visible until everyone has recorded the result."),
        ]
        article = _article(middle, rows, kind=kind).replace(
            f"## 可复用做法\n\n{NO_ADDITIONAL_CASE}",
            "## 可复用做法\n\n先把预期结果写下来，记录结果之前保留状态。 ⏱ 00:00 ⏱ 01:00",
        )
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp) / "job", article, _transcript(rows), _selection(90, [0, 30, 60]), 90)
            result = _check_note(job)
        return _c04_reasons(result)

    def test_thin_delivery_fails_and_full_delivery_passes(self) -> None:
        rows = ARCS[:3]
        article = _arc_note(rows)
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp) / "job", article, _transcript(rows), _selection(180, [0, 90, 150]), 180)
            self.assertTrue(_check_note(job)["allowed"], _check_note(job)["reasons"])
            for thin in ("导出隔夜文件。 ⏱ 00:30", FRONT.format(kind="讲座", path="transcript.txt").replace("合成示例", "alphabet" * 40) + "\n导出隔夜文件。 ⏱ 00:30"):
                (job / "note.md").write_text(thin, encoding="utf-8")
                result = _check_note(job)
                self.assertFalse(result["allowed"])
                self.assertIn("C04a", _c04_reasons(result), result["reasons"])

    def test_delivery_format_examples_pass_c04(self) -> None:
        reference = (ROOT / "references/delivery-format.md").read_text(encoding="utf-8")
        examples = re.split(r"^## 合成示例[一二三四]：", reference, flags=re.MULTILINE)[1:]
        names = ("cold-dough", "clinic-reminders", "cold-chain", "kitchen-stock")
        self.assertEqual(len(examples), len(names))
        for name, example in zip(names, examples, strict=True):
            with self.subTest(example=name):
                job = ROOT / "evals/fixtures/delivery-examples" / f"synthetic-{name}"
                blocks = re.findall(
                    r"^```(?:markdown|text)\n(.*?)^```$", example, re.MULTILINE | re.DOTALL,
                )
                self.assertEqual(len(blocks), 2, "expected the frozen single-note and selection blocks")
                article, selection = blocks
                self.assertEqual((job / "note.md").read_text(encoding="utf-8"), article)
                self.assertEqual((job / "selection.md").read_text(encoding="utf-8"), selection)
                transcript = (job / "transcript.txt").read_text(encoding="utf-8").splitlines()
                evidence = re.findall(r"^> (\[\d\d:\d\d\].*)$", article, re.MULTILINE)
                omitted_cues = re.findall(r"`(\[\d\d:\d\d\] [^`]+)`", example)
                self.assertEqual(transcript, sorted(set(evidence + omitted_cues)))
                verified, covered = _check_note(job), cov.check_job(job)
                self.assertTrue(verified["allowed"], verified["reasons"])
                self.assertTrue(covered["ok"], covered["reasons"])

    def test_term_block_accepts_aliases_and_hyphen_spacing(self) -> None:
        cases = (
            ("tar pit / 沥青坑点子", "tar pit"),
            ("tar pit / 沥青坑点子", "沥青坑点子"),
            ("continual learning（持续学习）", "continual learning"),
            ("Y Combinator（YC）", "YC"),
            ("founder-market fit", "founder market fit"),
        )
        middle = (
            "## 主线论点\n\n讲者解释如何判断做法是否有效。 ⏱ 00:30\n\n"
            "> [!note] 术语：{term}\n"
            "> 在这里用来判断做法是否有效。（Claude 补充，非视频内容）"
        )
        for label, spoken in cases:
            with self.subTest(label=label, spoken=spoken):
                quote = f"The speaker uses the term {spoken} to discuss whether the method works."
                self.assertEqual(self._check_delivery(middle.format(term=spoken), quote=quote), set())
                self.assertEqual(self._check_delivery(middle.format(term=label), quote=quote), set())

    def test_list_item_opening_ordinals_are_not_body_numbers(self) -> None:
        heading = "## 主线论点\n\n"
        bullets = "- 检查状态。 ⏱ 00:30\n- 记录结果。 ⏱ 00:30"
        numbered_bullets = "- 3. 检查状态。 ⏱ 00:30\n- 4. 记录结果。 ⏱ 00:30"
        self.assertEqual(self._check_delivery(heading + bullets), set())
        self.assertEqual(self._check_delivery(heading + numbered_bullets), set())

    def test_each_delivery_type_accepts_claim_subheadings(self) -> None:
        claim = "检查状态后再记录结果。 ⏱ 00:30\n"
        cases = (
            ("讲座", "## 主线论点\n\n", ""),
            ("访谈", "## 话题\n\n### 方法\n\n", "\n## 意见不一致的地方\n\n不适用（文稿中未出现意见分歧）。\n"),
            ("大会", "## 发布或主张了什么\n\n", (
                "\n## 有证据的 / 只是说法\n\n"
                f"### 演示过或给出数据\n\n{claim}\n### 只是口头声称\n\n{claim}"
            )),
            ("演示", "## 演示了什么\n\n", f"\n## 关键数字与条件\n\n{claim}"),
        )
        for kind, before, after in cases:
            with self.subTest(kind=kind):
                self.assertEqual(self._check_delivery(before + claim + after, kind=kind), set())
                self.assertEqual(
                    self._check_delivery(before + "### 检查步骤\n\n" + claim + after, kind=kind), set(),
                )

    def test_caption_correction_grounds_prose_and_term_block(self) -> None:
        middle = (
            "## 主线论点\n\n讲者用 QuasarLab 记录结果。 ⏱ 00:30\n\n"
            "> [!note] 术语：QuasarLab\n"
            "> 这里用它记录检查结果。（Claude 补充，非视频内容）"
        )
        quote = "Record the results in QuazerLab after checking the status."
        correction = "\n\n> [!warning] 字幕更正\n> 字幕写作 QuazerLab，实为 QuasarLab。"
        self.assertEqual(self._check_delivery(middle, quote=quote), {"C04c", "C04d"})
        self.assertEqual(self._check_delivery(middle + correction, quote=quote), set())


class Phase2CAcceptanceTests(unittest.TestCase):
    def _sample(self, name: str) -> str:
        return (ADVERSARIAL / f"phase2c_{name}.md").read_text(encoding="utf-8")

    def _assert_rejected(
        self, text: str, control: str, rule: str, detail: str, *, coverage: bool = False,
    ) -> None:
        results = check_sample(text)
        gate = results[int(coverage)]
        actual = failed_ids(gate)
        reasons = "\n".join(gate["reasons"])
        expected = rf"(?im)^(?:{rule} FAIL:|C04 FAIL: {rule}:).*(?:{detail})"
        self.assertRegex(
            reasons, expected,
            f"expected {rule} for this mutation, got {sorted(actual)}. Diagnostics:\n{reasons}",
        )
        self.assertFalse(gate["ok" if coverage else "allowed"], reasons)
        self.assertNotIn("C04a", failed_ids(results[0]), results[0]["reasons"])
        verified, covered = check_sample(control)
        self.assertTrue(verified["allowed"], verified["reasons"])
        self.assertTrue(covered["ok"], covered["reasons"])

    def test_a_unmatched_body_timestamp(self) -> None:
        text = self._sample("a_unmatched_link")
        self._assert_rejected(text, text.replace(" ⏱ 03:00", ""), "C04b", r"03:00")

    def test_b_nonverbatim_end_quote(self) -> None:
        text = self._sample("b_nonverbatim_quote")
        control = text.replace("still small and building rockets", "still small and learning")
        self._assert_rejected(text, control, "R04", r"building rockets|02:05")

    def test_c_unused_end_quote(self) -> None:
        text = self._sample("c_unused_quote")
        control = text.replace("> [02:05] Keep the cheap plan for teams that are still small and learning.\n", "")
        self._assert_rejected(text, control, "C04b", r"(?:unused|未用|未引用).*02:05|02:05.*(?:unused|未用|未引用)")

    def test_d_missing_or_used_omitted_selection(self) -> None:
        text = self._sample("d_selection")
        with self.subTest(case="missing"):
            control = "# fixture_selection: evals/corpus/short.selection\n" + text
            self._assert_rejected(text, control, "S01", r"selection\.md", coverage=True)
        with self.subTest(case="uses an omitted unit"):
            control = (
                "# fixture_selection: evals/corpus/short-omitted.selection\n"
                + text.replace("本文略去｜无", "本文略去｜旁支（02:05–03:20）")
            )
            attack = control.replace(
                "## 可复用做法\n\n" + NO_ADDITIONAL_CASE,
                "## 可复用做法\n\nKeep the cheap plan for teams that are still small and learning. ⏱ 02:05",
            ) + "> [02:05] Keep the cheap plan for teams that are still small and learning.\n"
            self._assert_rejected(attack, control, "S01", r"(?:omitted|略).*02:05|02:05.*(?:omitted|略)", coverage=True)


if __name__ == "__main__":
    unittest.main()
