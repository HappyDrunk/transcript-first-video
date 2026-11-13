"""Regression cases from the first formal Phase 2E acceptance."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import screen_ocr

FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "phase2e" / "first-acceptance"
TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
TRUSTED = "[画面] "
UNCERTAIN = "[画面?] "


def ocr_tsv(*lines: tuple[int, int, str]) -> str:
    """Create a Tesseract response with positions in the processed image's pixels."""
    rows = [TSV_HEADER]
    for number, (x, y, text) in enumerate(lines, 1):
        for word_number, word in enumerate(text.split(), 1):
            width = 8 * len(word)
            rows.append(f"5\t1\t1\t1\t{number}\t{word_number}\t{x}\t{y}\t{width}\t16\t95\t{word}")
            x += width + 8
    return "\n".join(rows) + "\n"


class FrameCommands:
    """Provide one timed frame. Use real image transforms and OCR for image fixtures."""

    def __init__(self, seconds: int, *, ocr_passes: list[str] | None = None, image: Path | None = None):
        self.seconds = seconds
        self.ocr_passes = iter(ocr_passes) if ocr_passes is not None else None
        self.image = image
        self.run_real = subprocess.run
        self.find_real = shutil.which

    def which(self, command, *args, **kwargs):
        if self.ocr_passes is not None and command in {"ffmpeg", "tesseract"}:
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
            frame = Path(re.sub(r"%0?(\d*)d", lambda match: str(1).zfill(int(match[1] or 0)), target))
            if self.image is None:
                frame.touch()
            else:
                shutil.copyfile(self.image, frame)
            stderr = f"[Parsed_showinfo_0 @ fixture] n: 0 pts: {self.seconds} pts_time:{self.seconds} pos: 0\n"
        elif self.ocr_passes is not None and tool in {"ffmpeg", "tesseract"}:
            if "-version" in command or "--version" in command:
                stdout = f"{tool} fixture\n"
            elif tool == "ffmpeg":
                Path(command[-1]).touch()
            else:
                stdout = next(self.ocr_passes, TSV_HEADER + "\n")
        else:
            return self.run_real(command, *args, **kwargs)
        return subprocess.CompletedProcess(command, 0, stdout, stderr)


def screen_output(mode: str, commands: FrameCommands) -> tuple[list[str], dict]:
    with (
        tempfile.TemporaryDirectory() as temp,
        patch.dict(os.environ, {"TFV_OCR_LANG": "eng", "TFV_SLIDE_CROP": ""}),
        patch("shutil.which", commands.which),
        patch("subprocess.run", commands.run),
    ):
        staged = Path(temp)
        status = screen_ocr.extract(
            staged, mode, "https://example.invalid/video", ["fixture-download"],
            240 if mode == "nameplate" else 800, lambda: [],
        )
        path = staged / "screen.txt"
        rows = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        print(f"screen_ocr: {status}")
        print("screen.txt:", *rows, sep="\n")
    return rows, status


class OCRReplayTests(unittest.TestCase):
    def slides(self, *passes: str, seconds: int = 96) -> list[str]:
        rows, status = screen_output("slides", FrameCommands(seconds, ocr_passes=list(passes)))
        self.assertEqual(status["state"], "ready", status)
        return [row.partition("]")[2] for row in rows]

    def test_short_noise_is_omitted(self):
        rows = self.slides(
            ocr_tsv((80, 10, "k"), (80, 50, "Prices correct"), (80, 90, "71")),
            ocr_tsv((40, 10, "Cy"), (40, 25, "’"), (40, 45, "71")),
            ocr_tsv((80, 50, "Prices correct")),
        )
        self.assertIn(TRUSTED + "Prices correct", rows)
        self.assertIn(TRUSTED + "71", rows)
        fragments = {"k", "Cy", "’"}
        published_text = {row.split("] ", 1)[1] for row in rows}
        self.assertFalse(published_text & fragments, "Short OCR fragments leaked into screen.txt: " + repr(rows))

    def test_three_spellings_of_same_line_publish_once(self):
        first = "Read text first. Spend image reads only on what text "
        last = " rule out."
        variants = [first + word + last for word in ("can’t", "can't", "cant")]
        rows = self.slides(
            ocr_tsv((107, 732, variants[0]), (107, 670, "Same answer, and a finished report")),
            ocr_tsv((54, 366, variants[1])),
            ocr_tsv((107, 733, variants[2]), (107, 670, "Same answer, and a finished report")),
            seconds=632,
        )
        self.assertIn(TRUSTED + "Same answer, and a finished report", rows)
        matches = [row for row in rows if first in row]
        self.assertEqual(len(matches), 1, matches)
        self.assertTrue(matches[0].startswith(TRUSTED), matches)

    def test_ampersand_misread_of_digit_is_not_citable(self):
        rows = self.slides(
            ocr_tsv((223, 284, "AUG 4 RUN"), (223, 200, "RESEARCH & DESIGN"), (600, 284, "MAY 7 RUN")),
            ocr_tsv((111, 100, "RESEARCH & DESIGN"), (300, 142, "MAY 7 RUN")),
            ocr_tsv((223, 284, "AUG & RUN")),
            seconds=632,
        )
        self.assertIn(TRUSTED + "RESEARCH & DESIGN", rows)
        self.assertIn(TRUSTED + "MAY 7 RUN", rows)
        self.assertNotIn(TRUSTED + "AUG 4 RUN", rows, "The digit 4 has only one matching OCR pass")
        self.assertNotIn(TRUSTED + "AUG & RUN", rows, "The symbol replaced a digit at the same position")

    def test_matching_malformed_percentages_are_not_citable(self):
        # The published text gives the wrong readings, with no per-pass TSV for this frame.
        # Give the exact malformed comparison two votes to exercise the failure directly.
        rows = self.slides(
            ocr_tsv((120, 100, "A1% > 97%"), (550, 100, "52% > 40%")),
            ocr_tsv((60, 50, "A1% > 97%"), (275, 50, "52% > 40%")),
            ocr_tsv((120, 100, "A1% 97%")),
        )
        self.assertIn(TRUSTED + "52% > 40%", rows)
        self.assertEqual([row for row in rows if row.startswith(TRUSTED) and "A1%" in row], [],
                         "Matching OCR passes made malformed percentages citable")

    def test_gibberish_is_not_published_as_a_nameplate(self):
        name = "Mira Vellora, Horticulturist"
        noise = ("Lr EES EE", "————————— Oe", "Sc Se")
        rows, status = screen_output("nameplate", FrameCommands(112, ocr_passes=[
            ocr_tsv((100, 50, noise[0]), (100, 76, noise[1]), (100, 95, noise[2]), (400, 50, name)),
            ocr_tsv((200, 25, name)),
            ocr_tsv((400, 50, name)),
        ]))
        self.assertEqual(status["state"], "ready", status)
        self.assertIn("[01:52]" + TRUSTED + name, rows)
        self.assertEqual([row for row in rows if any(text in row for text in noise)], [],
                         "Screen noise was published as a nameplate")

    def test_single_pass_and_different_numeric_spellings_stay_uncertain(self):
        rows = self.slides(
            ocr_tsv((200, 100, "$6.93"), (400, 100, "$2.11"), (600, 100, "$3.17")),
            ocr_tsv((200, 50, "$2.11"), (300, 50, "$3.1")),
            ocr_tsv((600, 100, "$3.170")),
        )
        self.assertIn(TRUSTED + "$2.11", rows)
        self.assertIn(UNCERTAIN + "$6.93", rows)
        self.assertIn(UNCERTAIN + "$3.17", rows)
        self.assertNotIn(TRUSTED + "$6.93", rows)
        self.assertNotIn(TRUSTED + "$3.17", rows)


@unittest.skipUnless(os.environ.get("TFV_TEST_REAL_OCR") == "1", "set TFV_TEST_REAL_OCR=1 for local FFmpeg and Tesseract")
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
