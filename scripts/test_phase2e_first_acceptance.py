"""Regression cases from the first formal Phase 2E acceptance."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import screen_ocr

from test_phase2e_media_fixture import (
    FULL_SIZE, HALF_SIZE, OCRPackages, frame_data, frame_png, ocr_result, transform_frame,
)


FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "phase2e" / "first-acceptance"
TRUSTED = "[画面] "
UNCERTAIN = "[画面?] "


class FrameCommands:
    """Provide timed frames at the FFmpeg boundary, with optional OCR replay."""

    def __init__(
        self, seconds: int, *, ocr_passes: tuple[SimpleNamespace, SimpleNamespace] | None = None,
        image: Path | None = None, extra_frames: dict[int, tuple[SimpleNamespace, SimpleNamespace]] | None = None,
        duration: int | None = None,
    ):
        self.seconds = seconds
        self.image = image
        self.duration = duration
        replay = {} if ocr_passes is None else {seconds: ocr_passes, **(extra_frames or {})}
        self.replay = sorted(replay.items())
        self.ocr_packages = OCRPackages(self.recognize, [])
        self.run_real = subprocess.run
        self.find_real = shutil.which

    def recognize(self, image, **kwargs):
        marker, size = frame_data(image)
        _, (original, half) = self.replay[marker - 1]
        if size == FULL_SIZE:
            return original
        if size == HALF_SIZE:
            return half
        raise AssertionError(f"unexpected OCR dimensions: {size}")

    def which(self, command, *args, **kwargs):
        if self.replay and command == "ffmpeg":
            return command
        return self.find_real(command, *args, **kwargs)

    def run(self, command, *args, **kwargs):
        tool = Path(command[0]).stem.lower()
        stdout = stderr = ""
        if tool == "fixture-download":
            output = command[command.index("-o") + 1].replace("%(ext)s", "mp4")
            Path(output).touch()
        elif tool == "ffmpeg" and "-i" in command and Path(command[command.index("-i") + 1]).suffix == ".mp4":
            target = command[-1]
            if self.duration is not None:
                hours, remaining = divmod(self.duration, 3600)
                minutes, seconds = divmod(remaining, 60)
                stderr = f"Duration: {hours:02d}:{minutes:02d}:{seconds:02d}.00\n"
            timestamps = [seconds for seconds, _ in self.replay] if self.replay else [self.seconds]
            for index, seconds in enumerate(timestamps, 1):
                frame = Path(re.sub(r"%0?(\d*)d", lambda match: str(index).zfill(int(match[1] or 0)), target))
                if self.image is None:
                    frame.write_bytes(frame_png(index))
                else:
                    shutil.copyfile(self.image, frame)
                stderr += f"[Parsed_showinfo_0 @ fixture] n: {index - 1} pts: {seconds} pts_time:{seconds} pos: 0\n"
        elif self.replay and tool == "ffmpeg":
            if "-version" in command or "--version" in command:
                stdout = "ffmpeg fixture\n"
            else:
                source = Path(command[command.index("-i") + 1])
                filters = command[command.index("-vf") + 1]
                transform_frame(source, Path(command[-1]), filters)
        else:
            return self.run_real(command, *args, **kwargs)
        return subprocess.CompletedProcess(command, 0, stdout, stderr)


def screen_output(mode: str, commands: FrameCommands) -> tuple[list[str], dict]:
    with (
        tempfile.TemporaryDirectory() as temp,
        patch.dict(os.environ, {"TFV_SLIDE_CROP": ""}),
        commands.ocr_packages.installed() if commands.replay else nullcontext(),
        patch("shutil.which", commands.which),
        patch("subprocess.run", commands.run),
    ):
        staged = Path(temp)
        status = screen_ocr.extract(
            staged, mode, "https://example.invalid/video", ["fixture-download"],
            commands.duration or (240 if mode == "nameplate" else 800), lambda: [],
        )
        path = staged / "screen.txt"
        rows = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        print(f"screen_ocr: {status}")
        print("screen.txt:", *rows, sep="\n")
    return rows, status


class OCRReplayTests(unittest.TestCase):
    def slides(self, original: SimpleNamespace, half: SimpleNamespace, *, seconds: int = 96) -> list[str]:
        rows, status = screen_output("slides", FrameCommands(seconds, ocr_passes=(original, half)))
        self.assertEqual(status["state"], "ready", status)
        return [row.partition("]")[2] for row in rows]

    def test_short_noise_is_omitted(self):
        rows = self.slides(
            ocr_result((80, 10, "k"), (80, 50, "Prices correct"), (80, 90, "71")),
            ocr_result((40, 10, "Cy"), (40, 25, "’"), (40, 45, "71")),
        )
        self.assertIn(TRUSTED + "Prices correct", rows)
        self.assertIn(TRUSTED + "71", rows)
        fragments = {"k", "Cy", "’"}
        published_text = {row.split("] ", 1)[1] for row in rows}
        self.assertFalse(published_text & fragments, "Short OCR fragments leaked into screen.txt: " + repr(rows))

    def test_two_spellings_of_same_line_publish_once(self):
        first = "Read text first. Spend image reads only on what text "
        last = " rule out."
        control = "Same answer, and a finished report"
        for spelling in ("can't", "cant"):
            with self.subTest(spelling=spelling):
                rows = self.slides(
                    ocr_result((107, 732, first + "can’t" + last), (107, 670, control)),
                    ocr_result((54, 366, first + spelling + last), (54, 335, control)),
                    seconds=632,
                )
                self.assertIn(TRUSTED + control, rows)
                matches = [row for row in rows if first in row]
                self.assertEqual(len(matches), 1, matches)
                self.assertTrue(matches[0].startswith(TRUSTED), matches)

    def test_ampersand_misread_of_digit_is_not_citable(self):
        rows = self.slides(
            ocr_result((223, 284, "AUG 4 RUN"), (223, 200, "RESEARCH & DESIGN"), (600, 284, "MAY 7 RUN")),
            ocr_result((111, 142, "AUG & RUN"), (111, 100, "RESEARCH & DESIGN"), (300, 142, "MAY 7 RUN")),
            seconds=632,
        )
        self.assertIn(TRUSTED + "RESEARCH & DESIGN", rows)
        self.assertIn(TRUSTED + "MAY 7 RUN", rows)
        self.assertNotIn(TRUSTED + "AUG 4 RUN", rows, "The digit 4 has only one matching OCR pass")
        self.assertNotIn(TRUSTED + "AUG & RUN", rows, "The symbol replaced a digit at the same position")

    def test_matching_malformed_percentages_are_not_citable(self):
        # Replay the malformed comparison in both passes.
        rows = self.slides(
            ocr_result((120, 100, "A1% > 97%"), (550, 100, "52% > 40%")),
            ocr_result((60, 50, "A1% > 97%"), (275, 50, "52% > 40%")),
        )
        self.assertIn(TRUSTED + "52% > 40%", rows)
        self.assertEqual([row for row in rows if row.startswith(TRUSTED) and "A1%" in row], [],
                         "Matching OCR passes made malformed percentages citable")

    def test_gibberish_is_not_published_as_a_nameplate(self):
        name = "Mira Vellora, Horticulturist"
        noise = ("Lr EES EE", "————————— Oe", "Sc Se")
        rows, status = screen_output("nameplate", FrameCommands(112, ocr_passes=(
            ocr_result((100, 50, noise[0]), (100, 76, noise[1]), (100, 95, noise[2]), (400, 50, name)),
            ocr_result((200, 25, name)),
        )))
        self.assertEqual(status["state"], "ready", status)
        self.assertIn("[01:52]" + TRUSTED + name, rows)
        self.assertEqual([row for row in rows if any(text in row for text in noise)], [],
                         "Screen noise was published as a nameplate")

    def test_single_pass_and_different_numeric_spellings_stay_uncertain(self):
        rows = self.slides(
            ocr_result((200, 100, "$6.93"), (400, 100, "$2.11"), (600, 100, "$3.17")),
            ocr_result((200, 50, "$2.11"), (300, 50, "$3.1")),
        )
        self.assertIn(TRUSTED + "$2.11", rows)
        self.assertIn(UNCERTAIN + "$6.93", rows)
        self.assertIn(UNCERTAIN + "$3.17", rows)
        self.assertNotIn(TRUSTED + "$6.93", rows)
        self.assertNotIn(TRUSTED + "$3.17", rows)

    def test_cross_frame_exact_text_uses_first_citable_occurrence(self):
        first = ocr_result(
            (80, 40, "Transfer overview"), (80, 80, "Cost $6.93"),
            (80, 120, "Notes on the author's example"), (80, 160, "Capacity 75GB"),
        )
        first_half = ocr_result((40, 20, "Transfer overview"))
        second = ocr_result(
            (80, 40, "Transfer overview"), (80, 80, "Cost $6.93"),
            (80, 120, "Notes on the authors example"), (80, 160, "Capacity 75GB"),
        )
        second_half = ocr_result((40, 20, "Transfer overview"), (40, 40, "Cost $6.93"))
        rows, status = screen_output("slides", FrameCommands(
            12, ocr_passes=(first, first_half), extra_frames={20: (second, second_half)},
        ))
        self.assertEqual(status["state"], "ready", status)
        self.assertCountEqual(rows, [
            "[00:12]" + TRUSTED + "Transfer overview",
            "[00:20]" + TRUSTED + "Cost $6.93",
            "[00:12]" + TRUSTED + "Notes on the author's example",
            "[00:20]" + TRUSTED + "Notes on the authors example",
            "[00:12]" + UNCERTAIN + "Capacity 75GB",
        ])
        rows_by_screenshot = [
            {rows[line_number - 1] for line_number in line_numbers}
            for line_numbers in status["screenshot_lines"].values()
        ]
        self.assertIn({"[00:20]" + TRUSTED + "Cost $6.93",
                       "[00:20]" + TRUSTED + "Notes on the authors example"}, rows_by_screenshot)

    def test_nameplate_budget_is_fixed_and_slides_keep_half_duration(self):
        original = ocr_result((80, 40, "Mira Vellora, Horticulturist"))
        half = ocr_result((40, 20, "Mira Vellora, Horticulturist"))
        for duration in (90, 600):
            for mode, expected in (("nameplate", 120), ("slides", duration / 2)):
                with self.subTest(mode=mode, duration=duration):
                    rows, status = screen_output(mode, FrameCommands(
                        8, ocr_passes=(original, half), duration=duration,
                    ))
                    self.assertEqual(status["state"], "ready", status)
                    self.assertEqual(status["timeout_seconds"], expected, status)
                    self.assertIn("[00:08]" + TRUSTED + "Mira Vellora, Horticulturist", rows)


@unittest.skipUnless(
    os.environ.get("TFV_TEST_REAL_OCR") == "1", "set TFV_TEST_REAL_OCR=1 for local FFmpeg, RapidOCR and ONNX Runtime",
)
class DiagnosticFrameTests(unittest.TestCase):
    """Read original PNGs from tfv-phase2e-diagnose.zip with the installed OCR tools."""

    def test_large_colored_amount_is_citable(self):
        # Original frame-000081.png. Keep the slide crop unset.
        rows, status = screen_output("slides", FrameCommands(632, image=FIXTURES / "slides-632s.png"))
        self.assertEqual(status["state"], "ready", status)
        amounts = [row for row in rows if re.search(r"(?<!\w)\$6\.93(?!\w|[.,]\d)", row)]
        self.assertTrue(
            any(row.startswith("[10:32]" + TRUSTED) for row in amounts),
            f"The frame must yield citable $6.93 with two matching OCR passes. Published: {amounts}",
        )

    def test_readable_nameplate_from_frame_at_eight_seconds(self):
        rows, status = screen_output("nameplate", FrameCommands(8, image=FIXTURES / "nameplate-8s.png"))
        nameplate = re.compile(re.escape("[00:08]" + TRUSTED) + r"Erik Chen\b")
        self.assertTrue(
            any(nameplate.match(row) for row in rows),
            f"The OCR of the supplied 00:08 frame did not publish Erik Chen. {status}, {rows}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
