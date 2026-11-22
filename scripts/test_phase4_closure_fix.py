#!/usr/bin/env python3
"""RED/GREEN contracts for W11 WARN guidance, S7 slide budget floor, A3 venv docs, and D2 deliver state."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import c04c_review
import render_reading_note
import screen_ocr
import verify_rules
import youtube_host
from test_phase2e import NOTE, TRANSCRIPT
from test_phase2e_w10 import SCREEN_LINE
from test_render_reading_note import write_job


ROOT = Path(__file__).resolve().parents[1]
WRITER_REQUIRED = ("SKILL.md", "references/delivery-format.md", "references/rules.md")
WRITER_BASELINE_BYTES = 25_895
CLAIM = "stopping two centimeters below the rim"
BAD_C04C_NOTE = NOTE.replace(CLAIM, "stopping 21.1 centimeters below the rim", 1)
OLD_C04C_HINT = "所链引文里没有这个词或数：补挂出处，或改正文"
PASSED_C04C_HINT = "已过检，交复核裁定（勿为 WARN 改稿）"
SOURCE = "https://www.youtube.com/watch?v=AbCdEfGhI_j"
VIDEO = SOURCE.rsplit("=", 1)[1]


def _h2_section(document: str, heading: str) -> str:
    lines = document.splitlines(keepends=True)
    in_fence = False
    start = None
    for index, line in enumerate(lines):
        if line.startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        if start is None:
            if line.rstrip("\n") == heading:
                start = index
        elif line.startswith("## "):
            return "".join(lines[start:index])
    return "" if start is None else "".join(lines[start:])


class W11WarnGuidanceTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.job = self.root / "job"
        self.job.mkdir()
        (self.job / "transcript.txt").write_text(TRANSCRIPT, encoding="utf-8")
        (self.job / "selection.md").write_bytes((ROOT / "evals/fixtures/usable_selection.md").read_bytes())
        (self.job / "status.json").write_text(
            json.dumps({
                "status": "transcript_ready",
                "expected_lang": "en",
                "duration_seconds": 120,
                "next_step": "write-note",
            }),
            encoding="utf-8",
        )

    def _note(self, text: str) -> None:
        (self.job / "note.md").write_bytes(text.encode("utf-8"))

    def _run_verify(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts/verify_note.py"),
             "--job", str(self.job), "--with-coverage", *extra],
            cwd=ROOT,
            env=dict(os.environ, TFV_SCREEN_MODE="off"),
            capture_output=True,
            encoding="utf-8",
            timeout=25,
        )

    def _break_quote(self, note: str, token: str) -> str:
        return note.replace("> [00:30] Snip the black", f"> [00:30] {token} the black", 1)

    def test_w11_draft1_allowed_with_c04c_warn_prints_next_step_and_suppresses_edit_hint(self) -> None:
        self._note(BAD_C04C_NOTE)
        result = self._run_verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stdout_lines = result.stdout.splitlines()
        self.assertGreaterEqual(len(stdout_lines), 2, result.stdout)
        self.assertEqual(stdout_lines[0], "allowed")
        self.assertIn("下一步：交独立复核", result.stdout)
        self.assertIn("1/3", result.stdout)
        self.assertIn("C04c-001 WARN", result.stderr)
        self.assertIn("交复核裁定", result.stderr)
        self.assertIn(PASSED_C04C_HINT, result.stderr)
        self.assertNotIn("改正文", result.stdout + result.stderr)
        self.assertNotIn("补挂出处", result.stdout + result.stderr)

    def test_w11_draft3_allowed_with_c04c_warn_prints_next_step_3_of_3_and_no_edit_hint(self) -> None:
        for token in ("Preserve", "Inspect"):
            self._note(self._break_quote(NOTE, token))
            failed = self._run_verify()
            self.assertEqual(failed.returncode, 2, failed.stdout + failed.stderr)
        self._note(BAD_C04C_NOTE)
        result = self._run_verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stdout_lines = result.stdout.splitlines()
        self.assertGreaterEqual(len(stdout_lines), 2, result.stdout)
        self.assertEqual(stdout_lines[0], "allowed")
        self.assertIn("下一步：交独立复核", result.stdout)
        self.assertIn("3/3", result.stdout)
        self.assertIn("C04c-001 WARN", result.stderr)
        self.assertIn("交复核裁定", result.stderr)
        self.assertNotIn("改正文", result.stdout + result.stderr)
        self.assertNotIn("补挂出处", result.stdout + result.stderr)

    def test_w11_refused_with_c04c_warn_keeps_original_edit_hint_and_no_review_next_step(self) -> None:
        self.assertEqual(getattr(c04c_review, "PASSED_HINT", None), PASSED_C04C_HINT)
        with self.subTest(case="verify_fail"):
            self._note(BAD_C04C_NOTE.replace("> [00:00] Today", "> [00:00] Yesterday", 1))
            result = self._run_verify()
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(result.stdout.splitlines()[0], "refused")
            self.assertNotIn("下一步：交独立复核", result.stdout)
            self.assertIn("C04c-001 WARN", result.stderr)
            self.assertIn(OLD_C04C_HINT, result.stderr)
            self.assertNotIn("交复核裁定", result.stderr)

        with self.subTest(case="coverage_fail"):
            selection = (ROOT / "evals/fixtures/usable_selection.md").read_text(encoding="utf-8")
            (self.job / "selection.md").write_text(
                selection.replace("00:00", "00:05", 1),
                encoding="utf-8",
            )
            self._note(BAD_C04C_NOTE)
            result = self._run_verify()
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(result.stdout.splitlines()[0], "refused")
            self.assertNotIn("下一步：交独立复核", result.stdout)
            self.assertIn("C04c-001 WARN", result.stderr)
            self.assertIn(OLD_C04C_HINT, result.stderr)
            self.assertNotIn("交复核裁定", result.stderr)

    def test_w11_skill_step6_replaces_ambiguous_c04c_round_wording(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        run = _h2_section(skill, "## Run")
        step_six = run.split("\n6. ", 1)[1].split("\n7. ", 1)[0]
        self.assertNotIn("C04c warnings consume no ordinary repair round.", step_six)
        self.assertRegex(step_six.lower(), r"step 7|review")
        self.assertRegex(step_six.lower(), r"3-draft|three|every.*edit")
        sizes = {rel: len((ROOT / rel).read_bytes()) for rel in WRITER_REQUIRED}
        for rel in WRITER_REQUIRED:
            self.assertNotIn(b"\r", (ROOT / rel).read_bytes(), rel)
        total = sum(sizes.values())
        self.assertLessEqual(total, WRITER_BASELINE_BYTES + 200, f"sizes={sizes}, total={total}")

    def test_w11_allowed_draft_with_s01_and_length_warns_contains_no_edit_hint(self) -> None:
        (self.job / "selection.md").write_text(
            "00:00–00:30 | 开场换盆 | 留 | 演示脱盆与松土\n"
            "00:30–01:00 | 修根加树皮 | 留 | 讲清修根和换新盆土\n"
            "01:00–02:00 | 浇水与养护 | 留 | 说明浇透水和摆放位置\n"
            "02:00–04:40 | 闲聊收尾 | 略 | 与换盆步骤无关\n",
            encoding="utf-8",
        )
        (self.job / "status.json").write_text(
            json.dumps({
                "status": "transcript_ready",
                "expected_lang": "en",
                "duration_seconds": 280,
                "next_step": "write-note",
            }),
            encoding="utf-8",
        )
        long_zh = "先把发黑发软的根系剪掉，保留结实发白的根系，再在新花盆底部铺上一层树皮颗粒让多余水分能够顺利排出，避免积水影响排水导致叶片发黄。" * 3
        note = NOTE.replace(
            "Protect the firm roots and let the new pot drain.",
            long_zh,
            1,
        ).replace(
            "本文略去｜无",
            "本文略去｜闲聊收尾（02:00–04:40）",
            1,
        )
        self._note(note)
        result = self._run_verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], "allowed")
        self.assertIn("下一步：交独立复核", result.stdout)
        self.assertIn("S01 WARN:", result.stderr)
        self.assertIn("长度 WARN:", result.stderr)
        self.assertNotIn("改正文", result.stdout + result.stderr)
        self.assertNotIn("补挂出处", result.stdout + result.stderr)


class S7SlideBudgetFloorTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.out = Path(folder.name)

    def _run_auto_host(self, duration: float, estimated_total: float) -> tuple[dict, int]:
        intervals = max(1, int((duration + screen_ocr.SLIDE_INTERVAL - 1) // screen_ocr.SLIDE_INTERVAL))
        per_interval = estimated_total / intervals
        sample_result = {
            "result": "slides_detected",
            "duration": duration,
            "calibration_status": "calibrated",
            "calibration": {
                "intervals": intervals,
                "download_seconds": 0.0,
                "extract_seconds_per_interval": per_interval,
                "group_seconds_per_frame": 0.0,
                "read_frame_seconds": 0.0,
                "estimated_total_seconds": estimated_total,
            },
        }

        def ready_screen(staging, mode, *args):
            screen_bytes = (SCREEN_LINE + "\n").encode("utf-8")
            (staging / "screen.txt").write_bytes(screen_bytes)
            (staging / verify_rules.SCREEN_FRAMES).mkdir()
            return {
                "mode": mode,
                "state": "ready",
                "timeout_seconds": screen_ocr.slide_full_budget(duration),
                "sha256": "0" * 64,
            }

        env = {key: value for key, value in os.environ.items() if key != "TFV_SCREEN_MODE"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(youtube_host, "ytdlp_base", return_value=["fetch"]),
            patch.object(youtube_host, "fetch_ytdlp_captions", return_value={
                "text": TRANSCRIPT + "\n[01:59] That concludes the demonstration.\n",
                "source": "yt-dlp",
                "language": "en",
                "kind": "manual",
                "media_duration": duration,
            }),
            patch.object(screen_ocr, "sample_slides", return_value=sample_result),
            patch.object(screen_ocr, "extract", side_effect=ready_screen) as extract,
        ):
            result = youtube_host.run_host(
                video_id=VIDEO,
                source=SOURCE,
                out_dir=self.out,
                expected_lang="en",
                asr_choice="off",
                verify=True,
            )
        return result, extract.call_count

    def test_s7_796s_video_320s_estimate_not_skipped_with_600s_floor(self) -> None:
        self.assertEqual(getattr(screen_ocr, "SLIDE_MIN_FULL_BUDGET", None), 600)
        budget_fn = getattr(screen_ocr, "slide_full_budget", None)
        self.assertTrue(callable(budget_fn))
        self.assertEqual(budget_fn(796), 600.0)
        self.assertEqual(budget_fn(802), 600.0)
        self.assertEqual(budget_fn(None), 600.0)
        self.assertEqual(budget_fn(0), 600.0)
        self.assertEqual(budget_fn(float("nan")), 600.0)
        self.assertEqual(budget_fn(3600), 1800.0)

        result, extract_calls = self._run_auto_host(796, 320.0)
        self.assertEqual(extract_calls, 1, result["screen_ocr"])
        self.assertEqual(result["screen_ocr"]["state"], "ready")
        self.assertEqual(result["screen_ocr"]["mode"], "slides")

    def test_s7_3600s_video_over_1260s_still_skipped_with_factual_hint(self) -> None:
        result, extract_calls = self._run_auto_host(3600, 1300.0)
        self.assertEqual(extract_calls, 0)
        screen = result["screen_ocr"]
        self.assertEqual((screen["mode"], screen["state"], screen["result"]), ("off", "fallback", "timeout"))
        self.assertEqual(screen["timeout_seconds"], 1800)
        self.assertEqual(screen["safe_budget_seconds"], 1260.0)
        expected_hint = "预估 1300.0 秒超过按片长算的预算 1260.0 秒，只用了字幕；需要画面可设 TFV_SCREEN_MODE=slides"
        self.assertEqual(screen["hint"], expected_hint)
        self.assertNotIn("这台机器识别太慢", screen["hint"])

    def test_s7_real_frames_path_preserves_600s_budget_floor_on_802s_video(self) -> None:
        for duration_str, duration_sec, expected_budget in (
            ("00:13:22.00", 802.0, 600.0),
            ("01:00:00.00", 3600.0, 1800.0),
        ):
            with self.subTest(duration=duration_str), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                video = work / "video.mp4"
                video.write_bytes(b"video")
                scan = screen_ocr.Scan("slides", duration_sec)

                def fake_subprocess_run(args, **kwargs):
                    (work / "frame-000001.png").write_bytes(b"png")
                    stderr = (
                        f"  Duration: {duration_str}, start: 0.000000, bitrate: 500 kb/s\n"
                        "[Parsed_showinfo_1 @ 0x1] n:   0 pts:      0 pts_time:0.000000 checksum:ABCDEF01\n"
                    )
                    return SimpleNamespace(returncode=0, stdout="", stderr=stderr)

                with patch.object(screen_ocr.subprocess, "run", side_effect=fake_subprocess_run):
                    frames = screen_ocr._frames(scan, "ffmpeg", video, work, "slides")

                self.assertEqual(len(frames), 1)
                self.assertEqual(scan.budget, expected_budget)

    def test_s7_live_overrun_hint_distinguishes_remaining_budget_from_full_budget(self) -> None:
        sample_result = {"result": "slides_detected", "duration": 1000, "mean_frame_ocr_seconds": 0.2}
        overrun_extract = {
            "mode": "slides",
            "state": "fallback",
            "failure": "timeout",
            "reason": "Estimated remaining OCR time (100.0s) exceeds remaining budget (99.0s).",
            "overrun_aborted": True,
            "estimated_remaining_seconds": 100.0,
            "remaining_budget_seconds": 99.0,
            "timeout_seconds": 600.0,
            "elapsed_seconds": 501.0,
        }
        env = {key: value for key, value in os.environ.items() if key != "TFV_SCREEN_MODE"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(youtube_host, "ytdlp_base", return_value=["fetch"]),
            patch.object(youtube_host, "fetch_ytdlp_captions", return_value={
                "text": TRANSCRIPT + "\n[01:59] That concludes the demonstration.\n",
                "source": "yt-dlp",
                "language": "en",
                "kind": "manual",
                "media_duration": 1000,
            }),
            patch.object(screen_ocr, "sample_slides", return_value=sample_result),
            patch.object(screen_ocr, "extract", return_value=overrun_extract),
        ):
            result = youtube_host.run_host(
                video_id=VIDEO, source=SOURCE, out_dir=self.out,
                expected_lang="en", asr_choice="off", verify=True,
            )
        hint = result["screen_ocr"]["hint"]
        self.assertEqual(
            hint,
            "预估剩余 100.0 秒超过剩余预算 99.0 秒，只用了字幕；需要画面可设 TFV_SCREEN_MODE=slides",
        )
        self.assertNotIn("按片长算的预算", hint)


class A3AndD2ClosureTests(unittest.TestCase):
    def test_d2_render_reading_note_sets_next_step_deliver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            output = root / "reading.md"
            write_job(job)
            status_path = job / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["next_step"] = "write-note"
            status_path.write_text(json.dumps(status), encoding="utf-8")

            rendered = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "scripts/render_reading_note.py"),
                 "--task-dir", str(job), "--output", str(output)],
                cwd=ROOT,
                capture_output=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            updated = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertIs(updated["finished"], True)
            self.assertEqual(updated.get("next_step"), "deliver")

    def test_d2_render_reading_note_with_review_sets_next_step_deliver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            output = root / "reading.md"
            job.mkdir()
            (job / "transcript.txt").write_text(TRANSCRIPT, encoding="utf-8")
            (job / "selection.md").write_bytes((ROOT / "evals/fixtures/usable_selection.md").read_bytes())
            (job / "note.md").write_bytes(BAD_C04C_NOTE.encode("utf-8"))
            (job / "status.json").write_text(
                json.dumps({
                    "status": "transcript_ready",
                    "expected_lang": "en",
                    "duration_seconds": 120,
                    "next_step": "write-note",
                }),
                encoding="utf-8",
            )
            env = dict(os.environ, TFV_SCREEN_MODE="off")
            checked = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "scripts/verify_note.py"),
                 "--job", str(job), "--with-coverage", "--json"],
                cwd=ROOT, env=env, capture_output=True, encoding="utf-8", timeout=25,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            status = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status.get("next_step"), "review")
            verifier = status["verifier"]
            header = {
                "inputs": verifier["inputs"],
                "result": "clear",
                "c04c_sha256": verifier["c04c_sha256"],
            }
            (job / "review.md").write_text(
                f"<!-- tfv-review: {json.dumps(header, ensure_ascii=False)} -->\n\n"
                "## C04c 告警裁定\n\n"
                "- C04c-001 | 21.1 | two centimeters below the rim | 误报\n",
                encoding="utf-8",
            )
            rendered = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "scripts/render_reading_note.py"),
                 "--task-dir", str(job), "--output", str(output), "--require-review"],
                cwd=ROOT, env=env, capture_output=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            updated = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertIs(updated["finished"], True)
            self.assertEqual(updated.get("next_step"), "deliver")

    def test_d2_status_stage_failure_preserves_prior_reading_file_and_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            output = root / "reading.md"
            write_job(job)
            status_path = job / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["next_step"] = "write-note"
            status_path.write_text(json.dumps(status), encoding="utf-8")
            output.write_bytes(b"prior reading copy\n")

            real_ntf = render_reading_note.tempfile.NamedTemporaryFile
            rendered_markdown = False
            real_render_note = render_reading_note.render_note

            def tracked_render_note(*args, **kwargs):
                nonlocal rendered_markdown
                rendered_markdown = True
                return real_render_note(*args, **kwargs)

            def fail_status_stage(*args, **kwargs):
                if rendered_markdown and Path(kwargs.get("dir", "")).resolve() == job.resolve():
                    raise OSError("No space left on device")
                return real_ntf(*args, **kwargs)

            with (
                patch.object(render_reading_note, "render_note", side_effect=tracked_render_note),
                patch.object(render_reading_note.tempfile, "NamedTemporaryFile", side_effect=fail_status_stage),
            ):
                with self.assertRaisesRegex(OSError, "No space left on device"):
                    render_reading_note.render_job(job, output, keep_frontmatter=False)

            self.assertEqual(output.read_bytes(), b"prior reading copy\n")
            after = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertNotEqual(after.get("next_step"), "deliver")

    def test_d2_replace_failures_preserve_reading_file_and_roll_back_next_step(self) -> None:
        for failing_target in ("status", "output"):
            with self.subTest(failing_target=failing_target), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                job = root / "job"
                output = root / "reading.md"
                write_job(job)
                status_path = job / "status.json"
                status = json.loads(status_path.read_text(encoding="utf-8"))
                status["next_step"] = "write-note"
                status_path.write_text(json.dumps(status), encoding="utf-8")
                output.write_bytes(b"prior reading copy\n")

                rendered_markdown = False
                real_render_note = render_reading_note.render_note
                real_replace = Path.replace

                def tracked_render_note(*args, **kwargs):
                    nonlocal rendered_markdown
                    rendered_markdown = True
                    return real_render_note(*args, **kwargs)

                def fail_replace(self_path, target):
                    if rendered_markdown:
                        resolved_target = Path(target).resolve()
                        if failing_target == "status" and resolved_target == status_path.resolve():
                            raise PermissionError("status.json locked")
                        if failing_target == "output" and resolved_target == output.resolve():
                            raise PermissionError("reading.md locked")
                    return real_replace(self_path, target)

                with (
                    patch.object(render_reading_note, "render_note", side_effect=tracked_render_note),
                    patch.object(Path, "replace", autospec=True, side_effect=fail_replace),
                ):
                    with self.assertRaisesRegex(PermissionError, "locked"):
                        render_reading_note.render_job(job, output, keep_frontmatter=False)

                self.assertEqual(output.read_bytes(), b"prior reading copy\n")
                after = json.loads(status_path.read_text(encoding="utf-8"))
                self.assertEqual(after.get("next_step"), "write-note")

    def test_a3_skill_step1_and_readme_document_pep668_venv_and_screen_group(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        run = _h2_section(skill, "## Run")
        step_one = run.split("\n1. ", 1)[1].split("\n2. ", 1)[0]
        self.assertIn("venv", step_one.lower())
        self.assertRegex(step_one, re.compile(r"PEP 668|externally-managed", re.IGNORECASE))

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        quickstart = _h2_section(readme, "## Quickstart")
        checks = _h2_section(readme, "## Checks")
        zh = _h2_section(readme, "## 中文")
        for label, section in (("Quickstart", quickstart), ("Checks", checks), ("中文", zh)):
            with self.subTest(section=label):
                self.assertIn("python3 -m pip install --group base --group screen", section)
                self.assertNotRegex(section, r"(?m)^python3 -m pip install --group base[ \t]*$")
        self.assertRegex(quickstart, re.compile(r"venv", re.IGNORECASE))
        self.assertRegex(quickstart, re.compile(r"PEP 668|externally-managed", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
