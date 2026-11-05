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
import knowledge_note  # noqa: E402
import verify_note  # noqa: E402
import verify_rules  # noqa: E402
import youtube_host  # noqa: E402


def _fixture(name: str) -> str:
    return (ROOT / "evals" / "fixtures" / name).read_text(encoding="utf-8")


def _rule(result: dict, rule_id: str) -> dict:
    return next(rule for rule in result["rules"] if rule["id"] == rule_id)


def _short_job(root: Path, note: str, transcript: str | None = None) -> Path:
    job = root / "job"
    job.mkdir(parents=True)
    (job / "note.md").write_text(note, encoding="utf-8")
    (job / "transcript.txt").write_text(
        transcript or _fixture("usable_en_transcript.txt"), encoding="utf-8"
    )
    (job / "status.json").write_text('{"duration_seconds": 120}\n', encoding="utf-8")
    return job


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
        quote = "The first cue has a carefully chosen opening phrase and the second cue completes this contiguous quote for testing."
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.txt"
            transcript = _fixture("usable_en_transcript.txt").rstrip() + "\n[00:20] The first cue has a carefully chosen opening phrase\n[00:21] and the second cue completes this contiguous quote for testing.\n"
            path.write_text(transcript, encoding="utf-8")
            note = knowledge_note.render_scaffold(
                job_id="cross-cue",
                video_id="cross-cue",
                source="fixture",
                acquisition="fixture",
                transcript_cite=path.as_posix(),
                caption_language="en",
            )
            lines = note.splitlines()
            for index, line in enumerate(lines):
                if line.startswith("quoted_window:"):
                    lines[index:index + 2] = ["quoted_window: |-", "  " + quote]
                    break
            note = "\n".join(lines) + "\n"
            result = verify_note.verify(path, note, expected_lang="en")
        self.assertTrue(_rule(result, "R02")["ok"], _rule(result, "R02")["message"])

    def test_red4_unstamped_long_chunks_get_quartile_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            chunks = job / "chunks"
            chunks.mkdir(parents=True)
            for index in range(1, 5):
                (chunks / f"{index:02d}.txt").write_text(
                    f"Write the observation for stage {index} and compare it against the expected result. "
                    f"The reviewer notes whether stage {index} reduces delays or adds handoffs.\n",
                    encoding="utf-8",
                )
                (chunks / f"{index:02d}.notes.md").write_text(
                    f"- [00:0{index}] Write the observation for stage {index} and compare it against the expected result. "
                    f"| Stage {index} records the observation and the comparison.\n",
                    encoding="utf-8",
                )
            (job / "note.md").write_text(
                "---\n"
                "title: \"red4\"\n"
                "source_url: \"fixture\"\n"
                "video_id: \"red4\"\n"
                "acquisition: \"fixture\"\n"
                "gate_passed: true\n"
                "transcript_path: \"transcript.txt\"\n"
                "quoted_window: |-\n"
                "  Write the observation for stage 1 and compare it against the expected result.\n"
                "---\n\n"
                "Transcript: `transcript.txt`.\n\n"
                "## \u95ee\u9898\u4e0e\u505a\u6cd5\n\n"
                "The reviewer checks whether the first stage reduces waiting or creates extra handoffs. "
                "This records an outcome the team can compare before changing its routine.\n\n"
                "> The reviewer notes whether stage 1 reduces delays or adds handoffs.\n\n"
                "## \u5b8c\u6574\u600e\u4e48\u505a\n\n"
                "The reviewer checks the stage for delays and added handoffs. "
                "This keeps the team focused on the same outcome before it changes the broader workflow. "
                "The observation also shows whether the adjustment helps the next decision.\n\n"
                "> The reviewer notes whether stage 2 reduces delays or adds handoffs.\n\n"
                "## \u7ffb\u8f66\u6216\u522b\u7528\n\n"
                "The reviewer checks the stage for delays and extra handoffs. "
                "This keeps the evidence tied to the work instead of an assumption. "
                "The team can discuss the outcome before it changes another step.\n\n"
                "> The reviewer notes whether stage 3 reduces delays or adds handoffs.\n\n"
                "## \u4eca\u5929\u7acb\u523b\u52a8\u624b\u4e00\u6b65\n\n"
                "Write down the observation and compare it with the expected result before choosing whether to keep the change. "
                "This gives the team a clear reason for its next step.\n\n"
                + "\n".join(
                    f"> Write the observation for stage {index} and compare it against the expected result. "
                    f"The reviewer notes whether stage {index} reduces delays or adds handoffs."
                    for index in range(1, 5)
                ),
                encoding="utf-8",
            )
            result = coverage_check.check_job(job)
        c02 = [line for line in result["reasons"] if line.startswith("C02 FAIL:")]
        self.assertFalse(c02, "\n".join(c02))
        self.assertTrue(result["quartiles"])

    def test_red5_chinese_translation_of_english_note_passes_c04(self) -> None:
        english = "The speaker explains how the team divides a large codebase into modular components, tests each part independently, and uses repeated review to improve the work. " * 3
        chinese = "\u8bb2\u8005\u8bf4\u660e\u56e2\u961f\u5982\u4f55\u628a\u5e9e\u5927\u7684\u4ee3\u7801\u5e93\u62c6\u6210\u6a21\u5757\uff0c\u8ba9\u5404\u4e2a\u90e8\u5206\u80fd\u72ec\u7acb\u5f00\u53d1\u548c\u6d4b\u8bd5\uff0c\u518d\u901a\u8fc7\u53cd\u590d\u5ba1\u67e5\u6539\u8fdb\u5de5\u4f5c\u3002" * 3
        with tempfile.TemporaryDirectory() as tmp:
            note = "## Local note\n\n" + english
            job = _short_job(Path(tmp), note)
            delivery = Path(tmp) / "delivery.md"
            delivery.write_text("## \u4ea4\u4ed8\n\n" + chinese, encoding="utf-8")
            result = coverage_check.check_job(job, delivery)
        self.assertFalse(any(line.startswith("C04 FAIL:") for line in result["reasons"]))

    def test_red6a_unrelated_long_delivery_fails_c04(self) -> None:
        grounded = "The speaker describes a practical method, explains why the team uses it, and names the checks that keep the work reliable. " * 8
        unrelated = "A distant garden contains blue stones, quiet rivers, and several birds resting beneath the trees. " * 10
        with tempfile.TemporaryDirectory() as tmp:
            job = _short_job(Path(tmp), "## Note\n\n" + grounded)
            delivery = Path(tmp) / "delivery.md"
            delivery.write_text("## Delivery\n\n" + unrelated, encoding="utf-8")
            result = coverage_check.check_job(job, delivery)
        self.assertTrue(any(line.startswith("C04 FAIL:") for line in result["reasons"]), result["reasons"])

    def test_red6b_orphan_paragraph_in_observed_delivery_fails_c04(self) -> None:
        source = ROOT / "evals" / "fixtures" / "red6b"
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "youtube_LVEfFyijQ2c"
            job.mkdir()
            for name in ("note.md", "transcript.txt", "status.json", "segments.json"):
                shutil.copyfile(source / name, job / name)
            delivery = Path(tmp) / "delivery.md"
            shutil.copyfile(source / "delivery.md", delivery)
            result = coverage_check.check_job(job, delivery)
        c04 = [line for line in result["reasons"] if line.startswith("C04 FAIL:")]
        self.assertTrue(c04, result["reasons"])
        self.assertTrue(any("orphan" in line.casefold() or "\u6e38\u79bb" in line for line in c04), c04)

    def test_red7_normal_imperative_openers_are_verbs(self) -> None:
        cases = (
            ("en", "Try a small test today.", "Try a small test today, then write down what changed."),
            ("en", "Watch the result closely.", "Watch the result closely, then record what changed."),
            ("zh", "\u8bd5\u7740\u505a\u4e00\u6b21\u3002", "\u8bd5\u7740\u505a\u4e00\u6b21\uff0c\u5e76\u8bb0\u4e0b\u6bcf\u6b21\u53d8\u5316\u7684\u7ed3\u679c\u4ee5\u4fbf\u7a0d\u540e\u6bd4\u8f83\u3002"),
            ("zh", "\u5217\u51fa\u4e09\u4e2a\u9009\u9879\u3002", "\u5217\u51fa\u4e09\u4e2a\u9009\u9879\uff0c\u5e76\u8bb0\u4e0b\u5b83\u4eec\u5404\u81ea\u7684\u4f18\u7f3a\u70b9\u4ee5\u4fbf\u540e\u7eed\u6bd4\u8f83\u3002"),
        )
        for lang, action, quote in cases:
            with self.subTest(action=action):
                base = _fixture(f"usable_{lang}_note.md")
                raw = _fixture(f"usable_{lang}_transcript.txt")
                with tempfile.TemporaryDirectory() as tmp:
                    transcript = Path(tmp) / "transcript.txt"
                    transcript.write_text(raw.rstrip() + "\n" + quote + "\n", encoding="utf-8")
                    note = base.replace(f"evals/fixtures/usable_{lang}_transcript.txt", transcript.as_posix())
                    heading = knowledge_note.SECTIONS[-1]
                    marker = "## " + heading
                    start = note.rfind(marker)
                    self.assertGreaterEqual(start, 0)
                    note = note[:start] + marker + "\n\n" + action + "\n\n> " + quote + "\n"
                    result = verify_note.verify(transcript, note, expected_lang=lang)
                self.assertTrue(_rule(result, "R13")["ok"], _rule(result, "R13")["message"])

    def test_red9_missing_lead_sentence_section_fails_verify(self) -> None:
        note = _fixture("usable_en_note.md")
        self.assertNotIn("## \u5148\u8bb0\u4f4f\u4e00\u53e5\u8bdd", note)
        result = verify_note.verify(ROOT / "evals/fixtures/usable_en_transcript.txt", note, expected_lang="en")
        self.assertFalse(result["allowed"])
        self.assertTrue(any("\u5148\u8bb0\u4f4f\u4e00\u53e5\u8bdd" in line for line in result["reasons"]), result["reasons"])

    def test_red10_third_consecutive_edit_is_locked_as_not_delivered(self) -> None:
        note = _fixture("usable_en_note.md")
        transcript = ROOT / "evals/fixtures/usable_en_transcript.txt"
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            transcript_path = job / "transcript.txt"
            (job / "transcript.txt").write_text(transcript.read_text(encoding="utf-8"), encoding="utf-8")
            note = note.replace("evals/fixtures/usable_en_transcript.txt", transcript_path.as_posix())
            (job / "note.md").write_text(note, encoding="utf-8")
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
        transcript = ROOT / "evals/fixtures/usable_en_transcript.txt"
        note = _fixture("usable_en_note.md")
        heading = "## " + knowledge_note.SECTIONS[0]
        note = note.replace(heading, heading + "\n\nThe repository contains \u56db\u5343\u4e07 lines.", 1)
        self.assertIn("\u56db\u5343\u4e07", note)
        result = verify_note.verify(transcript, note, expected_lang="en")
        self.assertFalse(_rule(result, "R07")["ok"], _rule(result, "R07")["message"])

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
        prose = "The team divides the large repository into smaller modules and tests each part independently. " * 4
        quote = "The team divides the large repository into smaller modules and tests each part independently."
        heading = knowledge_note.SECTIONS[0]
        note = "## " + heading + "\n\n" + prose + "\n> [00:30] " + quote + "\n"
        delivery = "## " + heading + "\n\n" + prose + "\n[09:59] This central claim does not appear in the local note."
        transcript = "[00:30] " + quote + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            job = _short_job(Path(tmp), note, transcript)
            body = Path(tmp) / "delivery.md"
            body.write_text(delivery, encoding="utf-8")
            result = coverage_check.check_job(job, body)
        self.assertTrue(any(line.startswith("C04 FAIL:") for line in result["reasons"]), result["reasons"])

    def test_red15_unmarked_name_or_number_absent_from_note_fails_c04(self) -> None:
        prose = "The team divides the large repository into smaller modules and tests each part independently. " * 4
        quote = "The team divides the large repository into smaller modules and tests each part independently."
        heading = knowledge_note.SECTIONS[0]
        note = "## " + heading + "\n\n" + prose + "\n> [00:30] " + quote + "\n"
        delivery = "## " + heading + "\n\n" + prose + "\nThe new policy was tested on Project Zephyr 2048."
        transcript = "[00:30] " + quote + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            job = _short_job(Path(tmp), note, transcript)
            body = Path(tmp) / "delivery.md"
            body.write_text(delivery, encoding="utf-8")
            result = coverage_check.check_job(job, body)
        self.assertTrue(any(line.startswith("C04 FAIL:") for line in result["reasons"]), result["reasons"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
