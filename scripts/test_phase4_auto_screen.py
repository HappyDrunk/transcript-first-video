"""Exercise automatic screen routing and the hand-off from acquisition to the writer."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import coverage_check
import render_reading_note
import screen_ocr
import verify_note
import verify_rules
import youtube_host
from test_phase2e_w10 import ROOT, SCREEN_LINE, SCREEN_NOTE, TRANSCRIPT


MODE = "TFV_SCREEN_MODE"
SOURCE = "https://www.youtube.com/watch?v=AbCdEfGhI_j"
VIDEO = SOURCE.rsplit("=", 1)[1]


class ScreenHostTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.out = Path(folder.name)
        self.job = self.out / f"youtube_{VIDEO}"

    def host(self, mode=None, *, sample=None, full=None):
        env = {key: value for key, value in os.environ.items() if key != MODE}
        if mode is not None:
            env[MODE] = mode
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(youtube_host, "ytdlp_base", return_value=["fetch"]),
            patch.object(youtube_host, "fetch_ytdlp_captions", return_value={
                "text": TRANSCRIPT + "\n[01:59] That concludes the demonstration.\n",
                "source": "yt-dlp", "language": "en",
                "kind": "manual", "media_duration": 120,
            }),
            patch.object(screen_ocr, "sample_slides", create=True,
                         side_effect=sample or AssertionError("unexpected sample")) as sampling,
            patch.object(screen_ocr, "extract", side_effect=full or AssertionError("unexpected full OCR")) as complete,
        ):
            result = youtube_host.run_host(
                video_id=VIDEO, source=SOURCE, out_dir=self.out, expected_lang="en",
                asr_choice="off", verify=True,
            )
        return result, sampling.call_count, complete.call_count

    def check_pending(self):
        self.assertTrue((self.job / "transcript.txt").is_file())
        status = verify_note.read_job_status(self.job)
        self.assertEqual(status["status"], "screen_pending")
        self.assertEqual(status["screen_ocr"]["state"], "pending")
        self.assertNotEqual(status["next_step"], "write-note")
        before = (self.job / "status.json").read_bytes()
        self.assertIn("screen", verify_note.check_job_submission(self.job)["reasons"][0].lower())
        self.assertIn("screen", coverage_check._check_and_record(self.job, None)["reasons"][0].lower())
        self.assertFalse(coverage_check.check_structure(self.job)["allowed"])
        with self.assertRaisesRegex(render_reading_note.RenderError, "Screen acquisition is pending"):
            render_reading_note.render_job(self.job, self.out / "reading.md", keep_frontmatter=False)
        self.assertEqual((self.job / "status.json").read_bytes(), before)

    def ready_screen(self, staging, mode, *args):
        self.check_pending()
        screen = (SCREEN_LINE + "\n").encode("utf-8")
        (staging / "screen.txt").write_bytes(screen)
        (staging / verify_rules.SCREEN_FRAMES).mkdir()
        return {"mode": mode, "state": "ready", "sha256": hashlib.sha256(screen).hexdigest()}

    def test_auto_writes_transcript_before_sampling_and_both_gates_use_stored_mode(self):
        def detect(*args):
            self.check_pending()
            return {"result": "slides_detected", "groups_checked": 1}

        result, sampled, full = self.host(sample=detect, full=self.ready_screen)

        self.assertEqual((sampled, full), (1, 1))
        self.assertEqual(result["next_step"], "write-note")
        self.assertEqual(result["screen_ocr"]["mode"], "slides")
        self.assertEqual(result["screen_ocr"]["result"], "slides_detected")
        self.assertEqual(verify_note.read_job_status(self.job)["screen_ocr"], result["screen_ocr"])
        (self.job / "note.md").write_bytes(SCREEN_NOTE.encode("utf-8"))
        (self.job / "selection.md").write_bytes((ROOT / "evals/fixtures/usable_selection.md").read_bytes())
        with patch.dict(os.environ, {MODE: "off"}):
            actual = verify_note.check_job_submission(self.job, with_coverage=True)
        self.assertTrue(actual["allowed"], actual["reasons"])
        status = verify_note.read_job_status(self.job)
        self.assertEqual(status["verifier"]["inputs"], status["coverage"]["inputs"])
        self.assertIn("screen", status["coverage"]["inputs"])
        self.assertEqual(status["repair_rounds"], 0)
        (self.job / "screen.txt").write_text("replaced screen", encoding="utf-8")
        with patch.dict(os.environ, {MODE: "slides"}):
            self.assertEqual(verify_rules.screen_mode(self.job), "off")

    def test_no_slides_or_failed_probe_continue_with_subtitles_and_no_stale_screen(self):
        for outcome in ("not_found", "missing_dependencies", "error", "timeout"):
            with self.subTest(outcome=outcome):
                self.host("slides", full=self.ready_screen)
                self.assertTrue((self.job / "screen.txt").is_file())
                result, sampled, full = self.host(sample=lambda *a: {"result": outcome})
                self.assertEqual((sampled, full), (1, 0))
                self.assertEqual(result["screen_ocr"]["result"], outcome)
                self.assertEqual(result["screen_ocr"]["mode"], "off")
                self.assertEqual(result["next_step"], "write-note")
                self.assertFalse((self.job / "screen.txt").exists())
                if outcome == "not_found":
                    self.assertIn("TFV_SCREEN_MODE=slides", result["screen_ocr"]["hint"])
                with patch.dict(os.environ, {MODE: "slides"}):
                    self.assertEqual(verify_rules.screen_mode(self.job), "off")

    def test_explicit_modes_bypass_sampling(self):
        for mode in ("off", "nameplate", "slides"):
            with self.subTest(mode=mode):
                result, sampled, full = self.host(mode, full=self.ready_screen)
                self.assertEqual((sampled, full), (0, int(mode != "off")))
                self.assertEqual(result["screen_ocr"]["mode"], mode)
                self.assertEqual(result["next_step"], "write-note")

    def test_full_error_preserves_probe_and_discards_partial_evidence(self):
        def fail(staging, *args):
            self.check_pending()
            (staging / "screen.txt").write_text("partial", encoding="utf-8")
            raise RuntimeError("recognition worker broke")

        result, sampled, full = self.host(sample=lambda *a: {"result": "slides_detected"}, full=fail)

        self.assertEqual((sampled, full), (1, 1))
        self.assertEqual(result["next_step"], "write-note")
        screen = result["screen_ocr"]
        self.assertEqual((screen["result"], screen["mode"]), ("error", "off"))
        self.assertEqual(screen["sample"]["result"], "slides_detected")
        self.assertFalse((self.job / "screen.txt").exists())
        self.assertTrue((self.job / "transcript.txt").is_file())

    def test_partial_publication_of_full_scan_rolls_back_screen_file(self):
        def incomplete(staging, mode, *args):
            self.check_pending()
            screen = b"not yet published"
            (staging / "screen.txt").write_bytes(screen)
            return {"state": "ready", "mode": mode, "sha256": hashlib.sha256(screen).hexdigest()}

        result, _, _ = self.host("slides", full=incomplete)

        self.assertEqual(result["next_step"], "write-note")
        self.assertEqual(result["screen_ocr"]["result"], "error")
        self.assertFalse((self.job / "screen.txt").exists())

    def test_superseded_scan_cannot_publish_over_newer_acquisition(self):
        def old_scan(*args):
            with patch.dict(os.environ, {MODE: "off"}):
                newer = youtube_host.run_host(
                    video_id=VIDEO, source=SOURCE, out_dir=self.out, expected_lang="en",
                    asr_choice="off", verify=True,
                )
            self.assertEqual(newer["screen_ocr"]["requested_mode"], "off")
            return {"result": "not_found"}

        result, _, _ = self.host(sample=old_scan)

        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(verify_note.read_job_status(self.job)["screen_ocr"]["result"], "disabled")


class SampleTests(unittest.TestCase):
    def trial(self, hits, *, fault=None):
        stream = json.dumps({"duration": 1000, "height": 480, "url": "https://media.example/track"})
        commands = []
        windows = []
        budgets = []

        def run(scan, args, description, **kwargs):
            budgets.append(scan.budget)
            commands.append(args)
            if fault and args[0] == "ffmpeg":
                raise fault
            if args[0] == "ffmpeg":
                output = Path(args[-1])
                for frame in (1, 2):
                    output.with_name(output.name.replace("%02d", f"{frame:02d}")).write_bytes(b"image")
            return SimpleNamespace(stdout=stream)

        def qualify(scan, ocr, paths, height):
            windows.append(int(paths[0].stem.split("-")[0]))
            return next(hits)

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(screen_ocr.Scan, "probe", return_value="ffmpeg"),
            patch.object(screen_ocr.Scan, "run", autospec=True, side_effect=run),
            patch.object(screen_ocr.Scan, "recognize", return_value=object()),
            patch.object(screen_ocr, "_sample_pair_qualifies", create=True, side_effect=qualify),
            patch.object(screen_ocr, "getproxies", create=True, return_value={"https": "http://proxy.test:8080"}),
        ):
            result = screen_ocr.sample_slides(Path(folder), SOURCE, ["fetch"], lambda: [])
        return result, commands, windows, budgets

    def test_probe_selects_original_positions_uses_one_proxy_and_stops_at_first_hit(self):
        result, commands, windows, budgets = self.trial(iter((False, True)))

        self.assertEqual(windows, [100, 330])
        self.assertEqual(result["result"], "slides_detected")
        self.assertEqual(result["timeout_seconds"], 45)
        self.assertEqual(len(budgets), 3)
        self.assertTrue(all(0 < budget <= 45 for budget in budgets))
        self.assertEqual(commands[0][commands[0].index("--proxy") + 1], "http://proxy.test:8080")
        for args in commands[1:]:
            self.assertEqual(args[args.index("-http_proxy") + 1], "http://proxy.test:8080")

    def test_probe_uses_at_most_four_pairs(self):
        result, _, windows, _ = self.trial(iter((False, False, False, False)))

        self.assertEqual(windows, [100, 330, 560, 800])
        self.assertEqual(result["result"], "not_found")

    def test_timed_out_media_fetch_stops_probe(self):
        result, commands, windows, _ = self.trial(iter(()), fault=subprocess.TimeoutExpired("ffmpeg", 45))

        self.assertEqual(result["result"], "timeout")
        self.assertEqual(len(commands), 2)
        self.assertEqual(windows, [])


class AutoScreenBudgetTests(unittest.TestCase):
    DURATION = 1000
    HINT = (
        "这台机器识别太慢，只用了字幕；需要画面可在更快的机器上设 TFV_SCREEN_MODE=slides"
    )

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.out = Path(folder.name)
        self.job = self.out / f"youtube_{VIDEO}"

    @contextmanager
    def ocr_io(self, seconds_per_call, model_load_seconds=0):
        elapsed = 0.0
        recognition = SimpleNamespace(
            boxes=[[(10, y), (240, y), (240, y + 16), (10, y + 16)]
                   for y in (40, 140, 240)],
            txts=[
                "Project milestones and scope",
                "Deployment readiness checklist",
                "Customer feedback and next steps",
            ],
            scores=[0.99, 0.99, 0.99],
        )
        stream = json.dumps({
            "duration": self.DURATION,
            "height": 480,
            "url": "https://media.example/track",
        })

        def run(scan, args, step, **kwargs):
            scan.remaining()
            if step == "yt-dlp sample stream":
                return SimpleNamespace(stdout=stream)
            if step == "FFmpeg sample frames":
                for index in (1, 2):
                    Path(args[-1].replace("%02d", f"{index:02d}")).write_bytes(b"image")
            elif step == "video download":
                Path(args[args.index("-o") + 1].replace("%(ext)s", "mp4")).write_bytes(b"video")
            elif step == "frame extraction":
                # One retained frame drives both real OCR passes without thumbnail grouping.
                Path(args[-1].replace("%06d", "000001")).write_bytes(b"image")
                return SimpleNamespace(
                    stderr="[Parsed_showinfo_1 @ 0x1] n: 0 pts: 0 pts_time:0 checksum:ABCD\n",
                )
            elif step == "FFmpeg half transform":
                Path(args[-1]).write_bytes(b"image")
            else:
                self.fail(f"Unexpected external command: {step}")
            return SimpleNamespace(stdout="", stderr="")

        def recognize(scan, operation, *args):
            nonlocal elapsed
            scan.remaining()
            if operation is screen_ocr._rapidocr:
                elapsed += model_load_seconds
                value = model
            else:
                self.assertIs(operation, model)
                elapsed += seconds_per_call
                value = recognition
            scan.remaining()
            return value

        model = object()
        with (
            patch.dict(os.environ, {"TFV_SLIDE_CROP": ""}),
            patch.object(screen_ocr.Scan, "probe", return_value="ffmpeg"),
            patch.object(screen_ocr.Scan, "run", autospec=True, side_effect=run),
            patch.object(screen_ocr.Scan, "recognize", autospec=True, side_effect=recognize)
            as recognize_call,
            patch.object(screen_ocr, "getproxies", return_value={}),
            patch.object(screen_ocr.time, "monotonic", side_effect=lambda: elapsed),
        ):
            yield recognize_call

    def host(self, seconds_per_call, *, mode=None, model_load_seconds=0):
        env = {key: value for key, value in os.environ.items() if key != MODE}
        if mode is not None:
            env[MODE] = mode
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(youtube_host, "ytdlp_base", return_value=["fetch"]),
            patch.object(youtube_host, "fetch_ytdlp_captions", return_value={
                "text": TRANSCRIPT + "\n[01:59] That concludes the demonstration.\n",
                "source": "yt-dlp",
                "language": "en",
                "kind": "manual",
                "media_duration": self.DURATION,
            }),
            self.ocr_io(seconds_per_call, model_load_seconds),
            patch.object(screen_ocr, "sample_slides", wraps=screen_ocr.sample_slides) as sample,
            patch.object(screen_ocr, "extract", wraps=screen_ocr.extract) as extract,
        ):
            result = youtube_host.run_host(
                video_id=VIDEO, source=SOURCE, out_dir=self.out, expected_lang="en",
                asr_choice="off", verify=True,
            )
        return result, sample, extract

    def test_auto_skips_full_scan_when_estimate_exceeds_budget(self):
        baseline, _, _ = self.host(5.0, mode="off")
        self.assertEqual(baseline["exit_code"], 0)
        transcript = self.job / "transcript.txt"
        expected_transcript = transcript.read_bytes()
        stale_screen = self.job / "screen.txt"

        for seconds_per_call in (5.0, 3.0):
            with self.subTest(seconds_per_call=seconds_per_call):
                stale_screen.write_bytes(b"stale screen evidence\n")

                result, sample, extract = self.host(seconds_per_call)

                sample.assert_called_once()
                self.assertEqual(result["screen_ocr"]["sample"]["result"], "slides_detected")
                self.assertEqual(extract.call_count, 0)
                self.assertEqual(result["exit_code"], 0)
                self.assertEqual(result["next_step"], "write-note")
                self.assertEqual(transcript.read_bytes(), expected_transcript)
                self.assertFalse(stale_screen.exists())

                status = json.loads((self.job / "status.json").read_text(encoding="utf-8"))
                self.assertEqual(status["next_step"], "write-note")
                screen = status["screen_ocr"]
                self.assertEqual(screen, result["screen_ocr"])
                self.assertEqual((screen["mode"], screen["state"]), ("off", "fallback"))
                reason = screen["reason"].strip()
                self.assertRegex(reason, r"(?i)estimat|预计|预估|估算")
                self.assertRegex(reason, r"(?i)budget|预算")
                self.assertRegex(
                    reason,
                    r"(?i)exceed|over|greater|longer|above|insufficient|<|>|超[过出]|不足",
                )
                self.assertEqual(screen["hint"], self.HINT)
                with patch.dict(os.environ, {MODE: "slides"}):
                    self.assertEqual(verify_rules.screen_mode(self.job), "off")

                stderr = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    self.assertEqual(youtube_host._emit(result, as_json=False), 0)
                self.assertIn(self.HINT, stderr.getvalue().splitlines())

    def assert_slides_ready(self, result, extract):
        extract.assert_called_once()
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["next_step"], "write-note")
        self.assertEqual(result["screen_ocr"]["mode"], "slides")
        self.assertEqual(result["screen_ocr"]["state"], "ready")

    def test_auto_scans_when_estimate_fits_budget(self):
        for seconds_per_call in (0.2, 2.0):
            with self.subTest(seconds_per_call=seconds_per_call):
                result, sample, extract = self.host(seconds_per_call)

                sample.assert_called_once()
                self.assertEqual(result["screen_ocr"]["sample"]["result"], "slides_detected")
                self.assert_slides_ready(result, extract)

    def test_explicit_slides_bypasses_sampling_with_slow_ocr(self):
        result, sample, extract = self.host(5.0, mode="slides")

        sample.assert_not_called()
        self.assert_slides_ready(result, extract)

    def test_direct_slides_extraction_finishes_with_slow_ocr(self):
        with self.ocr_io(5.0) as recognize:
            result = screen_ocr.extract(
                self.out, "slides", SOURCE, ["fetch"], self.DURATION, lambda: [],
            )

        self.assertEqual(result["state"], "ready", result)
        self.assertEqual(result["mode"], "slides")
        self.assertEqual(result["timeout_seconds"], 500)
        self.assertEqual(result["elapsed_seconds"], 10.0)
        self.assertEqual(recognize.call_count, 3)  # Model initialization and two OCR passes.
        self.assertTrue((self.out / "screen.txt").is_file())

    def test_auto_estimate_excludes_slow_model_initialization(self):
        result, sample, extract = self.host(0.2, model_load_seconds=20.0)

        sample.assert_called_once()
        self.assertEqual(result["screen_ocr"]["sample"]["result"], "slides_detected")
        self.assert_slides_ready(result, extract)


if __name__ == "__main__":
    unittest.main()
