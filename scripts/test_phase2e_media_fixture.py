"""Deterministic command-boundary replacements for the Phase 2E YouTube tests."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path


class MediaTools:
    versions = {"ffmpeg": "7.81.4", "tesseract": "5.81.9"}
    image_suffixes = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".ppm", ".pgm", ".pnm"}
    frame_time = 95
    ocr_text = {
        b"original": "Drainage $48.27\nCoarse bark\nMoisture 72%\nCalibration $8.30\n",
        b"half": "Drainage $48.27\nCalibration $8.3\n",
        b"inverted-binary": "Calibration $08.30\n",
    }

    def __init__(self, video_id: str, speech: str, *, missing: str | None = None,
                 timeout: bool = False, mode: str | None = None, watermark: bool = False):
        self.video_id = video_id
        self.speech = speech
        self.missing = missing
        self.timeout = timeout
        self.mode = mode
        self.watermark = watermark
        self.events = []
        self.videos = []
        self.ocr_images = []
        self.scan_limits = []
        self.real_which = shutil.which
        self.real_run = subprocess.run

    def which(self, command, *args, **kwargs):
        name = Path(command).stem.lower()
        if name in {"yt-dlp", *self.versions}:
            self.events.append(("missing" if name == self.missing else "lookup", name))
            return None if name == self.missing else name
        return self.real_which(command, *args, **kwargs)

    @staticmethod
    def write(path: Path, contents: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    @staticmethod
    def value(args: list[str], *flags: str) -> str | None:
        return next((args[index + 1] for index, item in enumerate(args[:-1]) if item in flags), None)

    def captions(self) -> bytes:
        cues = [line.split("] ", 1) for line in self.speech.splitlines()]
        times = [f"00:{clock[1:]}.000" for clock, _ in cues] + ["00:02:00.000"]
        return ("WEBVTT\n\n" + "\n\n".join(
            f"{times[index]} --> {times[index + 1]}\n{text}"
            for index, (_, text) in enumerate(cues)
        ) + "\n").encode("utf-8")

    def ytdlp(self, args: list[str]) -> tuple[str, str]:
        if "--version" in args:
            return "2026.08.19\n", ""
        if any(flag in args for flag in ("-J", "--dump-json", "--dump-single-json")):
            return json.dumps({
                "id": self.video_id, "duration": 240 if self.mode == "nameplate" else 120,
                "subtitles": {"en": [{"ext": "vtt", "url": "https://example.invalid/en.vtt"}]},
            }), ""
        template = self.value(args, "-o", "--output")
        if template is None:
            raise AssertionError(f"yt-dlp needs an output path: {args}")
        if "--skip-download" in args:
            path = Path(template.replace("%(id)s", self.video_id))
            self.write(path.parent / f"{self.video_id}.en.vtt", self.captions())
        else:
            filename = template.replace("%(id)s", self.video_id).replace("%(ext)s", "mp4")
            video = Path(filename)
            self.write(video, b"fixture video")
            self.videos.append(video)
            return f"{video}\n", ""
        return "", ""

    def ffmpeg(self, args: list[str]) -> tuple[str, str]:
        target = Path(args[-1])
        if target.suffix.lower() not in self.image_suffixes:
            raise AssertionError(f"unexpected FFmpeg output: {args}")
        filters = self.value(args, "-vf", "-filter:v", "-filter_complex") or ""
        source = Path(self.value(args, "-i") or "")
        if source in self.videos:
            self.events.append(("frames", "ffmpeg"))
            start = float(self.value(args, "-ss") or 0)
            end = self.value(args, "-to")
            length = self.value(args, "-t")
            if self.mode == "nameplate":
                frame = 160
                stop = float(end) if end is not None else start + float(length or 240)
                self.scan_limits.append(stop)
                if not start <= frame < stop:
                    return "", ""
            else:
                frame = self.frame_time
            marker = b"frame"
            if "%" in target.name:
                def frame_name(index: int, stamp: int) -> Path:
                    number = stamp if "-frame_pts" in args else index
                    name = re.sub(r"%0?(\d*)d", lambda m: f"{number:0{int(m[1] or 1)}d}", target.name)
                    return target.with_name(name)
                if self.watermark:
                    times = (20, 40, 60, 80, 100)
                    for index, stamp in enumerate(times, 1):
                        self.write(frame_name(index, stamp), f"frame:{index}".encode())
                    return "", "".join(self.showinfo(index, stamp) for index, stamp in enumerate(times))
                target = frame_name(1, frame)
        else:
            marker = source.read_bytes()
            frame = self.frame_time
        variant, separator, sample = marker.partition(b":")
        if "crop" in filters:
            variant = b"original"
        if "scale" in filters:
            if variant not in {b"original", b"half"}:
                raise AssertionError(f"resize must use the cropped slide: {args}")
            variant = b"half"
        if "negate" in filters:
            if variant not in {b"original", b"inverted-binary"}:
                raise AssertionError(f"inversion must use the cropped slide: {args}")
            variant = b"inverted"
        if any(operation in filters for operation in ("threshold", "lut", "binarize")):
            if variant not in {b"inverted", b"inverted-binary"}:
                raise AssertionError(f"binarization must follow inversion: {args}")
            variant = b"inverted-binary"
        self.write(target, variant + separator + sample)
        return "", self.showinfo(0, frame)

    @staticmethod
    def showinfo(index: int, stamp: int) -> str:
        return f"[Parsed_showinfo_0 @ fixture] n:{index:4d} pts:{stamp:7d} pts_time:{stamp} pos: 0\n"

    def tesseract(self, args: list[str], timeout: int | None) -> tuple[str, str]:
        if self.timeout:
            self.events.append(("timeout", "tesseract"))
            raise subprocess.TimeoutExpired(args, timeout)
        source = Path(args[1])
        marker = source.read_bytes()
        variant, _, sample = marker.partition(b":")
        self.ocr_images.append(variant)
        if self.mode == "nameplate":
            text = "Mira Vellora, Horticulturist\n"
        elif sample:
            names = ("Topsoil", "Fine bark", "Stones", "Mulch", "Compost")
            index = int(sample) - 1
            text = f"Garden Channel\n{names[index]}\n"
            if index < 2:
                text += "Seasonal\n"
        elif variant in self.ocr_text:
            text = self.ocr_text[variant]
        else:
            raise AssertionError(f"unexpected OCR input {marker!r}: {args}")
        if "tsv" in args:
            rows = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"]
            for line, words in enumerate(text.splitlines(), 1):
                rows.extend(f"5\t1\t1\t1\t{line}\t{word}\t{word*60}\t{line*35}\t56\t24\t99\t{value}"
                            for word, value in enumerate(words.split(), 1))
            text = "\n".join(rows) + "\n"
        if args[2] != "stdout":
            output_suffix = ".tsv" if "tsv" in args else ".txt"
            self.write(Path(args[2] + output_suffix), text.encode("utf-8"))
            return "", ""
        return text, ""

    def run(self, command, *args, **kwargs):
        argv = [os.fsdecode(arg) for arg in command]
        name = Path(argv[0]).stem.lower()
        if name == "git" or (Path(argv[0]) == Path(sys.executable) and argv[1:] == ["--version"]):
            return self.real_run(command, *args, **kwargs)
        if name not in {"yt-dlp", *self.versions}:
            raise AssertionError(f"unexpected external command: {argv}")
        if name == self.missing:
            self.events.append(("missing", name))
            raise FileNotFoundError(name)
        self.events.append(("run", name, argv[1:]))
        if name == "yt-dlp":
            stdout, stderr = self.ytdlp(argv)
        elif any(flag in argv for flag in ("-version", "--version")):
            prefix = "ffmpeg version" if name == "ffmpeg" else "tesseract"
            stdout, stderr = f"{prefix} {self.versions[name]}\n", ""
        elif name == "ffmpeg":
            stdout, stderr = self.ffmpeg(argv)
        else:
            stdout, stderr = self.tesseract(argv, kwargs.get("timeout"))
        if not (kwargs.get("text") or kwargs.get("encoding") or kwargs.get("universal_newlines")):
            stdout, stderr = stdout.encode("utf-8"), stderr.encode("utf-8")
        return subprocess.CompletedProcess(command, 0, stdout, stderr)
