"""Deterministic command-boundary replacements for the Phase 2E YouTube tests."""

from __future__ import annotations

import importlib.abc
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


OCR_VERSIONS = {"rapidocr": "3.81.9", "onnxruntime": "1.81.8"}
FULL_SIZE = (1280, 800)
HALF_SIZE = (640, 400)


def frame_png(marker: int, size: tuple[int, int] = FULL_SIZE) -> bytes:
    """Make a valid grayscale PNG whose pixels carry the frame identity."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(kind + payload)
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    width, height = size
    return b"".join((
        b"\x89PNG\r\n\x1a\n",
        chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)),
        chunk(b"IDAT", zlib.compress((b"\x00" + bytes([marker]) * width) * height)),
        chunk(b"IEND", b""),
    ))


def frame_data(image) -> tuple[int, tuple[int, int]]:
    if hasattr(image, "shape"):
        height, width = image.shape[:2]
        pixel = image[0, 0] if image.ndim == 2 else image[0, 0, 0]
        return int(pixel), (width, height)
    if hasattr(image, "getpixel"):
        pixel = image.convert("L").getpixel((0, 0))
        return pixel, image.size

    png = image if isinstance(image, bytes) else Path(image).read_bytes()
    size = struct.unpack_from(">II", png, 16)
    length, kind = struct.unpack_from(">I4s", png, 33)
    if kind != b"IDAT":
        raise AssertionError("not a fixture PNG")
    scanlines = zlib.decompress(png[41:41 + length])
    return scanlines[1], size


def transform_frame(source: Path, target: Path, filters: str) -> None:
    marker, size = frame_data(source)
    width, height = size
    if "scale" in filters:
        size = (width // 2, height // 2)
    # The tests exercise both source sizes. Reject the retired OCR-only transforms.
    if any(operation in filters for operation in ("negate", "lut", "threshold", "signalstats", "geq")):
        raise AssertionError(f"unexpected OCR transform: {filters}")
    target.write_bytes(frame_png(marker, size))


def ocr_result(*lines: tuple[int, int, str]) -> SimpleNamespace:
    boxes = []
    for x, y, text in lines:
        right = x + 8 * len(text)
        boxes.append(((x, y), (right, y), (right, y + 16), (x, y + 16)))
    return SimpleNamespace(boxes=tuple(boxes) or None,
                           txts=tuple(text for _, _, text in lines) or None,
                           scores=(0.99,) * len(lines) or None)


class OCRPackages(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Expose the optional OCR packages at their regular import and version boundaries."""

    def __init__(self, recognize, events, missing=None):
        self.recognize = recognize
        self.events = events
        self.missing = missing

    def find_spec(self, fullname, path=None, target=None):
        if fullname in OCR_VERSIONS:
            self.events.append(("missing" if fullname == self.missing else "lookup", fullname))
            if fullname == self.missing:
                raise ModuleNotFoundError(f"No module named '{fullname}'", name=fullname)
            return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__version__ = OCR_VERSIONS[module.__name__]
        if module.__name__ == "rapidocr":
            module.RapidOCR = self.engine

    def engine(self, *args, **kwargs):
        return self.recognize

    @contextmanager
    def installed(self):
        distribution = importlib.metadata.Distribution.from_name

        def find_distribution(name):
            if name not in OCR_VERSIONS:
                return distribution(name)
            self.events.append(("missing" if name == self.missing else "lookup", name))
            if name == self.missing:
                raise importlib.metadata.PackageNotFoundError(name)
            return SimpleNamespace(version=OCR_VERSIONS[name])

        saved = {name: sys.modules.pop(name) for name in OCR_VERSIONS if name in sys.modules}
        try:
            with (
                patch.object(sys, "meta_path", [self, *sys.meta_path]),
                patch.object(importlib.metadata.Distribution, "from_name", side_effect=find_distribution),
            ):
                yield
        finally:
            for name in OCR_VERSIONS:
                sys.modules.pop(name, None)
            sys.modules.update(saved)


class MediaTools:
    versions = {"ffmpeg": "7.81.4", **OCR_VERSIONS}
    image_suffixes = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".ppm", ".pgm", ".pnm"}
    frame_time = 95
    ocr_text = {
        FULL_SIZE: ("Drainage $48.27", "Coarse bark", "Moisture 72%", "Calibration $8.30"),
        HALF_SIZE: ("Drainage $48.27", "", "", "Calibration $8.3"),
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
        self.real_monotonic = time.monotonic
        self.clock_offset = 0
        self.ocr_packages = OCRPackages(self.recognize, self.events, missing)

    def monotonic(self):
        return self.real_monotonic() + self.clock_offset

    def which(self, command, *args, **kwargs):
        name = Path(command).stem.lower()
        if name in {"yt-dlp", "ffmpeg", "tesseract"}:
            self.events.append(("missing" if name == self.missing else "lookup", name))
            return None if name in {self.missing, "tesseract"} else name
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
            if "%" in target.name:
                def frame_name(index: int, stamp: int) -> Path:
                    number = stamp if "-frame_pts" in args else index
                    name = re.sub(r"%0?(\d*)d", lambda m: f"{number:0{int(m[1] or 1)}d}", target.name)
                    return target.with_name(name)
                if self.watermark:
                    times = (20, 40, 60, 80, 100)
                    for index, stamp in enumerate(times, 1):
                        self.write(frame_name(index, stamp), frame_png(index))
                    return "", "".join(self.showinfo(index, stamp) for index, stamp in enumerate(times))
                target = frame_name(1, frame)
            self.write(target, frame_png(0))
            return "", self.showinfo(0, frame)
        transform_frame(source, target, filters)
        return "", ""

    @staticmethod
    def showinfo(index: int, stamp: int) -> str:
        return f"[Parsed_showinfo_0 @ fixture] n:{index:4d} pts:{stamp:7d} pts_time:{stamp} pos: 0\n"

    def recognize(self, image, **kwargs):
        marker, size = frame_data(image)
        self.ocr_images.append(size)
        if self.timeout and not self.clock_offset:
            self.events.append(("timeout", "rapidocr"))
            self.clock_offset = 300
        if self.mode == "nameplate":
            lines = ("Mira Vellora, Horticulturist",)
        elif self.watermark:
            names = ("Topsoil", "Fine bark", "Stones", "Mulch", "Compost")
            index = marker - 1
            lines = ("Garden Channel", names[index], "Seasonal" if index < 2 else "")
        else:
            lines = self.ocr_text[size]
        scale = FULL_SIZE[0] // size[0]
        return ocr_result(*((60 // scale, i * 40 // scale, line)
                            for i, line in enumerate(lines, 1) if line))

    def run(self, command, *args, **kwargs):
        argv = [os.fsdecode(arg) for arg in command]
        name = Path(argv[0]).stem.lower()
        if name == "git" or (Path(argv[0]) == Path(sys.executable) and argv[1:] == ["--version"]):
            return self.real_run(command, *args, **kwargs)
        if name not in {"yt-dlp", "ffmpeg"}:
            raise AssertionError(f"unexpected external command: {argv}")
        if name == self.missing:
            self.events.append(("missing", name))
            raise FileNotFoundError(name)
        self.events.append(("run", name, argv[1:]))
        if name == "yt-dlp":
            stdout, stderr = self.ytdlp(argv)
        elif any(flag in argv for flag in ("-version", "--version")):
            stdout, stderr = f"ffmpeg version {self.versions[name]}\n", ""
        else:
            stdout, stderr = self.ffmpeg(argv)
        if not (kwargs.get("text") or kwargs.get("encoding") or kwargs.get("universal_newlines")):
            stdout, stderr = stdout.encode("utf-8"), stderr.encode("utf-8")
        return subprocess.CompletedProcess(command, 0, stdout, stderr)
