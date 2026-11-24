#!/usr/bin/env python3
"""Freeze slide grouping, repeated text, and per-slide selection behavior."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import screen_ocr
import verify_report
from test_phase2e_media_fixture import frame_data, frame_png


ROOT = Path(__file__).resolve().parents[1]
MARKER = re.compile(r"^\[((?:\d+:)?\d{2,}:\d{2})\]\[幻灯片 (\d+)\](?: frame-\d+\.png)?$")


def recognized(text: str, y: int = 100) -> tuple[screen_ocr.Line, bool]:
    return screen_ocr.Line(text, 100, y, 250, 20, 99), True


class SlideGroupingTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def frames(self, folder: Path, levels: tuple[int, ...]) -> list[screen_ocr.Frame]:
        folder.mkdir(parents=True)
        frames = []
        for index, level in enumerate(levels):
            path = folder / f"frame-{index + 1:06d}.png"
            path.write_bytes(frame_png(level))
            frames.append(screen_ocr.Frame(path, index * 8))
        return frames

    def write(self, levels: tuple[int, ...], results: list, indices: list[list[int]]) -> tuple[list[str], dict]:
        staged = self.root / "output"
        staged.mkdir()
        frames = self.frames(self.root / "frames", levels)
        groups = [[frames[index] for index in group] for group in indices]
        options = {"filter_watermarks": True}
        # Run the old writer on the same data to expose its global text loss.
        # The new argument becomes active as soon as the implementation exists.
        if "slide_groups" in inspect.signature(screen_ocr._write_evidence).parameters:
            options["slide_groups"] = groups
        references = screen_ocr._write_evidence(staged, frames, results, **options)
        rows = (staged / "screen.txt").read_text(encoding="utf-8").splitlines()
        print(json.dumps({"screen": rows, "screenshot_lines": references}, ensure_ascii=False))
        for filename, line_numbers in references.items():
            self.assertTrue((staged / "screen-frames" / filename).is_file())
            for line_number in line_numbers:
                self.assertTrue(MARKER.fullmatch(rows[line_number - 1]) or
                                re.match(r"^\[[^]]+\]\[画面\??\] ", rows[line_number - 1]))
        return rows, references

    def test_same_slide_duplicates_collapse(self) -> None:
        rows, _ = self.write(
            (10, 12),
            [[recognized("Shared page heading"), recognized("First detail", 200)],
             [recognized("Shared page heading"), recognized("Next detail", 220)]],
            [[0, 1]],
        )
        self.assertEqual(sum(row.endswith(" Shared page heading") for row in rows), 1, rows)

    def test_non_majority_text_survives_in_each_slide(self) -> None:
        results = []
        for index in range(5):
            lines = [recognized(f"Unique page {index + 1}", 300)]
            if index in (0, 1):
                lines.append(recognized("Shared formal heading", 100 + index * 40))
            results.append(lines)
        rows, _ = self.write((10, 50, 90, 140, 200), results, [[0], [1], [2], [3], [4]])
        shared = [row for row in rows if row.endswith(" Shared formal heading")]
        self.assertEqual(shared, ["[00:00][画面] Shared formal heading", "[00:08][画面] Shared formal heading"])
        self.assertEqual([MARKER.fullmatch(row).group(2) for row in rows if MARKER.fullmatch(row)],
                         ["1", "2", "3", "4", "5"])

    def test_text_in_exactly_half_the_slides_is_written_once(self) -> None:
        # The reference replay's 20 slides reach 893 lines with >=10, not >10.
        results = []
        for index in range(4):
            lines = [recognized(f"Distinct body {index + 1}", 300)]
            if index in (0, 1):
                lines.append(recognized("Session footer", 100 + index * 50))
            results.append(lines)
        rows, _ = self.write((10, 50, 90, 140), results, [[0], [1], [2], [3]])
        self.assertEqual([row for row in rows if row.endswith(" Session footer")],
                         ["[00:00][画面] Session footer"])

    def test_repeated_samples_do_not_change_the_slide_frequency(self) -> None:
        results = []
        for index in range(10):
            group = 0 if index < 6 else index - 5
            lines = [recognized(f"Page body {group + 1}", 300)]
            if group < 2:
                lines.append(recognized("Repeated formal heading", 100 + group * 50))
            results.append(lines)
        rows, _ = self.write(
            (10, 11, 12, 13, 14, 15, 50, 90, 140, 200), results,
            [[0, 1, 2, 3, 4, 5], [6], [7], [8], [9]],
        )
        self.assertEqual([row for row in rows if row.endswith(" Repeated formal heading")],
                         ["[00:00][画面] Repeated formal heading", "[00:48][画面] Repeated formal heading"])

    def test_text_in_more_than_half_the_slides_is_written_once(self) -> None:
        results = []
        for index in range(5):
            lines = [recognized(f"Distinct body {index + 1}", 300)]
            if index < 3:
                lines.append(recognized("Conference footer", 100 + index * 50))
            results.append(lines)
        rows, _ = self.write((10, 50, 90, 140, 200), results, [[0], [1], [2], [3], [4]])
        self.assertEqual([row for row in rows if row.endswith(" Conference footer")],
                         ["[00:00][画面] Conference footer"])

    def test_frame_pixels_separate_slides_but_small_changes_stay_together(self) -> None:
        frames = self.frames(self.root / "pixels", (10, 12, 50, 52, 90, 92))
        transform_calls = []

        def transform(command, step, **kwargs):
            source = Path(command[command.index("-i") + 1])
            level, _ = frame_data(source)
            Path(command[-1]).write_bytes(frame_png(level, (160, 90)))
            transform_calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        group_frames = getattr(screen_ocr, "_group_frames", None)
        self.assertIsNotNone(group_frames, "screen extraction has no pixel-based slide grouping")
        scan = screen_ocr.Scan("slides", 800)
        with patch.object(scan, "run", side_effect=transform), \
             patch.object(screen_ocr, "_memory_thumbnail", return_value=None):
            groups = group_frames(scan, "ffmpeg", frames)
        self.assertEqual([[frame.seconds for frame in group] for group in groups],
                         [[0, 8], [16, 24], [32, 40]])
        self.assertEqual(len(transform_calls), len(frames))
        for command in transform_calls:
            filters = command[command.index("-vf") + 1]
            self.assertIn("crop=", filters)
            self.assertIn("160:90", filters)
            self.assertIn("gray", filters)

    def test_extract_uses_pixel_groups_when_writing_evidence(self) -> None:
        staged = self.root / "extracted"
        staged.mkdir()
        image_frames = []

        def download(scan, command, source, work):
            video = work / "source.mp4"
            video.touch()
            return video

        def frames(scan, ffmpeg, video, work, mode):
            for index, level in enumerate((10, 12, 50, 52, 90, 92, 140, 142, 200, 202)):
                path = work / f"frame-{index + 1:06d}.png"
                path.write_bytes(frame_png(level))
                image_frames.append(screen_ocr.Frame(path, index * 8))
            return image_frames

        def read_frame(scan, ffmpeg, ocr, mode, crop, frame):
            group = image_frames.index(frame) // 2
            lines = [recognized(f"Page detail {group + 1}", 300)]
            if group < 2:
                lines.append(recognized("Shared formal heading", 100 + group * 30))
            if group < 3:
                lines.append(recognized("Session footer", 400 + group * 40))
            return lines

        def transform(scan, command, step, **kwargs):
            source = Path(command[command.index("-i") + 1])
            level, _ = frame_data(source)
            Path(command[-1]).write_bytes(frame_png(level, (160, 90)))
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            patch.dict(os.environ, {"TFV_SLIDE_CROP": ""}),
            patch.object(screen_ocr.Scan, "probe", return_value="ffmpeg"),
            patch.object(screen_ocr.Scan, "run", autospec=True, side_effect=transform),
            patch.object(screen_ocr, "_download", side_effect=download),
            patch.object(screen_ocr, "_frames", side_effect=frames),
            patch.object(screen_ocr, "_rapidocr", return_value=object()),
            patch.object(screen_ocr, "_read_frame", side_effect=read_frame),
        ):
            status = screen_ocr.extract(staged, "slides", "https://example.invalid/film", ["download"], 800, lambda: [])
        self.assertEqual(status["state"], "ready", status)
        output = (staged / "screen.txt").read_bytes()
        rows = output.decode("utf-8").splitlines()
        print(json.dumps({"status": status, "screen": rows}, ensure_ascii=False))
        self.assertEqual(sum(row.endswith(" Shared formal heading") for row in rows), 2, rows)
        self.assertEqual(sum(row.endswith(" Session footer") for row in rows), 1, rows)
        self.assertEqual([MARKER.fullmatch(row).groups() for row in rows if MARKER.fullmatch(row)],
                         [("00:00", "1"), ("00:16", "2"), ("00:32", "3"), ("00:48", "4"), ("01:04", "5")])
        for row in rows:
            if MARKER.fullmatch(row):
                self.assertRegex(row, r"\] frame-\d+\.png$")
                self.assertTrue((staged / "screen-frames" / row.rpartition(" ")[2]).is_file())
        self.assertEqual(status["sha256"], hashlib.sha256(output).hexdigest())
        for filename, line_numbers in status["screenshot_lines"].items():
            self.assertTrue((staged / "screen-frames" / filename).is_file())
            self.assertTrue(all("[画面] " in rows[number - 1] or MARKER.fullmatch(rows[number - 1])
                                for number in line_numbers))


class SlideSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def fixture_job(self, sample: Path) -> Path:
        text = sample.read_text(encoding="utf-8")
        fixture = dict(verify_report._FIXTURE.findall(text))
        job = self.root / sample.stem
        job.mkdir()
        (job / "note.md").write_text(text, encoding="utf-8")
        for field, name in (("transcript", "transcript.txt"), ("selection", "selection.md"), ("screen", "screen.txt")):
            shutil.copyfile(ROOT / fixture[field], job / name)
        screen = (job / "screen.txt").read_bytes()
        (job / "status.json").write_text(json.dumps({
            "status": "transcript_ready", "duration_seconds": int(fixture["duration"]), "expected_lang": fixture["lang"],
            "screen_ocr": {"state": "ready", "mode": "slides", "sha256": hashlib.sha256(screen).hexdigest()},
        }), encoding="utf-8")
        return job

    def submit(self, job: Path, mode: str = "slides") -> tuple[int, dict]:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts/verify_note.py"), "--job", str(job), "--with-coverage", "--json"],
            cwd=ROOT, env=dict(os.environ, TFV_SCREEN_MODE=mode),
            capture_output=True, encoding="utf-8", timeout=30,
        )
        self.assertTrue(result.stdout, result)
        parsed = json.loads(result.stdout)
        print(json.dumps({"sample": job.name, "mode": mode, "exit": result.returncode, "result": parsed}, ensure_ascii=False))
        return result.returncode, parsed

    def test_every_slide_is_listed_even_when_some_are_omitted(self) -> None:
        for sample in sorted((ROOT / "evals/good/phase2e-slides").glob("*.md")):
            with self.subTest(sample=sample.name):
                code, result = self.submit(self.fixture_job(sample))
                self.assertEqual(code, 0, result["reasons"])
                self.assertTrue(result["allowed"], result)

    def test_omitting_a_slide_from_selection_reports_s01(self) -> None:
        for name, missing in (("all-listed", "2"), ("part-omitted", "3")):
            with self.subTest(sample=name):
                sample = ROOT / "evals/adversarial/phase2e-slides" / f"{name}.md"
                code, result = self.submit(self.fixture_job(sample))
                self.assertNotEqual(code, 0, result)
                reasons = "\n".join(reason for reason in result["reasons"] if reason.startswith("S01 FAIL:"))
                self.assertRegex(reasons, rf"幻灯片\s*{missing}\b")

    def test_ungrouped_legacy_selection_still_passes(self) -> None:
        sample = ROOT / "evals/adversarial/phase2e-slides/all-listed.md"
        job = self.fixture_job(sample)
        shutil.copyfile(ROOT / "evals/fixtures/usable_selection.md", job / "selection.md")
        (job / "screen.txt").write_text("[00:00][画面] Root inspection\n", encoding="utf-8")
        status = json.loads((job / "status.json").read_text(encoding="utf-8"))
        status["screen_ocr"]["sha256"] = hashlib.sha256((job / "screen.txt").read_bytes()).hexdigest()
        (job / "status.json").write_text(json.dumps(status), encoding="utf-8")
        code, result = self.submit(job)
        self.assertEqual(code, 0, result["reasons"])

    def test_untrusted_or_disabled_markers_do_not_require_slide_selections(self) -> None:
        sample = ROOT / "evals/adversarial/phase2e-slides/all-listed.md"
        for name, mode, change in (
            ("off", "off", {}), ("nameplate", "nameplate", {}),
            ("hash-mismatch", "slides", {"sha256": "0" * 64}),
            ("fallback", "slides", {"state": "fallback"}),
            ("wrong-mode", "slides", {"mode": "nameplate"}),
        ):
            with self.subTest(case=name):
                job = self.fixture_job(sample)
                target = job.with_name(name)
                job.rename(target)
                job = target
                shutil.copyfile(ROOT / "evals/fixtures/usable_selection.md", job / "selection.md")
                if change:
                    status = json.loads((job / "status.json").read_text(encoding="utf-8"))
                    status["screen_ocr"].update(change)
                    (job / "status.json").write_text(json.dumps(status), encoding="utf-8")
                code, result = self.submit(job, mode)
                self.assertEqual(code, 0, result["reasons"])


if __name__ == "__main__":
    unittest.main()
