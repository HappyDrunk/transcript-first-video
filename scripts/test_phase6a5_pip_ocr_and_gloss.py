#!/usr/bin/env python3
"""Phase 6A.5 tests: talking-head PiP/corner-card overlay OCR and redundant gloss dedup."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import render_reading_note as rrn
import screen_ocr
import youtube_host


SOURCE = "https://www.youtube.com/watch?v=test6a5pip0"


def _gray_png_grid(width: int, height: int, tile_shades: dict[tuple[int, int], int], bg: int = 30) -> bytes:
    """Build an 8-bit grayscale PNG with an 8x8 tile grid of deterministic shades."""
    rows_grid, cols_grid = screen_ocr.SLIDE_TILE_GRID
    pixels = bytearray([bg] * (width * height))
    for (tr, tc), shade in tile_shades.items():
        y0 = tr * height // rows_grid
        y1 = (tr + 1) * height // rows_grid
        x0 = tc * width // cols_grid
        x1 = (tc + 1) * width // cols_grid
        for y in range(y0, y1):
            row_start = y * width
            for x in range(x0, x1):
                pixels[row_start + x] = shade

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * width:(y + 1) * width])
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )


def _ocr_result(lines: list[tuple[str, float, float] | tuple[str, float, float, float, float]]):
    """Build a RapidOCR-like result from (text, y_center, score[, x0, x1]) tuples."""
    boxes, txts, scores = [], [], []
    for item in lines:
        if len(item) == 5:
            text, y_center, score, x0, x1 = item
        else:
            text, y_center, score = item
            x0, x1 = 20.0, 220.0
        boxes.append([(x0, y_center - 8.0), (x1, y_center - 8.0), (x1, y_center + 8.0), (x0, y_center + 8.0)])
        txts.append(text)
        scores.append(score)
    return SimpleNamespace(boxes=boxes, txts=txts, scores=scores)


class OverlaySampleTests(unittest.TestCase):
    def _run_sample(self, frame_results: dict[int, list[tuple[str, float, float]]], *, duration: int = 1000,
                    fake_elapsed_per_pair: float = 0.0):
        stream = json.dumps({
            "duration": duration,
            "height": 480,
            "url": "https://media.example/480.mp4",
            "ext": "mp4",
            "protocol": "https",
        })
        windows: list[int] = []
        now = [100.0]

        def fake_monotonic():
            return now[0]

        def fake_run(scan, args, description, **kwargs):
            if args[0] == "ffmpeg":
                output = Path(args[-1])
                at = int(output.stem.split("-")[0])
                windows.append(at)
                for idx in (1, 2):
                    output.with_name(output.name.replace("%02d", f"{idx:02d}")).write_bytes(f"frame-{at}-{idx}".encode())
                now[0] += fake_elapsed_per_pair
            return SimpleNamespace(stdout=stream)

        def fake_recognize(scan, func, *args, **kwargs):
            if func is screen_ocr._rapidocr:
                return object()
            frame_bytes = args[0]
            # frame-{at}-{idx}
            parts = frame_bytes.decode().split("-")
            at = int(parts[1])
            return _ocr_result(frame_results.get(at, []))

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(screen_ocr.Scan, "probe", return_value="ffmpeg"),
            patch.object(screen_ocr.Scan, "run", autospec=True, side_effect=fake_run),
            patch.object(screen_ocr.Scan, "recognize", autospec=True, side_effect=fake_recognize),
            patch.object(screen_ocr, "getproxies", return_value={}),
            patch.object(screen_ocr.time, "monotonic", side_effect=fake_monotonic),
        ):
            result = screen_ocr.sample_slides(Path(folder), SOURCE, ["yt-dlp"], lambda: [])
        return result, windows

    def test_fm1_persistent_watermark_never_triggers_overlay(self):
        """Persistent corner watermark at all 4 positions must stay not_found with 4 groups."""
        watermark = [("CommonSenseInvesting2024", 440.0, 0.95), ("BenFelixChannel", 455.0, 0.95)]
        frame_results = {100: watermark, 330: watermark, 560: watermark, 800: watermark}
        result, windows = self._run_sample(frame_results)

        self.assertEqual(result["result"], "not_found")
        self.assertNotIn("profile", result)
        self.assertEqual(result["groups_checked"], 4)
        self.assertEqual(windows, [100, 330, 560, 800])

    def test_fm1_transient_corner_cards_trigger_overlay_profile(self):
        """Two distinct transient corner cards at 0.33 and 0.80 must trigger slides_detected + overlay."""
        frame_results = {
            100: [],
            330: [("ERUS YTD", 60.0, 0.92), ("-99.86%", 78.0, 0.91)],
            560: [],
            800: [("Albuquerque (2012)", 410.0, 0.93), ("Journal of Financial Economics", 426.0, 0.90)],
        }
        result, windows = self._run_sample(frame_results)

        self.assertEqual(result["result"], "slides_detected")
        self.assertEqual(result.get("profile"), "overlay")
        self.assertEqual(result.get("overlay_positions"), [330, 800])
        self.assertEqual(result["groups_checked"], 4)
        self.assertEqual(windows, [100, 330, 560, 800])

    def test_fm1_short_single_label_does_not_false_positive_workshop_video(self):
        """Short single labels like 'Model 1' / '0.5 g' must NOT trigger overlay on workshop videos."""
        frame_results = {
            100: [("Model 1", 400.0, 0.92)],
            330: [("0.5 g", 400.0, 0.92)],
            560: [("Section 2", 400.0, 0.92)],
            800: [("Test 3", 400.0, 0.92)],
        }
        result, windows = self._run_sample(frame_results)

        self.assertEqual(result["result"], "not_found")
        self.assertNotIn("profile", result)
        self.assertEqual(windows, [100, 330, 560, 800])

    def test_fm1_single_hit_triggers_conditional_extra_probes_when_budget_allows(self):
        """Exactly 1 transient hit runs extra probes at 0.22/0.68 if budget permits, stopping on 2nd hit."""
        frame_results = {
            100: [],
            330: [("Albuquerque (2012)", 410.0, 0.93), ("Review of Financial Studies", 426.0, 0.91)],
            560: [],
            800: [],
            220: [("ERUS YTD", 60.0, 0.94), ("-99.86%", 76.0, 0.92)],
            680: [],
        }
        result, windows = self._run_sample(frame_results, fake_elapsed_per_pair=2.0)

        self.assertEqual(result["result"], "slides_detected")
        self.assertEqual(result.get("profile"), "overlay")
        self.assertEqual(windows, [100, 330, 560, 800, 220])
        self.assertEqual(result["groups_checked"], 5)

    def test_fm1_single_hit_skips_extra_probes_when_budget_tight(self):
        """When remaining sample budget is too tight, do NOT run extra probes."""
        frame_results = {
            100: [],
            330: [("Albuquerque (2012)", 410.0, 0.93), ("Review of Financial Studies", 426.0, 0.91)],
            560: [],
            800: [],
            220: [("ERUS YTD", 60.0, 0.94), ("-99.86%", 76.0, 0.92)],
        }
        # 4 pairs * 9.5s = 38.0s elapsed out of 44.5s budget -> remaining 6.5s <= 1.5*9.5 + 0.5
        result, windows = self._run_sample(frame_results, fake_elapsed_per_pair=9.5)

        self.assertEqual(result["result"], "not_found")
        self.assertEqual(windows, [100, 330, 560, 800])
        self.assertEqual(result["groups_checked"], 4)

    def test_fm1_short_video_repeated_seeks_do_not_self_classify_as_persistent(self):
        """A 4s video seeks [0, 1, 2, 2]; repeating at=2 must not treat card@2 as persistent."""
        frame_results = {
            0: [("ERUS YTD", 60.0, 0.92), ("-99.86%", 78.0, 0.91)],
            1: [],
            2: [("Albuquerque (2012)", 410.0, 0.93), ("Journal of Financial Economics", 426.0, 0.90)],
        }
        result, windows = self._run_sample(frame_results, duration=4)

        self.assertEqual(windows, [0, 1, 2, 2])
        self.assertEqual(result["result"], "slides_detected")
        self.assertEqual(result.get("profile"), "overlay")
        self.assertEqual(result.get("overlay_positions"), [0, 2])

    def test_fm1_burned_in_bottom_center_subtitles_do_not_trigger_overlay(self):
        """Two-line burned-in subtitles centered in the bottom band must stay not_found."""
        frame_results = {
            100: [],
            330: [
                ("This is a long burned in subtitle line", 420.0, 0.95, 180.0, 680.0),
                ("continuing across the bottom center", 442.0, 0.95, 210.0, 650.0),
            ],
            560: [],
            800: [
                ("Another spoken sentence shown here", 420.0, 0.95, 190.0, 670.0),
                ("still inside the subtitle region", 442.0, 0.95, 220.0, 640.0),
            ],
        }
        result, _ = self._run_sample(frame_results)

        self.assertEqual(result["result"], "not_found")
        self.assertNotIn("profile", result)

    def test_fm1_extra_probe_failure_degrades_cleanly_to_not_found(self):
        """An error or timeout during an optional extra probe must preserve clean not_found."""
        stream = json.dumps({
            "duration": 1000, "height": 480, "url": "https://media.example/480.mp4",
            "ext": "mp4", "protocol": "https",
        })
        frame_results = {
            330: [("Albuquerque (2012)", 410.0, 0.93), ("Review of Financial Studies", 426.0, 0.91)],
        }

        def fake_run(scan, args, description, **kwargs):
            if args[0] == "ffmpeg":
                output = Path(args[-1])
                at = int(output.stem.split("-")[0])
                if at == 220:
                    raise screen_ocr.ScreenTimeout("extra probe stalled")
                for idx in (1, 2):
                    output.with_name(output.name.replace("%02d", f"{idx:02d}")).write_bytes(f"frame-{at}-{idx}".encode())
            return SimpleNamespace(stdout=stream)

        def fake_recognize(scan, func, *args, **kwargs):
            if func is screen_ocr._rapidocr:
                return object()
            at = int(args[0].decode().split("-")[1])
            return _ocr_result(frame_results.get(at, []))

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(screen_ocr.Scan, "probe", return_value="ffmpeg"),
            patch.object(screen_ocr.Scan, "run", autospec=True, side_effect=fake_run),
            patch.object(screen_ocr.Scan, "recognize", autospec=True, side_effect=fake_recognize),
            patch.object(screen_ocr, "getproxies", return_value={}),
        ):
            result = screen_ocr.sample_slides(Path(folder), SOURCE, ["yt-dlp"], lambda: [])

        self.assertEqual(result["result"], "not_found")
        self.assertEqual(result["groups_checked"], 4)


class OverlayFullScanTests(unittest.TestCase):
    def test_fm2_overlay_retains_corner_card_under_talking_head_motion(self):
        """With 6 moving center face tiles, overlay profile keeps the frame where a bottom-left card appears."""
        face_tiles = [(2, 3), (2, 4), (3, 3), (3, 4), (4, 3), (4, 4)]
        card_tile = (7, 0)  # bottom-left 22% / left 30% zone (cropped out by default ROI!)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            frames = []
            for idx in range(16):
                shades = {tile: (200 if idx % 2 == 0 else 40) for tile in face_tiles}
                if idx == 11:
                    shades[card_tile] = 245
                path = root / f"frame-{idx:02d}.png"
                path.write_bytes(_gray_png_grid(160, 90, shades))
                frames.append(screen_ocr.Frame(path, float(idx * 8)))

            scan = screen_ocr.Scan("slides", 128)
            overlay_groups = screen_ocr._group_frames(scan, "ffmpeg", frames, profile="overlay")
            self.assertEqual([len(g) for g in overlay_groups], [8, 8])

            selected, capped = screen_ocr._select_representative_frames(
                scan, "ffmpeg", overlay_groups, profile="overlay",
            )
            chosen_indices = [int(f.seconds // 8) for g in selected for f in g]
            self.assertIn(11, chosen_indices)
            self.assertEqual(capped, 0)

            # Default profile (profile=None) still collapses >4 dynamic tiles to [group[0], group[-1]]!
            default_selected, _ = screen_ocr._select_representative_frames(scan, "ffmpeg", [frames])
            self.assertEqual([int(f.seconds // 8) for f in default_selected[0]], [0, 15])

    def test_fm2_overlay_falls_back_to_endpoints_when_full_screen_moves(self):
        """If >= 49 of 64 tiles are dynamic (<16 static active tiles), overlay safely collapses to endpoints."""
        moving_tiles = [(r, c) for r in range(8) for c in range(8) if not (r < 2 and c < 7)]  # 50 moving, 14 static
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            frames = []
            for idx in range(16):
                shades = {tile: (220 if idx % 2 == 0 else 20) for tile in moving_tiles}
                path = root / f"frame-{idx:02d}.png"
                path.write_bytes(_gray_png_grid(160, 90, shades))
                frames.append(screen_ocr.Frame(path, float(idx * 8)))

            scan = screen_ocr.Scan("slides", 128)
            overlay_groups = screen_ocr._group_frames(scan, "ffmpeg", frames, profile="overlay")
            selected, _ = screen_ocr._select_representative_frames(
                scan, "ffmpeg", overlay_groups, profile="overlay",
            )
            self.assertEqual([[int(f.seconds // 8) for f in g] for g in selected], [[0, 7], [8, 15]])

    def test_fm2_youtube_host_forwards_overlay_profile_only_when_present(self):
        """youtube_host._screen_result passes profile='overlay' iff sample returns profile='overlay'."""
        calls = []

        def fake_extract(*args, **kwargs):
            calls.append((args, kwargs))
            return {"state": "ready", "mode": "slides", "path": "screen.txt", "sha256": "0" * 64}

        with tempfile.TemporaryDirectory() as folder:
            staged = Path(folder)
            with (
                patch.object(
                    screen_ocr, "sample_slides",
                    return_value={"result": "slides_detected", "profile": "overlay", "duration": 964.0},
                ),
                patch.object(screen_ocr, "extract", side_effect=fake_extract),
            ):
                res = youtube_host._screen_result(staged, "auto", SOURCE, ["yt-dlp"], 964.0)
            self.assertEqual(res["state"], "ready")
            self.assertEqual(calls[-1][1], {"profile": "overlay"})

            # Without profile key, extract receives zero kwargs (backward-compatible with existing mocks)
            with (
                patch.object(
                    screen_ocr, "sample_slides",
                    return_value={"result": "slides_detected", "duration": 964.0},
                ),
                patch.object(screen_ocr, "extract", side_effect=fake_extract),
            ):
                res2 = youtube_host._screen_result(staged, "auto", SOURCE, ["yt-dlp"], 964.0)
            self.assertEqual(res2["state"], "ready")
            self.assertEqual(calls[-1][1], {})

    def test_fm2_overlay_budget_estimation_uses_overlay_ratio(self):
        """Overlay profile budgets for 100% of intervals so frequent static changes don't surprise overrun."""
        self.assertEqual(screen_ocr.estimate_ocr_frames(16), 8)
        self.assertEqual(screen_ocr.estimate_ocr_frames(16, profile="overlay"), 16)

        with tempfile.TemporaryDirectory() as folder:
            staged = Path(folder)
            sample = {
                "result": "slides_detected",
                "profile": "overlay",
                "duration": 128.0,  # 16 intervals
                "mean_frame_ocr_seconds": 15.0,  # 15 * 2 * 16 = 480s > safe_budget (420s)
                "mean_sample_extract_seconds": 0.0,
            }
            with (
                patch.object(screen_ocr, "sample_slides", return_value=sample),
                patch.object(screen_ocr, "extract", side_effect=AssertionError("should be budget-rejected")),
            ):
                res = youtube_host._screen_result(staged, "auto", SOURCE, ["yt-dlp"], 128.0)
        self.assertEqual(res["state"], "fallback")
        self.assertEqual(res["result"], "timeout")
        self.assertEqual(res["sample"]["ocr_frame_ratio_assumed"], screen_ocr.AUTO_OVERLAY_OCR_FRAME_RATIO)

        # Calibrated duration-adjustment path also uses overlay ratio (1.0)
        with tempfile.TemporaryDirectory() as folder:
            staged = Path(folder)
            cal_sample = {
                "result": "slides_detected",
                "profile": "overlay",
                "duration": 160.0,  # 20 intervals (differs from calibration.intervals=16)
                "calibration_status": "calibrated",
                "calibration": {
                    "intervals": 16,
                    "download_seconds": 10.0,
                    "extract_seconds_per_interval": 0.5,
                    "group_seconds_per_frame": 0.0,
                    "read_frame_seconds": 25.0,  # 20 * 25 + 20 = 520s > 420s safe_budget (ordinary 9*25+20=245s would pass!)
                    "estimated_total_seconds": 200.0,
                },
            }
            with (
                patch.object(screen_ocr, "sample_slides", return_value=cal_sample),
                patch.object(screen_ocr, "extract", side_effect=AssertionError("calibrated overlay should be rejected")),
            ):
                res_cal = youtube_host._screen_result(staged, "auto", SOURCE, ["yt-dlp"], 160.0)
        self.assertEqual(res_cal["state"], "fallback")
        self.assertEqual(res_cal["result"], "timeout")
        self.assertGreater(res_cal["estimated_seconds"], 500.0)

        # _calibrate_full_scan(profile="overlay") directly records ocr_frame_ratio_assumed=1.0
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)

            def fake_cal_run(scan, args, step, **kwargs):
                output = Path(args[-1])
                output.write_bytes(_gray_png_grid(160, 90, {}))
                return SimpleNamespace(stdout="", stderr="")

            with (
                patch.object(screen_ocr, "_measure_download_seconds", return_value=1.0),
                patch.object(screen_ocr.Scan, "run", autospec=True, side_effect=fake_cal_run),
                patch.object(screen_ocr, "_frames", return_value=[]),
                patch.object(screen_ocr, "_group_frames", return_value=[]),
                patch.object(screen_ocr, "_read_frame", return_value=[]),
            ):
                cal = screen_ocr._calibrate_full_scan(
                    "ffmpeg", object(),
                    {"url": "https://media.example/1080.mp4", "height": 1080, "filesize": 10_000_000, "http_headers": {}},
                    128.0, 32, "", work, profile="overlay",
                )
        self.assertEqual(cal["ocr_frame_ratio_assumed"], 1.0)
        self.assertEqual(cal["ocr_frames_estimated"], 16)

    def test_fm2_extract_records_overlay_profile_in_status(self):
        """screen_ocr.extract(profile='overlay') records profile='overlay' in returned status."""
        with tempfile.TemporaryDirectory() as folder:
            staged = Path(folder)

            def fake_frames(scan, ffmpeg, video, work, mode):
                paths = []
                for idx in range(4):
                    p = work / f"frame-{idx:06d}.png"
                    p.write_bytes(_gray_png_grid(160, 90, {(7, 0): 240 if idx == 2 else 30}))
                    paths.append(screen_ocr.Frame(p, float(idx * 8)))
                return paths

            def fake_download(scan, cmd, source, work):
                v = work / "video.mp4"
                v.write_bytes(b"vid")
                return v

            def fake_read(scan, ffmpeg, ocr, mode, crop, frame, **kwargs):
                if frame.seconds == 16.0:
                    return [(screen_ocr.Line("Albuquerque (2012)", 20, 410, 200, 16, 95.0), True)]
                return []

            with (
                patch.object(screen_ocr.Scan, "probe", return_value="ffmpeg"),
                patch.object(screen_ocr, "_download", side_effect=fake_download),
                patch.object(screen_ocr, "_frames", side_effect=fake_frames),
                patch.object(screen_ocr.Scan, "recognize", return_value=object()),
                patch.object(screen_ocr, "_read_frame", side_effect=fake_read),
            ):
                status = screen_ocr.extract(staged, "slides", SOURCE, ["yt-dlp"], 32.0, list, True, profile="overlay")

        self.assertEqual(status["state"], "ready")
        self.assertEqual(status.get("profile"), "overlay")


class GlossDedupTests(unittest.TestCase):
    def test_fm3_rule_a_skips_when_next_sentence_defines_term(self):
        block = "只看一项资产对组合的均值和方差，会漏掉一个叫偏度的统计量。偏度衡量分布是否对称。"
        self.assertIsNone(rrn._resolve_gloss_insertion(block, "偏度", "涨跌分布够不够对称"))

    def test_fm3_rule_a_keeps_gloss_when_next_sentence_merely_mentions_term(self):
        block1 = "只看均值会漏掉一个叫偏度的统计量。偏度很高。"
        res1 = rrn._resolve_gloss_insertion(block1, "偏度", "涨跌分布够不够对称")
        self.assertIsNotNone(res1)
        self.assertEqual(res1[1], "（注：涨跌分布够不够对称）")

        block2 = "医院采用了基础隔震方案。基础隔震是 1991 年才在美国兴起的。"
        res2 = rrn._resolve_gloss_insertion(block2, "基础隔震", "把房子和地面松开")
        self.assertIsNotNone(res2)
        self.assertEqual(res2[1], "（注：把房子和地面松开）")

        # Non-definitional prefixes like 指标 / 表示 / 指的方向 must NOT be falsely suppressed
        block3 = "这里需要考虑偏度。偏度指标很高。"
        self.assertIsNotNone(rrn._resolve_gloss_insertion(block3, "偏度", "涨跌分布够不够对称"))
        block4 = "市场紧盯美联储动向。美联储表示将加息。"
        self.assertIsNotNone(rrn._resolve_gloss_insertion(block4, "美联储", "美国中央银行"))
        block5 = "先看指针。指针指的方向是北。"
        self.assertIsNotNone(rrn._resolve_gloss_insertion(block5, "指针", "用来显示方向或读数的细杆"))

    def test_fm3_rule_b_skips_preceding_clause_echo(self):
        block = "人们往往先划一条多少有些任意的风险线，比如防洪里常用的 1-percent storm；地震规范也是同一思路。"
        self.assertIsNone(rrn._resolve_gloss_insertion(block, "1-percent storm", "防洪里常用的风险门槛"))

    def test_fm3_rule_b_keeps_short_overlap_and_helpful_glosses(self):
        # 3-char overlap (< 4) must still be kept
        block_short = "这是防洪里 1-percent storm 概念。"
        res_short = rrn._resolve_gloss_insertion(block_short, "1-percent storm", "防洪里的风险门槛")
        self.assertIsNotNone(res_short)

        # Single shared 4-char common word (< 50% of gloss) must still be kept
        block_common = "构建投资组合时会画出有效前沿。"
        self.assertIsNotNone(rrn._resolve_gloss_insertion(block_common, "有效前沿", "投资组合的最优边界"))

        # Negated preceding clause (adjacent or with intervening words) must NOT suppress gloss
        block_neg = "这不是衡量分布是否对称的偏度。"
        self.assertIsNotNone(rrn._resolve_gloss_insertion(block_neg, "偏度", "衡量分布是否对称的统计量"))
        block_neg2 = "这并不是在衡量分布是否对称的偏度。"
        self.assertIsNotNone(rrn._resolve_gloss_insertion(block_neg2, "偏度", "衡量分布是否对称的统计量"))

        # Protected-anchor fallback path must obey Invariant #7
        block_fallback = "先看 `偏度`。这个数值很高。"
        res_fb = rrn._resolve_gloss_insertion(block_fallback, "偏度", "涨跌分布够不够对称")
        self.assertIsNotNone(res_fb)
        rendered_fb = block_fallback[:res_fb[0]] + res_fb[1] + block_fallback[res_fb[0]:]
        self.assertEqual(rrn.GENERATED_NOTE_RE.sub("", rendered_fb), block_fallback)

        helpful_cases = [
            ("从物理上把上部结构和地面脱开。", "上部结构", "地面以上的房子主体"),
            ("把整组响应画出来，就得到一次地震的反应谱。对许多地震来说，加速度在短周期达到峰值。", "反应谱", "不同周期结构的晃动图"),
            ("今天，新兴市场约占全球自由流通市值的 10% 到 12%。", "自由流通市值", "能公开买卖的股份市值"),
        ]
        for block, label, gloss in helpful_cases:
            res = rrn._resolve_gloss_insertion(block, label, gloss)
            self.assertIsNotNone(res, f"helpful gloss unexpectedly suppressed: {label}")
            rendered = block[:res[0]] + res[1] + block[res[0]:]
            self.assertEqual(rrn.GENERATED_NOTE_RE.sub("", rendered), block)

    def test_fm3_rules_apply_to_english_paren_merge_path(self):
        block_a = "会漏掉一个叫偏度（skewness）的统计量。偏度衡量分布是否对称。"
        self.assertIsNone(rrn._resolve_gloss_insertion(block_a, "偏度", "涨跌分布够不够对称"))

        block_b = "比如防洪里常用的百年一遇（1-percent storm）；地震规范也是同一思路。"
        self.assertIsNone(rrn._resolve_gloss_insertion(block_b, "百年一遇", "防洪里常用的风险门槛"))

        block_keep = "今天，新兴市场约占全球自由流通市值（free-float market cap）的 10%。"
        res = rrn._resolve_gloss_insertion(block_keep, "自由流通市值", "能公开买卖的股份市值")
        self.assertIsNotNone(res)
        self.assertEqual(res[1], "；注：能公开买卖的股份市值")
        rendered = block_keep[:res[0]] + res[1] + block_keep[res[0]:]
        self.assertEqual(rrn.GENERATED_NOTE_RE.sub("", rendered), block_keep)


if __name__ == "__main__":
    unittest.main()
