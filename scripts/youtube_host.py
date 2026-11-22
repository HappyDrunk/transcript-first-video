#!/usr/bin/env python3
"""Minimal YouTube host: captions first, optional ASR, otherwise no transcript.

A passing transcript writes transcript.txt (caption lines keep [mm:ss]), segments.json,
chunks/, status.json, and note.scaffold.md. The scaffold is frontmatter, empty
section headings, and fill instructions. It is not a finished knowledge note.
YouTube title, channel and publication date are separate from the transcript.
The host does not analyze the transcript or store the description. On failure the job directory
keeps status.json and no scaffold.

Exit 0 when the transcript passes and a scaffold is written. That exit does not
mean a finished knowledge note. Exit 2 when the transcript is not usable.
Exit 1 usage.
"""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import knowledge_note  # noqa: E402
import quality_gate  # noqa: E402
import screen_ocr  # noqa: E402
import user_prefs  # noqa: E402
import verify_note  # noqa: E402
import verify_rules  # noqa: E402

USER_AGENT = "Mozilla/5.0 (compatible; transcript-first-video/1.0)"
INSTANCE_LIST = "https://api.invidious.io/instances.json?sort_by=health"
# This single built-in seed is a single point of failure used only when public discovery fails or yields no usable hosts.
SEED_INVIDIOUS_INSTANCES = ("https://yt.chocolatemoo53.com",)
MIRROR_REQUEST_TIMEOUT = 7
MIRROR_TOTAL_BUDGET = 30.0
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_SECRET = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|sessdata|cookie|token)(['\"=: ]+)(\S+)"
)
_LABEL_LANG = {
    "english": "en",
    "chinese": "zh",
    "mandarin": "zh",
    "japanese": "ja",
    "korean": "ko",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "portuguese": "pt",
    "russian": "ru",
    "arabic": "ar",
    "hindi": "hi",
    "indonesian": "id",
    "vietnamese": "vi",
    "dutch": "nl",
    "italian": "it",
    "polish": "pl",
    "turkish": "tr",
    "ukrainian": "uk",
    "hebrew": "he",
    "thai": "th",
    "swedish": "sv",
    "bangla": "bn",
    "bengali": "bn",
}


def skill_version() -> str:
    """Return this install's commit id, or its VERSION for a source copy."""
    root = Path(__file__).resolve().parents[1]
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        ).stdout.strip()
        if Path(top).resolve() != root.resolve():
            raise subprocess.CalledProcessError(1, "git rev-parse --show-toplevel")
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        commit = result.stdout.strip()
        if commit:
            return commit
    except (OSError, subprocess.SubprocessError):
        pass
    version_file = root / "VERSION"
    if version_file.is_file():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version
    return "unknown"


class HostError(Exception):
    pass


def redact(text: str, limit: int = 700) -> str:
    cleaned = re.sub(r"(?i)(https?://)[^/\s?#]+@", r"\1<redacted>@", text or "")
    cleaned = _SECRET.sub(r"\1\2<redacted>", cleaned)
    cleaned = re.sub(r"sk-[A-Za-z0-9]{8,}", "sk-<redacted>", cleaned)
    cleaned = re.sub(r"https?://\S+", lambda match: match.group(0).split("?")[0], cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]


def log(message: str) -> None:
    print(message, file=sys.stderr)


def parse_youtube_ref(value: str) -> tuple[str, str]:
    raw = value.strip()
    if _VIDEO_ID.fullmatch(raw):
        return raw, f"https://www.youtube.com/watch?v={raw}"
    parsed = urllib.parse.urlparse(raw if "://" in raw else "https://" + raw)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    elif host.startswith("m."):
        host = host[2:]
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "music.youtube.com", "youtube-nocookie.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0] in {"shorts", "embed", "live", "v"} and len(parts) >= 2:
            video_id = parts[1]
        else:
            ids = urllib.parse.parse_qs(parsed.query).get("v") or []
            video_id = ids[0] if ids else ""
    else:
        raise HostError(f"not a YouTube URL or 11-character video id: {raw}")
    if not _VIDEO_ID.fullmatch(video_id):
        raise HostError(f"not a YouTube URL or 11-character video id: {raw}")
    return video_id, f"https://www.youtube.com/watch?v={video_id}"


_PLATFORMS = {"youtube", "x"}


def job_id_for(video_id: str, platform: str = "youtube") -> str:
    if platform not in _PLATFORMS:
        raise HostError(f"unsupported platform {platform}")
    if not _SAFE_ID.fullmatch(video_id):
        raise HostError("video id contains characters that are not safe in a path")
    return f"{platform}_{video_id}"


def cite_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ytdlp_base() -> list[str] | None:
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    probe = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "yt_dlp"]
    return None


def _ytdlp_extra_args() -> list[str]:
    args: list[str] = []
    cookies = os.environ.get("YTDLP_COOKIES", "").strip()
    if cookies:
        cookie_path = Path(cookies)
        if cookie_path.is_file():
            args.extend(["--cookies", str(cookie_path)])
        else:
            raise HostError("YTDLP_COOKIES is set but that file does not exist")
    extractor = os.environ.get("YTDLP_EXTRACTOR_ARGS", "").strip()
    if extractor:
        args.extend(["--extractor-args", extractor])
    return args


def _screen_download_options() -> list[str]:
    try:
        return _ytdlp_extra_args()
    except HostError as exc:
        raise screen_ocr.ScreenError(str(exc)) from exc


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _json_from_output(blob: str) -> dict:
    start = blob.find("{")
    end = blob.rfind("}")
    if start < 0 or end < start:
        raise HostError("yt-dlp did not return video metadata")
    try:
        data = json.loads(blob[start : end + 1])
    except json.JSONDecodeError as exc:
        raise HostError("yt-dlp metadata was not valid JSON") from exc
    if not isinstance(data, dict):
        raise HostError("yt-dlp metadata was not an object")
    return data


def _interesting_error(stderr: str, stdout: str) -> str:
    lines = [line.strip() for line in f"{stderr}\n{stdout}".splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith("ERROR")]
    message = errors[-1] if errors else (lines[-1] if lines else "yt-dlp failed")
    return redact(message)


def _lang_key_matches(key: str, expected: str) -> bool:
    normalized = quality_gate.normalize_lang(key)
    return normalized == expected


def _original_auto_langs(automatic: dict) -> dict:
    """Drop YouTube translation tracks (their format URLs carry tlang=)."""
    kept = {}
    for lang, formats in automatic.items():
        formats = formats or []
        urls = [(item.get("url") or "") for item in formats if isinstance(item, dict)]
        if urls and all("tlang=" in url for url in urls):
            continue
        kept[lang] = formats
    return kept


def select_caption_language(info: dict, expected: str | None) -> tuple[str, str] | None:
    """Pick (language key, manual|auto) from a yt-dlp info dict.

    Only id, language, subtitles, and automatic_captions are read.
    """
    subs = info.get("subtitles") or {}
    auto = _original_auto_langs(info.get("automatic_captions") or {})
    if not auto:
        auto = info.get("automatic_captions") or {}
    expected_norm = quality_gate.normalize_lang(expected)

    def match(keys: list[str], want: str | None) -> str | None:
        if not want:
            return None
        for key in keys:
            if _lang_key_matches(key, want):
                return key
        return None

    if expected_norm:
        found = match(list(subs), expected_norm)
        if found:
            return found, "manual"
        found = match(list(auto), expected_norm)
        if found:
            return found, "auto"
        return None

    video_lang = quality_gate.normalize_lang(info.get("language"))
    for table, kind in ((subs, "manual"), (auto, "auto")):
        found = match(list(table), video_lang)
        if found:
            return found, kind
    if subs:
        if any(_lang_key_matches(key, "en") for key in subs):
            return next(key for key in subs if _lang_key_matches(key, "en")), "manual"
        return sorted(subs)[0], "manual"
    if auto:
        if any(_lang_key_matches(key, "en") for key in auto):
            return next(key for key in auto if _lang_key_matches(key, "en")), "auto"
        return sorted(auto)[0], "auto"
    return None


def _youtube_metadata(info: dict) -> dict[str, str]:
    metadata = {}
    for field, candidates in (("title", ("title",)), ("channel", ("channel", "uploader"))):
        for candidate in candidates:
            value = info.get(candidate)
            if isinstance(value, str) and (value := " ".join(value.split())):
                metadata[field] = value
                break
    published = info.get("upload_date")
    if isinstance(published, str) and re.fullmatch(r"[0-9]{8}", published):
        try:
            metadata["published"] = date.fromisoformat(published).isoformat()
        except ValueError:
            pass
    return metadata


def fetch_ytdlp_captions(
    url: str,
    video_id: str,
    expected_lang: str | None,
    base_cmd: list[str],
    accept_info=None,
    *,
    include_metadata: bool = False,
) -> dict:
    """Return caption text, or a dict with text None and an error string.

    accept_info(info) may allow a metadata id that is not video_id. YouTube
    leaves it unset. The X host uses it when the media id differs from the
    status id but the webpage URL is that status.
    """
    meta_cmd = [
        *base_cmd,
        "-J",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        "--no-progress",
        *_ytdlp_extra_args(),
        url,
    ]
    try:
        meta = _run(meta_cmd, timeout=90)
    except subprocess.TimeoutExpired:
        return {"text": None, "error": "yt-dlp metadata timed out"}
    except HostError as exc:
        return {"text": None, "error": redact(str(exc))}
    if meta.returncode != 0:
        return {"text": None, "error": _interesting_error(meta.stderr, meta.stdout)}
    try:
        info = _json_from_output(meta.stdout)
    except HostError as exc:
        return {"text": None, "error": redact(str(exc))}
    got_id = str(info.get("id") or "")
    if got_id and got_id != video_id and not (accept_info is not None and accept_info(info)):
        return {"text": None, "error": "yt-dlp returned a different video id than requested"}
    details = {"metadata": _youtube_metadata(info)} if include_metadata and got_id == video_id else {}
    picked = select_caption_language(info, expected_lang)
    if not picked:
        if expected_lang:
            return {
                **details,
                "text": None,
                "error": f"no captions in expected language {quality_gate.normalize_lang(expected_lang)}",
            }
        return {**details, "text": None, "error": "no captions in yt-dlp metadata"}
    lang_key, kind = picked
    with tempfile.TemporaryDirectory(prefix="tfv-ytdlp-") as tmp:
        out = Path(tmp)
        sub_cmd = [
            *base_cmd,
            "--skip-download",
            "--no-playlist",
            "--no-warnings",
            "--no-progress",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            lang_key,
            "--convert-subs",
            "vtt",
            *_ytdlp_extra_args(),
            "-o",
            str(out / "%(id)s"),
            url,
        ]
        try:
            downloaded = _run(sub_cmd, timeout=90)
        except subprocess.TimeoutExpired:
            return {**details, "text": None, "error": "yt-dlp subtitle download timed out"}
        if downloaded.returncode != 0:
            return {**details, "text": None, "error": _interesting_error(downloaded.stderr, downloaded.stdout)}
        files = sorted(out.glob("*.*"))
        caption_files = [
            path
            for path in files
            if path.suffix.lower() in {".vtt", ".srt", ".json", ".srv3", ".ttml"}
        ]
        caption_files.sort(key=lambda path: (path.suffix.lower() != ".vtt", path.name))
        if not caption_files:
            return {**details, "text": None, "error": "yt-dlp reported captions but wrote no subtitle file"}
        raw = caption_files[0].read_text(encoding="utf-8", errors="replace")
    return {
        **details,
        "text": raw,
        "language": quality_gate.normalize_lang(lang_key),
        "kind": kind,
        "error": None,
        "source": "yt-dlp",
        "media_duration": verify_rules._checked_clock(info.get("duration")),
    }


class _DeadlineSocket:
    def __init__(self, sock, deadline: float) -> None:
        self._sock = sock
        self._deadline = deadline

    def _arm(self) -> None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("caption request exceeded deadline")
        self._sock.settimeout(remaining)

    def recv_into(self, buffer, *args, **kwargs):
        self._arm()
        return self._sock.recv_into(buffer, *args, **kwargs)

    def recv(self, *args, **kwargs):
        self._arm()
        return self._sock.recv(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._sock, name)


def http_get(url: str, *, limit: int, timeout: int | float, accept: str) -> bytes:
    deadline = time.monotonic() + float(timeout)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Encoding": "identity",
        },
    )
    data = bytearray()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            is_http_response = isinstance(response, http.client.HTTPResponse)
            read_chunk = response.read1 if is_http_response else response.read
            raw = getattr(getattr(response, "fp", None), "raw", None)
            orig_sock = getattr(raw, "_sock", None)
            try:
                if orig_sock is not None:
                    raw._sock = _DeadlineSocket(orig_sock, deadline)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise HostError("caption request exceeded deadline")
                    chunk = read_chunk(min(16_384, limit + 1 - len(data)))
                    data.extend(chunk)
                    if len(data) > limit:
                        raise HostError("caption response too large")
                    if time.monotonic() > deadline:
                        raise HostError("caption request exceeded deadline")
                    if not chunk:
                        if is_http_response and not response.chunked and response.length not in (None, 0):
                            raise HostError("caption response was truncated before Content-Length")
                        break
            finally:
                if orig_sock is not None:
                    raw._sock = orig_sock
    except urllib.error.HTTPError as exc:
        raise HostError(f"HTTP {exc.code} for caption request") from exc
    except http.client.InvalidURL:
        raise HostError("caption request failed: invalid URL") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
        raise HostError(f"caption request failed: {redact(str(exc))}") from exc
    return bytes(data)


def _mirror_host(base: str) -> str:
    parsed = urllib.parse.urlparse(base)
    host = parsed.hostname or ""
    port = parsed.port
    if port is not None and ":" in host:
        host = f"[{host}]"
    return f"{host}:{port}" if port is not None else host


def _valid_mirror_base(base: str, *, require_https: bool = False) -> str | None:
    if not base or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in base):
        return None
    try:
        parsed = urllib.parse.urlparse(base)
        host = parsed.hostname
        schemes = {"https"} if require_https else {"http", "https"}
        if parsed.scheme not in schemes or parsed.query or parsed.fragment or not host:
            return None
        if require_https and (parsed.username is not None or parsed.password is not None or "@" in parsed.netloc):
            return None
        port = parsed.port
        hostport = parsed.netloc.rsplit("@", 1)[-1]
        expected_host = f"[{host}]" if ":" in host else host
        if port is None:
            if hostport.casefold() != expected_host.casefold():
                return None
        else:
            if ":" not in hostport:
                return None
            raw_host, raw_port = hostport.rsplit(":", 1)
            if raw_host.casefold() != expected_host.casefold():
                return None
            if not (raw_port.isascii() and raw_port.isdigit() and int(raw_port) == port):
                return None
        try:
            ipaddress.ip_address(host)
        except ValueError:
            label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
            if not re.fullmatch(rf"{label}(?:\.{label})*\.?", host):
                return None
        return _mirror_host(base)
    except ValueError:
        return None


def _public_invidious_bases(payload: bytes) -> list[str]:
    data = json.loads(payload.decode("utf-8", errors="replace"))
    bases: list[str] = []
    if not isinstance(data, list):
        return bases
    for item in data:
        if not isinstance(item, list) or len(item) < 2 or not isinstance(item[1], dict):
            continue
        meta = item[1]
        if meta.get("api") is not True:
            continue
        if meta.get("type") not in (None, "https"):
            continue
        uri = str(meta.get("uri") or "").rstrip("/")
        if _valid_mirror_base(uri, require_https=True):
            bases.append(uri)
        if len(bases) >= 3:
            break
    return bases


def invidious_bases() -> list[str]:
    raw = os.environ.get("INVIDIOUS_INSTANCE", "").strip()
    if raw.casefold() == "off":
        return []
    if raw:
        return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    try:
        payload = http_get(INSTANCE_LIST, limit=1_000_000, timeout=MIRROR_REQUEST_TIMEOUT, accept="application/json")
        return _public_invidious_bases(payload)
    except (HostError, ValueError, OSError, RecursionError) as exc:
        raise HostError(f"could not list public caption mirrors: {redact(str(exc))}") from exc


def _track_lang(track: dict) -> tuple[str | None, bool]:
    label = str(track.get("label") or "")
    code = track.get("languageCode") or track.get("language_code") or ""
    lang = quality_gate.normalize_lang(str(code)) if code else None
    if lang is None:
        name = re.sub(r"\s*\(auto-generated\)\s*", " ", label, flags=re.IGNORECASE)
        name = re.sub(r"\s*\([^)]*\)\s*", " ", name).strip().casefold()
        lang = _LABEL_LANG.get(name) or quality_gate.normalize_lang(name)
    auto = "auto-generated" in label.casefold()
    return lang, auto


def pick_mirror_track(tracks: list, expected: str | None) -> dict | None:
    parsed = []
    for track in tracks:
        if not isinstance(track, dict):
            continue
        lang, auto = _track_lang(track)
        url = str(track.get("url") or "")
        if not lang or not url:
            continue
        parsed.append({"lang": lang, "auto": auto, "url": url, "label": track.get("label") or lang})
    expected_norm = quality_gate.normalize_lang(expected)
    if expected_norm:
        pool = [item for item in parsed if item["lang"] == expected_norm]
    else:
        manuals = [item for item in parsed if not item["auto"]]
        pool = manuals or parsed
        english = [item for item in pool if item["lang"] == "en"]
        if english:
            pool = english
    if not pool:
        return None
    pool.sort(key=lambda item: item["auto"])
    return pool[0]


def safe_caption_url(base: str, url: str) -> str:
    if url.startswith("/"):
        return base.rstrip("/") + url
    parsed = urllib.parse.urlparse(url)
    base_host = urllib.parse.urlparse(base).netloc
    if parsed.scheme in {"http", "https"} and parsed.netloc == base_host:
        return url
    raise HostError("caption URL is not on the mirror host")


def fetch_mirror_captions(video_id: str, expected_lang: str | None) -> dict:
    deadline = time.monotonic() + MIRROR_TOTAL_BUDGET
    mirror_attempts: list[dict] = []
    raw = os.environ.get("INVIDIOUS_INSTANCE", "").strip()
    layer = "env" if raw else "public-list"

    class BudgetExhausted(HostError):
        pass

    def remaining_budget() -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BudgetExhausted("caption mirror budget exhausted")
        return remaining

    def get(url: str, *, limit: int, accept: str) -> bytes:
        return http_get(url, limit=limit, timeout=min(MIRROR_REQUEST_TIMEOUT, remaining_budget()), accept=accept)

    def record(ok: bool, detail: str) -> None:
        mirror_attempts.append({
            "source": "caption-mirror", "layer": layer, "ok": ok, "detail": redact(detail),
        })

    def failure(error: str) -> dict:
        return {"text": None, "error": error, "mirror_layer": layer, "mirror_attempts": mirror_attempts}

    if raw.casefold() == "off":
        return failure("caption mirror disabled (INVIDIOUS_INSTANCE=off)")
    if raw:
        bases = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
        if not bases:
            record(False, "INVIDIOUS_INSTANCE contains no caption mirror URLs")
    else:
        try:
            bases = _public_invidious_bases(get(INSTANCE_LIST, limit=1_000_000, accept="application/json"))
            if not bases:
                raise HostError("public caption mirror list contained no usable HTTPS API hosts")
        except BudgetExhausted as exc:
            record(False, str(exc))
            return failure(str(exc))
        except (HostError, ValueError, OSError, RecursionError) as exc:
            record(False, f"could not list public caption mirrors: {exc}")
            layer = "seed-fallback"
            bases = SEED_INVIDIOUS_INSTANCES
            log(f"public caption mirror discovery failed, trying seed-fallback at {_mirror_host(bases[0])} if budget remains")

    for base in bases:
        host = "invalid mirror URL"
        try:
            remaining_budget()
            mirror_host = _valid_mirror_base(base)
            if mirror_host is None:
                raise HostError("mirror URL must use http or https with a host")
            host = mirror_host
            listing = get(
                f"{base}/api/v1/captions/{video_id}",
                limit=1_000_000,
                accept="application/json",
            )
            data = json.loads(listing.decode("utf-8", errors="replace"))
            tracks = data.get("captions") if isinstance(data, dict) else None
            if not isinstance(tracks, list):
                raise HostError("mirror caption list was not usable")
            picked = pick_mirror_track(tracks, expected_lang)
            if not picked:
                want = quality_gate.normalize_lang(expected_lang) or "a default"
                raise HostError(f"no caption track for {want}")
            target = safe_caption_url(base, picked["url"])
            body = get(target, limit=2_000_000, accept="text/vtt, text/plain, */*")
            if time.monotonic() > deadline:
                raise BudgetExhausted("caption mirror budget exhausted")
            if not body:
                raise HostError("mirror caption track was empty")
            text = body.decode("utf-8", errors="replace")
            language = picked["lang"]
            kind = "auto" if picked["auto"] else "manual"
            record(True, f"{language} {kind} via {host} (layer={layer})")
            return {
                "text": text,
                "language": language,
                "kind": kind,
                "error": None,
                "source": "caption-mirror",
                "mirror_host": host,
                "mirror_layer": layer,
                "mirror_attempts": mirror_attempts,
            }
        except BudgetExhausted as exc:
            record(False, str(exc))
            break
        except (HostError, ValueError, OSError, RecursionError) as exc:
            record(False, f"{host}: {exc}")
            if time.monotonic() >= deadline:
                record(False, "caption mirror budget exhausted")
                break
    return failure("; ".join(attempt["detail"] for attempt in mirror_attempts))


def asr_plan(choice: str) -> tuple[str, str | None]:
    """Return (backend, block_reason). block_reason is set when ASR cannot run."""
    backend = choice.strip().casefold()
    if backend == "auto":
        backend = os.environ.get("ASR_BACKEND", "off").strip().casefold() or "off"
    if backend in {"", "off", "none"}:
        return "off", (
            "not finished: no usable captions and ASR is not configured. "
            "Set ASR_BACKEND=whisper (local whisper, optional WHISPER_UPGRADE_MODEL) "
            "or ASR_BACKEND=openai with OPENAI_API_KEY. No note was written."
        )
    if backend == "whisper":
        if shutil.which("whisper"):
            return "whisper", None
        probe = subprocess.run(
            [sys.executable, "-c", "import whisper"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if probe.returncode == 0:
            return "whisper", None
        return "whisper", (
            "not finished: ASR_BACKEND=whisper but the whisper CLI and the whisper "
            "module are not installed. No note was written."
        )
    if backend == "openai":
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            return "openai", (
                "not finished: ASR_BACKEND=openai but OPENAI_API_KEY is not set. "
                "No note was written."
            )
        return "openai", None
    return "off", f"not finished: unknown ASR_BACKEND {backend!r}. No note was written."


def _whisper_cmd(audio: Path, out_dir: Path, model: str, language: str | None) -> list[str]:
    binary = shutil.which("whisper")
    if binary:
        cmd = [binary]
    else:
        cmd = [sys.executable, "-m", "whisper"]
    cmd.extend(
        [
            str(audio),
            "--model",
            model,
            "--output_format",
            "txt",
            "--output_dir",
            str(out_dir),
        ]
    )
    lang = language or os.environ.get("WHISPER_LANGUAGE", "").strip()
    if lang:
        cmd.extend(["--language", quality_gate.normalize_lang(lang) or lang])
    return cmd


def transcribe_whisper(audio: Path, model: str, language: str | None, out_dir: Path) -> str:
    cmd = _whisper_cmd(audio, out_dir, model, language)
    try:
        result = _run(cmd, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise HostError("whisper timed out") from exc
    if result.returncode != 0:
        raise HostError(f"whisper failed: {_interesting_error(result.stderr, result.stdout)}")
    texts = sorted(out_dir.glob("*.txt"))
    if not texts:
        raise HostError("whisper wrote no transcript")
    return texts[0].read_text(encoding="utf-8", errors="replace")


def transcribe_openai(audio: Path, language: str | None) -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise HostError("OPENAI_API_KEY is not set")
    model = os.environ.get("OPENAI_TRANSCRIBE_MODEL", "whisper-1").strip() or "whisper-1"
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    boundary = "----tfv" + uuid.uuid4().hex
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )

    add_field("model", model)
    add_field("response_format", "json")
    if language:
        add_field("language", language)
    filename = audio.name.replace('"', "")
    header = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body = b"".join(parts) + header + audio.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        base + "/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise HostError(f"openai ASR HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise HostError(f"openai ASR request failed: {redact(str(exc.reason))}") from exc
    if not isinstance(payload, dict):
        raise HostError("openai ASR returned an unexpected payload")
    return str(payload.get("text") or "")


def download_audio(url: str, base_cmd: list[str], dest_dir: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        raise HostError("ffmpeg is not installed, so audio for ASR cannot be extracted")
    cmd = [
        *base_cmd,
        "-f",
        "ba/b",
        "-x",
        "--audio-format",
        "mp3",
        "--no-playlist",
        "--no-warnings",
        "--no-progress",
        *_ytdlp_extra_args(),
        "-o",
        str(dest_dir / "%(id)s.%(ext)s"),
        url,
    ]
    try:
        result = _run(cmd, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise HostError("audio download timed out") from exc
    if result.returncode != 0:
        raise HostError(f"audio download failed: {_interesting_error(result.stderr, result.stdout)}")
    files = sorted(dest_dir.glob("*.mp3")) or sorted(dest_dir.glob("*.*"))
    audio = [path for path in files if path.suffix.lower() in {".mp3", ".m4a", ".wav", ".opus", ".webm"}]
    if not audio:
        raise HostError("audio download produced no audio file")
    return audio[0]


_EXCERPT_LIMIT = 360


def _cut_words(text: str, limit: int) -> str:
    cut = text[:limit].rstrip()
    if " " in cut:
        trimmed = cut.rsplit(" ", 1)[0]
        if len(trimmed) >= verify_note.QUOTE_WINDOW:
            return trimmed
    return cut


def transcript_excerpt(text: str, limit: int = _EXCERPT_LIMIT) -> tuple[str, list[str]]:
    """Return a collapsed quote and the same words split on the transcript's lines.

    The collapsed line is what frontmatter stores. The lines are what the body
    quotes, so a short caption stays readable. Both are copied, not rewritten.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        collapsed = re.sub(r"\s+", " ", text).strip()
        return collapsed, ([collapsed] if collapsed else [])
    chosen: list[str] = []
    total = 0
    for line in lines:
        addition = len(line) if not chosen else len(line) + 1
        if chosen and total + addition > limit:
            break
        if not chosen and len(line) > limit:
            chosen.append(_cut_words(line, limit))
            break
        chosen.append(line)
        total += addition
    return " ".join(chosen), chosen


def transcript_window(text: str, limit: int = _EXCERPT_LIMIT) -> str:
    """A single collapsed line copied from the transcript, long enough to quote."""
    collapsed, _lines = transcript_excerpt(text, limit)
    return collapsed


def _failure_status_name(reasons: list[str]) -> str:
    if reasons and all(
        reason.startswith("empty or unusable") or reason.startswith("transcript too short")
        for reason in reasons
    ):
        return "not_finished"
    return "quality_gate_failed"


def _next_step(status_name: str, acquisition: str, upgrade_attempted: bool) -> str:
    if status_name == "finished":
        return "none"
    if acquisition == "asr" and not upgrade_attempted:
        return "retry-stronger-asr"
    if acquisition == "none":
        return "configure-asr-or-retry-captions"
    return "stop"


def render_scaffold(
    *,
    job_id: str,
    video_id: str,
    source: str,
    acquisition: str,
    caption_language: str | None,
    caption_kind: str | None,
    transcript_cite: str,
    caption_trust: str | None = None,
    selection_end: str | None = None,
    metadata: dict[str, str] | None = None,
    reading_level: str | None = None,
) -> str:
    """Blank Obsidian scaffold with known YouTube metadata.

    The body has empty headings and fill instructions. It does not analyze
    the transcript. A finished note.md is not this file.
    """
    return knowledge_note.render_scaffold(
        job_id=job_id,
        video_id=video_id,
        source=source,
        acquisition=acquisition,
        transcript_cite=transcript_cite,
        caption_language=caption_language,
        caption_kind=caption_kind,
        caption_trust=caption_trust,
        skill_version=skill_version(),
        selection_end=selection_end,
        metadata=metadata,
        reading_level=reading_level,
    )


def finalize_job(
    *,
    text: str,
    video_id: str,
    source: str,
    out_dir: Path,
    expected_lang: str | None,
    acquisition: str,
    caption_language: str | None = None,
    caption_kind: str | None = None,
    confidence: float | None = None,
    extra: dict | None = None,
    verify: bool = True,
    upgrade_attempted: bool = False,
    platform: str = "youtube",
    screen_download: list[str] | None = None,
    media_duration: float | None = None,
    metadata: dict[str, str] | None = None,
    reading_level: str | None = None,
) -> dict:
    job_id = job_id_for(video_id, platform)
    job_dir = out_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    gate_lang = quality_gate.normalize_lang(expected_lang) or quality_gate.normalize_lang(caption_language)
    with tempfile.TemporaryDirectory(prefix=".tfv-fetch-", dir=job_dir) as temp_dir:
        candidate = Path(temp_dir) / "transcript.txt"
        candidate.write_text(text, encoding="utf-8")
        result = quality_gate.assess(
            candidate.read_text(encoding="utf-8"),
            expected_lang=gate_lang,
            confidence=confidence,
        )
    trust = quality_gate.caption_trust(caption_kind, caption_language, expected_lang)
    transcript_path = job_dir / "transcript.txt"
    segments_path = job_dir / "segments.json"
    chunks_dir = job_dir / "chunks"
    base = {
        "schema_version": 1,
        "skill_version": skill_version(),
        "job_id": job_id,
        "source_url": source,
        "finished": False,
        "acquisition": acquisition,
        "caption_language": caption_language,
        "caption_kind": caption_kind,
        "caption_trust": trust,
        "expected_lang": quality_gate.normalize_lang(expected_lang),
        "gate_lang": gate_lang,
        "transcript": None,
        "segments": None,
        "chunks": None,
        "chunk_count": None,
        "duration_seconds": None,
        "note": None,
        "scaffold": None,
        "gate": result.to_dict(),
        "verifier": None,
    }
    if extra:
        base.update(extra)
    if platform == "youtube":
        previous = verify_note.read_job_status(job_dir)
        metadata = {
            key: previous[key] for key in ("title", "channel", "published")
            if isinstance(previous.get(key), str) and previous[key]
        } | (metadata or {})
        base.update(metadata)
    if not result.passed:
        status_name = _failure_status_name(result.reasons)
        base.update(
            {
                "status": status_name,
                "reason": "; ".join(result.reasons),
                "next_step": _next_step(status_name, acquisition, upgrade_attempted),
                "exit_code": 2,
            }
        )
        _record_failed_attempt(job_dir, base, platform=platform, reading_level=reading_level)
        return base

    segments = quality_gate.prepare_segments(text)
    transcript_body = quality_gate.format_transcript(segments) or result.text
    has_clock = any(
        cue.start is not None or verify_rules.parse_stamp(cue.text)[0] is not None
        for cue in segments
    )
    groups = quality_gate.chunk_segments(segments)
    with tempfile.TemporaryDirectory(prefix=".tfv-attempt-", dir=job_dir) as temp_dir:
        staged = Path(temp_dir)
        staged_transcript = staged / "transcript.txt"
        staged_segments = staged / "segments.json"
        staged_chunks = staged / "chunks"
        staged_transcript.write_text(transcript_body.rstrip() + "\n", encoding="utf-8")
        staged_segments.write_text(
            json.dumps([segment.to_dict() for segment in segments], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        staged_chunks.mkdir()
        for index, group in enumerate(groups, start=1):
            chunk_body = quality_gate.format_transcript(group)
            (staged_chunks / f"{index:02d}.txt").write_text(chunk_body.rstrip() + "\n", encoding="utf-8")
        cite = cite_path(transcript_path)
        # ``verify`` remains accepted for existing callers. The scaffold is
        # not a deposit, so the host does not run verify_note on it.
        del verify
        duration = quality_gate.duration_seconds(segments)
        selection_end = verify_rules.selection_endpoint(segments, duration)
        scaffold = partial(
            render_scaffold,
            job_id=job_id,
            video_id=video_id,
            source=source,
            acquisition=acquisition,
            caption_language=caption_language or gate_lang,
            caption_kind=caption_kind,
            caption_trust=trust,
            transcript_cite=cite if Path(cite).is_absolute() else "transcript.txt",
            metadata=metadata,
            selection_end=(quality_gate.format_stamp(selection_end)[1:-1]
                           if selection_end is not None else None),
        )
        base.update(
            {
                "status": "transcript_ready",
                "finished": False,
                "repair_rounds": 0,
                "edit_rounds": 0,
                "note_digest": None,
                "locked": False,
                "reason": (
                    "transcript passed the quality gate; "
                    "note.scaffold.md is a blank form, not a finished knowledge note"
                    if has_clock else verify_rules.MISSING_TIMESTAMPS
                ),
                "next_step": "write-note" if has_clock else "retry-timed-transcript",
                "transcript": cite,
                "segments": cite_path(segments_path),
                "chunks": cite_path(chunks_dir),
                "chunk_count": len(groups),
                "duration_seconds": duration,
                "scaffold": cite_path(job_dir / "note.scaffold.md"),
                "verifier": None,
                "exit_code": 0,
            }
        )
        if screen_download is None:
            _publish_transcript(job_dir, staged, base, scaffold, platform=platform, reading_level=reading_level)
            return base
        request = verify_rules.screen_mode() if "TFV_SCREEN_MODE" in os.environ else "auto"
        if request == "off":
            base["screen_ocr"] = {"requested_mode": "off", "mode": "off", "state": "disabled", "result": "disabled"}
            _publish_transcript(job_dir, staged, base, scaffold, platform=platform, reading_level=reading_level)
            return base
        pending = {
            **base, "status": verify_note.SCREEN_PENDING, "next_step": "wait-for-screen",
            "reason": verify_note.SCREEN_PENDING_MESSAGE,
            "screen_ocr": {"requested_mode": request, "mode": "off", "state": "pending", "attempt": staged.name},
        }
        _publish_transcript(job_dir, staged, pending, scaffold, platform=platform, reading_level=reading_level)
        base.update({key: pending[key] for key in ("note", "delivery", "note_stale")})
        if platform == "youtube":
            base.update(reading_level=pending["reading_level"], reading_level_source=pending["reading_level_source"])
        base["screen_ocr"] = _screen_result(staged, request, source, screen_download, media_duration)
        return _publish_screen(job_dir, staged, base)


def _budget_exceeded_hint(estimated: float, safe_budget: float) -> str:
    return (
        f"预估 {estimated:.1f} 秒超过按片长算的预算 {safe_budget:.1f} 秒，"
        "只用了字幕；需要画面可设 TFV_SCREEN_MODE=slides"
    )


def _live_overrun_hint(estimated_remaining: float, remaining_budget: float) -> str:
    return (
        f"预估剩余 {estimated_remaining:.1f} 秒超过剩余预算 {remaining_budget:.1f} 秒，"
        "只用了字幕；需要画面可设 TFV_SCREEN_MODE=slides"
    )


OVERRUN_HINT = "扫描耗时超过按片长算的预算，只用了字幕；需要画面可设 TFV_SCREEN_MODE=slides"


def _screen_fallback(screen: dict, result: str, reason: str = "") -> dict:
    fallback = {**screen, "state": "fallback", "mode": "off", "result": result}
    if reason:
        fallback["reason"] = redact(re.sub(r"\w+://\S+", "<URL>", reason))
    if result == "not_found":
        fallback["hint"] = "No slides found. If the video has slides, rerun with TFV_SCREEN_MODE=slides."
    elif result == "missing_dependencies":
        fallback["hint"] = "Using subtitles only. For screen OCR, install rapidocr and onnxruntime in this Python and put ffmpeg and yt-dlp on PATH."
    return fallback


def _screen_result(staged: Path, request: str, source: str, command: list[str], duration: float | None) -> dict:
    screen = {"requested_mode": request}
    try:
        mode = request
        if request == "auto":
            sample = screen_ocr.sample_slides(staged, source, command, _screen_download_options)
            sample = dict(sample)
            if "calibration_reason" in sample:
                sample["calibration_reason"] = screen_ocr._sanitize_calibration_reason(
                    str(sample["calibration_reason"]),
                    "timeout" if sample.get("calibration_status") == "timeout_fallback" else "fallback",
                )
            screen["sample"] = sample
            if sample["result"] != "slides_detected":
                return _screen_fallback(screen, sample["result"], sample.get("reason", ""))
            if (
                not isinstance(duration, (int, float))
                or isinstance(duration, bool)
                or not math.isfinite(duration)
                or duration <= 0
            ):
                sampled_duration = sample.get("duration")
                duration = (
                    sampled_duration
                    if isinstance(sampled_duration, (int, float))
                    and not isinstance(sampled_duration, bool)
                    and math.isfinite(sampled_duration)
                    and sampled_duration > 0
                    else None
                )
            budget = screen_ocr.slide_full_budget(duration)
            safe_budget = budget * screen_ocr.AUTO_BUDGET_HEADROOM
            estimated = None
            calibration = sample.get("calibration")
            calibrated = calibration.get("estimated_total_seconds") if isinstance(calibration, dict) else None
            latency = sample.get("mean_frame_ocr_seconds")
            if (
                isinstance(calibrated, (int, float))
                and not isinstance(calibrated, bool)
                and math.isfinite(calibrated)
                and calibrated > 0
            ):
                estimated = float(calibrated)
                if duration is not None:
                    intervals = calibration.get("intervals")
                    download_seconds = calibration.get("download_seconds")
                    extract_per_interval = calibration.get("extract_seconds_per_interval")
                    group_per_frame = calibration.get("group_seconds_per_frame")
                    read_per_frame = calibration.get("read_frame_seconds")
                    effective_intervals = max(1, math.ceil(duration / screen_ocr.SLIDE_INTERVAL))
                    if all(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(value)
                        and value >= 0
                        for value in (intervals, download_seconds, extract_per_interval, group_per_frame, read_per_frame)
                    ) and effective_intervals != intervals:
                        seconds_per_interval = float(extract_per_interval) + float(group_per_frame) + float(read_per_frame)
                        adjusted = float(download_seconds) + seconds_per_interval * effective_intervals
                        estimated = adjusted if math.isfinite(adjusted) and adjusted > 0 else None
            if estimated is None:
                if sample.get("calibration_status") == "calibrated":
                    sample["calibration_status"] = "fallback"
                    sample.setdefault("calibration_reason", "calibration estimate unavailable")
                if (
                    duration is not None
                    and isinstance(latency, (int, float))
                    and not isinstance(latency, bool)
                    and math.isfinite(latency)
                    and latency > 0
                ):
                    frames = max(1, math.ceil(duration / screen_ocr.SLIDE_INTERVAL))
                    sample_extract = sample.get("mean_sample_extract_seconds")
                    if (
                        not isinstance(sample_extract, (int, float))
                        or isinstance(sample_extract, bool)
                        or not math.isfinite(sample_extract)
                        or sample_extract < 0
                    ):
                        sample_extract = 0.0
                    estimated = (latency * screen_ocr.SLIDE_OCR_PASSES + sample_extract) * frames
            sample["estimated_seconds"] = round(estimated, 3) if estimated is not None and math.isfinite(estimated) else None
            if sample.get("calibration_status") in ("timeout_fallback", "fallback"):
                est_value = sample["estimated_seconds"]
                est_text = f"{est_value:.1f}s" if est_value is not None else "unknown"
                log(f"screen OCR calibration {sample['calibration_status']} (estimated {est_text}): {sample.get('calibration_reason', '')}")
            if estimated is not None and estimated > safe_budget:
                screen["timeout_seconds"] = budget
                screen["safe_budget_seconds"] = round(safe_budget, 3)
                if math.isfinite(estimated):
                    screen["estimated_seconds"] = round(estimated, 3)
                reason = (
                    f"Estimated full-scan screen time ({estimated:.1f}s) "
                    f"exceeds safe full-scan budget ({safe_budget:.1f}s)."
                )
                fallback = _screen_fallback(screen, "timeout", reason)
                fallback["hint"] = _budget_exceeded_hint(estimated, safe_budget)
                return fallback
            mode = "slides"
        if request == "auto":
            result = screen_ocr.extract(
                staged, mode, source, command, duration, _screen_download_options, True,
            )
        else:
            result = screen_ocr.extract(
                staged, mode, source, command, duration, _screen_download_options,
            )
        if result.get("state") == "ready":
            return {**screen, **result, "result": "slides_detected" if mode == "slides" else "nameplate_ready"}
        screen.update({key: result[key] for key in ("versions", "elapsed_seconds", "timeout_seconds") if key in result})
        fallback = _screen_fallback(screen, result.get("failure", "error"), result.get("reason", ""))
        if result.get("overrun_aborted"):
            rem_est = result.get("estimated_remaining_seconds")
            rem_budget = result.get("remaining_budget_seconds")
            if (
                isinstance(rem_est, (int, float))
                and not isinstance(rem_est, bool)
                and isinstance(rem_budget, (int, float))
                and not isinstance(rem_budget, bool)
                and math.isfinite(rem_est)
                and math.isfinite(rem_budget)
            ):
                fallback["hint"] = _live_overrun_hint(float(rem_est), float(rem_budget))
            else:
                fallback["hint"] = OVERRUN_HINT
        return fallback
    except Exception as exc:
        return _screen_fallback(screen, screen_ocr.failure_result(exc), str(exc))


def _set_reading_level(payload: dict, platform: str, requested: str | None, previous: dict) -> str | None:
    if platform == "youtube":
        level, source = user_prefs.resolve_reading_level(requested, previous)
        payload.update(reading_level=level, reading_level_source=source)
        return level
    payload.pop("reading_level", None)
    payload.pop("reading_level_source", None)
    return None


def _publish_transcript(
    job: Path, staged: Path, payload: dict, scaffold: partial, *, platform: str, reading_level: str | None,
) -> None:
    """Install the staged transcript as a unit and keep old writing traceable."""
    backup = staged / "previous"
    backup.mkdir()
    with verify_note.job_lock(job):
        level = _set_reading_level(payload, platform, reading_level, verify_note.read_job_status(job))
        (staged / "note.scaffold.md").write_text(scaffold(reading_level=level), encoding="utf-8", newline="\n")
        replacing = (job / "transcript.txt").is_file()
        old_notes = (job / "note.md", job / "delivery.md")
        payload["note_stale"] = any(path.is_file() for path in old_notes)
        archived, installed = [], []
        try:
            if replacing:
                for path in (*old_notes, job / "selection.md", job / "review.md"):
                    target = verify_note.archive_file(path)
                    if target is not None:
                        archived.append((target, path))
            chunks = job / "chunks"
            if chunks.is_dir() and any(chunks.glob("*.notes.md")):
                saved = verify_note.archive_file(chunks)
                if saved is not None:
                    archived.append((saved, chunks))
            optional = (verify_rules.SCREEN_FILE, verify_rules.SCREEN_FRAMES)
            for name in ("transcript.txt", "segments.json", "chunks", "note.scaffold.md", *optional):
                target = job / name
                if target.exists():
                    saved = backup / name
                    target.replace(saved)
                    archived.append((saved, target))
                source = staged / name
                if name not in optional:
                    source.replace(target)
                    installed.append((target, source))
            for key, path in zip(("note", "delivery"), old_notes):
                payload[key] = cite_path(path) if path.is_file() else None
            verify_note.write_job_status(job, {key: value for key, value in payload.items() if key != "exit_code"})
        except OSError:
            for target, source in reversed(installed):
                target.replace(source)
            for saved, target in reversed(archived):
                saved.replace(target)
            raise


def _publish_screen(job: Path, staged: Path, payload: dict) -> dict:
    """Finish the same acquisition that installed the transcript."""
    with verify_note.job_lock(job):
        current = verify_note.read_job_status(job)
        pending = current.get("screen_ocr")
        if (current.get("status") != verify_note.SCREEN_PENDING
                or not isinstance(pending, dict) or pending.get("attempt") != staged.name):
            return {**current, "exit_code": 2, "reason": "another acquisition superseded this screen attempt"}
        if "last_attempt" in current:
            payload["last_attempt"] = current["last_attempt"]
        installed = []
        screen = payload["screen_ocr"]
        if screen["state"] == "ready":
            try:
                for name in (verify_rules.SCREEN_FILE, verify_rules.SCREEN_FRAMES):
                    target = job / name
                    (staged / name).replace(target)
                    installed.append(target)
            except OSError as exc:
                for target in installed:
                    target.replace(staged / target.name)
                installed.clear()
                context = {key: screen[key] for key in ("requested_mode", "sample") if key in screen}
                payload["screen_ocr"] = _screen_fallback(context, "error", str(exc))
        try:
            verify_note.write_job_status(job, {key: value for key, value in payload.items() if key != "exit_code"})
        except OSError:
            for target in installed:
                target.replace(staged / target.name)
            raise
    return payload


def _record_failed_attempt(job: Path, payload: dict, *, platform: str, reading_level: str | None) -> None:
    with verify_note.job_lock(job):
        previous = verify_note.read_job_status(job)
        _set_reading_level(payload, platform, reading_level, previous)
        attempt = {key: value for key, value in payload.items() if key != "exit_code"}
        if previous and (job / "transcript.txt").is_file():
            verify_note.write_job_status(job, {**previous, "last_attempt": attempt})
        else:
            state = {**previous, **attempt}
            note = job / "note.md"
            if note.is_file():
                state["note"] = cite_path(note)
            verify_note.write_job_status(job, state)


def write_refusal(
    *,
    video_id: str,
    source: str,
    out_dir: Path,
    reason: str,
    next_step: str,
    extra: dict | None = None,
    platform: str = "youtube",
    reading_level: str | None = None,
) -> dict:
    job_id = job_id_for(video_id, platform)
    job_dir = out_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "skill_version": skill_version(),
        "job_id": job_id,
        "source_url": source,
        "status": "not_finished",
        "finished": False,
        "reason": reason,
        "next_step": next_step,
        "acquisition": "none",
        "caption_language": None,
        "caption_kind": None,
        "caption_trust": None,
        "transcript": None,
        "segments": None,
        "chunks": None,
        "chunk_count": None,
        "duration_seconds": None,
        "note": None,
        "scaffold": None,
        "gate": None,
        "verifier": None,
    }
    if extra:
        payload.update(extra)
    _record_failed_attempt(job_dir, payload, platform=platform, reading_level=reading_level)
    payload["exit_code"] = 2
    return payload


def transcribe_file(audio: Path, backend: str, language: str | None) -> tuple[str, str, bool]:
    """Return (text, model description, upgrade_attempted) for one audio file."""
    if backend == "openai":
        text = transcribe_openai(audio, language)
        return text, os.environ.get("OPENAI_TRANSCRIBE_MODEL", "whisper-1"), False
    model = os.environ.get("WHISPER_MODEL", "small").strip() or "small"
    upgrade = os.environ.get("WHISPER_UPGRADE_MODEL", "").strip()
    work = audio.parent
    first_dir = work / "asr-first"
    first_dir.mkdir(parents=True, exist_ok=True)
    text = transcribe_whisper(audio, model, language, first_dir)
    gate_lang = quality_gate.normalize_lang(language)
    first = quality_gate.assess(text, expected_lang=gate_lang)
    if first.passed or not upgrade or upgrade == model:
        return text, model, False
    second_dir = work / "asr-second"
    second_dir.mkdir(parents=True, exist_ok=True)
    second = transcribe_whisper(audio, upgrade, language, second_dir)
    return second, upgrade, True


def _run_asr(url: str, base_cmd: list[str], backend: str, language: str | None) -> tuple[str, str, bool]:
    """Return (text, model_description, upgrade_attempted)."""
    with tempfile.TemporaryDirectory(prefix="tfv-asr-") as tmp:
        audio = download_audio(url, base_cmd, Path(tmp))
        return transcribe_file(audio, backend, language)


def run_host(
    *,
    video_id: str,
    source: str,
    out_dir: Path,
    expected_lang: str | None,
    asr_choice: str,
    verify: bool,
    settle_text: str | None = None,
    language: str | None = None,
    reading_level: str | None = None,
    save_pref: bool = False,
) -> dict:
    if save_pref:
        if language is None or reading_level is None:
            raise HostError("--save-pref requires both --language and --reading-level")
        reading_level, _ = user_prefs.resolve_reading_level(reading_level, {})
        user_prefs.save_prefs(language, reading_level)
    if settle_text is not None:
        return finalize_job(
            text=settle_text,
            video_id=video_id,
            source=source,
            out_dir=out_dir,
            expected_lang=expected_lang,
            acquisition="settle-transcript",
            verify=verify,
            reading_level=reading_level,
        )

    attempts: list[dict] = []
    caption = None
    metadata: dict[str, str] = {}
    base_cmd = ytdlp_base()
    screen_download = base_cmd or []
    if base_cmd is None:
        attempts.append({"source": "yt-dlp", "ok": False, "detail": "yt-dlp is not installed"})
    else:
        log(f"fetching captions with yt-dlp for youtube_{video_id}")
        fetched = fetch_ytdlp_captions(source, video_id, expected_lang, base_cmd, include_metadata=True)
        metadata = fetched.get("metadata", {})
        if fetched.get("text"):
            attempts.append(
                {
                    "source": "yt-dlp",
                    "ok": True,
                    "detail": f"{fetched.get('language')} {fetched.get('kind')}",
                }
            )
            caption = fetched
        else:
            attempts.append({"source": "yt-dlp", "ok": False, "detail": fetched.get("error") or "no captions"})

    if caption is None and os.environ.get("INVIDIOUS_INSTANCE", "").strip().casefold() != "off":
        log("yt-dlp did not yield captions. Trying caption mirrors.")
        mirrored = fetch_mirror_captions(video_id, expected_lang)
        mirror_attempts = mirrored.get("mirror_attempts")
        if mirror_attempts:
            attempts.extend(mirror_attempts)
        elif mirrored.get("text"):
            attempts.append(
                {
                    "source": "caption-mirror",
                    "ok": True,
                    "detail": f"{mirrored.get('language')} {mirrored.get('kind')} via {mirrored.get('mirror_host')}",
                }
            )
        else:
            attempts.append({"source": "caption-mirror", "ok": False, "detail": mirrored.get("error") or "no captions"})
        if mirrored.get("text"):
            caption = mirrored

    if caption and caption.get("text"):
        log(f"captions acquired via {caption.get('source')} ({caption.get('language')} {caption.get('kind')})")
        return finalize_job(
            text=caption["text"],
            video_id=video_id,
            source=source,
            out_dir=out_dir,
            expected_lang=expected_lang,
            acquisition=str(caption.get("source") or "captions"),
            caption_language=caption.get("language"),
            caption_kind=caption.get("kind"),
            verify=verify,
            reading_level=reading_level,
            extra={
                "attempts": attempts,
                "mirror_host": caption.get("mirror_host"),
                "mirror_layer": caption.get("mirror_layer"),
            },
            screen_download=screen_download,
            media_duration=caption.get("media_duration"),
            metadata=metadata,
        )

    backend, block = asr_plan(asr_choice)
    if block:
        if backend == "off" and "ASR is not configured" in block:
            block = (
                "The YouTube job is not finished because no usable captions were found and ASR is not configured. "
                "Retry with a working caption mirror in INVIDIOUS_INSTANCE, or set ASR_BACKEND=whisper "
                "for local transcription or ASR_BACKEND=openai with OPENAI_API_KEY. No note was written."
            )
        detail = "; ".join(
            f"{item['source']}: {item['detail']}" for item in attempts if not item["ok"]
        )
        reason = block if not detail else f"{block} Caption attempts: {detail}"
        log(reason)
        return write_refusal(
            video_id=video_id,
            source=source,
            out_dir=out_dir,
            reading_level=reading_level,
            reason=reason,
            next_step="configure-asr-or-retry-captions",
            extra={**metadata, "attempts": attempts, "asr_backend": backend},
        )
    if base_cmd is None:
        return write_refusal(
            video_id=video_id,
            source=source,
            out_dir=out_dir,
            reading_level=reading_level,
            reason="not finished: ASR needs yt-dlp to download audio, and yt-dlp is not installed.",
            next_step="configure-asr-or-retry-captions",
            extra={**metadata, "attempts": attempts, "asr_backend": backend},
        )
    log(f"no captions; running ASR backend {backend}")
    try:
        text, model, upgraded = _run_asr(source, base_cmd, backend, expected_lang)
    except HostError as exc:
        reason = f"not finished: ASR failed: {redact(str(exc))}"
        log(reason)
        return write_refusal(
            video_id=video_id,
            source=source,
            out_dir=out_dir,
            reading_level=reading_level,
            reason=reason,
            next_step="retry-stronger-asr",
            extra={**metadata, "attempts": attempts, "asr_backend": backend},
        )
    return finalize_job(
        text=text,
        video_id=video_id,
        source=source,
        out_dir=out_dir,
        expected_lang=expected_lang,
        acquisition="asr",
        caption_language=quality_gate.normalize_lang(expected_lang),
        caption_kind=None,
        verify=verify,
        reading_level=reading_level,
        upgrade_attempted=upgraded,
        extra={"attempts": attempts, "asr_backend": backend, "asr_model": model},
        metadata=metadata,
        screen_download=screen_download,
    )


def _emit(payload: dict, as_json: bool) -> int:
    # ``exit_code`` 0 is a real success. A scaffold job is not ``finished``,
    # so a truthiness check would turn that 0 into a refusal.
    code = payload.get("exit_code")
    if code is None:
        code = 0 if payload.get("finished") else 2
    code = int(code)
    public = {key: value for key, value in payload.items() if key != "exit_code"}
    if as_json:
        json.dump(public, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(public.get("status") or ("finished" if public.get("finished") else "not_finished"))
        if public.get("reason"):
            print(public["reason"], file=sys.stderr)
        if public.get("transcript"):
            print(f"transcript: {public['transcript']}")
        if public.get("segments"):
            print(f"segments: {public['segments']}")
        if public.get("chunks"):
            print(f"chunks: {public['chunks']}")
        if public.get("scaffold"):
            print(f"scaffold: {public['scaffold']}")
        if public.get("note"):
            print(f"note: {public['note']}")
        if hint := public.get("screen_ocr", {}).get("hint"):
            print(hint, file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a public YouTube transcript. When the quality gate passes, "
            "write note.scaffold.md. Do not write a finished knowledge note."
        )
    )
    parser.add_argument("url", nargs="?", help="YouTube URL or 11-character video id")
    parser.add_argument(
        "--settle-transcript",
        type=Path,
        help="Offline path: gate this text file instead of fetching. Not a watch.",
    )
    parser.add_argument("--video-id", help="Required with --settle-transcript")
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument("--expected-lang", default=None)
    parser.add_argument("--language", choices=user_prefs.VALID_LANGUAGES, default=None)
    parser.add_argument("--reading-level", choices=user_prefs.VALID_READING_LEVELS, default=None)
    parser.add_argument("--save-pref", action="store_true")
    parser.add_argument("--show-pref", action="store_true")
    parser.add_argument("--asr", choices=["auto", "off", "whisper", "openai"], default="auto")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Accepted for compatibility. The host writes a scaffold, not a finished note, "
            "so this flag does not run verify_note."
        ),
    )
    args = parser.parse_args(argv)
    if args.save_pref and (args.language is None or args.reading_level is None):
        parser.error("--save-pref requires both --language and --reading-level")
    if args.show_pref:
        saved = user_prefs.load_prefs()
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(saved, ensure_ascii=False) if args.json or saved else "No saved preferences.")
        return 0
    try:
        if args.settle_transcript:
            if not args.video_id:
                parser.error("--settle-transcript requires --video-id")
            if not args.settle_transcript.is_file():
                raise HostError(f"settle transcript does not exist: {args.settle_transcript}")
            video_id = args.video_id
            source = f"settle-transcript:{video_id}"
            text = args.settle_transcript.read_text(encoding="utf-8", errors="replace")
            payload = run_host(
                video_id=video_id,
                source=source,
                out_dir=args.out,
                expected_lang=args.expected_lang,
                asr_choice="off",
                verify=args.verify,
                language=args.language,
                reading_level=args.reading_level,
                save_pref=args.save_pref,
                settle_text=text,
            )
        else:
            if not args.url:
                parser.error("pass a YouTube URL or video id")
            video_id, source = parse_youtube_ref(args.url)
            payload = run_host(
                video_id=video_id,
                source=source,
                out_dir=args.out,
                expected_lang=args.expected_lang,
                asr_choice=args.asr,
                verify=args.verify,
                language=args.language,
                reading_level=args.reading_level,
                save_pref=args.save_pref,
            )
    except (HostError, OSError, ValueError) as exc:
        message = redact(str(exc))
        if args.json:
            json.dump({"status": "not_finished", "finished": False, "reason": message}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(message, file=sys.stderr)
        return 2
    return _emit(payload, args.json)


if __name__ == "__main__":
    exit_code = main()
    if screen_ocr.native_ocr_running():
        # The job is already published. A timed-out native call can crash
        # interpreter teardown, so exit directly once the CLI output is sent.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)
    sys.exit(exit_code)
