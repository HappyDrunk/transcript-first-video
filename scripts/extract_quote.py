#!/usr/bin/env python3
"""Extract timed speech and screen quotes without changing any task files."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from quality_gate import Segment, format_stamp
from verify_rules import (
    QUOTE_WINDOW,
    SCREEN_FILE,
    SCREEN_TAG,
    SLIDE_MARKER,
    UNCERTAIN_SCREEN_TAG,
    _fold,
    _screen_source,
    _screen_status,
    clock_seconds,
    parse_stamp,
    screen_mode,
    transcript_segments,
)

MAX_CUE_GAP_SECONDS = 5


def _clock(seconds: float) -> str:
    whole, millis = divmod(round(seconds * 1000), 1000)
    stamp = format_stamp(whole)[1:-1]
    return f"{stamp}.{millis:03d}".rstrip("0") if millis else stamp


def extract(job: Path, start: int, end: int) -> tuple[str, str]:
    transcript = job / "transcript.txt"
    cues = transcript_segments(transcript.read_text(encoding="utf-8"), job / "segments.json")
    timed = [(i, cue) for i, cue in enumerate(cues) if cue.start is not None]
    if not timed:
        raise ValueError(f"{transcript}: no cue clocks; use a timed transcript")

    selected = [i for i, cue in timed if cue.start < end and (
        cue.start >= start or (cue.end is not None and cue.end > start)
    )]
    if not selected:
        raise ValueError(f"{transcript}: no timed captions in {_clock(start)}–{_clock(end)}")

    first, last = selected[0], selected[-1]
    span = cues[first:last + 1]
    previous: Segment | None = None
    seen_end = None
    for i, cue in enumerate(span, start=first + 1):
        if cue.start is None:
            raise ValueError(f"{transcript}: captions not continuous; cue {i} has no clock")
        if previous is not None and (
            cue.start < previous.start or cue.start - seen_end > MAX_CUE_GAP_SECONDS
        ):
            raise ValueError(
                f"{transcript}: captions not continuous between cue {i - 1} "
                f"({_clock(previous.start)}) and cue {i} ({_clock(cue.start)})"
            )
        previous = cue
        seen_end = max(seen_end or cue.start, cue.end if cue.end is not None else cue.start)

    text = " ".join(cue.text for cue in span)
    actual_start, last_start = span[0].start, span[-1].start
    bounds = (
        f"{_clock(actual_start)}–{_clock(seen_end)}" if seen_end > last_start
        else f"{_clock(actual_start)}; last cue starts at {_clock(last_start)} (end unavailable)"
    )
    count = len(_fold(text))
    if count < QUOTE_WINDOW:
        raise ValueError(
            f"{transcript}: {bounds} has {count} characters; need at least {QUOTE_WINDOW}"
        )
    return f"> {format_stamp(actual_start)} {text}", bounds


def extract_screen(job: Path, start: int, end: int) -> tuple[str, list[str]]:
    screen_path = job / SCREEN_FILE
    status = _screen_status(job)
    if status is None:
        raise ValueError(f"{job / 'status.json'}: 缺少 screen_ocr 状态，不能摘取画面引文")
    if status.get("mode") == "off":
        raise ValueError(f"{screen_path}: 画面模式为 off，不能摘取画面引文")
    if status.get("state") != "ready":
        raise ValueError(
            f"{screen_path}: screen_ocr 状态为 {status.get('state')!r}（非 ready），不能摘取画面引文"
        )
    if not screen_path.is_file():
        raise ValueError(f"{screen_path}: 找不到 screen.txt")
    source = _screen_source(screen_path)
    if source is None:
        raise ValueError(f"{screen_path}: screen.txt 与 status.json 的 SHA-256 不一致或无法读取")
    if screen_mode(job) == "off":
        raise ValueError(f"{screen_path}: 画面模式为 off，不能摘取画面引文")

    lines = source[0]
    output: list[str] = []
    pending_blank = False
    skipped_uncertain = 0
    for line in lines:
        if not line.strip():
            if output:
                pending_blank = True
            continue
        stamp, tagged = parse_stamp(line)
        if stamp is None:
            continue
        if SLIDE_MARKER.fullmatch(tagged):
            pending_blank = False
            continue
        if not (start <= stamp < end):
            continue
        if tagged.startswith(UNCERTAIN_SCREEN_TAG):
            skipped_uncertain += 1
            continue
        if not tagged.startswith(SCREEN_TAG):
            continue
        text = tagged[len(SCREEN_TAG):].strip()
        if not text:
            continue
        if pending_blank:
            output.append("")
            pending_blank = False
        output.append(f"> {line.strip()}")

    warnings = [f"跳过 {skipped_uncertain} 行存疑画面（不能当依据）"] if skipped_uncertain else []
    if not output:
        raise ValueError("\n".join([
            *warnings,
            f"{screen_path}: {_clock(start)}–{_clock(end)} 没有可信 [画面] 行",
        ]))
    return "\n".join(output), warnings


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen", action="store_true", help="extract trusted [画面] lines from screen.txt")
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("start", metavar="START", help="inclusive start in mm:ss or hh:mm:ss")
    parser.add_argument("end", metavar="END", help="exclusive end in mm:ss or hh:mm:ss")
    args = parser.parse_intermixed_args(argv)
    start, end = clock_seconds(args.start), clock_seconds(args.end)
    if start is None or end is None or start >= end:
        parser.error("use mm:ss or hh:mm:ss with START earlier than END")
    try:
        if args.screen:
            quote, messages = extract_screen(args.task_dir, start, end)
        else:
            quote, bounds = extract(args.task_dir, start, end)
            messages = [f"Actual subtitles: {bounds}"]
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(quote)
    for message in messages:
        print(message, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
