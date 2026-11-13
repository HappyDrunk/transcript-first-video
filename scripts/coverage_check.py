#!/usr/bin/env python3
"""Check C02 and S01 against a job's single note and full transcript."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_note  # noqa: E402
import verify_rules as rules  # noqa: E402

LONG_AFTER = 300
OVERLAP = rules.QUOTE_WINDOW
MIN_HITS = 3
HIT_RATE_NUMERATOR = 9
HIT_RATE_DENOMINATOR = 10
DELIVERY_RATIO = 0.9  # Legacy C04e threshold. C04b now requires every quote to be used.


def fold(text: str) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def chunk_txts(job: Path) -> list[Path]:
    folder = job / "chunks"
    if not folder.is_dir():
        return []
    found = [path for path in folder.glob("*.txt") if path.stem.isdigit()]
    return sorted(found, key=lambda path: int(path.stem))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def text_positions(transcript: str, excerpts: list[str]) -> dict[str, int]:
    """Find excerpt starts, keeping offsets in the original character stream."""
    if not excerpts:
        return {}
    characters: list[str] = []
    offsets: list[int] = []
    for match in re.finditer(r"\S", transcript):
        character = match.group().casefold()
        characters.append(character)
        offsets.extend([match.start()] * len(character))
    folded = "".join(characters)
    positions: dict[str, int] = {}
    for excerpt in dict.fromkeys(excerpts):
        key = fold(excerpt)
        if len(key) < OVERLAP:
            continue
        start = folded.find(key)
        if start < 0:
            # If the full excerpt is unavailable, use an unambiguous shared window.
            for index in range(len(key) - OVERLAP + 1):
                window = key[index : index + OVERLAP]
                match = folded.find(window)
                if match >= 0 and folded.find(window, match + 1) < 0:
                    start = max(0, match - index)
                    break
        if start >= 0:
            positions[excerpt] = offsets[start]
    return positions


def quartile(moment: float, duration: float) -> int:
    if duration <= 0:
        return 0
    ratio = min(max(moment, 0.0), duration) / duration
    if ratio >= 1:
        return 3
    return min(3, int(ratio * 4))


def hits_required(line_count: int) -> int:
    """``max(3, ceil(0.9 × lines))``. Integer math, so 0.9×10 is 9 not 8."""
    if line_count <= 0:
        return MIN_HITS
    scaled = (HIT_RATE_NUMERATOR * line_count + HIT_RATE_DENOMINATOR - 1) // HIT_RATE_DENOMINATOR
    return max(MIN_HITS, scaled)


_CLOCK = r"(?:[0-9]+:)?[0-9]{2,}:[0-9]{2}"
_RANGE = rf"({_CLOCK})\s*[-–—]\s*({_CLOCK})"
_OMITTED_ITEM = re.compile(rf"(.+?)[（(]{_RANGE}[）)]\s*(?:[、，,]\s*|$)")


@dataclass(frozen=True)
class SelectionUnit:
    start: int
    end: int
    retained: bool


def _range_seconds(start: str, end: str) -> tuple[int, int] | None:
    left, right = rules.clock_seconds(start), rules.clock_seconds(end)
    if left is None or right is None or left >= right:
        return None
    return left, right


def read_selection(job: Path) -> tuple[list[SelectionUnit], list[str]]:
    path = job / "selection.md"
    if not path.is_file():
        return [], ["selection.md is missing"]
    units, issues = [], []
    for line_no, line in enumerate(_read(path).splitlines(), 1):
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split("|")]
        if len(fields) == 4:
            time, category, decision, reason = fields
            match = re.fullmatch(_RANGE, time)
            if match and category and decision in {"留", "略"} and reason:
                bounds = _range_seconds(*match.groups())
                if bounds:
                    units.append(SelectionUnit(*bounds, retained=decision == "留"))
                    continue
        issues.append(f"selection.md line {line_no}: expected time range | category | 留 or 略 | reason")
    if not units:
        issues.append("selection.md has no usable units")
    return units, issues


def omitted_ranges(omission: str | None) -> list[tuple[int, int]] | None:
    if omission == "无":
        return []
    if not omission:
        return None
    ranges = []
    cursor = 0
    for match in _OMITTED_ITEM.finditer(omission):
        bounds = _range_seconds(match[2], match[3])
        if match.start() != cursor or not match[1].strip() or bounds is None:
            return None
        ranges.append(bounds)
        cursor = match.end()
    return ranges if cursor == len(omission) else None


def _crosses_omission(moments: list[float], omitted: list[SelectionUnit]) -> bool:
    low, high = min(moments), max(moments)
    return any(low < unit.end and high >= unit.start for unit in omitted)


def _has_omitted_excerpt(
    prose: str, index: rules.TranscriptIndex, omitted_starts: set[float],
) -> bool:
    text = rules._fold(prose)
    for start in range(len(text) - OVERLAP + 1):
        matches = index.matches(text[start:start + OVERLAP])
        if matches and all(any(cue.start in omitted_starts for cue in match.cues) for match in matches):
            return True
    return False


def check_selection(
    job: Path, ctx: rules.RuleContext, duration: float | None,
) -> tuple[list[str], list[str]]:
    units, issues = read_selection(job)
    if issues:
        return issues, []
    if units[0].start != 0 or any(left.end != right.start for left, right in zip(units, units[1:])):
        return ["selection.md must cover the transcript in order without gaps or overlaps, starting at 00:00"], []
    if not ctx.has_clock:
        return ["selection.md timing cannot be verified without a transcript clock"], []
    latest = max(cue.start for cue in ctx.segments if cue.start is not None)
    endpoint = max(math.ceil(duration or 0), math.floor(latest) + 1)
    if units[-1].end != endpoint:
        return [f"selection.md must end at the transcript endpoint {rules._fmt(endpoint)}"], []

    starts = [unit.start for unit in units]

    def unit_at(moment: float) -> SelectionUnit | None:
        if not 0 <= moment < units[-1].end:
            return None
        return units[bisect_right(starts, moment) - 1]

    if any(cue.start is None or unit_at(cue.start) is None for cue in ctx.segments):
        return ["selection.md cannot assign every transcript cue to a unit"], []

    omitted = [unit for unit in units if not unit.retained]
    expected = [(unit.start, unit.end) for unit in omitted]
    if omitted_ranges(ctx.omission) != expected:
        issues.append("本文略去 must list the omitted selection.md ranges in order, or 无")

    valid = ctx.valid_quotes
    hit = set()
    for quote in valid:
        moments = [cue.start for cue in quote.match.cues if cue.start is not None]
        if unit_at(quote.stamp) is None:
            issues.append(f"quote [{rules._fmt(quote.stamp)}] is outside the selection.md ranges")
            continue
        if _crosses_omission([quote.stamp, *moments], omitted):
            issues.append(f"quote [{rules._fmt(quote.stamp)}] uses or crosses an omitted (略) unit")
            continue
        anchor_unit = unit_at(quote.anchor.start)
        if anchor_unit and anchor_unit.retained:
            hit.add(anchor_unit)

    omitted_starts = {cue.start for cue in ctx.segments if not unit_at(cue.start).retained}
    index = rules.TranscriptIndex(ctx.segments) if omitted_starts else None
    for section in ctx.sections:
        for prose in [section.heading, *section.prose]:
            for stamp in sorted(rules.delivery_times(prose)):
                if unit_at(stamp) is None:
                    issues.append(f"{section.heading}: ⏱ {rules._fmt(stamp)} is outside the selection.md ranges")
                    continue
                linked, _ = rules.match_link(stamp, valid)
                if _crosses_omission([stamp], omitted) or any(
                    _crosses_omission([stamp, quote.stamp, quote.anchor.start], omitted) for quote in linked
                ):
                    issues.append(f"{section.heading}: ⏱ {rules._fmt(stamp)} uses or crosses an omitted (略) unit")
            if index and _has_omitted_excerpt(rules.prose_without_times(prose), index, omitted_starts):
                issues.append(f"{section.heading}: prose quotes an omitted (略) unit")

    retained = len(units) - len(omitted)
    needed = hits_required(retained)
    if len(hit) < needed:
        issues.append(f"{len(hit)} of {retained} retained units have verified quotes; need {needed} (9/10, at least 3)")
    omitted_time = sum(unit.end - unit.start for unit in omitted)
    warnings = (
        [f"S01 WARN: 略去 {omitted_time} 秒，超过全片一半"]
        if 2 * omitted_time > (duration if duration is not None else endpoint) else []
    )
    return issues, warnings


def check_job(job: Path, delivery: Path | None = None) -> dict:
    """Read C02/S01 independently so a failed R05 cannot hide C02 diagnostics."""
    note_path = job / "note.md"
    transcript = job / "transcript.txt"
    note = _read(note_path) if note_path.is_file() else ""
    raw = _read(transcript) if transcript.is_file() else ""
    chunks = chunk_txts(job)
    status = verify_note.read_job_status(job)
    speech = raw if raw.strip() else "\n".join(_read(chunk) for chunk in chunks)
    ctx = rules.build_context(
        transcript, note, raw=speech,
        expected_lang=status.get("gate_lang") or status.get("expected_lang"), job=True,
    )
    duration = rules._checked_clock(status.get("duration_seconds")) or None
    ends = [cue.end for cue in ctx.segments if cue.end is not None
            and cue.start is not None and cue.end > cue.start]
    clock_end = max(ends, default=0)
    if clock_end:
        duration = max(duration or 0, clock_end)
    latest = max((cue.start for cue in ctx.segments if cue.start is not None), default=0)
    long = (duration is not None and duration > LONG_AFTER) or max(latest, clock_end) >= LONG_AFTER
    if duration is None and len(chunks) >= 2:
        long = True

    reasons, warnings, not_checked, quartiles = [], [], [], []
    if not note_path.is_file():
        reasons.append("C00 FAIL: note.md is missing")
    if not raw.strip():
        reasons.append("C00 FAIL: transcript.txt is missing or empty")
    if long:
        if ctx.has_clock and (duration is not None or any(quote.screen for quote in ctx.valid_quotes)):
            time_span = duration or math.floor(latest) + 1
            quartiles = sorted({quartile(quote.anchor.start, time_span) for quote in ctx.valid_quotes})
            basis = "time"
        elif ctx.has_clock:
            length = len(rules.TranscriptIndex(ctx.segments).text)
            quartiles = sorted({quartile(quote.match.offset, length) for quote in ctx.valid_quotes})
            basis = "character position"
        else:
            excerpts = [quote.text.removeprefix("[--:--]").strip() for quote in ctx.quotes if quote.matches]
            positions = text_positions(speech, excerpts)
            quartiles = sorted({quartile(offset, len(speech)) for offset in positions.values()})
            basis = "character position"
        if len(quartiles) < 3:
            reasons.append(f"C02 FAIL: quotes cover {len(quartiles)} quartile(s) by {basis}; need 3")
    else:
        not_checked.append("C02 NOT CHECKED: short job")

    selection_issues, selection_warnings = check_selection(job, ctx, duration)
    reasons.extend(f"S01 FAIL: {issue}" for issue in selection_issues)
    warnings.extend(selection_warnings)
    if delivery is not None and (not delivery.is_file() or not note_path.is_file()
                                 or delivery.read_bytes() != note_path.read_bytes()):
        reasons.append("C00 FAIL: --delivery must point to note.md or its exact copy")
    return {
        "ok": not reasons,
        "long": long,
        "skipped": not long,
        "reasons": reasons,
        "warnings": warnings,
        "not_checked": not_checked,
        "duration_seconds": duration,
        "quartiles": quartiles,
    }


def _check_and_record(job: Path, delivery: Path | None) -> dict:
    status = verify_note.read_job_status(job)
    if verify_note.repair_lock(status):
        return {"ok": False, "reasons": [verify_note.REPAIR_LIMIT_MESSAGE], "warnings": [], "not_checked": []}
    inputs = verify_note.job_inputs(job)
    if inputs["note"] is not None:
        status = verify_note.record_note_revision(job, digest=inputs["note"])
        if verify_note.repair_lock(status):
            return {"ok": False, "reasons": [verify_note.REPAIR_LIMIT_MESSAGE], "warnings": [], "not_checked": []}
    result = check_job(job, delivery)
    if inputs != verify_note.job_inputs(job):
        result["ok"] = False
        result["reasons"].append("C00 FAIL: job files changed during coverage; rerun both checks")
    status = verify_note.record_gate_result(job, "coverage", result["ok"], result["reasons"], inputs=inputs)
    result["finished"] = status["finished"]
    if result["ok"] and not status["finished"]:
        result["not_checked"].append("完成 NOT CHECKED: run verify and coverage on the current job files")
    if verify_note.repair_lock(status):
        result["ok"] = False
        result["reasons"].append(verify_note.REPAIR_LIMIT_MESSAGE)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a job's single-note coverage and selection.")
    parser.add_argument("--job", type=Path, required=True, help="Job directory")
    parser.add_argument("--delivery", type=Path, help="Compatibility option for note.md or its exact copy")
    parser.add_argument("--json", action="store_true", help="Print the result JSON")
    args = parser.parse_args(argv)
    if not args.job.is_dir():
        print(f"C00 FAIL: job directory is missing: {args.job}", file=sys.stderr)
        return 2
    with verify_note.job_lock(args.job):
        result = _check_and_record(args.job, args.delivery)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for line in result["reasons"] or ["coverage ok"]:
            print(line)
        for line in result["warnings"] + result["not_checked"]:
            print(line)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
