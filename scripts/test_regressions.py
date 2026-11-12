#!/usr/bin/env python3
"""Frozen Phase 0 regressions. These describe failures present at e870f15."""

from __future__ import annotations

import json
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import coverage_check  # noqa: E402
import verify_note  # noqa: E402
import youtube_host  # noqa: E402
from test_coverage_check import _article, _selection, _transcript, _write_job  # noqa: E402
from verify_report import failed_ids  # noqa: E402


def _fixture(name: str) -> str:
    return (ROOT / "evals" / "fixtures" / name).read_text(encoding="utf-8")


def _rule(result: dict, rule_id: str) -> dict:
    return next(rule for rule in result["rules"] if rule["id"] == rule_id)


def _usable(lang: str) -> tuple[Path, str]:
    return (
        ROOT / "evals" / "fixtures" / f"usable_{lang}_timed_transcript.txt",
        _fixture(f"usable_{lang}_note.md"),
    )


def _verify(path: Path, note: str, lang: str = "en") -> dict:
    return verify_note.verify(path, note, expected_lang=lang)


class RegressionTests(unittest.TestCase):
    def test_red1_successful_settle_preserves_accepted_note(self) -> None:
        transcript = _fixture("usable_en_transcript.txt")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            job = out / youtube_host.job_id_for("regression-red1")
            job.mkdir()
            note = "accepted note stays byte-for-byte\n"
            (job / "note.md").write_text(note, encoding="utf-8")
            result = youtube_host.run_host(
                video_id="regression-red1",
                source="settle-transcript:regression-red1",
                out_dir=out,
                expected_lang="en",
                asr_choice="off",
                verify=True,
                settle_text=transcript,
            )
            self.assertEqual(result["exit_code"], 0)
            self.assertTrue((job / "note.md").is_file(), "successful settle deleted the accepted note")
            self.assertEqual((job / "note.md").read_text(encoding="utf-8"), note)

    def test_red2_failed_settle_preserves_all_existing_deposit_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            job = out / youtube_host.job_id_for("regression-red2")
            chunks = job / "chunks"
            chunks.mkdir(parents=True)
            names = ("note.md", "note.scaffold.md", "transcript.txt", "segments.json")
            for name in names:
                (job / name).write_text(f"old {name}\n", encoding="utf-8")
            (chunks / "01.txt").write_text("old chunk\n", encoding="utf-8")
            result = youtube_host.run_host(
                video_id="regression-red2",
                source="settle-transcript:regression-red2",
                out_dir=out,
                expected_lang="en",
                asr_choice="off",
                verify=True,
                settle_text="Today.",
            )
            self.assertNotEqual(result["exit_code"], 0)
            for name in names:
                self.assertTrue((job / name).is_file(), f"failed settle deleted {name}")
                self.assertEqual((job / name).read_text(encoding="utf-8"), f"old {name}\n")
            self.assertTrue((chunks / "01.txt").is_file(), "failed settle deleted old chunks")
            self.assertEqual((chunks / "01.txt").read_text(encoding="utf-8"), "old chunk\n")

    def test_red3_r02_cross_cue_window(self) -> None:
        first = "Slide the plant out of the old pot"
        second = "and loosen the soil with your fingers."
        quote = f"{first} {second}"
        transcript, note = _usable("en")
        raw = transcript.read_text(encoding="utf-8")
        split = raw.replace(quote, first + "\n[00:08] " + second, 1)
        self.assertNotEqual(split, raw)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.txt"
            path.write_text(split, encoding="utf-8")
            note = note.replace("evals/fixtures/usable_en_timed_transcript.txt", "transcript.txt")
            result = _verify(path, note)
        for rule in ("R04", "R05"):
            self.assertTrue(_rule(result, rule)["ok"], _rule(result, rule)["message"])

    def test_red4_unstamped_long_chunks_get_quartile_coverage(self) -> None:
        # This is a C02 diagnostic input, deliberately without a reliable clock.
        # Final verification must separately refuse untimed delivery.
        excerpts = [
            f"Write the observation for stage {index} and compare it against the expected result. "
            f"The reviewer notes whether stage {index} reduces delays or adds handoffs."
            for index in range(1, 5)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp)
            chunks = job / "chunks"
            chunks.mkdir()
            for index, excerpt in enumerate(excerpts, 1):
                (chunks / f"{index:02d}.txt").write_text(excerpt + "\n", encoding="utf-8")
            note = job / "note.md"
            note.write_text("## 原文依据\n" + "".join(f"> {excerpt}\n" for excerpt in excerpts), encoding="utf-8")
            spread = coverage_check.check_job(job)
            self.assertTrue(spread["long"])
            self.assertIsNone(spread["duration_seconds"])
            self.assertEqual(spread["quartiles"], [0, 1, 2, 3], spread["reasons"])
            self.assertNotIn("C02", failed_ids(spread), spread["reasons"])
            note.write_text("## 原文依据\n> " + excerpts[0] + "\n", encoding="utf-8")
            sparse = coverage_check.check_job(job)
        self.assertEqual(sparse["quartiles"], [0])
        self.assertIn("C02", failed_ids(sparse), sparse["reasons"])
        self.assertTrue(any("character" in line or "字符" in line for line in sparse["reasons"] if line.startswith("C02 FAIL:")), sparse["reasons"])

    def test_red5_chinese_translation_of_english_note_passes_c04(self) -> None:
        rows = [
            (0, "Divide a large codebase into modules that can be tested independently."),
            (30, "The team tests each module independently and reviews the results before moving on."),
            (60, "Start with a module that already has a clear boundary before testing other modules."),
        ]
        middle = (
            "## 主线论点\n\n把大型代码库拆成可独立测试的模块。 ⏱ 00:00\n\n"
            "团队逐个独立测试模块，审查结果后再继续。 ⏱ 00:30"
        )
        note = _article(
            middle, rows, lead="先把代码拆成能各自测试的模块。",
            action="选一个边界明确的模块，单独运行它的测试。（改写讲者做法） ⏱ 01:00",
        )
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp) / "job", note, _transcript(rows), _selection(90, [0, 30, 60]), 90)
            verified = _verify(job / "transcript.txt", note)
            covered = coverage_check.check_job(job)
        self.assertFalse(any(line.startswith("C04 FAIL:") for line in verified["reasons"]))
        self.assertTrue(verified["allowed"], verified["reasons"])
        self.assertTrue(covered["ok"], covered["reasons"])

    def test_red6a_unrelated_long_delivery_fails_c04(self) -> None:
        transcript, control = _usable("en")
        unrelated = "A distant garden contains blue stones, quiet rivers, and several birds resting beneath the trees. " * 10
        start = control.index("## 主线论点")
        end = control.index("## 可复用做法")
        attack = control[:start] + "## Delivery\n\n" + unrelated + "\n\n" + control[end:]
        result = _verify(transcript, attack)
        self.assertIn("C04a", failed_ids(result), result["reasons"])
        self.assertTrue(_verify(transcript, control)["allowed"])

    def test_red6b_orphan_paragraph_in_observed_delivery_fails_c04(self) -> None:
        source = ROOT / "evals" / "fixtures" / "red6b"
        historical = (source / "delivery.md").read_text(encoding="utf-8")
        orphan = next(line for line in historical.splitlines() if line.startswith("补充："))
        note = (source / "note.md").read_text(encoding="utf-8")
        self.assertIn(orphan, note)
        result = _verify(source / "transcript.txt", note)
        self.assertIn("C04a", failed_ids(result), result["reasons"])
        self.assertTrue(any("orphan" in line.casefold() or "游离" in line for line in result["reasons"]), result["reasons"])
        control = _verify(source / "transcript.txt", note.replace(orphan + "\n\n", ""))
        self.assertTrue(control["allowed"], control["reasons"])

    def test_red7_normal_imperative_openers_are_verbs(self) -> None:
        cases = (
            ("en", "Try a small test today.", "Try a small test today, then write down what changed."),
            ("en", "Watch the result closely.", "Watch the result closely, then record what changed."),
            ("zh", "\u8bd5\u7740\u505a\u4e00\u6b21\u3002", "\u8bd5\u7740\u505a\u4e00\u6b21\uff0c\u5e76\u8bb0\u4e0b\u6bcf\u6b21\u53d8\u5316\u7684\u7ed3\u679c\u4ee5\u4fbf\u7a0d\u540e\u6bd4\u8f83\u3002"),
            ("zh", "\u5217\u51fa\u4e09\u4e2a\u9009\u9879\u3002", "\u5217\u51fa\u4e09\u4e2a\u9009\u9879\uff0c\u5e76\u8bb0\u4e0b\u5b83\u4eec\u5404\u81ea\u7684\u4f18\u7f3a\u70b9\u4ee5\u4fbf\u540e\u7eed\u6bd4\u8f83\u3002"),
        )
        for lang, action, quote in cases:
            with self.subTest(action=action):
                source, base = _usable(lang)
                raw = source.read_text(encoding="utf-8")
                # Both original prose variants remain real evidence. The added action
                # has its own timed cue and is the only change to the action section.
                padding = (
                    " Keep a written record so that the next person can compare the results."
                    if lang == "en" else "把记录放在手边，方便回来检查结果。"
                )
                quote += padding
                with tempfile.TemporaryDirectory() as tmp:
                    transcript = Path(tmp) / "transcript.txt"
                    transcript.write_text(raw.rstrip() + "\n[01:30] " + quote + "\n", encoding="utf-8")
                    note = base.replace(f"evals/fixtures/usable_{lang}_timed_transcript.txt", "transcript.txt")
                    start = note.index("## 今天立刻动手一步")
                    end = note.index("本文略去", start)
                    note = note[:start] + "## 今天立刻动手一步\n\n" + action + " ⏱ 01:30\n\n" + note[end:]
                    note += f"> [01:30] {quote}\n"
                    result = _verify(transcript, note, lang)
                self.assertTrue(_rule(result, "R13")["ok"], _rule(result, "R13")["message"])

    def test_red9_missing_lead_sentence_section_fails_verify(self) -> None:
        transcript, control = _usable("en")
        start, end = control.index("## 先记住一句话"), control.index("## 这场在谈什么、谁")
        result = _verify(transcript, control[:start] + control[end:])
        self.assertFalse(result["allowed"])
        self.assertIn("C04a", failed_ids(result), result["reasons"])
        self.assertTrue(any("先记住一句话" in line for line in result["reasons"]), result["reasons"])
        self.assertTrue(_verify(transcript, control)["allowed"])

    def test_red10_third_consecutive_edit_is_locked_as_not_delivered(self) -> None:
        transcript, note = _usable("en")
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            transcript_path = job / "transcript.txt"
            (job / "transcript.txt").write_text(transcript.read_text(encoding="utf-8"), encoding="utf-8")
            note = note.replace("evals/fixtures/usable_en_timed_transcript.txt", "transcript.txt")
            (job / "note.md").write_text(note, encoding="utf-8")
            (job / "selection.md").write_text(_fixture("usable_selection.md"), encoding="utf-8")
            (job / "status.json").write_text('{"status":"transcript_ready","duration_seconds":120}\n', encoding="utf-8")
            outcomes = []
            for attempt in range(1, 4):
                if attempt > 1:
                    updated = note.replace("\n---\n", f"\nrevision: {attempt}\n---\n", 1)
                    (job / "note.md").write_text(updated, encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    outcomes.append(verify_note.main(["--job", str(job), "--json"]))
            status_path = job / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
        self.assertEqual(outcomes[:2], [0, 0], "the valid note must be deliverable before the retry limit")
        self.assertNotEqual(outcomes[-1], 0)
        self.assertFalse(status.get("finished", False))
        self.assertIn("locked", json.dumps(status).casefold())

    def test_red11_chinese_number_without_transcript_support_fails_r07(self) -> None:
        transcript, control = _usable("en")
        note = control.replace("loosen the soil with your fingers. ⏱ 00:00",
                               "loosen the soil with your fingers. 这批文件有四千万行。 ⏱ 00:00", 1)
        self.assertIn("四千万", note)
        result = _verify(transcript, note)
        self.assertIn("C04c", failed_ids(result), result["reasons"])
        self.assertTrue(any("四千万" in line or "40000000" in line for line in result["reasons"]), result["reasons"])
        self.assertTrue(_verify(transcript, control)["allowed"])

    def test_red12_partial_install_reports_missing_script_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "skill"
            scripts = install / "scripts"
            scripts.mkdir(parents=True)
            shutil.copyfile(ROOT / "scripts/verify_note.py", scripts / "verify_note.py")
            shutil.copyfile(ROOT / "scripts/knowledge_note.py", scripts / "knowledge_note.py")
            shutil.copyfile(ROOT / "SKILL.md", install / "SKILL.md")
            completed = subprocess.run(
                [sys.executable, str(scripts / "verify_note.py"), "--help"],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
        output = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("verify_rules.py", output)
        self.assertIn("missing", output.casefold())

    def test_red14_delivery_timestamp_must_trace_to_note_quote(self) -> None:
        transcript, control = _usable("en")
        attack = control.replace(" ⏱ 00:00", " ⏱ 00:00 ⏱ 09:59", 1)
        result = _verify(transcript, attack)
        self.assertEqual(failed_ids(result), {"C04b"}, result["reasons"])
        self.assertTrue(any("09:59" in line for line in result["reasons"]), result["reasons"])
        self.assertTrue(_verify(transcript, control)["allowed"])

    def test_red15_unmarked_name_or_number_absent_from_note_fails_c04(self) -> None:
        transcript, control = _usable("en")
        for detail in ("Project Zephyr", "2048"):
            with self.subTest(detail=detail):
                attack = control.replace(
                    "loosen the soil with your fingers. ⏱ 00:00",
                    f"loosen the soil with your fingers. The trial involved {detail}. ⏱ 00:00", 1,
                )
                result = _verify(transcript, attack)
                self.assertEqual(failed_ids(result), {"C04c"}, result["reasons"])
                self.assertTrue(any(detail.casefold() in line.casefold() or detail.split()[-1].casefold() in line.casefold() for line in result["reasons"]), result["reasons"])
        self.assertTrue(_verify(transcript, control)["allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
