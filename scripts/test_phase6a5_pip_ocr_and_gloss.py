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


def _ocr_result(lines: list[tuple[str, float, float]]):
    """Build a RapidOCR-like result from (text, y_center, score) tuples."""
    boxes, txts, scores = [], [], []
    for text, y_center, score in lines:
        boxes.append([(20.0, y_center - 8.0), (220.0, y_center - 8.0), (220.0, y_center + 8.0), (20.0, y_center + 8.0)])
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
        # 4 pairs * 9.5s = 38.0s elapsed out of 44.5s budget -> remaining 6.5s < 2*9.5 + 0.5
        result, windows = self._run_sample(frame_results, fake_elapsed_per_pair=9.5)

        self.assertEqual(result["result"], "not_found")
        self.assertEqual(windows, [100, 330, 560, 800])
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

    def test_fm3_rule_b_skips_preceding_clause_echo(self):
        block = "人们往往先划一条多少有些任意的风险线，比如防洪里常用的 1-percent storm；地震规范也是同一思路。"
        self.assertIsNone(rrn._resolve_gloss_insertion(block, "1-percent storm", "防洪里常用的风险门槛"))

    def test_fm3_rule_b_keeps_short_overlap_and_helpful_glosses(self):
        # 3-char overlap (< 4) must still be kept
        block_short = "这是防洪里 1-percent storm 概念。"
        res_short = rrn._resolve_gloss_insertion(block_short, "1-percent storm", "防洪里的风险门槛")
        self.assertIsNotNone(res_short)

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
