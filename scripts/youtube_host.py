#!/usr/bin/env python3
"""Minimal YouTube host: captions first, optional ASR, otherwise not finished.

A finished job writes note.md, an Obsidian-friendly Markdown file with YAML
frontmatter. The note cites the transcript path and quotes a real window of
that file. The platform title and description are not stored. status.json is
a machine stub. On failure the job directory keeps that stub and no note.

Exit 0 finished. Exit 2 not finished or quality-gate failure. Exit 1 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quality_gate  # noqa: E402
import verify_note  # noqa: E402

USER_AGENT = "Mozilla/5.0 (compatible; transcript-first-video/1.0)"
INSTANCE_LIST = "https://api.invidious.io/instances.json?sort_by=health"
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


class HostError(Exception):
    pass


def redact(text: str, limit: int = 700) -> str:
    cleaned = _SECRET.sub(r"\1\2<redacted>", text or "")
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


def clear_deposit(job_dir: Path) -> None:
    for name in ("transcript.txt", "note.md"):
        target = job_dir / name
        if target.exists():
            target.unlink()


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


def fetch_ytdlp_captions(
    url: str,
    video_id: str,
    expected_lang: str | None,
    base_cmd: list[str],
    accept_info=None,
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
    picked = select_caption_language(info, expected_lang)
    if not picked:
        if expected_lang:
            return {
                "text": None,
                "error": f"no captions in expected language {quality_gate.normalize_lang(expected_lang)}",
            }
        return {"text": None, "error": "no captions in yt-dlp metadata"}
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
            return {"text": None, "error": "yt-dlp subtitle download timed out"}
        if downloaded.returncode != 0:
            return {"text": None, "error": _interesting_error(downloaded.stderr, downloaded.stdout)}
        files = sorted(out.glob("*.*"))
        caption_files = [
            path
            for path in files
            if path.suffix.lower() in {".vtt", ".srt", ".json", ".srv3", ".ttml"}
        ]
        caption_files.sort(key=lambda path: (path.suffix.lower() != ".vtt", path.name))
        if not caption_files:
            return {"text": None, "error": "yt-dlp reported captions but wrote no subtitle file"}
        raw = caption_files[0].read_text(encoding="utf-8", errors="replace")
    return {
        "text": raw,
        "language": quality_gate.normalize_lang(lang_key),
        "kind": kind,
        "error": None,
        "source": "yt-dlp",
    }


def http_get(url: str, *, limit: int, timeout: int, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        raise HostError(f"HTTP {exc.code} for caption request") from exc
    except urllib.error.URLError as exc:
        raise HostError(f"caption request failed: {redact(str(exc.reason))}") from exc
    if len(data) > limit:
        raise HostError("caption response too large")
    return data


def invidious_bases() -> list[str]:
    raw = os.environ.get("INVIDIOUS_INSTANCE", "").strip()
    if raw.casefold() == "off":
        return []
    if raw:
        return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    try:
        payload = http_get(INSTANCE_LIST, limit=1_000_000, timeout=20, accept="application/json")
        data = json.loads(payload.decode("utf-8", errors="replace"))
    except (HostError, json.JSONDecodeError, TimeoutError) as exc:
        raise HostError(f"could not list public caption mirrors: {redact(str(exc))}") from exc
    bases: list[str] = []
    if not isinstance(data, list):
        return bases
    for item in data:
        if not isinstance(item, list) or len(item) < 2 or not isinstance(item[1], dict):
            continue
        meta = item[1]
        if meta.get("api") is not True:
            continue
        if meta.get("type") not in {None, "https"}:
            continue
        uri = str(meta.get("uri") or "").rstrip("/")
        if uri.startswith("https://"):
            bases.append(uri)
        if len(bases) >= 3:
            break
    return bases


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
    try:
        bases = invidious_bases()
    except HostError as exc:
        return {"text": None, "error": redact(str(exc))}
    if not bases:
        return {"text": None, "error": "caption mirror disabled (INVIDIOUS_INSTANCE=off)"}
    errors: list[str] = []
    for base in bases:
        host = urllib.parse.urlparse(base).netloc or base
        try:
            listing = http_get(
                f"{base}/api/v1/captions/{video_id}",
                limit=1_000_000,
                timeout=25,
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
            body = http_get(target, limit=2_000_000, timeout=40, accept="text/vtt, text/plain, */*")
            text = body.decode("utf-8", errors="replace")
            return {
                "text": text,
                "language": picked["lang"],
                "kind": "auto" if picked["auto"] else "manual",
                "error": None,
                "source": "caption-mirror",
                "mirror_host": host,
            }
        except (HostError, json.JSONDecodeError, TimeoutError) as exc:
            errors.append(f"{host}: {redact(str(exc))}")
    return {"text": None, "error": "; ".join(errors) or "no public caption mirror responded"}


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


def yaml_double(value: str) -> str:
    """Quote a frontmatter scalar so colons and quotes stay inside the value."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


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


def render_note(
    *,
    job_id: str,
    video_id: str,
    source: str,
    acquisition: str,
    caption_language: str | None,
    caption_kind: str | None,
    transcript_cite: str,
    excerpt: str,
) -> str:
    """Obsidian Markdown. Frontmatter title is the job id, not the platform title.

    The quoted window is copied from the transcript. The body does not retell it.
    """
    window, quote_lines = transcript_excerpt(excerpt)
    lines = [
        "---",
        f"title: {yaml_double(job_id)}",
        f"source_url: {yaml_double(source)}",
        f"video_id: {yaml_double(video_id)}",
        f"acquisition: {yaml_double(acquisition)}",
        "gate_passed: true",
        f"transcript_path: {yaml_double(transcript_cite)}",
        "quoted_window: |-",
        f"  {window}",
    ]
    if caption_language:
        lines.append(f"caption_language: {yaml_double(caption_language)}")
    if caption_kind:
        lines.append(f"caption_kind: {yaml_double(caption_kind)}")
    lines.extend(
        [
            "---",
            "",
            f"# {job_id}",
            "",
            "This note is allowed because the transcript passed the quality gate. "
            "The quoted window is copied from that file.",
            "",
            "## Source",
            "",
            f"- Source URL: {source}",
            f"- Video id: `{video_id}`",
            f"- Acquisition: `{acquisition}`",
        ]
    )
    if caption_language:
        lines.append(f"- Caption language: `{caption_language}`")
    if caption_kind:
        lines.append(f"- Caption kind: `{caption_kind}`")
    lines.extend(
        [
            "- Gate passed: yes",
            "",
            "## Transcript",
            "",
            "[transcript.txt](transcript.txt)",
            "",
            f"`{transcript_cite}`",
            "",
            "## Quoted window",
            "",
            *[f"> {line}" for line in quote_lines],
            "",
            "Match these lines to the transcript file. The file may be longer than the quote.",
            "",
        ]
    )
    return "\n".join(lines)


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
) -> dict:
    job_id = job_id_for(video_id, platform)
    job_dir = out_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    clear_deposit(job_dir)
    gate_lang = quality_gate.normalize_lang(expected_lang) or quality_gate.normalize_lang(caption_language)
    result = quality_gate.assess(text, expected_lang=gate_lang, confidence=confidence)
    transcript_path = job_dir / "transcript.txt"
    note_path = job_dir / "note.md"
    status_path = job_dir / "status.json"
    base = {
        "schema_version": 1,
        "job_id": job_id,
        "source_url": source,
        "finished": False,
        "acquisition": acquisition,
        "caption_language": caption_language,
        "caption_kind": caption_kind,
        "expected_lang": quality_gate.normalize_lang(expected_lang),
        "gate_lang": gate_lang,
        "transcript": None,
        "note": None,
        "gate": result.to_dict(),
        "verifier": None,
    }
    if extra:
        base.update(extra)
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
        write_json(status_path, {key: value for key, value in base.items() if key != "exit_code"})
        return base

    transcript_path.write_text(result.text.rstrip() + "\n", encoding="utf-8")
    excerpt = result.text
    cite = cite_path(transcript_path)
    note_body = render_note(
        job_id=job_id,
        video_id=video_id,
        source=source,
        acquisition=acquisition,
        caption_language=caption_language or gate_lang,
        caption_kind=caption_kind,
        transcript_cite=cite,
        excerpt=excerpt,
    )
    note_path.write_text(note_body, encoding="utf-8")
    verifier = None
    if verify:
        verifier = verify_note.verify(transcript_path, note_body, expected_lang=gate_lang, confidence=confidence)
        if not verifier["allowed"]:
            clear_deposit(job_dir)
            base.update(
                {
                    "status": "not_finished",
                    "finished": False,
                    "reason": "internal verifier refused the note: " + "; ".join(verifier["reasons"]),
                    "next_step": "stop",
                    "verifier": {"allowed": False, "reasons": verifier["reasons"]},
                    "exit_code": 2,
                }
            )
            write_json(status_path, {key: value for key, value in base.items() if key != "exit_code"})
            return base
    base.update(
        {
            "status": "finished",
            "finished": True,
            "reason": None,
            "next_step": "none",
            "transcript": cite,
            "note": cite_path(note_path),
            "verifier": None if verifier is None else {"allowed": True, "reasons": []},
            "exit_code": 0,
        }
    )
    stored = {key: value for key, value in base.items() if key != "exit_code"}
    write_json(status_path, stored)
    return base


def write_refusal(
    *,
    video_id: str,
    source: str,
    out_dir: Path,
    reason: str,
    next_step: str,
    extra: dict | None = None,
    platform: str = "youtube",
) -> dict:
    job_id = job_id_for(video_id, platform)
    job_dir = out_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    clear_deposit(job_dir)
    payload = {
        "schema_version": 1,
        "job_id": job_id,
        "source_url": source,
        "status": "not_finished",
        "finished": False,
        "reason": reason,
        "next_step": next_step,
        "acquisition": "none",
        "transcript": None,
        "note": None,
        "gate": None,
        "verifier": None,
    }
    if extra:
        payload.update(extra)
    write_json(job_dir / "status.json", payload)
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
) -> dict:
    if settle_text is not None:
        return finalize_job(
            text=settle_text,
            video_id=video_id,
            source=source,
            out_dir=out_dir,
            expected_lang=expected_lang,
            acquisition="settle-transcript",
            verify=verify,
        )

    attempts: list[dict] = []
    caption = None
    base_cmd = ytdlp_base()
    if base_cmd is None:
        attempts.append({"source": "yt-dlp", "ok": False, "detail": "yt-dlp is not installed"})
    else:
        log(f"fetching captions with yt-dlp for youtube_{video_id}")
        fetched = fetch_ytdlp_captions(source, video_id, expected_lang, base_cmd)
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
        log("yt-dlp did not yield captions; trying a public caption mirror")
        mirrored = fetch_mirror_captions(video_id, expected_lang)
        if mirrored.get("text"):
            attempts.append(
                {
                    "source": "caption-mirror",
                    "ok": True,
                    "detail": f"{mirrored.get('language')} {mirrored.get('kind')} via {mirrored.get('mirror_host')}",
                }
            )
            caption = mirrored
        else:
            attempts.append(
                {"source": "caption-mirror", "ok": False, "detail": mirrored.get("error") or "no captions"}
            )

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
            extra={"attempts": attempts, "mirror_host": caption.get("mirror_host")},
        )

    backend, block = asr_plan(asr_choice)
    if block:
        detail = "; ".join(
            f"{item['source']}: {item['detail']}" for item in attempts if not item["ok"]
        )
        reason = block if not detail else f"{block} Caption attempts: {detail}"
        log(reason)
        return write_refusal(
            video_id=video_id,
            source=source,
            out_dir=out_dir,
            reason=reason,
            next_step="configure-asr-or-retry-captions",
            extra={"attempts": attempts, "asr_backend": backend},
        )
    if base_cmd is None:
        return write_refusal(
            video_id=video_id,
            source=source,
            out_dir=out_dir,
            reason="not finished: ASR needs yt-dlp to download audio, and yt-dlp is not installed.",
            next_step="configure-asr-or-retry-captions",
            extra={"attempts": attempts, "asr_backend": backend},
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
            reason=reason,
            next_step="retry-stronger-asr",
            extra={"attempts": attempts, "asr_backend": backend},
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
        upgrade_attempted=upgraded,
        extra={"attempts": attempts, "asr_backend": backend, "asr_model": model},
    )


def _emit(payload: dict, as_json: bool) -> int:
    code = int(payload.get("exit_code") or (0 if payload.get("finished") else 2))
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
        if public.get("note"):
            print(f"note: {public['note']}")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a public YouTube transcript and write an Obsidian Markdown note only if the quality gate passes."
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
    parser.add_argument("--asr", choices=["auto", "off", "whisper", "openai"], default="auto")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verify", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
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
            )
    except HostError as exc:
        message = redact(str(exc))
        if args.json:
            json.dump({"status": "not_finished", "finished": False, "reason": message}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(message, file=sys.stderr)
        return 2
    return _emit(payload, args.json)


if __name__ == "__main__":
    sys.exit(main())
