"""Optional YouTube frame extraction and OCR. The caller publishes the result."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zlib
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from itertools import groupby
from pathlib import Path
from statistics import median
from threading import BoundedSemaphore, Thread, enumerate as live_threads
from urllib.request import ProxyHandler, Request, build_opener, getproxies

import quality_gate
from verify_rules import SCREEN_FILE, SCREEN_FRAMES, SCREEN_TAG, UNCERTAIN_SCREEN_TAG

SLIDE_INTERVAL = 8
SLIDE_OCR_PASSES = 2
SLIDE_GROUP_LEFT = 0.30
SLIDE_GROUP_BOTTOM = 0.78
SLIDE_GROUP_SIZE = (160, 90)
SLIDE_GROUP_DIFFERENCE = 5.5
SLIDE_COMMON_RATIO = 0.5
NAMEPLATE_INTERVAL = 2
NAMEPLATE_SECONDS = 180
NAMEPLATE_TIMEOUT = 120
UNKNOWN_DURATION_TIMEOUT = 600
AUTO_SAMPLE_TIMEOUT = 45
AUTO_CALIBRATION_TIMEOUT = 30
AUTO_BUDGET_HEADROOM = 0.70
AUTO_LIVE_OVERRUN_MIN_FRAMES = 4
AUTO_SAMPLE_CLEANUP_SECONDS = 0.5
AUTO_SAMPLE_POSITIONS = (0.10, 0.33, 0.56, 0.80)
AUTO_MIN_CONFIDENCE = 0.80
AUTO_MIN_LINE_LENGTH = 6
AUTO_MIN_LINES = 3
AUTO_MIN_TEXT_LENGTH = 42
AUTO_MIN_VERTICAL_SPAN = 0.12
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


class ScreenTimeout(ScreenError):
    pass


class ScreenDependencyError(ScreenError):
    pass


def failure_result(exc: Exception) -> str:
    if isinstance(exc, (ScreenTimeout, subprocess.TimeoutExpired, TimeoutError)):
        return "timeout"
    if isinstance(exc, (ScreenDependencyError, ModuleNotFoundError)):
        return "missing_dependencies"
    return "error"


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
    def __init__(self, mode: str, duration: float | None, *, budget: float | None = None):
        self.started = time.monotonic()
        full_budget = NAMEPLATE_TIMEOUT if mode == "nameplate" else (
            duration / 2 if duration else UNKNOWN_DURATION_TIMEOUT
        )
        self.budget = full_budget if budget is None else budget

    def remaining(self) -> float:
        left = self.budget - (time.monotonic() - self.started)
        if left <= 0:
            raise ScreenTimeout("screen OCR timed out")
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
            raise ScreenTimeout(f"{step} timed out") from exc
        except OSError as exc:
            raise ScreenError(f"{step} unavailable: {exc.strerror or exc}") from exc
        if result.returncode:
            lines = (result.stderr or result.stdout).splitlines()
            detail = lines[-1].strip() if lines else f"exit {result.returncode}"
            raise ScreenError(f"{step} failed: {detail}")
        return result

    def probe(self, versions: dict[str, str]) -> str:
        ffmpeg = shutil.which("ffmpeg")
        missing = [] if ffmpeg else ["ffmpeg missing"]
        for package in ("rapidocr", "onnxruntime"):
            try:
                versions[package] = version(package)
            except PackageNotFoundError:
                missing.append(f"{package} missing")
        if missing:
            raise ScreenDependencyError(", ".join(missing))
        assert ffmpeg is not None
        for name, executable, flag in (
            ("python", sys.executable, "--version"),
            ("ffmpeg", ffmpeg, "-version"),
        ):
            result = self.run([executable, flag], f"{name} version probe", limit=10)
            output = (result.stdout or result.stderr).strip()
            if not output:
                raise ScreenError(f"{name} version probe returned no version")
            versions[name] = output.splitlines()[0]
        return ffmpeg

    def recognize(self, operation, *args):
        # Native inference can outlive its deadline. Keep it off the caller
        # thread and use bytes so it cannot race temporary-file cleanup.
        deadline = time.monotonic() + min(30, self.remaining())
        if not _OCR_SLOTS.acquire(timeout=max(0, deadline - time.monotonic())):
            raise ScreenTimeout("RapidOCR timed out")
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
            raise ScreenTimeout("RapidOCR timed out") from exc
        except Exception as exc:
            if isinstance(exc, ModuleNotFoundError):
                raise ScreenDependencyError(str(exc)) from exc
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
    previous_checksum = None
    for index, pts, details in _SHOWINFO.findall(result.stderr):
        seconds = float(pts)
        if not math.isfinite(seconds) or seconds < 0 or (mode == "nameplate" and seconds >= NAMEPLATE_SECONDS):
            continue
        path = work / f"frame-{int(index) + 1:06d}.png"
        if not path.is_file():
            raise ScreenError(f"FFmpeg did not preserve the frame at {seconds:g}s")
        checksum = _CHECKSUM.search(details)
        duplicate = checksum is not None and (
            checksum[1] == previous_checksum if mode == "slides" else checksum[1] in checksums
        )
        if not duplicate:
            frames.append(Frame(path, seconds))
        previous_checksum = checksum[1] if checksum else None
        if checksum:
            checksums.add(checksum[1])
    if not frames:
        raise ScreenError("FFmpeg returned no timed frames")
    return frames


def _gray_pixels(path: Path) -> bytes:
    """Read only the gray8, non-interlaced, unfiltered PNG emitted below."""
    png = path.read_bytes()
    if png[:8] != b"\x89PNG\r\n\x1a\n" or png[24:29] != b"\x08\x00\x00\x00\x00":
        raise ScreenError("slide thumbnail is not an unfiltered gray8 PNG")
    width, height = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    chunks, cursor = [], 8
    while cursor + 12 <= len(png):
        length = int.from_bytes(png[cursor:cursor + 4], "big")
        if png[cursor + 4:cursor + 8] == b"IDAT":
            chunks.append(png[cursor + 8:cursor + 8 + length])
        cursor += length + 12
    try:
        rows = zlib.decompress(b"".join(chunks))
    except zlib.error as exc:
        raise ScreenError("slide thumbnail PNG is unreadable") from exc
    stride = width + 1
    if not width or not height or len(rows) != stride * height or any(rows[::stride]):
        raise ScreenError("slide thumbnail PNG has an unexpected row format")
    return b"".join(rows[start + 1:start + stride] for start in range(0, len(rows), stride))


def _group_frames(scan: Scan, ffmpeg: str, frames: list[Frame]) -> list[list[Frame]]:
    if len(frames) < 2:
        return [frames] if frames else []
    groups: list[list[Frame]] = []
    previous = None
    width, height = SLIDE_GROUP_SIZE
    filters = (
        f"format=gray,crop=iw-trunc(iw*{SLIDE_GROUP_LEFT}):trunc(ih*{SLIDE_GROUP_BOTTOM})"
        f":trunc(iw*{SLIDE_GROUP_LEFT}):0,scale={width}:{height}:flags=area"
    )
    for frame in frames:
        thumbnail = frame.path.with_name(f"{frame.path.stem}-group.png")
        try:
            scan.run([
                ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
                "-filter_threads", "1", "-i", str(frame.path), "-vf", filters,
                "-frames:v", "1", "-threads", "1", "-pix_fmt", "gray", "-pred", "none", str(thumbnail),
            ], "slide grouping")
            pixels = _gray_pixels(thumbnail)
        finally:
            thumbnail.unlink(missing_ok=True)
        if previous is not None and len(previous) != len(pixels):
            raise ScreenError("slide thumbnail dimensions changed during grouping")
        difference = (
            sum(abs(left - right) for left, right in zip(previous, pixels)) / len(pixels)
            if previous is not None else SLIDE_GROUP_DIFFERENCE
        )
        if difference >= SLIDE_GROUP_DIFFERENCE:
            groups.append([])
        groups[-1].append(frame)
        previous = pixels
        scan.remaining()
    return groups


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


def _sample_pair_qualifies(scan: Scan, ocr, paths: list[Path], height: int) -> bool:
    readings = []
    frame_ocr_times = getattr(scan, "frame_ocr_times", None)
    for path in paths:
        frame = path.read_bytes()
        started = time.monotonic()
        result = scan.recognize(ocr, frame)
        elapsed = time.monotonic() - started
        if frame_ocr_times is not None and math.isfinite(elapsed) and elapsed > 0:
            frame_ocr_times.append(elapsed)
        lines = {}
        for box, text, score in zip(result.boxes if result.boxes is not None else (),
                                    result.txts or (), result.scores or ()):
            key = "".join(char for char in text.casefold() if char.isalnum())
            if score >= AUTO_MIN_CONFIDENCE and len(key) >= AUTO_MIN_LINE_LENGTH:
                lines[key] = sum(point[1] for point in box) / len(box)
        readings.append(lines)
    first, second = readings
    stable = first.keys() & second.keys()
    if len(stable) < AUTO_MIN_LINES or sum(map(len, stable)) < AUTO_MIN_TEXT_LENGTH:
        return False
    positions = [first[key] for key in stable]
    return max(positions) - min(positions) >= height * AUTO_MIN_VERTICAL_SPAN


def _measure_download_seconds(
    url: str, headers: dict, proxy: str, filesize: float | int | None, timeout: float,
) -> float:
    try:
        if not filesize or filesize <= 0 or timeout <= 0:
            return 0.0
        opener = build_opener(ProxyHandler({"https": proxy, "http": proxy} if proxy else {}))
        request = Request(url, headers=headers)
        request.add_header("Range", "bytes=0-1048575")
        wall_limit = min(6.0, timeout)
        future = Future()

        def measure() -> float:
            deadline = time.monotonic() + wall_limit
            with opener.open(request, timeout=wall_limit) as response:
                started = time.monotonic()
                reader = getattr(response, "read1", response.read)
                sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                total = 0
                while total < 1048576:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        break
                    try:
                        if sock is not None and hasattr(sock, "settimeout"):
                            sock.settimeout(left)
                    except Exception:
                        pass
                    chunk = reader(min(65536, 1048576 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                elapsed = time.monotonic() - started
                if total >= 65536 and elapsed > 0:
                    return float(filesize) / (total / elapsed)
            return 0.0

        def worker():
            try:
                future.set_result(measure())
            except Exception as exc:
                future.set_exception(exc)

        Thread(target=worker, name="tfv-dl-probe", daemon=True).start()
        return future.result(timeout=wall_limit)
    except Exception:
        return 0.0


def _calibrate_full_scan(
    ffmpeg: str, ocr, full_fmt: dict, duration: float, hit_at: int, proxy: str, work: Path,
) -> dict:
    cal_scan = Scan("slides", None, budget=AUTO_CALIBRATION_TIMEOUT)
    full_url = full_fmt["url"]
    full_headers = full_fmt.get("http_headers") or {}
    filesize = full_fmt.get("filesize") or full_fmt.get("filesize_approx")
    download_seconds = _measure_download_seconds(
        full_url, full_headers, proxy, filesize, cal_scan.remaining(),
    )
    if not math.isfinite(download_seconds) or download_seconds < 0:
        download_seconds = 0.0
    headers = "".join(f"{name}: {value}\r\n" for name, value in full_headers.items())
    full_network = (["-http_proxy", proxy] if proxy else []) + (["-headers", headers] if headers else [])
    ffmpeg_input = [ffmpeg, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                    "-rw_timeout", "8000000", *full_network]
    cal_dir = work / "calibration"
    cal_dir.mkdir(exist_ok=True)
    clip = cal_dir / "clip.mkv"
    cal_scan.run([
        *ffmpeg_input, "-i", full_url, "-t", str(SLIDE_INTERVAL), "-an", "-c", "copy", str(clip),
    ], "FFmpeg calibration clip")

    frame_dir = cal_dir / "clip-frames"
    frame_dir.mkdir()
    frame_scan = Scan("slides", duration, budget=cal_scan.remaining())
    started = time.monotonic()
    _frames(frame_scan, ffmpeg, clip, frame_dir, "slides")
    decode_seconds = time.monotonic() - started

    last_seek = max(0, int(duration) - 2)
    alt = min(last_seek, round(duration * 0.33))
    if abs(alt - hit_at) < SLIDE_INTERVAL:
        alt = min(last_seek, hit_at + SLIDE_INTERVAL)
    if alt == hit_at and duration >= 2:
        alt = 0 if hit_at else min(SLIDE_INTERVAL, duration / 2)
    if duration < 2:
        alt = hit_at
    cal_frames = []
    for index, pos in enumerate((hit_at, alt)):
        frame_path = cal_dir / f"cal-{index:02d}.png"
        cal_scan.run([
            *ffmpeg_input, "-ss", str(pos), "-i", full_url, "-frames:v", "1", "-an", str(frame_path),
        ], "FFmpeg calibration frame")
        cal_frames.append(Frame(frame_path, float(pos)))

    started = time.monotonic()
    _group_frames(cal_scan, ffmpeg, cal_frames)
    group_per_frame = (time.monotonic() - started) / len(cal_frames)
    crop = _crop("slides")
    read_times = []
    for frame in cal_frames:
        started = time.monotonic()
        _read_frame(cal_scan, ffmpeg, ocr, "slides", crop, frame)
        read_times.append(time.monotonic() - started)
    mean_read_frame = sum(read_times) / len(read_times)
    intervals = max(1, math.ceil(duration / SLIDE_INTERVAL))
    extract_seconds = decode_seconds * intervals
    group_seconds = group_per_frame * intervals
    ocr_seconds = mean_read_frame * intervals
    return {
        "intervals": intervals,
        "download_seconds": round(download_seconds, 3),
        "download_measured": download_seconds > 0,
        "extract_seconds_per_interval": round(decode_seconds, 6),
        "extract_seconds": round(extract_seconds, 3),
        "group_seconds_per_frame": round(group_per_frame, 6),
        "group_seconds": round(group_seconds, 3),
        "read_frame_seconds": round(mean_read_frame, 6),
        "ocr_seconds": round(ocr_seconds, 3),
        "estimated_total_seconds": round(download_seconds + extract_seconds + group_seconds + ocr_seconds, 3),
    }


def _is_direct_https_format(fmt: dict) -> bool:
    if not isinstance(fmt, dict):
        return False
    url = fmt.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    path = url.split("?", 1)[0].split("#", 1)[0][len("https://"):].partition("/")[2]
    return (
        fmt.get("protocol") in (None, "https")
        and not path.lower().endswith((".m3u8", ".mpd"))
    )


def _is_sample_format(fmt: dict) -> bool:
    if not _is_direct_https_format(fmt) or fmt.get("ext") not in (None, "mp4"):
        return False
    height = fmt.get("height")
    return isinstance(height, (int, float)) and not isinstance(height, bool) and 0 < height <= 480


def _is_full_scan_format(fmt: dict, sample_height: float | int) -> bool:
    if not _is_direct_https_format(fmt):
        return False
    height = fmt.get("height")
    return (
        isinstance(height, (int, float))
        and not isinstance(height, bool)
        and (isinstance(height, int) or math.isfinite(height))
        and height >= sample_height
    )


def _sanitize_calibration_reason(text: str, kind: str) -> str:
    cleaned = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]", "", text)
    cleaned = re.sub(
        r"(?i)\b((?:set-)?cookie|(?:proxy-)?authorization|x-api-key)\s*[:=][^\r\n]*",
        r"\1: <redacted>",
        cleaned,
    )
    cleaned = re.sub(r"\w+://\S+", "<URL>", cleaned)
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]+", " ", cleaned)
    return " ".join(cleaned.split()) or f"calibration {kind}"


def sample_slides(
    staged: Path, source: str, download_command: list[str],
    download_options: Callable[[], list[str]],
) -> dict:
    """Check at most four pairs for stable screen text before the full scan."""
    # Leave time to terminate the child and discard its temporary frames.
    scan = Scan("slides", None, budget=AUTO_SAMPLE_TIMEOUT - AUTO_SAMPLE_CLEANUP_SECONDS)
    scan.frame_ocr_times = []
    sample_extract_times = []
    status = {"groups_checked": 0, "timeout_seconds": AUTO_SAMPLE_TIMEOUT}
    try:
        if not download_command:
            raise ScreenDependencyError("yt-dlp missing")
        ffmpeg = scan.probe({})
        proxies = getproxies()
        proxy = proxies.get("https") or proxies.get("all") or proxies.get("http") or ""
        response = scan.run([
            *download_command, *download_options(), "--proxy", proxy, "--no-playlist",
            "--skip-download", "--no-warnings", "--socket-timeout", "8", "--retries", "0",
            "-f", "bv[height<=480][ext=mp4][protocol=https],(bv[height=1080]/bv[height<=1080]/b[height<=1080])",
            "--dump-single-json", source,
        ], "yt-dlp sample stream")
        info = json.loads(response.stdout)
        requested_downloads = info.get("requested_downloads")
        if isinstance(requested_downloads, list) and requested_downloads:
            sample_fmt = next((fmt for fmt in requested_downloads if _is_sample_format(fmt)), None)
            if sample_fmt is None:
                raise ScreenError("sample stream has no usable <=480p HTTPS MP4 video")
            sample_height = int(sample_fmt["height"])
            full_fmt = max(
                (fmt for fmt in requested_downloads
                 if fmt is not sample_fmt and _is_full_scan_format(fmt, sample_height)),
                key=lambda fmt: fmt["height"],
                default=None,
            )
        else:
            sample_fmt = info
            full_fmt = None
            if not _is_sample_format(sample_fmt):
                raise ScreenError("sample stream has no usable <=480p HTTPS MP4 video")
        media = sample_fmt["url"]
        duration = float(info.get("duration") or sample_fmt.get("duration"))
        height = int(sample_fmt.get("height") or info.get("height"))
        sample_headers = sample_fmt.get("http_headers") or info.get("http_headers") or {}
        if not math.isfinite(duration) or duration <= 0 or height <= 0:
            raise ScreenError("sample stream has no usable HTTPS video or duration")
        status["duration"] = duration
        headers = "".join(f"{name}: {value}\r\n" for name, value in sample_headers.items())
        network = (["-http_proxy", proxy] if proxy else []) + (["-headers", headers] if headers else [])
        with tempfile.TemporaryDirectory(prefix="sample-", dir=staged) as temp:
            work = Path(temp)
            ocr = None
            status["result"] = "not_found"
            for fraction in AUTO_SAMPLE_POSITIONS:
                at = min(round(duration * fraction), max(0, int(duration) - 2))
                result_path = work / f"{at:04d}-%02d.jpg"
                started = time.monotonic()
                scan.run([
                    ffmpeg, "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
                    "-rw_timeout", "8000000", *network, "-ss", str(at), "-i", media,
                    "-t", "2", "-vf", "fps=1", "-an", "-q:v", "3", str(result_path),
                ], "FFmpeg sample frames")
                extract_elapsed = time.monotonic() - started
                paths = sorted(work.glob(f"{at:04d}-*.jpg"))
                if paths and math.isfinite(extract_elapsed) and extract_elapsed > 0:
                    sample_extract_times.append(extract_elapsed / len(paths))
                if len(paths) != 2:
                    raise ScreenError("FFmpeg did not return two sample frames")
                if ocr is None:
                    ocr = scan.recognize(_rapidocr, "slides")
                qualifies = _sample_pair_qualifies(scan, ocr, paths, height)
                for path in paths:
                    path.unlink()
                scan.remaining()
                status["groups_checked"] += 1
                if qualifies:
                    status["result"] = "slides_detected"
                    hit_at = at
                    break
            if status["result"] == "slides_detected" and full_fmt is not None and ocr is not None:
                try:
                    status["calibration"] = _calibrate_full_scan(ffmpeg, ocr, full_fmt, duration, hit_at, proxy, work)
                    status["calibration_status"] = "calibrated"
                except Exception as exc:
                    kind = failure_result(exc)
                    status["calibration_status"] = "timeout_fallback" if kind == "timeout" else "fallback"
                    status["calibration_reason"] = _sanitize_calibration_reason(str(exc), kind)
    except Exception as exc:
        status.update(result=failure_result(exc), reason=re.sub(r"\w+://\S+", "<URL>", str(exc)))
    if scan.frame_ocr_times:
        status["mean_frame_ocr_seconds"] = round(
            sum(scan.frame_ocr_times) / len(scan.frame_ocr_times), 6
        )
    if sample_extract_times:
        status["mean_sample_extract_seconds"] = round(
            sum(sample_extract_times) / len(sample_extract_times), 6,
        )
    status["elapsed_seconds"] = round(time.monotonic() - scan.started, 3)
    return status


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


def _fixed_watermarks(frames: list[Frame], results: list[list[tuple[Line, bool]]]) -> set[str]:
    positions = defaultdict(list)
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
    return watermarks


def _reading_columns(items: list[tuple[Frame, Line, bool]]) -> list[list[tuple[Frame, Line, bool]]]:
    """Split a frame at its widest clear gutter between vertically overlapping columns."""
    by_x = sorted(items, key=lambda item: item[1].x)
    gutter = median(item[1].height for item in items)
    split = 0
    right_edge = 0
    for index, (_, line, _) in enumerate(by_x):
        gap = line.x - right_edge
        if gap > gutter and 2 <= index <= len(items) - 2:
            left, right = by_x[:index], by_x[index:]
            if max(min(item[1].y for item in side) for side in (left, right)) < min(
                max(item[1].y + item[1].height for item in side) for side in (left, right)
            ):
                split, gutter = index, gap
        right_edge = max(right_edge, line.x + line.width)
    if not split:
        return [items]
    return [sorted(side, key=lambda item: (item[1].y, item[1].x))
            for side in (by_x[:split], by_x[split:])]


def _write_evidence(
    staged: Path, frames: list[Frame], results: list[list[tuple[Line, bool]]], *, filter_watermarks: bool,
    slide_groups: list[list[Frame]] | None = None,
) -> dict[str, list[int]]:
    groups = slide_groups if slide_groups is not None else [frames]
    # Preserve the established fixed-position filter for a single screen.
    watermarks = _fixed_watermarks(frames, results) if filter_watermarks and len(groups) == 1 else set()
    by_frame = dict(zip(frames, results))
    chosen = [_deduplicate(group, [by_frame[frame] for frame in group], watermarks) for group in groups]
    if not any(chosen):
        raise ScreenError("OCR found no screen text after filtering")
    occurrences = defaultdict(set)
    preferred = {}
    for index, lines in enumerate(chosen):
        for item in lines:
            frame, line, trusted = item
            occurrences[line.text].add(index)
            previous = preferred.get(line.text)
            if previous is None or trusted > previous[2]:
                preferred[line.text] = item
    common = {text for text, indices in occurrences.items() if len(indices) / len(groups) >= SLIDE_COMMON_RATIO}
    screenshots = staged / SCREEN_FRAMES
    screenshots.mkdir()
    references = {}
    rows = []

    def retain(frame: Frame) -> None:
        if frame.path.name not in references:
            frame.path.replace(screenshots / frame.path.name)
            references[frame.path.name] = []
        references[frame.path.name].append(len(rows))

    for index, (group, lines) in enumerate(zip(groups, chosen), 1):
        if slide_groups is not None and len(groups) > 1:
            first = group[0]
            rows.append(f"{quality_gate.format_stamp(first.seconds)}[幻灯片 {index}] {first.path.name}")
            retain(first)
        visible = [item for item in lines if item[1].text not in common or item == preferred[item[1].text]]
        for frame, same_frame in groupby(visible, key=lambda item: item[0]):
            items = list(same_frame)
            columns = _reading_columns(items) if filter_watermarks else [items]
            for column_number, column in enumerate(columns):
                if column_number:
                    rows.append("")  # A physical boundary stops quotes from joining columns.
                for _, line, trusted in column:
                    tag = SCREEN_TAG if trusted else UNCERTAIN_SCREEN_TAG
                    rows.append(f"{quality_gate.format_stamp(frame.seconds)}{tag} {line.text}")
                    retain(frame)
    (staged / SCREEN_FILE).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return references


def extract(
    staged: Path, mode: str, source: str, download_command: list[str], duration: float | None,
    download_options: Callable[[], list[str]], abort_on_overrun: bool = False,
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
            groups = _group_frames(scan, ffmpeg, frames) if mode == "slides" else None
            ocr = scan.recognize(_rapidocr, mode)
            results, read_times = [], []
            for frame in frames:
                started = time.monotonic()
                results.append(_read_frame(scan, ffmpeg, ocr, mode, crop, frame))
                read_times.append(time.monotonic() - started)
                if abort_on_overrun and mode == "slides" and len(read_times) >= AUTO_LIVE_OVERRUN_MIN_FRAMES:
                    remaining_frames = len(frames) - len(read_times)
                    if remaining_frames > 0:
                        mean_read = sum(read_times) / len(read_times)
                        remaining_needed = mean_read * remaining_frames
                        left = scan.remaining()
                        if remaining_needed > left:
                            status["overrun_aborted"] = True
                            raise ScreenTimeout(
                                f"Estimated remaining OCR time ({remaining_needed:.1f}s) "
                                f"exceeds remaining budget ({left:.1f}s)."
                            )
            references = _write_evidence(
                staged, frames, results, filter_watermarks=mode == "slides", slide_groups=groups,
            )
            if groups is not None:
                status["slide_count"] = len(groups)
        scan.remaining()
        status.update(state="ready", path=SCREEN_FILE, screenshot_directory=SCREEN_FRAMES,
                      screenshot_lines=references,
                      sha256=hashlib.sha256((staged / SCREEN_FILE).read_bytes()).hexdigest())
    except (OSError, ScreenError) as exc:
        status.update(state="fallback", reason=str(exc), failure=failure_result(exc))
    status.update(elapsed_seconds=round(time.monotonic() - scan.started, 3),
                  timeout_seconds=scan.budget)
    return status
