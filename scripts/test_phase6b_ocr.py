import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import screen_ocr as ocr
import youtube_host


class SlideBudgetTest(unittest.TestCase):
    def test_budget_clamps_to_floor_and_cap(self):
        for duration, budget in ((5082.35, 900.0), (3600, 900.0), (796, 600.0)):
            with self.subTest(duration=duration):
                self.assertEqual(ocr.slide_full_budget(duration), budget)

    def test_frame_extraction_recalculates_budget_with_cap(self):
        scan = ocr.Scan("slides", None)
        stderr = (
            "Duration: 01:24:42.35, start: 0.000000\n"
            "[Parsed_showinfo_1 @ 0x1] n: 0 pts: 0 pts_time:0.000000 checksum:ABCDEF01\n"
        )
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(scan, "run", return_value=SimpleNamespace(stderr=stderr)):
            work = Path(tmp)
            (work / "frame-000001.png").touch()
            self.assertEqual(len(ocr._frames(scan, "ffmpeg", work / "video", work, "slides")), 1)
        self.assertEqual(scan.budget, 900.0)

    def auto_result(self, duration, **sample):
        staged = Path("unused")
        with patch.object(ocr, "sample_slides", return_value={"result": "slides_detected", **sample}), \
             patch.object(ocr, "extract", return_value={"state": "ready"}) as extract:
            result = youtube_host._screen_result(staged, "auto", "source", ["yt-dlp"], duration)
        extract.assert_called_once()
        self.assertEqual(result["state"], "ready")
        return result["sample"]

    def test_85_minute_calibrated_scan_fits_safe_budget(self):
        duration = 5082
        scan = Mock()
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(ocr, "Scan", return_value=scan), \
             patch.object(ocr, "_measure_download_seconds", return_value=35.0), \
             patch.object(ocr, "_frames"), patch.object(ocr, "_group_frames"), \
             patch.object(ocr, "_read_frame"), \
             patch.object(ocr.time, "monotonic", side_effect=[0, 0.10, 0, 0.04, 0, 1.7, 0, 1.7]):
            calibration = ocr._calibrate_full_scan(
                "ffmpeg", Mock(), {"url": "https://example.com/video"}, duration, 0, "", Path(tmp),
            )
        self.assertEqual(calibration["ocr_frame_ratio_assumed"], 0.45)
        self.assertEqual(calibration["ocr_frames_estimated"], 287)
        sample = self.auto_result(duration, calibration=calibration, calibration_status="calibrated")
        self.assertEqual(sample["calibration_status"], "calibrated")
        self.assertEqual(sample["estimated_seconds"], 599.22)
        self.assertLessEqual(sample["estimated_seconds"], 630.0)

    def test_effective_intervals_use_representative_frame_estimate(self):
        sample = self.auto_result(800, calibration={
            "estimated_total_seconds": 20.0,
            "intervals": 10,
            "download_seconds": 10.0,
            "extract_seconds_per_interval": 0.25,
            "group_seconds_per_frame": 0.05,
            "read_frame_seconds": 1.7,
        })
        self.assertEqual(sample["estimated_seconds"], 116.5)

    def test_latency_fallback_uses_representative_frame_estimate(self):
        sample = self.auto_result(800, mean_frame_ocr_seconds=0.85, mean_sample_extract_seconds=0.25)
        self.assertEqual(sample["estimated_seconds"], 101.5)
        self.assertEqual(sample["ocr_frame_ratio_assumed"], 0.45)


class InMemoryFramesTest(unittest.TestCase):
    def test_onnx_thread_cap(self):
        engine = Mock()
        with patch.dict(sys.modules, {"rapidocr": SimpleNamespace(RapidOCR=engine)}):
            for cpu, expected in [(None, 1), (2, 2), (32, 4)]:
                with self.subTest(cpu=cpu), patch.object(ocr.os, "cpu_count", return_value=cpu):
                    ocr._rapidocr("slides")
                    self.assertEqual(engine.call_args.kwargs["params"][
                        "EngineConfig.onnxruntime.intra_op_num_threads"], expected)

    def test_grouping_only_transforms_failed_frame(self):
        scan = Mock()
        pixels = bytes(160 * 90)
        decode = ocr._memory_thumbnail
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            frames = [ocr.Frame(Path(tmp) / f"{i}.png", i) for i in range(2)]
            frames[1].path.write_bytes(b"image-1080")
            with patch.object(ocr, "_memory_thumbnail",
                              side_effect=lambda path: pixels if path == frames[0].path else decode(path)), \
                 patch.object(ocr, "_gray_pixels", return_value=pixels):
                self.assertEqual(ocr._group_frames(scan, "ffmpeg", frames), [frames])
        scan.run.assert_called_once()
        self.assertIn(str(frames[1].path), scan.run.call_args.args[0])

    def test_half_size_uses_memory_or_transforms_failed_frame(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            frame = ocr.Frame(Path(tmp) / "frame.png", 0)
            frame.path.write_bytes(b"image-1080")
            scan = Mock()
            scan.run.side_effect = lambda args, step: Path(args[-1]).write_bytes(b"image-540")
            scan.recognize.return_value = SimpleNamespace(boxes=None, txts=None, scores=None)
            ocr._read_frame(scan, "ffmpeg", "engine", "slides", "", frame)
            self.assertEqual([call.args for call in scan.recognize.call_args_list],
                             [("engine", b"image-1080"), ("engine", b"image-540")])
            scan.run.assert_called_once()
            self.assertEqual(scan.run.call_args.args[1], "FFmpeg half transform")

            scan.reset_mock()
            decoded = object()
            with patch.object(ocr, "_memory_half", return_value=decoded):
                ocr._read_frame(scan, "ffmpeg", "engine", "slides", "", frame)
            scan.run.assert_not_called()
            self.assertIs(scan.recognize.call_args.args[1], decoded)


def thumbnail(*levels):
    width, height = 160, 90
    pixels = bytes(
        levels[x // 20] if y < 11 and x // 20 < len(levels) else 0
        for y in range(height) for x in range(width)
    )
    return width, height, pixels


class RepresentativeFramesTest(unittest.TestCase):
    def select(self, sequences):
        groups = [[ocr.Frame(Path(f"{g}-{i}.png"), i) for i in range(len(sequence))]
                  for g, sequence in enumerate(sequences)]
        thumbnails = dict(zip((frame for group in groups for frame in group),
                              (thumb for sequence in sequences for thumb in sequence)))
        with patch.object(ocr, "_full_thumbnail", create=True,
                          side_effect=lambda scan, ffmpeg, frame: thumbnails[frame]), \
             patch.dict(sys.modules, {"numpy": None}):
            selected, capped = ocr._select_representative_frames(Mock(), "ffmpeg", groups)
        return [[frame.seconds for frame in group] for group in selected], capped

    def test_local_change_and_drift_from_last_selected(self):
        self.assertEqual(self.select([[thumbnail(x) for x in (0, 0, 7, 14, 14, 44, 44)]]),
                         ([[0, 3, 5, 6]], 0))

    def test_dynamic_jitter_and_group_boundaries(self):
        jitter = [thumbnail(40 * (i % 2), 40 if i >= 5 else 0) for i in range(11)]
        self.assertEqual(self.select([jitter]), ([[0, 5, 10]], 0))
        groups = [[thumbnail(0), thumbnail(40), thumbnail(40)] for _ in range(5)]
        self.assertEqual(self.select(groups), ([[0, 1, 2]] * 5, 0))

    def test_full_screen_motion_and_uniform_cap(self):
        motion = [thumbnail(*([40 * (i % 2)] * 5)) for i in range(11)]
        self.assertEqual(self.select([motion]), ([[0, 10]], 0))
        changes = [thumbnail(*([40 if j == i % 8 else 0 for j in range(8)])) for i in range(11)]
        self.assertEqual(self.select([changes]), ([[0, 1, 3, 4, 6, 7, 9, 10]], 3))

    def test_bottom_right_pixel_is_counted(self):
        a = thumbnail()
        b = (*a[:2], a[2][:-1] + b"\xff")
        with patch.dict(sys.modules, {"numpy": None}):
            diffs = ocr._tile_differences(a, b)
        self.assertEqual(diffs, (0.0,) * 63 + (255 / (12 * 20),))

    def test_failed_thumbnails_keep_group_and_short_groups_skip_decoding(self):
        short = [thumbnail(), thumbnail()]
        self.assertEqual(self.select([short, [thumbnail(), None, thumbnail()]]),
                         ([[0, 1], [0, 1, 2]], 0))

    def test_extract_aligns_overrun_and_evidence_with_selected_frames(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            staged = Path(tmp)
            frames = [ocr.Frame(staged / f"f{i}.png", i * 8) for i in range(6)]
            for frame in frames:
                frame.path.write_bytes(b"image-1080")
            video = staged / "video"
            video.touch()
            scan = Mock(started=0, budget=100)
            scan.remaining.return_value = 2.5
            pixels = thumbnail()
            with patch.object(ocr, "Scan", return_value=scan), \
                 patch.object(ocr, "_download", return_value=video), \
                 patch.object(ocr, "_frames", return_value=frames), \
                 patch.object(ocr, "_group_frames", return_value=[frames[:3], frames[3:]]), \
                 patch.object(ocr, "_full_thumbnail", create=True, return_value=pixels), \
                 patch.object(ocr, "AUTO_LIVE_OVERRUN_MIN_FRAMES", 2), \
                 patch.object(ocr.time, "monotonic", side_effect=range(20)), \
                 patch.object(ocr, "_read_frame", side_effect=lambda *args: [
                     (ocr.Line(args[-1].path.stem, 0, 0, 10, 10, 99), True)
                 ]):
                status = ocr.extract(staged, "slides", "source", ["yt-dlp"], 60, list, True)
            self.assertEqual(status["state"], "ready")
            self.assertEqual([status[key] for key in ("frames_extracted", "frames_ocred", "frames_capped")],
                             [6, 4, 0])
            self.assertEqual((staged / "screen.txt").read_text(encoding="utf-8").splitlines(), [
                "[00:00][幻灯片 1] f0.png", "[00:00][画面] f0", "[00:16][画面] f2",
                "[00:24][幻灯片 2] f3.png", "[00:24][画面] f3", "[00:40][画面] f5",
            ])

