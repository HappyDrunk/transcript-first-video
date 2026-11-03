#!/usr/bin/env python3
"""Minimal Twitter/X video host: captions first, optional ASR, otherwise not finished.

Same quality gate and the same knowledge note as the YouTube host: four sections,
each quoting the transcript. Post text is never a transcript. On failure the job
directory keeps status.json and no note.

Public media lookup uses the FxTwitter-style API at https://api.fxtwitter.com
(no key). Set FX_TWITTER_API=off to skip it. YTDLP_COOKIES is an optional path
when yt-dlp hits a sign-in wall. Never commit that file.

Exit 0 finished. Exit 2 not finished or quality-gate failure. Exit 1 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quality_gate  # noqa: E402
import youtube_host  # noqa: E402

HostError = youtube_host.HostError

_STATUS_ID = re.compile(r"^[0-9]{2,22}$")
_STATUS_HOSTS = {
    "x.com",
    "twitter.com",
    "mobile.twitter.com",
    "fxtwitter.com",
    "vxtwitter.com",
    "fixupx.com",
    "fixvx.com",
}
_API_HOST = "api.fxtwitter.com"
_MEDIA_HOSTS = {"video.twimg.com"}
_API_ORIGIN = "https://api.fxtwitter.com"
_NO_VIDEO = "status has no video"
_OFFSITE = "status embeds off-site media; pass that video URL to the matching host"
_BAD_MEDIA = "video URL was not on an allowlisted host"
_DEFINITIVE = {_NO_VIDEO, _OFFSITE, _BAD_MEDIA}
_MAX_JSON = 2_000_000
_MAX_CAPTION = 2_000_000
_MAX_MEDIA = 80 * 1024 * 1024
_MEDIA_EXTS = (".mp4", ".m4a", ".webm", ".mp3", ".opus", ".wav")


def status_in_page(info: dict, status_id: str) -> bool:
    """True when yt-dlp metadata is this status, even if its media id differs."""
    if str(info.get("id") or "") == status_id:
        return True
    for key in ("webpage_url", "original_url"):
        if f"/status/{status_id}" in str(info.get(key) or ""):
            return True
    return False


def parse_x_ref(value: str) -> tuple[str, str]:
    """Return (status id, canonical https://x.com/i/status/<id>)."""
    raw = value.strip()
    if _STATUS_ID.fullmatch(raw):
        return raw, f"https://x.com/i/status/{raw}"
    parsed = urllib.parse.urlparse(raw if "://" in raw else "https://" + raw)
    if parsed.scheme not in {"http", "https", ""}:
        raise HostError(f"not an X or Twitter status URL: {raw}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in _STATUS_HOSTS:
        raise HostError(f"not an X or Twitter status URL: {raw}")
    parts = [part for part in parsed.path.split("/") if part]
    status_id = ""
    if "status" in parts:
        index = parts.index("status")
        if index + 1 < len(parts):
            status_id = parts[index + 1]
    if not _STATUS_ID.fullmatch(status_id):
        raise HostError(f"not an X or Twitter status URL: {raw}")
    return status_id, f"https://x.com/i/status/{status_id}"


def require_api_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host != _API_HOST or parsed.username or parsed.password:
        raise HostError("refusing a status API URL that is not https://api.fxtwitter.com")


def public_api_bases() -> list[str]:
    """Origins for the public status API. `off` disables it. No API key."""
    raw = os.environ.get("FX_TWITTER_API", "").strip()
    if raw.casefold() == "off":
        return []
    if not raw:
        return [_API_ORIGIN]
    bases: list[str] = []
    for item in raw.split(","):
        base = item.strip()
        if not base:
            continue
        require_api_url(base if "://" in base else "https://" + base)
        parsed = urllib.parse.urlparse(base if "://" in base else "https://" + base)
        origin = f"https://{parsed.hostname}"
        if origin not in bases:
            bases.append(origin)
    return bases


def safe_media_url(url: str) -> str:
    parsed = urllib.parse.urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in _MEDIA_HOSTS or parsed.username or parsed.password:
        raise HostError("media URL is not an allowlisted https host")
    return urllib.parse.urlunparse(parsed)


def _caption_from_item(video: dict) -> tuple[str | None, str | None]:
    for key in ("subtitles", "captions", "subtitle_tracks", "caption_tracks"):
        raw = video.get(key)
        tracks: list = []
        if isinstance(raw, list):
            tracks = raw
        elif isinstance(raw, dict):
            tracks = [raw]
        elif isinstance(raw, str) and raw.strip():
            tracks = [{"url": raw}]
        for track in tracks:
            if not isinstance(track, dict):
                continue
            url = str(track.get("url") or "").strip()
            if not url:
                continue
            try:
                safe = safe_media_url(url)
            except HostError:
                continue
            lang = track.get("lang") or track.get("language") or track.get("languageCode")
            return safe, str(lang) if lang else None
    return None, None


def _pick_video_url(video: dict) -> str | None:
    mp4s: list[str] = []
    others: list[str] = []
    formats = video.get("formats") if isinstance(video.get("formats"), list) else []
    for fmt in formats:
        if not isinstance(fmt, dict) or not fmt.get("url"):
            continue
        url = str(fmt["url"])
        container = str(fmt.get("container") or "").lower()
        if container == "m3u8" or ".m3u8" in url.lower():
            continue
        if container == "mp4" or ".mp4" in url.lower():
            mp4s.append(url)
        else:
            others.append(url)
    direct = str(video.get("url") or "")
    if direct and ".m3u8" not in direct.lower():
        if ".mp4" in direct.lower() or not others:
            mp4s.insert(0, direct)
        else:
            others.insert(0, direct)
    for url in mp4s + others:
        try:
            return safe_media_url(url)
        except HostError:
            continue
    return None


def parse_public_status(data: object) -> dict:
    """Pull video and caption URLs. Never copy post text into the result."""
    empty = {
        "has_video": False,
        "video_url": None,
        "caption_url": None,
        "caption_lang": None,
        "error": None,
    }
    if not isinstance(data, dict):
        return {**empty, "error": "public status payload was not an object"}
    code = data.get("code")
    if code not in (None, 200, "200"):
        label = re.sub(r"\s+", " ", str(data.get("message") or "")).strip()[:80]
        detail = f"public status API returned {code}"
        if label and " " not in label:
            detail = f"{detail} {label}"
        return {**empty, "error": detail}
    body = data.get("status") if isinstance(data.get("status"), dict) else None
    if body is None and isinstance(data.get("tweet"), dict):
        body = data["tweet"]
    if not isinstance(body, dict):
        return {**empty, "error": "public status payload had no status object"}
    media = body.get("media") if isinstance(body.get("media"), dict) else {}
    videos = [item for item in (media.get("videos") or []) if isinstance(item, dict)]
    if not videos:
        for item in media.get("all") or []:
            if isinstance(item, dict) and str(item.get("type") or "").lower() in {"video", "gif"}:
                videos.append(item)
    caption_url = None
    caption_lang = None
    video_url = None
    saw_unsafe = False
    for video in videos:
        if caption_url is None:
            found, lang = _caption_from_item(video)
            if found:
                caption_url, caption_lang = found, lang
        if video_url is None:
            picked = _pick_video_url(video)
            if picked:
                video_url = picked
            elif video.get("url") or video.get("formats"):
                saw_unsafe = True
    if video_url is None and caption_url is None:
        if saw_unsafe:
            return {**empty, "error": _BAD_MEDIA}
        if not videos and isinstance(media.get("external"), dict):
            return {**empty, "error": _OFFSITE}
        return {**empty, "error": _NO_VIDEO}
    return {
        "has_video": video_url is not None,
        "video_url": video_url,
        "caption_url": caption_url,
        "caption_lang": caption_lang,
        "error": None,
    }


def _opener(check):
    class Guard(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
            check(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(Guard)


def http_get_checked(url: str, *, limit: int, timeout: int, check) -> bytes:
    check(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "transcript-first-video/1.0",
            "Accept": "application/json, text/vtt, text/plain, */*",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with _opener(check).open(request, timeout=timeout) as response:
            check(response.geturl())
            data = response.read(limit + 1)
    except HostError:
        raise
    except urllib.error.HTTPError as exc:
        raise HostError(f"HTTP {exc.code} for status request") from exc
    except urllib.error.URLError as exc:
        raise HostError(f"status request failed: {youtube_host.redact(str(exc.reason))}") from exc
    except TimeoutError as exc:
        raise HostError("status request timed out") from exc
    if len(data) > limit:
        raise HostError("status response too large")
    return data


def fetch_public_status(status_id: str) -> dict:
    empty = {
        "has_video": False,
        "video_url": None,
        "caption_url": None,
        "caption_lang": None,
        "error": None,
    }
    try:
        bases = public_api_bases()
    except HostError as exc:
        return {**empty, "error": youtube_host.redact(str(exc))}
    if not bases:
        return {**empty, "error": "public status API disabled (FX_TWITTER_API=off)"}
    errors: list[str] = []
    for base in bases:
        for path in (f"/2/status/{status_id}", f"/status/{status_id}"):
            try:
                raw = http_get_checked(
                    base + path,
                    limit=_MAX_JSON,
                    timeout=25,
                    check=require_api_url,
                )
            except HostError as exc:
                errors.append(youtube_host.redact(str(exc)))
                continue
            try:
                data = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                errors.append("public status payload was not JSON")
                continue
            parsed = parse_public_status(data)
            err = parsed.get("error")
            if err in _DEFINITIVE or (not err and (parsed.get("has_video") or parsed.get("caption_url"))):
                return parsed
            if err:
                errors.append(str(err))
                continue
            return parsed
    return {**empty, "error": "; ".join(errors) or "public status API failed"}


def download_caption(url: str) -> str:
    data = http_get_checked(url, limit=_MAX_CAPTION, timeout=30, check=safe_media_url)
    if data.lstrip().startswith((b"{", b"<html", b"<!doctype", b"<!DOCTYPE")):
        raise HostError("caption download was not a subtitle file")
    return data.decode("utf-8", errors="replace")


def _media_name(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    for ext in _MEDIA_EXTS:
        if path.endswith(ext):
            return "media" + ext
    return "media.mp4"


def download_media(url: str, dest_dir: Path) -> Path:
    safe = safe_media_url(url)
    data = http_get_checked(safe, limit=_MAX_MEDIA, timeout=90, check=safe_media_url)
    sample = data[:200].lstrip().lower()
    if sample.startswith((b"<", b"{", b"webvtt", b"error", b"not ")):
        raise HostError("media download was not a video file")
    if len(data) < 1000:
        raise HostError("media download was too small to be a video")
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / _media_name(safe)
    path.write_bytes(data)
    return path


def _attempt(source: str, ok: bool, detail: str) -> dict:
    return {"source": source, "ok": ok, "detail": youtube_host.redact(detail)}


def not_finished_reason(block: str, attempts: list[dict]) -> str:
    """Prefer a specific X reason when a video was found and ASR is off."""
    found_video = any(
        item.get("source") == "fx-twitter"
        and item.get("ok")
        and "no caption" in str(item.get("detail") or "")
        for item in attempts
    )
    failed = "; ".join(
        f"{item['source']}: {item['detail']}" for item in attempts if not item.get("ok")
    )
    if found_video and "ASR is not configured" in block:
        reason = (
            "not finished: this X video has no caption track and ASR is not configured. "
            "Set ASR_BACKEND=whisper (needs ffmpeg) or ASR_BACKEND=openai with OPENAI_API_KEY. "
            "Post text was not used. No note was written."
        )
        if failed:
            reason = f"{reason} Failed attempts: {failed}"
        return reason
    return block if not failed else f"{block} Attempts: {failed}"


def _refuse(
    *,
    status_id: str,
    source: str,
    out_dir: Path,
    reason: str,
    next_step: str,
    attempts: list[dict],
    extra: dict | None = None,
) -> dict:
    payload = {"attempts": attempts}
    if extra:
        payload.update(extra)
    return youtube_host.write_refusal(
        video_id=status_id,
        source=source,
        out_dir=out_dir,
        reason=reason,
        next_step=next_step,
        extra=payload,
        platform="x",
    )


def _transcribe_media(path: Path, backend: str, language: str | None) -> tuple[str, str, bool]:
    if backend == "whisper" and shutil.which("ffmpeg") is None:
        raise HostError("ffmpeg is not installed, so local whisper cannot read the media")
    return youtube_host.transcribe_file(path, backend, language)


def run_x_host(
    *,
    status_id: str,
    source: str,
    out_dir: Path,
    expected_lang: str | None,
    asr_choice: str,
    verify: bool,
    settle_text: str | None = None,
) -> dict:
    if not _STATUS_ID.fullmatch(status_id):
        raise HostError("status id must be the numeric id from the status URL")
    if settle_text is not None:
        return youtube_host.finalize_job(
            text=settle_text,
            video_id=status_id,
            source=source,
            out_dir=out_dir,
            expected_lang=expected_lang,
            acquisition="settle-transcript",
            verify=verify,
            platform="x",
        )

    attempts: list[dict] = []
    caption = None
    video_url = None
    public: dict | None = None
    base_cmd = youtube_host.ytdlp_base()
    if base_cmd is None:
        attempts.append(_attempt("yt-dlp", False, "yt-dlp is not installed"))
    else:
        youtube_host.log(f"fetching captions with yt-dlp for x_{status_id}")
        fetched = youtube_host.fetch_ytdlp_captions(
            source,
            status_id,
            expected_lang,
            base_cmd,
            accept_info=lambda info: status_in_page(info, status_id),
        )
        if fetched.get("text"):
            attempts.append(
                _attempt("yt-dlp", True, f"{fetched.get('language')} {fetched.get('kind')}")
            )
            caption = fetched
        else:
            attempts.append(_attempt("yt-dlp", False, fetched.get("error") or "no captions"))

    if caption is None:
        public = fetch_public_status(status_id)
        if public.get("caption_url"):
            try:
                raw = download_caption(str(public["caption_url"]))
            except HostError as exc:
                attempts.append(_attempt("fx-twitter", False, str(exc)))
            else:
                if raw.strip():
                    attempts.append(_attempt("fx-twitter", True, "caption track"))
                    caption = {
                        "text": raw,
                        "language": quality_gate.normalize_lang(public.get("caption_lang")),
                        "kind": "api",
                        "source": "fx-twitter",
                    }
                else:
                    attempts.append(_attempt("fx-twitter", False, "caption track was empty"))
        if caption is None:
            if public.get("video_url"):
                video_url = str(public["video_url"])
                attempts.append(_attempt("fx-twitter", True, "video URL, no caption track"))
            else:
                attempts.append(_attempt("fx-twitter", False, public.get("error") or "no video"))

    if caption and caption.get("text"):
        youtube_host.log(f"captions acquired via {caption.get('source') or 'captions'}")
        return youtube_host.finalize_job(
            text=caption["text"],
            video_id=status_id,
            source=source,
            out_dir=out_dir,
            expected_lang=expected_lang,
            acquisition=str(caption.get("source") or "captions"),
            caption_language=caption.get("language"),
            caption_kind=caption.get("kind"),
            verify=verify,
            platform="x",
            extra={"attempts": attempts},
        )

    if public is not None and public.get("error") in {_NO_VIDEO, _OFFSITE}:
        if public["error"] == _NO_VIDEO:
            reason = (
                "not finished: this status has no video. "
                "Post text is not a transcript. No note was written."
            )
        else:
            reason = (
                "not finished: this status only embeds off-site media. "
                "Pass that video's own URL to the matching host. No note was written."
            )
        youtube_host.log(reason)
        return _refuse(
            status_id=status_id,
            source=source,
            out_dir=out_dir,
            reason=reason,
            next_step="stop",
            attempts=attempts,
        )

    backend, block = youtube_host.asr_plan(asr_choice)
    if block:
        reason = not_finished_reason(block, attempts)
        youtube_host.log(reason)
        return _refuse(
            status_id=status_id,
            source=source,
            out_dir=out_dir,
            reason=reason,
            next_step="configure-asr-or-retry-captions",
            attempts=attempts,
            extra={"asr_backend": backend},
        )

    if backend == "whisper" and shutil.which("ffmpeg") is None:
        reason = (
            "not finished: ASR_BACKEND=whisper but ffmpeg is not installed, "
            "so the media cannot be read. No note was written."
        )
        youtube_host.log(reason)
        return _refuse(
            status_id=status_id,
            source=source,
            out_dir=out_dir,
            reason=reason,
            next_step="configure-asr-or-retry-captions",
            attempts=attempts,
            extra={"asr_backend": backend},
        )

    text = None
    model = None
    upgraded = False
    asr_error = None
    if base_cmd is not None:
        youtube_host.log(f"no captions; running ASR backend {backend} via yt-dlp")
        try:
            with tempfile.TemporaryDirectory(prefix="tfv-x-asr-") as tmp:
                audio = youtube_host.download_audio(source, base_cmd, Path(tmp))
                text, model, upgraded = _transcribe_media(audio, backend, expected_lang)
        except HostError as exc:
            asr_error = youtube_host.redact(str(exc))
            attempts.append(_attempt("asr", False, f"yt-dlp audio: {asr_error}"))
    if text is None and video_url:
        youtube_host.log(f"running ASR backend {backend} on the public media file")
        try:
            with tempfile.TemporaryDirectory(prefix="tfv-x-media-") as tmp:
                media = download_media(video_url, Path(tmp))
                text, model, upgraded = _transcribe_media(media, backend, expected_lang)
        except HostError as exc:
            asr_error = youtube_host.redact(str(exc))
            attempts.append(_attempt("asr", False, f"public media: {asr_error}"))
    if text is None:
        reason = f"not finished: ASR failed: {asr_error or 'no media URL'}. No note was written."
        youtube_host.log(reason)
        return _refuse(
            status_id=status_id,
            source=source,
            out_dir=out_dir,
            reason=reason,
            next_step="retry-stronger-asr",
            attempts=attempts,
            extra={"asr_backend": backend},
        )
    attempts.append(_attempt("asr", True, str(model)))
    return youtube_host.finalize_job(
        text=text,
        video_id=status_id,
        source=source,
        out_dir=out_dir,
        expected_lang=expected_lang,
        acquisition="asr",
        caption_language=quality_gate.normalize_lang(expected_lang),
        caption_kind=None,
        verify=verify,
        upgrade_attempted=upgraded,
        platform="x",
        extra={"attempts": attempts, "asr_backend": backend, "asr_model": model},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a public Twitter/X video transcript and write an Obsidian Markdown note only if the quality gate passes."
        )
    )
    parser.add_argument("url", nargs="?", help="x.com or twitter.com status URL, or a numeric status id")
    parser.add_argument(
        "--settle-transcript",
        type=Path,
        help="Offline path: gate this text file instead of fetching. Not a watch.",
    )
    parser.add_argument("--status-id", help="Numeric status id. Required with --settle-transcript.")
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument("--expected-lang", default=None)
    parser.add_argument("--asr", choices=["auto", "off", "whisper", "openai"], default="auto")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verify", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    try:
        if args.settle_transcript:
            if not args.status_id:
                parser.error("--settle-transcript requires --status-id")
            if not args.settle_transcript.is_file():
                raise HostError(f"settle transcript does not exist: {args.settle_transcript}")
            status_id = args.status_id.strip()
            source = f"settle-transcript:{status_id}"
            text = args.settle_transcript.read_text(encoding="utf-8", errors="replace")
            payload = run_x_host(
                status_id=status_id,
                source=source,
                out_dir=args.out,
                expected_lang=args.expected_lang,
                asr_choice="off",
                verify=args.verify,
                settle_text=text,
            )
        else:
            if not args.url:
                parser.error("pass an X or Twitter status URL")
            status_id, source = parse_x_ref(args.url)
            payload = run_x_host(
                status_id=status_id,
                source=source,
                out_dir=args.out,
                expected_lang=args.expected_lang,
                asr_choice=args.asr,
                verify=args.verify,
            )
    except HostError as exc:
        message = youtube_host.redact(str(exc))
        if args.json:
            json.dump({"status": "not_finished", "finished": False, "reason": message}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(message, file=sys.stderr)
        return 2
    return youtube_host._emit(payload, args.json)


if __name__ == "__main__":
    sys.exit(main())
