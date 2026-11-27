"""Exercise automatic screen routing and the hand-off from acquisition to the writer."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

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
    TRANSIENT = "FFmpeg sample frames failed: Connection timed out"

    def trial(self, hits, *, failures=None, failure_seconds=0.0, requested_downloads=None,
              forbidden_step=None, steps=None, stream_info=None):
        info = {"duration": 1000, "height": 480, "url": "https://media.example/track"}
        if stream_info is not None:
            info.update(stream_info)
        if requested_downloads is not None:
            info.update(requested_downloads[0], requested_downloads=requested_downloads)
        stream = json.dumps(info)
        commands = []
        windows = []
        budgets = []
        failures = {at: iter(errors) for at, errors in (failures or {}).items()}
        elapsed = 0.0

        def sleep(seconds):
            nonlocal elapsed
            elapsed += seconds

        def run(scan, args, description, **kwargs):
            nonlocal elapsed
            if steps is not None:
                steps.append(description)
            if description == forbidden_step:
                self.fail(f"Unexpected external command: {description}")
            budgets.append(scan.budget)
            commands.append(args)
            if args[0] == "ffmpeg":
                output = Path(args[-1])
                at = int(args[args.index("-ss") + 1])
                partial = output.with_name(output.name.replace("%02d", "09"))
                self.assertFalse(partial.exists(), f"Partial frame from the last attempt at {at}")
                if (fault := next(failures.get(at, iter(())), None)) is not None:
                    partial.write_bytes(b"incomplete image")
                    elapsed += failure_seconds
                    raise fault
                for frame in (1, 2):
                    output.with_name(output.name.replace("%02d", f"{frame:02d}")).write_bytes(b"image")
                elapsed += 0.25
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
            patch.object(screen_ocr.time, "monotonic", side_effect=lambda: elapsed),
            patch.object(screen_ocr, "_sleep", side_effect=sleep),
        ):
            result = screen_ocr.sample_slides(Path(folder), SOURCE, ["fetch"], lambda: [])
        return result, commands, windows, budgets

    @staticmethod
    def probe_calls(commands):
        return [int(args[args.index("-ss") + 1]) for args in commands if args[0] == "ffmpeg"]

    def test_sample_rejects_1080p_only_requested_downloads_without_480p_sample(self):
        full_format = {"url": "https://media.example/1080.mp4", "height": 1080,
                       "ext": "mp4", "protocol": "https"}
        steps = []
        result, _, _, _ = self.trial(
            iter(()), requested_downloads=[full_format],
            forbidden_step="FFmpeg sample frames", steps=steps,
        )

        self.assertEqual(result["result"], "error")
        self.assertNotIn("FFmpeg sample frames", steps)

    def test_sample_skips_hls_calibration_and_accepts_singleton_480p_sample(self):
        sample_format = {"url": "https://media.example/480.mp4", "height": 480,
                         "ext": "mp4", "protocol": "https"}
        hls_format = {"url": "https://media.example/1080.m3u8", "height": 1080,
                      "ext": "mp4", "protocol": "m3u8_native", "filesize": 30_000_000}
        for name, formats in (
            ("singleton_480p", [sample_format]),
            ("hls_full_format", [sample_format, hls_format]),
        ):
            with self.subTest(name=name):
                steps = []
                with patch.object(screen_ocr, "_measure_download_seconds", return_value=1.0) as measure:
                    result, _, _, _ = self.trial(
                        iter((True,)), requested_downloads=formats,
                        forbidden_step="FFmpeg calibration clip", steps=steps,
                    )

                self.assertEqual(result["result"], "slides_detected")
                self.assertNotIn("calibration", result)
                measure.assert_not_called()
                self.assertNotIn("FFmpeg calibration clip", steps)

    def test_sample_rejects_top_level_1080p_without_requested_downloads(self):
        steps = []
        result, _, _, _ = self.trial(
            iter(()),
            stream_info={"duration": 1000, "height": 1080, "url": "https://media.example/1080.mp4"},
            forbidden_step="FFmpeg sample frames", steps=steps,
        )

        self.assertEqual(result["result"], "error")
        self.assertNotIn("FFmpeg sample frames", steps)

    def test_sample_skips_protocolless_hls_and_low_res_calibration_candidates(self):
        sample_format = {"url": "https://media.example/480.mp4", "height": 480,
                         "ext": "mp4", "protocol": "https"}
        for name, candidate in (
            ("protocolless_m3u8", {
                "url": "https://media.example/master.m3u8?token=1",
                "height": 1080, "filesize": 30_000_000,
            }),
            ("lower_res_second_entry", {
                "url": "https://media.example/360.mp4", "height": 360,
                "protocol": "https", "filesize": 5_000_000,
            }),
        ):
            with self.subTest(name=name):
                steps = []
                with patch.object(screen_ocr, "_measure_download_seconds", return_value=1.0) as measure:
                    result, _, _, _ = self.trial(
                        iter((True,)), requested_downloads=[sample_format, candidate],
                        forbidden_step="FFmpeg calibration clip", steps=steps,
                    )

                self.assertEqual(result["result"], "slides_detected")
                self.assertNotIn("calibration", result)
                measure.assert_not_called()
                self.assertNotIn("FFmpeg calibration clip", steps)

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

    def test_probe_uses_at_most_seven_pairs(self):
        result, _, windows, _ = self.trial(iter((False,) * 7))

        self.assertEqual(windows, [100, 330, 560, 800, 220, 440, 680])
        self.assertEqual(result["result"], "not_found")

    def test_timed_out_media_fetch_stops_probe(self):
        result, commands, windows, _ = self.trial(
            iter(()), failures={100: [subprocess.TimeoutExpired("ffmpeg", 45)]},
        )

        self.assertEqual(result["result"], "timeout")
        self.assertEqual(len(commands), 2)
        self.assertEqual(windows, [])

    def test_transient_sample_failure_retries_same_stream_and_cleans_partial_frames(self):
        with patch.object(screen_ocr, "AUTO_OVERLAY_EXTRA_POSITIONS", ()):
            result, commands, windows, _ = self.trial(
                iter((False,) * 4), failures={330: [screen_ocr.ScreenError(self.TRANSIENT)]},
            )

        self.assertEqual(self.probe_calls(commands), [100, 330, 330, 560, 800])
        self.assertEqual(sum(args[0] == "fetch" for args in commands), 1)
        self.assertEqual(commands[2], commands[3])
        self.assertEqual(windows, [100, 330, 560, 800])
        self.assertEqual(result["groups_checked"], 4)
        self.assertEqual(result["result"], "not_found")
        self.assertNotIn("probe_failures", result)
        self.assertEqual(result["elapsed_seconds"], 2.0)
        self.assertLess(result["elapsed_seconds"], screen_ocr.AUTO_SAMPLE_TIMEOUT)

    def test_transient_sample_failure_with_too_little_budget_does_not_retry(self):
        result, commands, _, _ = self.trial(
            iter((False,) * 6), failures={330: [screen_ocr.ScreenError(self.TRANSIENT)]},
            failure_seconds=35.0,
        )

        self.assertEqual(self.probe_calls(commands).count(330), 1)
        self.assertEqual(result["probe_failures"], [{"at": 330, "reason": self.TRANSIENT}])
        self.assertEqual(result["result"], "error")

    def test_non_retryable_sample_errors_stop_probe(self):
        for fault, outcome in (
            (screen_ocr.ScreenError("Server returned 403 Forbidden"), "error"),
            (screen_ocr.ScreenError("HTTP error 404 Not Found: I/O error"), "error"),
            (screen_ocr.ScreenTimeout(self.TRANSIENT), "timeout"),
            (screen_ocr.ScreenDependencyError(self.TRANSIENT), "missing_dependencies"),
        ):
            with self.subTest(fault=fault):
                result, commands, _, _ = self.trial(iter(()), failures={100: [fault]})

                self.assertEqual(self.probe_calls(commands), [100])
                self.assertEqual(result["result"], outcome)
                self.assertNotIn("probe_failures", result)

    def test_ocr_error_with_transient_text_stops_probe(self):
        def hits():
            yield False
            raise screen_ocr.ScreenError("RapidOCR failed: I/O error")

        result, commands, _, _ = self.trial(hits())

        self.assertEqual(self.probe_calls(commands), [100, 330])
        self.assertEqual(result["result"], "error")
        self.assertEqual(result["reason"], "RapidOCR failed: I/O error")
        self.assertNotIn("probe_failures", result)

    def test_partial_sample_failure_redacts_url_and_reports_error_without_slides(self):
        url = "https://media.example/track?signature=secret"
        result, commands, windows, _ = self.trial(
            iter((False,) * 6),
            failures={560: [screen_ocr.ScreenError(f"{self.TRANSIENT} {url}")] * 2},
        )

        self.assertEqual(self.probe_calls(commands), [100, 330, 560, 560, 800, 220, 440, 680])
        self.assertEqual(windows, [100, 330, 800, 220, 440, 680])
        self.assertEqual(result["result"], "error")
        self.assertEqual(result["reason"], "FFmpeg sample frames failed at 1/4 positions")
        self.assertEqual(result["probe_failures"], [{"at": 560, "reason": f"{self.TRANSIENT} <URL>"}])

    def test_sample_failure_preserves_later_slide_detection_and_calibration(self):
        formats = [
            {"url": "https://media.example/480.mp4", "height": 480, "ext": "mp4", "protocol": "https"},
            {"url": "https://media.example/1080.mp4", "height": 1080, "ext": "mp4", "protocol": "https"},
        ]
        calibration = {"estimated_total_seconds": 120.0}
        with patch.object(screen_ocr, "_calibrate_full_scan", return_value=calibration) as calibrate:
            result, commands, _, _ = self.trial(
                iter((True,)), failures={100: [screen_ocr.ScreenError(self.TRANSIENT)] * 2},
                requested_downloads=formats,
            )

        self.assertEqual(self.probe_calls(commands), [100, 100, 330])
        self.assertEqual(result["result"], "slides_detected")
        self.assertEqual(result["probe_failures"], [{"at": 100, "reason": self.TRANSIENT}])
        calibrate.assert_called_once()
        self.assertEqual(calibrate.call_args.args[2:5], (formats[1], 1000.0, 330))
        self.assertEqual(result["calibration_status"], "calibrated")
        self.assertEqual(result["calibration"], calibration)

    def test_all_main_positions_fail_reports_last_error_without_extra_probes(self):
        positions = [100, 330, 560, 800]
        result, commands, _, _ = self.trial(
            iter(()), failures={
                at: [screen_ocr.ScreenError(f"{self.TRANSIENT} at {at}")] * 2 for at in positions
            },
        )

        self.assertEqual(self.probe_calls(commands), [at for at in positions for _ in range(2)])
        self.assertEqual(result["groups_checked"], 0)
        self.assertEqual(result["result"], "error")
        self.assertEqual(result["reason"], f"{self.TRANSIENT} at 800")
        self.assertEqual([failure["at"] for failure in result["probe_failures"]], positions)

    def test_extra_positions_retry_and_stop_after_a_failed_retry(self):
        fault = screen_ocr.ScreenError(self.TRANSIENT)
        result, commands, _, _ = self.trial(
            iter((False,) * 5), failures={220: [fault], 440: [fault, fault]},
        )

        self.assertEqual(self.probe_calls(commands), [100, 330, 560, 800, 220, 220, 440, 440])
        self.assertEqual(result["groups_checked"], 5)
        self.assertEqual(result["result"], "not_found")
        self.assertNotIn("probe_failures", result)


class AutoScreenBudgetTests(unittest.TestCase):
    DURATION = 1000
    HINT_SUFFIX = "只用了字幕；需要画面可设 TFV_SCREEN_MODE=slides"

    def assert_budget_hint(self, screen):
        hint = screen["hint"]
        self.assertNotIn("这台机器识别太慢", hint)
        if "estimated_seconds" in screen and "safe_budget_seconds" in screen:
            expected = (
                f"预估 {screen['estimated_seconds']:.1f} 秒超过按片长算的预算 "
                f"{screen['safe_budget_seconds']:.1f} 秒，{self.HINT_SUFFIX}"
            )
            self.assertEqual(hint, expected)
        else:
            self.assertRegex(
                hint,
                r"^预估剩余 \d+\.\d 秒超过剩余预算 \d+\.\d 秒，只用了字幕；需要画面可设 TFV_SCREEN_MODE=slides$",
            )

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.out = Path(folder.name)
        self.job = self.out / f"youtube_{VIDEO}"

    def test_measure_download_seconds_enforces_wall_clock_deadline_on_trickle(self):
        read_calls = 0
        elapsed = 0.0

        def read(size=-1):
            nonlocal read_calls, elapsed
            read_calls += 1
            if size > 65_536:
                # A large HTTPResponse.read can wait for many socket reads.
                elapsed += 2.0 * math.ceil(size / 32_768)
                return b"x" * size
            elapsed += 2.0
            return b"x" * (32_768 if size < 0 else min(size, 32_768))

        @contextmanager
        def open_response(*args, **kwargs):
            yield SimpleNamespace(read=read)

        with (
            patch.object(screen_ocr, "build_opener", return_value=SimpleNamespace(open=open_response)),
            patch.object(screen_ocr.time, "monotonic", side_effect=lambda: elapsed),
        ):
            est = screen_ocr._measure_download_seconds(
                "https://media.example/1080.mp4", {}, "", 30_000_000, 30.0,
            )

        self.assertLessEqual(read_calls, 4)
        self.assertLessEqual(elapsed, 8.0)
        self.assertGreater(est, 0)

    def test_measure_download_seconds_enforces_hard_wall_clock_during_open_and_read(self):
        def slow_open(*args, **kwargs):
            threading.Event().wait(0.6)
            return nullcontext(SimpleNamespace(read=lambda size: b""))

        with patch.object(screen_ocr, "build_opener", return_value=SimpleNamespace(open=slow_open)):
            started = time.monotonic()
            est = screen_ocr._measure_download_seconds(
                "https://media.example/1080.mp4", {}, "", 30_000_000, 0.08,
            )
            elapsed = time.monotonic() - started

        self.assertEqual(est, 0.0)
        self.assertLess(elapsed, 0.35)

    @staticmethod
    def gray_png(shade):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        header = struct.pack(">IIBBBBB", 160, 90, 8, 0, 0, 0, 0)
        rows = (b"\0" + bytes([shade]) * 160) * 90
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")

    @contextmanager
    def ocr_io(self, seconds_per_call, model_load_seconds=0, *, sample_decode=0,
               full_frames=1, calibration=None):
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
        stream = {
            "duration": self.DURATION,
            "height": 480,
            "url": "https://media.example/480.mp4",
        }
        if calibration:
            stream["requested_downloads"] = [
                {"url": stream["url"], "height": 480, "http_headers": {}},
                {"url": "https://media.example/1080.mp4", "height": 1080,
                 "filesize": calibration.filesize, "http_headers": {}},
            ]
        calibration_clips = set()

        def run(scan, args, step, **kwargs):
            nonlocal elapsed
            scan.remaining()
            if step == "yt-dlp sample stream":
                return SimpleNamespace(stdout=json.dumps(stream))
            output = Path(args[-1])
            stderr = ""
            if step == "FFmpeg sample frames":
                for index in (1, 2):
                    output.with_name(output.name.replace("%02d", f"{index:02d}")).write_bytes(b"image-480")
                elapsed += sample_decode
            elif step == "video download":
                Path(args[args.index("-o") + 1].replace("%(ext)s", "mp4")).write_bytes(b"video")
            elif step == "FFmpeg calibration clip":
                output.write_bytes(b"calibration clip")
                calibration_clips.add(output)
                elapsed += 0.1
            elif step == "frame extraction":
                is_calibration = Path(args[args.index("-i") + 1]) in calibration_clips
                count = 1 if is_calibration else full_frames
                for index in range(count):
                    frame = output.with_name(output.name.replace("%06d", f"{index + 1:06d}"))
                    frame.write_bytes(b"image-1080")
                stderr = "".join(
                    f"[Parsed_showinfo_1 @ 0x1] n: {i} pts: {i} pts_time:{8 * i} checksum:{i:08X}\n"
                    for i in range(count)
                )
                if is_calibration:
                    elapsed += calibration.decode
            elif step == "FFmpeg calibration frame":
                output.write_bytes(b"image-1080")
                elapsed += 0.1
            elif step == "slide grouping":
                index = int(output.stem.removesuffix("-group").rsplit("-", 1)[-1]) if full_frames > 1 else 1
                output.write_bytes(self.gray_png(255 * (index % 2)))
                elapsed += calibration.grouping if calibration else 0.05
            elif step == "FFmpeg half transform":
                output.write_bytes(b"image-540")
                if calibration:
                    elapsed += calibration.half_transform
            else:
                self.fail(f"Unexpected external command: {step}")
            scan.remaining()
            return SimpleNamespace(stdout="", stderr=stderr)

        def recognize(scan, operation, *args, frame_deadline=None):
            nonlocal elapsed
            scan.remaining()
            if operation is screen_ocr._rapidocr:
                elapsed += model_load_seconds
                value = model
            else:
                self.assertIs(operation, model)
                timings = {b"image-480": seconds_per_call}
                if calibration:
                    timings.update({b"image-1080": calibration.first_pass, b"image-540": calibration.second_pass})
                elapsed += timings.get(args[0], seconds_per_call)
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

    def host(self, seconds_per_call, *, mode=None, sample_result=None, **io_options):
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
            self.ocr_io(seconds_per_call, **io_options),
            patch.object(screen_ocr, "sample_slides", wraps=screen_ocr.sample_slides) as sample,
            patch.object(screen_ocr, "extract", wraps=screen_ocr.extract) as extract,
        ):
            if sample_result is not None:
                sample.return_value = sample_result
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

        for seconds_per_call in (5.0, 4.0):
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
                self.assert_budget_hint(screen)
                with patch.dict(os.environ, {MODE: "slides"}):
                    self.assertEqual(verify_rules.screen_mode(self.job), "off")

                stderr = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    self.assertEqual(youtube_host._emit(result, as_json=False), 0)
                self.assertIn(screen["hint"], stderr.getvalue().splitlines())

    def assert_slides_ready(self, result, extract):
        extract.assert_called_once()
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["next_step"], "write-note")
        self.assertEqual(result["screen_ocr"]["mode"], "slides")
        self.assertEqual(result["screen_ocr"]["state"], "ready")

    def test_auto_scans_when_estimate_fits_budget(self):
        # 2.0s * 2 * 125 = 500s exceeds the 70% safe budget (350s).
        # 1.4s * 2 * 125 = 350s fits.
        for seconds_per_call in (0.2, 1.4):
            with self.subTest(seconds_per_call=seconds_per_call):
                result, sample, extract = self.host(seconds_per_call)

                sample.assert_called_once()
                self.assertEqual(result["screen_ocr"]["sample"]["result"], "slides_detected")
                self.assert_slides_ready(result, extract)

    def assert_timeout_fallback(self, result):
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["next_step"], "write-note")
        screen = result["screen_ocr"]
        self.assertEqual((screen["mode"], screen["state"], screen["result"]),
                         ("off", "fallback", "timeout"))
        self.assert_budget_hint(screen)
        return screen

    def test_auto_skips_when_1080p_calibration_cost_exceeds_safe_budget(self):
        self.DURATION = 1069
        self.host(0.70, mode="off")
        transcript = self.job / "transcript.txt"
        expected_transcript = transcript.read_bytes()
        # 14s download, 134 extraction/grouping intervals and 61 OCR frames exceed 420s.
        calibration = SimpleNamespace(filesize=30_000_000, decode=0.85, grouping=0.05,
                                      first_pass=2.60, half_transform=0.06, second_pass=2.40)
        with patch.object(screen_ocr, "_measure_download_seconds", create=True, return_value=14.0):
            result, sample, extract = self.host(0.70, sample_decode=1.8, calibration=calibration)

        sample.assert_called_once()
        self.assertEqual(extract.call_count, 0)
        screen = self.assert_timeout_fallback(result)
        self.assertGreater(screen["estimated_seconds"], 420.0)
        self.assertGreater(screen["sample"]["calibration"]["estimated_total_seconds"], 420.0)
        self.assertEqual(transcript.read_bytes(), expected_transcript)
        self.assertFalse((self.job / "screen.txt").exists())

    def test_auto_records_calibrated_status_and_estimate_in_status_json(self):
        calibration = SimpleNamespace(filesize=30_000_000, decode=0.25, grouping=0.05,
                                      first_pass=0.5, half_transform=0.05, second_pass=0.5)
        with (
            patch.object(screen_ocr, "_measure_download_seconds", return_value=14.0),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            result, _, extract = self.host(0.2, sample_decode=0.2, calibration=calibration)

        self.assert_slides_ready(result, extract)
        status = json.loads((self.job / "status.json").read_text(encoding="utf-8"))
        sample = status["screen_ocr"]["sample"]
        self.assertIn("calibration", sample)
        self.assertIn("estimated_total_seconds", sample["calibration"])
        self.assertEqual(sample.get("calibration_status"), "calibrated")
        self.assertEqual(sample["estimated_seconds"], round(sample["calibration"]["estimated_total_seconds"], 3))
        self.assertNotIn("calibration", stderr.getvalue().lower())

    def test_auto_records_calibration_timeout_fallback_and_emits_stderr_notice(self):
        # The mocked decode advances the clock past the clip frame scan's
        # remaining calibration budget before Scan.run returns.
        calibration = SimpleNamespace(filesize=30_000_000, decode=31.0, grouping=0.05,
                                      first_pass=0.5, half_transform=0.05, second_pass=0.5)
        for seconds_per_call, sample_decode, state in ((0.2, 0.2, "ready"), (0.8, 6.0, "fallback")):
            with self.subTest(state=state):
                with (
                    patch.object(screen_ocr, "_measure_download_seconds", return_value=14.0) as download,
                    redirect_stderr(io.StringIO()) as stderr,
                ):
                    result, _, extract = self.host(
                        seconds_per_call, sample_decode=sample_decode, calibration=calibration,
                    )

                download.assert_called_once()
                if state == "ready":
                    self.assert_slides_ready(result, extract)
                else:
                    extract.assert_not_called()
                    self.assert_timeout_fallback(result)
                status = json.loads((self.job / "status.json").read_text(encoding="utf-8"))
                screen = status["screen_ocr"]
                self.assertEqual(screen["state"], state)
                if state == "fallback":
                    self.assertEqual(screen["result"], "timeout")
                sample = screen["sample"]
                self.assertNotIn("calibration", sample)
                self.assertEqual(sample.get("calibration_status"), "timeout_fallback")
                reason = sample["calibration_reason"]
                self.assertIsInstance(reason, str)
                self.assertTrue(reason.strip())
                self.assertEqual(reason.splitlines(), [reason])
                self.assertRegex(reason, r"(?i)timed?\s*out|timeout")
                self.assertEqual(sample["estimated_seconds"], self.expected_sample_estimate(sample))
                notices = [line for line in stderr.getvalue().splitlines() if "calibration" in line.lower()]
                self.assertEqual(len(notices), 1)
                self.assertIn("timeout_fallback", notices[0])
                self.assertIn(f"{sample['estimated_seconds']:.1f}s", notices[0])
                self.assertIn(reason, notices[0])

    def test_auto_records_calibration_error_fallback_and_redacts_url(self):
        calibration = SimpleNamespace(filesize=30_000_000, decode=0.25, grouping=0.05,
                                      first_pass=0.5, half_transform=0.05, second_pass=0.5)
        error = screen_ocr.ScreenError(
            "FFmpeg calibration clip failed: https://secret.example/v.mp4?token=abc123\nsecond line"
        )
        with (
            patch.object(screen_ocr, "_calibrate_full_scan", side_effect=error) as calibrate,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            result, _, extract = self.host(0.2, sample_decode=0.2, calibration=calibration)

        calibrate.assert_called_once()
        self.assert_slides_ready(result, extract)
        status = json.loads((self.job / "status.json").read_text(encoding="utf-8"))
        sample = status["screen_ocr"]["sample"]
        self.assertEqual(sample.get("calibration_status"), "fallback")
        reason = sample["calibration_reason"]
        self.assertIsInstance(reason, str)
        self.assertTrue(reason.strip())
        self.assertEqual(reason.splitlines(), [reason])
        self.assertIn("<URL>", reason)
        self.assertEqual(sample["estimated_seconds"], self.expected_sample_estimate(sample))
        notices = [line for line in stderr.getvalue().splitlines() if "calibration" in line.lower()]
        self.assertEqual(len(notices), 1)
        self.assertIn("fallback", notices[0])
        self.assertIn(f"{sample['estimated_seconds']:.1f}s", notices[0])
        for secret in ("secret.example", "abc123"):
            self.assertNotIn(secret, reason)
            self.assertNotIn(secret, notices[0])

    def test_auto_calibration_fallback_redacts_multitoken_credentials_and_control_chars(self):
        calibration = SimpleNamespace(filesize=30_000_000, decode=0.25, grouping=0.05,
                                      first_pass=0.5, half_transform=0.05, second_pass=0.5)
        error = screen_ocr.ScreenError(
            "FFmpeg calibration clip failed: \x1b[31mCookie: first=example; "
            "second=sensitive-value\x1b[0m\x07\nAuthorization: Bearer top-secret-token extra-part"
        )
        with (
            patch.object(screen_ocr, "_calibrate_full_scan", side_effect=error) as calibrate,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            result, _, _ = self.host(0.2, sample_decode=0.2, calibration=calibration)

        calibrate.assert_called_once()
        status = json.loads((self.job / "status.json").read_text(encoding="utf-8"))
        sample = status["screen_ocr"]["sample"]
        with redirect_stdout(io.StringIO()) as json_stdout:
            youtube_host._emit(result, as_json=True)
        self.assertEqual(json.loads(json_stdout.getvalue())["screen_ocr"]["sample"], sample)
        self.assertEqual(sample["calibration_status"], "fallback")
        reason = sample["calibration_reason"]
        stderr_text = stderr.getvalue()
        for fragment in ("first=example", "second=sensitive-value", "top-secret-token",
                         "extra-part", "\x1b", "\x07", "[31m", "[0m"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, reason)
                self.assertNotIn(fragment, stderr_text)

        stderr_lines = stderr_text.splitlines()
        for line in [reason, *stderr_lines]:
            self.assertFalse(any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in line), repr(line))
        notices = [
            line for line in stderr_lines
            if not line.startswith(("fetching captions with yt-dlp ", "captions acquired via yt-dlp "))
        ]
        self.assertEqual(len(notices), 1, notices)
        self.assertIn("calibration", notices[0])
        self.assertIn("fallback", notices[0])
        self.assertIn(f"{sample['estimated_seconds']:.1f}s", notices[0])

    def test_auto_unusable_calibration_without_sample_latency_records_null_estimate_and_fallback(self):
        sample_result = {
            "result": "slides_detected",
            "duration": 1000,
            "calibration_status": "calibrated",
            "calibration": {"estimated_total_seconds": 0.0},
        }
        with redirect_stderr(io.StringIO()) as stderr:
            self.host(0.2, sample_result=sample_result)

        status = json.loads((self.job / "status.json").read_text(encoding="utf-8"))
        sample = status["screen_ocr"]["sample"]
        self.assertEqual(sample["calibration_status"], "fallback")
        reason = sample["calibration_reason"]
        self.assertIsInstance(reason, str)
        self.assertTrue(reason.strip())
        self.assertEqual(reason.splitlines(), [reason])
        self.assertIn("estimated_seconds", sample)
        self.assertIsNone(sample["estimated_seconds"])
        notices = [
            line for line in stderr.getvalue().splitlines()
            if not line.startswith(("fetching captions with yt-dlp ", "captions acquired via yt-dlp "))
        ]
        self.assertEqual(len(notices), 1, notices)
        self.assertIn("calibration", notices[0])
        self.assertIn("fallback", notices[0])
        self.assertIn("(estimated unknown)", notices[0])

    def test_auto_calibration_fallback_uses_allowlisted_reason_drops_untrusted_detail_and_keeps_stdout_clean(self):
        calibration = SimpleNamespace(filesize=30_000_000, decode=0.25, grouping=0.05,
                                      first_pass=0.5, half_transform=0.05, second_pass=0.5)
        error = screen_ocr.ScreenError(
            "FFmpeg calibration clip failed: \x1bc\x1b[38:2:255:0:0m"
            "   orphaned-continuation-secret\n  more-secret-value"
        )
        with (
            patch.object(screen_ocr, "_calibrate_full_scan", side_effect=error) as calibrate,
            redirect_stdout(io.StringIO()) as host_stdout,
            redirect_stderr(io.StringIO()) as host_stderr,
        ):
            result, _, _ = self.host(0.2, sample_decode=0.2, calibration=calibration)
            self.assertEqual(host_stdout.getvalue(), "")
            youtube_host._emit(result, as_json=True)

        calibrate.assert_called_once()
        status = json.loads((self.job / "status.json").read_text(encoding="utf-8"))
        parsed = json.loads(host_stdout.getvalue())
        self.assertEqual(parsed["screen_ocr"]["sample"], status["screen_ocr"]["sample"])
        sample = status["screen_ocr"]["sample"]
        self.assertEqual(sample["calibration_status"], "fallback")
        reason = sample["calibration_reason"]
        self.assertEqual(reason, "FFmpeg calibration clip failed")
        for fragment in ("orphaned-continuation-secret", "more-secret-value", "38:2", "\x1b"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, reason)
                self.assertNotIn(fragment, host_stderr.getvalue())

    def test_auto_recalculated_zero_calibration_estimate_downgrades_to_fallback(self):
        # Rescaling from 100 to 125 intervals yields zero, with no sample latency to fall back on.
        sample_result = {
            "result": "slides_detected",
            "duration": 1000,
            "calibration_status": "calibrated",
            "calibration": {
                "estimated_total_seconds": 10.0,
                "intervals": 100,
                "download_seconds": 0.0,
                "extract_seconds_per_interval": 0.0,
                "group_seconds_per_frame": 0.0,
                "read_frame_seconds": 0.0,
            },
        }
        with redirect_stderr(io.StringIO()) as stderr:
            self.host(0.2, sample_result=sample_result)

        status = json.loads((self.job / "status.json").read_text(encoding="utf-8"))
        sample = status["screen_ocr"]["sample"]
        self.assertEqual(sample["calibration_status"], "fallback")
        self.assertEqual(sample["calibration_reason"], "calibration estimate unavailable")
        self.assertIn("estimated_seconds", sample)
        self.assertIsNone(sample["estimated_seconds"])
        notices = [
            line for line in stderr.getvalue().splitlines()
            if not line.startswith(("fetching captions with yt-dlp ", "captions acquired via yt-dlp "))
        ]
        self.assertEqual(len(notices), 1, notices)
        self.assertIn("calibration", notices[0])
        self.assertIn("fallback", notices[0])
        self.assertIn("(estimated unknown)", notices[0])

    def expected_sample_estimate(self, sample):
        intervals = math.ceil(self.DURATION / screen_ocr.SLIDE_INTERVAL)
        return round(
            sample["mean_sample_extract_seconds"] * intervals
            + sample["mean_frame_ocr_seconds"] * screen_ocr.SLIDE_OCR_PASSES
            * screen_ocr.estimate_ocr_frames(intervals),
            3,
        )

    def test_auto_skips_when_sample_extract_plus_ocr_exceeds_safe_budget(self):
        # Extraction at 3s over 125 intervals plus OCR at 1.6s over 57 frames exceeds 420s.
        result, sample, extract = self.host(0.8, sample_decode=6.0)

        sample.assert_called_once()
        self.assertEqual(extract.call_count, 0)
        screen = self.assert_timeout_fallback(result)
        self.assertGreater(screen["estimated_seconds"], 420.0)

    def test_auto_fast_machine_one_hour_slide_video_is_not_skipped(self):
        self.DURATION = 3600
        # 20s download, 450 extraction/grouping intervals and 203 OCR frames fit within 630s.
        calibration = SimpleNamespace(filesize=120_000_000, decode=0.25, grouping=0.02,
                                      first_pass=0.30, half_transform=0.02, second_pass=0.20)
        with patch.object(screen_ocr, "_measure_download_seconds", create=True, return_value=20.0) as download:
            result, sample, extract = self.host(0.25, sample_decode=0.4, calibration=calibration)

        sample.assert_called_once()
        self.assert_slides_ready(result, extract)
        download.assert_called()

    def test_auto_aborts_live_full_scan_on_sustained_overrun_while_explicit_slides_exempt(self):
        self.host(32.0, mode="off")
        transcript = self.job / "transcript.txt"
        expected_transcript = transcript.read_bytes()
        sample_result = {"result": "slides_detected", "duration": 1000, "mean_frame_ocr_seconds": 0.2}

        with self.subTest(mode="auto"):
            with patch.object(screen_ocr, "_read_frame", wraps=screen_ocr._read_frame) as read_frame:
                result, sample, extract = self.host(32.0, full_frames=10,
                                                    sample_result=sample_result)

            sample.assert_called_once()
            extract.assert_called_once()
            self.assertGreater(read_frame.call_count, 0)
            self.assertLess(read_frame.call_count, 8)
            self.assert_timeout_fallback(result)
            self.assertFalse((self.job / "screen.txt").exists())
            self.assertEqual(transcript.read_bytes(), expected_transcript)

        with self.subTest(mode="slides"):
            with patch.object(screen_ocr, "_read_frame", wraps=screen_ocr._read_frame) as read_frame:
                result, sample, extract = self.host(22.0, mode="slides", full_frames=10,
                                                    sample_result=sample_result)

            sample.assert_not_called()
            self.assertEqual(read_frame.call_count, 10)
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
        self.assertEqual(result["timeout_seconds"], 600)
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
