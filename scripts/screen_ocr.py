"""Optional YouTube frame extraction and OCR. The caller publishes the result."""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import quality_gate
from verify_rules import SCREEN_FILE, SCREEN_FRAMES, SCREEN_TAG, UNCERTAIN_SCREEN_TAG

SLIDE_INTERVAL = 8
NAMEPLATE_INTERVAL = 2
NAMEPLATE_SECONDS = 180
UNKNOWN_DURATION_TIMEOUT = 600

_SHOWINFO = re.compile(
    r"showinfo[^]\n]*]\s+n:\s*(\d+).*?\bpts_time:\s*([\d.eE+-]+)([^\n]*)"
)
_CHECKSUM = re.compile(r"\bchecksum:([A-Fa-f0-9]+)")
_DURATION = re.compile(r"\bDuration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_NUMERIC_TEXT = re.compile(
    r"(?:[A-Za-z]*[$€£¥￥][ \t]*)?[+\-−]?[A-Za-z]*[.,]?\d[A-Za-z\d]*"
    r"(?:[.,][A-Za-z\d]+|[.,][ \t]*\d+)*(?:[ \t]*(?:[%％×倍]|[xX](?![A-Za-z])))?"
)
_NUMERIC_MARK = re.compile(r"[\d$€£¥￥%％×]|[零〇一二两三四五六七八九十百千万亿]+倍")
_NAME = re.compile(
    r"(?:[A-Z][^\W\d_]+(?:[-’'][^\W\d_]+)?(?:[ \t]+[A-Z][^\W\d_]+(?:[-’'][^\W\d_]+)?){1,3}"
    r"|[\u3400-\u9fff]{2,4})"
)


class ScreenError(Exception):
    pass


@dataclass(frozen=True)
class Line:
    text: str
    x: int
    y: int
    width: int
    height: int

    def at_same_position(self, other: Line) -> bool:
        tolerance = max(6, min(self.height, other.height) // 2)
        return abs(self.x - other.x) <= tolerance and abs(self.y - other.y) <= tolerance


@dataclass(frozen=True)
class Frame:
    path: Path
    seconds: float


class Scan:
    def __init__(self, duration: float | None):
        self.started = time.monotonic()
        self.budget = duration / 2 if duration else UNKNOWN_DURATION_TIMEOUT

    def remaining(self) -> float:
        left = self.budget - (time.monotonic() - self.started)
        if left <= 0:
            raise ScreenError("screen OCR timed out")
        return left

    def run(self, args: list[str], step: str, *, limit: int | None = None, env=None):
        timeout = self.remaining()
        if limit is not None:
            timeout = min(timeout, limit)
        try:
            result = subprocess.run(
                args, capture_output=True, encoding="utf-8", errors="replace",
                timeout=timeout, env=env, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ScreenError(f"{step} timed out") from exc
        except OSError as exc:
            raise ScreenError(f"{step} unavailable: {exc.strerror or exc}") from exc
        if result.returncode:
            lines = (result.stderr or result.stdout).splitlines()
            detail = lines[-1].strip() if lines else f"exit {result.returncode}"
            raise ScreenError(f"{step} failed: {detail}")
        return result

    def probe(self, versions: dict[str, str]) -> dict[str, str]:
        commands = {}
        failures = []
        for name, executable, flag in (
            ("python", sys.executable, "--version"),
            ("ffmpeg", shutil.which("ffmpeg"), "-version"),
            ("tesseract", shutil.which("tesseract"), "--version"),
        ):
            if not executable:
                failures.append(f"{name} missing")
                continue
            try:
                result = self.run([executable, flag], f"{name} version probe", limit=10)
                output = (result.stdout or result.stderr).strip()
                if not output:
                    raise ScreenError(f"{name} version probe returned no version")
                versions[name] = output.splitlines()[0]
                commands[name] = executable
            except ScreenError as exc:
                failures.append(str(exc))
        if failures:
            raise ScreenError(", ".join(failures))
        return commands


def _download(scan: Scan, command: list[str], source: str, work: Path) -> Path:
    scan.run([
        *command, "--no-playlist", "--no-progress", "--fixup", "never",
        "-f", "bv[height=1080]/bv[height<=1080]/b[height<=1080]",
        "-o", str(work / "video.%(ext)s"), source,
    ], "video download")
    videos = [path for path in work.glob("video.*") if path.suffix in {".mp4", ".webm", ".mkv", ".mov"}]
    if len(videos) != 1:
        raise ScreenError("video download did not produce one usable video file")
    return videos[0]


def _crop(mode: str) -> str:
    if mode == "nameplate":
        return "crop=iw:trunc(ih*0.38/2)*2:0:ih-oh"
    raw = os.environ.get("TFV_SLIDE_CROP", "").strip()
    if not raw:
        return "crop=iw:ih:0:0"
    try:
        x, y, w, h = map(float, raw.split(","))
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x and 0 < h <= 1 - y):
            raise ValueError
    except ValueError as exc:
        raise ScreenError("TFV_SLIDE_CROP must be x,y,width,height as fractions within the frame") from exc
    return f"crop=trunc(iw*{w}/2)*2:trunc(ih*{h}/2)*2:iw*{x}:ih*{y}"


def _frames(scan: Scan, ffmpeg: str, video: Path, work: Path, mode: str) -> list[Frame]:
    interval = NAMEPLATE_INTERVAL if mode == "nameplate" else SLIDE_INTERVAL
    # Fixed clock buckets give brief slides a chance even after a nearby cut.
    select = (
        f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,1)*"
        f"(gt(scene,0.30)+gt(floor(t/{interval}),floor(prev_selected_t/{interval})))'"
    )
    result = scan.run([
        ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info",
        "-filter_threads", "1", *(["-t", str(NAMEPLATE_SECONDS)] if mode == "nameplate" else []),
        "-i", str(video), "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", f"{select},showinfo", "-fps_mode", "vfr",
        "-threads", "1", "-start_number", "1", str(work / "frame-%06d.png"),
    ], "frame extraction")
    if duration := _DURATION.search(result.stderr):
        actual = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3])
        if actual > 0:
            scan.budget = actual / 2
    frames, checksums = [], set()
    for index, pts, details in _SHOWINFO.findall(result.stderr):
        seconds = float(pts)
        if not math.isfinite(seconds) or seconds < 0 or (mode == "nameplate" and seconds >= NAMEPLATE_SECONDS):
            continue
        path = work / f"frame-{int(index) + 1:06d}.png"
        if not path.is_file():
            raise ScreenError(f"FFmpeg did not preserve the frame at {seconds:g}s")
        checksum = _CHECKSUM.search(details)
        if checksum is None or checksum[1] not in checksums:
            frames.append(Frame(path, seconds))
            if checksum:
                checksums.add(checksum[1])
    if not frames:
        raise ScreenError("FFmpeg returned no timed frames")
    return frames


def _tsv_lines(tsv: str, multiplier: int) -> list[Line]:
    groups = defaultdict(list)
    for row in tsv.splitlines():
        fields = row.split("\t", 11)
        if len(fields) != 12 or fields[0] != "5" or not fields[-1].strip():
            continue
        try:
            left, top, width, height = (int(field) * multiplier for field in fields[6:10])
        except ValueError:
            continue
        groups[tuple(fields[1:5])].append(Line(fields[-1].strip(), left, top, width, height))
    lines = []
    for words in groups.values():
        left = min(word.x for word in words)
        top = min(word.y for word in words)
        lines.append(Line(
            " ".join(word.text for word in words), left, top,
            max(word.x + word.width for word in words) - left,
            max(word.y + word.height for word in words) - top,
        ))
    return lines


def _nameplate(lines: list[Line]) -> list[Line]:
    """Keep lower-third names with nearby aligned role lines, in OCR reading order."""
    selected = set()
    for line in lines:
        name, comma, role = line.text.partition(",")
        if not _NAME.fullmatch(name.strip()):
            continue
        if comma and any(char.isalpha() for char in role):
            selected.add(line)
            continue
        following = sorted((
            other for other in lines if 0 < other.y - line.y <= line.height * 3
            and min(abs(other.x - line.x),
                    abs(other.x + other.width / 2 - line.x - line.width / 2),
                    abs(other.x + other.width - line.x - line.width)) <= line.height
            and any(char.isalpha() for char in other.text)
        ), key=lambda other: other.y)
        if following:
            selected.add(line)
            selected.update(following[:2])
    return [line for line in lines if line in selected]


def _read_frame(
    scan: Scan, ffmpeg: str, tesseract: str, mode: str, crop: str, frame: Frame,
) -> list[tuple[Line, bool]]:
    lang = os.environ.get("TFV_OCR_LANG", "").strip() or "eng"
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    passes = []
    original = frame.path.with_name(f"{frame.path.stem}-original.png")
    for name, filters, multiplier in (
        ("original", crop, 1),
        ("half", "scale=iw/2:ih/2", 2),
        ("binary", "format=gray,negate,lut=y='if(gte(val,128),255,0)'", 1),
    ):
        path = frame.path.with_name(f"{frame.path.stem}-{name}.png")
        source = frame.path if name == "original" else original
        scan.run([
            ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
            "-filter_threads", "1", "-i", str(source), "-vf", filters,
            "-frames:v", "1", "-threads", "1", str(path),
        ], f"FFmpeg {name} transform")
        try:
            result = scan.run([tesseract, str(path), "stdout", "--psm", "11", "-l", lang, "tsv"],
                              "Tesseract OCR", limit=30, env=env)
        finally:
            if name != "original":
                path.unlink(missing_ok=True)
        lines = _tsv_lines(result.stdout, multiplier)
        passes.append(lines)
    original.unlink()
    recognized = _agree(passes)
    if mode == "nameplate":
        # Role and name can be split differently by the three OCR passes.
        selected = {line for lines in passes for line in _nameplate(lines)}
        recognized = [(line, trusted) for line, trusted in recognized if line in selected]
    return recognized


def _agree(passes: list[list[Line]]) -> list[tuple[Line, bool]]:
    """Require matching numeric glyphs in distinct passes of the same frame."""
    result: dict[str, tuple[Line, bool]] = {}
    numbers = [[(line, tuple(_numeric_spelling(line.text))) for line in lines] for lines in passes]
    for index, lines in enumerate(numbers):
        for line, spelling in lines:
            trusted = not _NUMERIC_MARK.search(line.text) or any(
                spelling and spelling == other_spelling
                and (line.text == other.text or line.at_same_position(other))
                for other_index, others in enumerate(numbers) if index != other_index
                for other, other_spelling in others
            )
            earlier = result.get(line.text)
            if earlier is None or trusted and not earlier[1]:
                result[line.text] = (line, trusted)
    return list(result.values())


def _numeric_spelling(text: str) -> list[str]:
    # Keep punctuation, units and letter-shaped OCR errors adjacent to digits.
    matches = _NUMERIC_TEXT.finditer(text)
    spellings = []
    for match in matches:
        start, end = match.span()
        if start and text[start - 1] in ".,$€£¥￥":
            start -= 1
        if end < len(text) and text[end] in ".,":
            end += 1
        spellings.append(text[start:end])
    return spellings


def _write_evidence(
    staged: Path, frames: list[Frame], results: list[list[tuple[Line, bool]]], *, filter_watermarks: bool,
) -> dict[str, list[int]]:
    positions = defaultdict(list)
    if filter_watermarks:
        for index, lines in enumerate(results):
            for line, _ in lines:
                positions[line.text.casefold()].append((index, line))
    majority = max(3, len(frames) // 2 + 1)
    watermarks = set()
    for text, occurrences in positions.items():
        if len(occurrences) >= majority and any(
            len({index for index, other in occurrences if line.at_same_position(other)}) >= majority
            for _, line in occurrences
        ):
            watermarks.add(text)

    # Prefer a confirmed occurrence of the same text, even if an earlier frame was uncertain.
    chosen: dict[str, tuple[Frame, bool]] = {}
    for frame, lines in zip(frames, results):
        for line, trusted in lines:
            if line.text.casefold() in watermarks:
                continue
            previous = chosen.get(line.text)
            if previous is None or trusted and not previous[1]:
                chosen[line.text] = (frame, trusted)
    if not chosen:
        raise ScreenError("OCR found no screen text after filtering")
    screenshots = staged / SCREEN_FRAMES
    screenshots.mkdir()
    references = {}
    rows = []
    for text, (frame, trusted) in sorted(chosen.items(), key=lambda item: item[1][0].seconds):
        tag = SCREEN_TAG if trusted else UNCERTAIN_SCREEN_TAG
        rows.append(f"{quality_gate.format_stamp(frame.seconds)}{tag} {text}")
        if frame.path.name not in references:
            frame.path.replace(screenshots / frame.path.name)
            references[frame.path.name] = []
        references[frame.path.name].append(len(rows))
    (staged / SCREEN_FILE).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return references


def extract(
    staged: Path, mode: str, source: str, download_command: list[str], duration: float | None,
    download_options: Callable[[], list[str]],
) -> dict:
    scan = Scan(duration)
    versions: dict[str, str] = {}
    status: dict = {"mode": mode, "versions": versions}
    try:
        commands = scan.probe(versions)
        crop = _crop(mode)
        if not download_command:
            raise ScreenError("yt-dlp missing")
        with tempfile.TemporaryDirectory(prefix="ocr-", dir=staged) as temp:
            work = Path(temp)
            video = _download(scan, [*download_command, *download_options()], source, work)
            frames = _frames(scan, commands["ffmpeg"], video, work, mode)
            video.unlink()
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [
                    workers.submit(_read_frame, scan, commands["ffmpeg"], commands["tesseract"], mode, crop, frame)
                    for frame in frames
                ]
                try:
                    results = [future.result() for future in futures]
                except (ScreenError, OSError, KeyboardInterrupt):
                    for future in futures:
                        future.cancel()
                    raise
            references = _write_evidence(staged, frames, results, filter_watermarks=mode == "slides")
        scan.remaining()
        status.update(state="ready", path=SCREEN_FILE, screenshot_directory=SCREEN_FRAMES,
                      screenshot_lines=references,
                      sha256=hashlib.sha256((staged / SCREEN_FILE).read_bytes()).hexdigest())
    except (OSError, ScreenError) as exc:
        status.update(state="fallback", reason=str(exc))
    status.update(elapsed_seconds=round(time.monotonic() - scan.started, 3),
                  timeout_seconds=scan.budget)
    return status
