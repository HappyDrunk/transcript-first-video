#!/usr/bin/env python3
"""Copy a timed speech excerpt without changing any task files."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from quality_gate import Segment, format_stamp
from verify_rules import QUOTE_WINDOW, _fold, clock_seconds, transcript_segments

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("start", metavar="START", help="inclusive start in mm:ss or hh:mm:ss")
    parser.add_argument("end", metavar="END", help="exclusive end in mm:ss or hh:mm:ss")
    args = parser.parse_args()
    start, end = clock_seconds(args.start), clock_seconds(args.end)
    if start is None or end is None or start >= end:
        parser.error("use mm:ss or hh:mm:ss with START earlier than END")
    try:
        line, bounds = extract(args.task_dir, start, end)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(line)
    print(f"Actual subtitles: {bounds}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
