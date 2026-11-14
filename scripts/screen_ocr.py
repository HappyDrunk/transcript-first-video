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
from concurrent.futures import Future
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import BoundedSemaphore, Thread, enumerate as live_threads

import quality_gate
from verify_rules import SCREEN_FILE, SCREEN_FRAMES, SCREEN_TAG, UNCERTAIN_SCREEN_TAG

SLIDE_INTERVAL = 8
NAMEPLATE_INTERVAL = 2
NAMEPLATE_SECONDS = 180
NAMEPLATE_TIMEOUT = 120
UNKNOWN_DURATION_TIMEOUT = 600
_OCR_SLOTS = BoundedSemaphore(2)
_OCR_WORKER = "tfv-rapidocr"

_SHOWINFO = re.compile(
    r"showinfo[^]\n]*]\s+n:\s*(\d+).*?\bpts_time:\s*([\d.eE+-]+)([^\n]*)"
)
_CHECKSUM = re.compile(r"\bchecksum:([A-Fa-f0-9]+)")
_DURATION = re.compile(r"\bDuration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_NUMERIC_TEXT = re.compile(
    r"(?:[A-Za-z]*[$€£¥￥][ \t]*)?[+\-−]?[A-Za-z]*[.,]?\d[A-Za-z\d]*"
    r"(?:[.,][A-Za-z\d]+|[.,][ \t]*\d+)*(?:[ \t]*(?:[$€£¥￥%％×倍]|[xX](?![A-Za-z])))?"
    r"|[零〇一二两三四五六七八九十百千万亿]+倍"
)
_NUMERIC_MARK = re.compile(r"[\d$€£¥￥%％×]|[零〇一二两三四五六七八九十百千万亿]+倍")
_NUMERIC_SYMBOL = re.compile(r"[$€£¥￥%％×]")
_PERCENT = re.compile(
    r"(?<![A-Za-z\d.,])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+(?:,\d+)?"
    r"|\d+(?:[.,]\d+)?|[.,]\d+)[ \t]*[%％](?![A-Za-z\d])"
)
_PERCENT_MARK = re.compile(r"[%％]")
_SHORT_NUMBER = re.compile(r"[+\-−]?[$€£¥￥]?(?:\d+(?:[.,]\d+)?|[.,]\d+)[%％×xX倍kKmMbB]?")
_NAME = re.compile(
    r"(?:[A-Z][^\W\d_]+(?:[-’'][^\W\d_]+)?(?:[ \t]+[A-Z][^\W\d_]+(?:[-’'][^\W\d_]+)?){1,3}"
    r"|[\u3400-\u9fff]{2,4})"
)
_ROLE = re.compile(r"[^\W\d_][\w .,&()/’'+\-]*")
_WORD = re.compile(r"[^\W\d_]+")
_NAMEPLATE_CONFIDENCE = 80


class ScreenError(Exception):
    pass


def native_ocr_running() -> bool:
    return any(thread.name == _OCR_WORKER for thread in live_threads())


@dataclass(frozen=True)
class Line:
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 0

    def at_same_position(self, other: Line) -> bool:
        tolerance = max(6, min(self.height, other.height) // 2)
        return abs(self.x - other.x) <= tolerance and abs(self.y - other.y) <= tolerance

    def overlaps(self, other: Line) -> bool:
        vertical = min(self.y + self.height, other.y + other.height) - max(self.y, other.y)
        horizontal = min(self.x + self.width, other.x + other.width) - max(self.x, other.x)
        return vertical > 0 and vertical * 2 >= min(self.height, other.height) and horizontal > 0


@dataclass(frozen=True)
class Frame:
    path: Path
    seconds: float


class Scan:
    def __init__(self, mode: str, duration: float | None):
        self.started = time.monotonic()
        self.budget = NAMEPLATE_TIMEOUT if mode == "nameplate" else (
            duration / 2 if duration else UNKNOWN_DURATION_TIMEOUT
        )

    def remaining(self) -> float:
        left = self.budget - (time.monotonic() - self.started)
        if left <= 0:
            raise ScreenError("screen OCR timed out")
        return left

    def run(self, args: list[str], step: str, *, limit: int | None = None):
        timeout = self.remaining()
        if limit is not None:
            timeout = min(timeout, limit)
        try:
            result = subprocess.run(
                args, capture_output=True, encoding="utf-8", errors="replace",
                timeout=timeout, check=False,
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

    def probe(self, versions: dict[str, str]) -> str:
        ffmpeg = shutil.which("ffmpeg")
        failures = []
        for name, executable, flag in (
            ("python", sys.executable, "--version"),
            ("ffmpeg", ffmpeg, "-version"),
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
            except ScreenError as exc:
                failures.append(str(exc))
        for package in ("rapidocr", "onnxruntime"):
            try:
                versions[package] = version(package)
            except PackageNotFoundError:
                failures.append(f"{package} missing")
        if failures:
            raise ScreenError(", ".join(failures))
        assert ffmpeg is not None
        return ffmpeg

    def recognize(self, operation, *args):
        # Native inference can outlive its deadline. Keep it off the caller
        # thread and use bytes so it cannot race temporary-file cleanup.
        deadline = time.monotonic() + min(30, self.remaining())
        if not _OCR_SLOTS.acquire(timeout=max(0, deadline - time.monotonic())):
            raise ScreenError("RapidOCR timed out")
        future = Future()

        def run():
            try:
                future.set_result(operation(*args))
            except Exception as exc:
                future.set_exception(exc)
            finally:
                _OCR_SLOTS.release()

        try:
            Thread(target=run, name=_OCR_WORKER, daemon=True).start()
        except RuntimeError as exc:
            _OCR_SLOTS.release()
            raise ScreenError(f"RapidOCR worker unavailable: {exc}") from exc
        try:
            result = future.result(timeout=max(0, deadline - time.monotonic()))
        except TimeoutError as exc:
            raise ScreenError("RapidOCR timed out") from exc
        except Exception as exc:
            raise ScreenError(f"RapidOCR failed: {exc}") from exc
        self.remaining()
        return result


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
        return ""
    try:
        x, y, w, h = map(float, raw.split(","))
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x and 0 < h <= 1 - y):
            raise ValueError
    except ValueError as exc:
        raise ScreenError("TFV_SLIDE_CROP must be x,y,width,height as fractions within the frame") from exc
    return f"crop=trunc(iw*{w}/2)*2:trunc(ih*{h}/2)*2:iw*{x}:ih*{y}"


def _frames(scan: Scan, ffmpeg: str, video: Path, work: Path, mode: str) -> list[Frame]:
    interval = NAMEPLATE_INTERVAL if mode == "nameplate" else SLIDE_INTERVAL
    new_bucket = f"gt(floor(t/{interval}),floor(prev_selected_t/{interval}))"
    spaced = "gte(t-prev_selected_t,1)"
    # A nearby cut must not displace the next periodic sample of a brief lower third.
    extra = f"{new_bucket}+{spaced}*gt(scene,0.30)" if mode == "nameplate" else (
        f"{spaced}*(gt(scene,0.30)+{new_bucket})"
    )
    select = f"select='isnan(prev_selected_t)+{extra}'"
    result = scan.run([
        ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info",
        "-filter_threads", "1", *(["-t", str(NAMEPLATE_SECONDS)] if mode == "nameplate" else []),
        "-i", str(video), "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", f"{select},showinfo", "-fps_mode", "vfr",
        "-threads", "1", "-start_number", "1", str(work / "frame-%06d.png"),
    ], "frame extraction")
    duration = _DURATION.search(result.stderr)
    if mode == "slides" and duration:
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


def _rapidocr(mode: str):
    os.environ.setdefault("OPENCV_FOR_THREADS_NUM", "1")
    from rapidocr import RapidOCR

    # The package defaults to CPU ONNX Runtime and ships the corresponding models.
    params = {
        "EngineConfig.onnxruntime.intra_op_num_threads": min(8, os.cpu_count() or 1),
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    }
    if mode == "nameplate":
        # The detector normally enlarges the short side to 736 px, even on
        # a shallow lower-third crop. Keep the package's existing 2000 px cap.
        params.update({"Det.limit_type": "max", "Det.limit_side_len": 2000})
    return RapidOCR(params=params)


def _nameplate(lines: list[Line]) -> list[Line]:
    """Keep lower-third names with nearby aligned role lines, in OCR reading order."""
    def role_text(text: str) -> bool:
        return bool(_ROLE.fullmatch(text) and any(len(word) >= 3 for word in _WORD.findall(text)))

    readable = [line for line in lines if line.confidence >= _NAMEPLATE_CONFIDENCE]
    selected = set()
    for line in readable:
        name, comma, role = line.text.partition(",")
        if not _NAME.fullmatch(name.strip()):
            continue
        if comma and role_text(role.strip()):
            selected.add(line)
            continue
        following = sorted((
            other for other in readable if line.height / 2 < other.y - line.y <= line.height * 3
            and min(abs(other.x - line.x),
                    abs(other.x + other.width / 2 - line.x - line.width / 2),
                    abs(other.x + other.width - line.x - line.width)) <= line.height
            and role_text(other.text)
        ), key=lambda other: other.y)
        if following and following[0].y <= line.y + line.height * 2:
            selected.add(line)
            selected.update(following[:2])
    return [line for line in lines if line in selected]


def _read_frame(
    scan: Scan, ffmpeg: str, ocr, mode: str, crop: str, frame: Frame,
) -> list[tuple[Line, bool]]:
    def transform(source: Path, name: str, filters: str) -> Path:
        path = frame.path.with_name(f"{frame.path.stem}-{name}.png")
        scan.run([
            ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
            "-filter_threads", "1", "-i", str(source), "-vf", filters,
            "-frames:v", "1", "-threads", "1", str(path),
        ], f"FFmpeg {name} transform")
        return path

    original = transform(frame.path, "original", crop) if crop else frame.path
    passes = []
    for size in (1, 2):
        path = original if size == 1 else transform(original, "half", "scale=iw/2:ih/2")
        result = scan.recognize(ocr, path.read_bytes())
        if size == 2:
            path.unlink()
        lines = []
        for box, text, score in zip(result.boxes if result.boxes is not None else (),
                                    result.txts or (), result.scores or ()):
            x, y = zip(*box)
            left, right = round(min(x) * size), round(max(x) * size)
            top, bottom = round(min(y) * size), round(max(y) * size)
            if text := " ".join(text.split()):
                lines.append(Line(text, left, top, right - left, bottom - top, float(score) * 100))
        passes.append(lines)
    if original != frame.path:
        original.unlink()
    return _agree(passes, nameplate=mode == "nameplate")


def _agree(passes: list[list[Line]], *, nameplate: bool) -> list[tuple[Line, bool]]:
    """Require matching numeric glyphs in distinct passes of the same frame."""
    result: dict[str, tuple[Line, bool]] = {}
    numeric_lines = [
        [(line, _numeric_spelling(line.text)) for line in lines if _NUMERIC_MARK.search(line.text)]
        for lines in passes
    ]
    for index, lines in enumerate(passes):
        other_numbers = numeric_lines[1 - index]
        for line in _nameplate(lines) if nameplate else lines:
            if _NUMERIC_MARK.search(line.text):
                trusted = _confirmed_number(line, other_numbers)
            else:
                # Another pass may have read a number where this pass found a symbol or omitted it.
                trusted = not any(
                    line.overlaps(other) and _similar_words(line.text, other.text)
                    for other, _ in other_numbers
                )
            if not nameplate and len(line.text) <= 3 and not (trusted and _SHORT_NUMBER.fullmatch(line.text)):
                continue
            earlier = result.get(line.text)
            if earlier is None or (trusted, line.confidence) > (earlier[1], earlier[0].confidence):
                result[line.text] = (line, trusted)
    return list(result.values())


def _confirmed_number(line: Line, other_numbers: list[tuple[Line, tuple[str, ...]]]) -> bool:
    spelling = _numeric_spelling(line.text)
    if not spelling or _NUMERIC_SYMBOL.findall(line.text) != _NUMERIC_SYMBOL.findall(" ".join(spelling)):
        return False
    # OCR can produce the same letter/digit mixture in several passes.
    if len(_PERCENT.findall(line.text)) != len(_PERCENT_MARK.findall(line.text)):
        return False
    return any(
        spelling == other_spelling
        and (line.text == other.text or line.at_same_position(other) or line.overlaps(other))
        for other, other_spelling in other_numbers
    )


def _similar_words(text: str, other: str) -> bool:
    """Find shared context when a glyph in a line is read as a digit in another pass."""
    words = set(_WORD.findall(text.casefold()))
    other_words = set(_WORD.findall(other.casefold()))
    return bool(words and words == other_words) or any(len(word) >= 3 for word in words & other_words)


def _numeric_spelling(text: str) -> tuple[str, ...]:
    # Keep punctuation, units and letter-shaped OCR errors adjacent to digits.
    spellings = []
    for match in _NUMERIC_TEXT.finditer(text):
        start, end = match.span()
        if start and text[start - 1] in ".,$€£¥￥":
            start -= 1
        if end < len(text) and text[end] in ".,":
            end += 1
        spellings.append(text[start:end])
    return tuple(spellings)


def _deduplicate(
    frames: list[Frame], results: list[list[tuple[Line, bool]]], watermarks: set[str],
) -> list[tuple[Frame, Line, bool]]:
    chosen: dict[str, tuple[Frame, Line, bool]] = {}
    for frame, lines in sorted(zip(frames, results), key=lambda item: item[0].seconds):
        local: dict[tuple[str, tuple[str, ...]], tuple[Line, bool]] = {}
        for line, trusted in lines:
            folded = line.text.casefold()
            if folded in watermarks:
                continue
            normalized = folded.replace("'", "").replace("’", "")
            key = normalized, _numeric_spelling(line.text)
            same_frame = local.get(key)
            if same_frame is None or (trusted, line.confidence) > (same_frame[1], same_frame[0].confidence):
                local[key] = line, trusted
        for line, trusted in local.values():
            previous = chosen.get(line.text)
            if previous is None or trusted > previous[2]:
                chosen[line.text] = frame, line, trusted
    return sorted(chosen.values(), key=lambda item: item[0].seconds)


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

    chosen = _deduplicate(frames, results, watermarks)
    if not chosen:
        raise ScreenError("OCR found no screen text after filtering")
    screenshots = staged / SCREEN_FRAMES
    screenshots.mkdir()
    references = {}
    rows = []
    for frame, line, trusted in chosen:
        tag = SCREEN_TAG if trusted else UNCERTAIN_SCREEN_TAG
        rows.append(f"{quality_gate.format_stamp(frame.seconds)}{tag} {line.text}")
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
    scan = Scan(mode, duration)
    versions: dict[str, str] = {}
    status: dict = {"mode": mode, "versions": versions}
    try:
        ffmpeg = scan.probe(versions)
        crop = _crop(mode)
        if not download_command:
            raise ScreenError("yt-dlp missing")
        with tempfile.TemporaryDirectory(prefix="ocr-", dir=staged) as temp:
            work = Path(temp)
            video = _download(scan, [*download_command, *download_options()], source, work)
            frames = _frames(scan, ffmpeg, video, work, mode)
            video.unlink()
            ocr = scan.recognize(_rapidocr, mode)
            results = [_read_frame(scan, ffmpeg, ocr, mode, crop, frame) for frame in frames]
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
