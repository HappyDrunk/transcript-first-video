#!/usr/bin/env python3
"""Coverage gate C. Deterministic. No language model.

Faithfulness is not coverage. A long note can pass R01–R16 and
``claim_ground_check.py`` and still leave method-bearing arcs out. This
script refuses that deposit. It does not change R01–R16 or any Hall threshold.

Long means ``duration_seconds`` is greater than 300, or no clock exists and
the job has two or more ``chunks/NN.txt`` files (the host already split the
transcript). At or under 300 seconds, C01–C03 are skipped. ``verify_note.py``
still requires section quotes; this script does not add a second short-video
quote rule. R12 inside verify still treats exactly 300 seconds as long. C
uses a strict ``> 300`` so it matches the skill's inventory step.

On a long job:

- C01. Every ``chunks/NN.txt`` has ``chunks/NN.notes.md``, or the job has one
  ``inventory.md`` whose lines are ``[mm:ss] excerpt | restatement``.
  A usable ``inventory.md`` replaces the per-chunk files. Empty inventory fails.
- C02. Note quotes hit at least 3 duration quartiles
  (0–25, 25–50, 50–75, 75–100).
- C03. At least 9/10 of the inventory lines are represented in the note,
  and never fewer than 3. ``need = max(3, ceil(0.9 × lines))``. A line counts
  when a quote stamp equals that line's stamp in whole seconds, or the quote
  and the excerpt share 40 contiguous characters after whitespace is removed
  and case is folded. This is the detail-depth floor. It is not a 9/10 grade.

``--delivery PATH`` is how the pipeline passes the Feishu or chat body. The
gate is not opt-in: the run always executes this script after verify, and
always passes ``--delivery`` before sending. C04 fails when the delivery
body's CJK plus Latin letters, after YAML and blockquote lines are removed,
are under 0.9× the same count in ``note.md``. That is the summary-completeness
floor. A full-arc body clears it. A thin stub does not.

Quotes prefer ``> [mm:ss]`` or ``> [hh:mm:ss]``. A quote with no stamp takes
the start of the first ``segments.json`` cue whose text overlaps it by 40
characters, or the same overlap against a stamped transcript or chunk line
when ``segments.json`` has no timed cues.

Exit 0 when allowed. Exit 1 on FAIL. Exit 2 on usage. A failure line is
``Cxx FAIL: ...``. This script only reads the job. It does not write a file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_rules  # noqa: E402

LONG_AFTER = 300
OVERLAP = 40
MIN_HITS = 3
# 9/10 of inventory lines, and 9/10 of local prose letters. Floors, not a score.
HIT_RATE_NUMERATOR = 9
HIT_RATE_DENOMINATOR = 10
DELIVERY_RATIO = 0.9
_LETTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fffA-Za-z]")


@dataclass(frozen=True)
class InventoryLine:
    stamp: int
    excerpt: str


@dataclass(frozen=True)
class QuoteHit:
    stamp: int | None
    text: str
    moment: float | None


def fold(text: str) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def overlaps(left: str, right: str, window: int = OVERLAP) -> bool:
    """True when the two strings share ``window`` contiguous folded characters."""
    folded_left = fold(left)
    folded_right = fold(right)
    if len(folded_left) < window or len(folded_right) < window:
        return False
    short, long = (
        (folded_left, folded_right)
        if len(folded_left) <= len(folded_right)
        else (folded_right, folded_left)
    )
    for index in range(len(short) - window + 1):
        if short[index : index + window] in long:
            return True
    return False


def strip_yaml(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2]
    return text


def prose_letters(text: str) -> int:
    """CJK and Latin letters outside YAML and blockquote lines."""
    body = strip_yaml(text)
    kept = [line for line in body.splitlines() if not line.lstrip().startswith(">")]
    return len(_LETTER.findall("\n".join(kept)))


def chunk_txts(job: Path) -> list[Path]:
    folder = job / "chunks"
    if not folder.is_dir():
        return []
    found = [path for path in folder.glob("*.txt") if path.stem.isdigit()]
    return sorted(found, key=lambda path: int(path.stem))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _json_file(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(_read(path))
    except json.JSONDecodeError:
        return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def stamped_lines(path: Path) -> list[tuple[float, str]]:
    if not path.is_file():
        return []
    rows: list[tuple[float, str]] = []
    for line in _read(path).splitlines():
        stamp, text = verify_rules.parse_stamp(line.strip())
        if stamp is None or not text:
            continue
        rows.append((float(stamp), text))
    return rows


def load_cues(job: Path) -> list[tuple[float, str]]:
    """Timed cues. ``segments.json`` wins when it has a start time."""
    data = _json_file(job / "segments.json")
    cues: list[tuple[float, str]] = []
    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            start = _number(row.get("start"))
            text = row.get("text")
            if start is None or not text:
                continue
            cues.append((start, str(text)))
    if cues:
        return cues
    transcript = job / "transcript.txt"
    rows = stamped_lines(transcript)
    for path in chunk_txts(job):
        rows.extend(stamped_lines(path))
    return rows


def duration_seconds(job: Path, cues: list[tuple[float, str]]) -> float | None:
    values: list[float] = []
    status = _json_file(job / "status.json")
    if isinstance(status, dict):
        duration = _number(status.get("duration_seconds"))
        if duration is not None and duration > 0:
            values.append(duration)
    data = _json_file(job / "segments.json")
    if isinstance(data, list):
        ends: list[float] = []
        starts: list[float] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            end = _number(row.get("end"))
            start = _number(row.get("start"))
            if end is not None:
                ends.append(end)
            if start is not None:
                starts.append(start)
        if ends:
            values.append(max(ends))
        elif starts:
            values.append(max(starts))
    for path in [job / "transcript.txt", *chunk_txts(job)]:
        moments = [stamp for stamp, _text in stamped_lines(path)]
        if moments:
            values.append(max(moments))
    if cues:
        values.append(max(start for start, _text in cues))
    if not values:
        return None
    return max(values)


def is_long(job: Path, duration: float | None) -> bool:
    if duration is not None:
        return duration > LONG_AFTER
    return len(chunk_txts(job)) >= 2


def parse_inventory_text(text: str) -> list[InventoryLine]:
    lines: list[InventoryLine] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith(("- ", "* ")):
            stripped = stripped[2:].strip()
        stamp, rest = verify_rules.parse_stamp(stripped)
        if stamp is None or not rest:
            continue
        excerpt = rest.split("|", 1)[0].strip()
        if not excerpt:
            continue
        lines.append(InventoryLine(stamp=stamp, excerpt=excerpt))
    return lines


def load_inventory(job: Path) -> tuple[list[InventoryLine], str | None]:
    """Inventory lines, or a C01 reason when a long job has none."""
    inventory_path = job / "inventory.md"
    if inventory_path.is_file():
        lines = parse_inventory_text(_read(inventory_path))
        if lines:
            return lines, None
    chunks = chunk_txts(job)
    if chunks:
        missing = [
            path.name
            for path in chunks
            if not (path.parent / f"{path.stem}.notes.md").is_file()
        ]
        if missing:
            names = ", ".join(missing)
            return [], (
                "C01 FAIL: missing inventory for "
                f"{names}; write chunks/NN.notes.md or inventory.md"
            )
        lines: list[InventoryLine] = []
        for path in chunks:
            notes = path.parent / f"{path.stem}.notes.md"
            lines.extend(parse_inventory_text(_read(notes)))
        if not lines:
            return [], "C01 FAIL: inventory has no [mm:ss] lines"
        return lines, None
    if not inventory_path.is_file():
        return [], "C01 FAIL: long video has no inventory.md and no chunks/NN.notes.md"
    return [], "C01 FAIL: inventory has no [mm:ss] lines"


def quotes_in(note: str) -> list[tuple[int | None, str]]:
    found: list[tuple[int | None, str]] = []
    for line in strip_yaml(note).splitlines():
        stripped = line.strip()
        if not stripped.startswith(">"):
            continue
        raw = stripped.lstrip(">").strip()
        if not raw:
            continue
        stamp, text = verify_rules.parse_stamp(raw)
        if text:
            found.append((stamp, text))
    return found


def place_quotes(note: str, cues: list[tuple[float, str]]) -> list[QuoteHit]:
    placed: list[QuoteHit] = []
    for stamp, text in quotes_in(note):
        moment: float | None
        if stamp is not None:
            moment = float(stamp)
        else:
            moment = None
            for start, cue in cues:
                if overlaps(text, cue):
                    moment = start
                    break
        placed.append(QuoteHit(stamp=stamp, text=text, moment=moment))
    return placed


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


def line_represented(line: InventoryLine, quotes: list[QuoteHit]) -> bool:
    for quote in quotes:
        if quote.moment is not None and int(quote.moment) == line.stamp:
            return True
        if quote.stamp is not None and quote.stamp == line.stamp:
            return True
        if overlaps(quote.text, line.excerpt):
            return True
    return False


def check_job(job: Path, delivery: Path | None = None) -> dict:
    """Run coverage gate C. ``reasons`` are ``Cxx FAIL: ...`` lines."""
    reasons: list[str] = []
    note_path = job / "note.md"
    has_transcript = (job / "transcript.txt").is_file() or bool(chunk_txts(job))
    if not note_path.is_file():
        reasons.append("C00 FAIL: note.md is missing")
    if not has_transcript:
        reasons.append("C00 FAIL: no transcript.txt and no chunks")
    note_text = _read(note_path) if note_path.is_file() else ""
    cues = load_cues(job) if has_transcript else []
    duration = duration_seconds(job, cues) if has_transcript else None
    long = is_long(job, duration) if has_transcript else False
    quotes = place_quotes(note_text, cues) if note_text else []
    quartiles: list[int] = []
    inventory: list[InventoryLine] = []
    hits = 0
    need = 0
    if reasons:
        long = False
    elif long:
        inventory, inventory_reason = load_inventory(job)
        if inventory_reason:
            reasons.append(inventory_reason)
        if duration is None or duration <= 0:
            reasons.append(
                "C02 FAIL: duration is unknown, so quotes cannot be placed in quartiles; need 3"
            )
        else:
            found = {
                quartile(quote.moment, duration)
                for quote in quotes
                if quote.moment is not None
            }
            quartiles = sorted(found)
            if len(quartiles) < 3:
                reasons.append(
                    "C02 FAIL: quotes cover "
                    f"{len(quartiles)} quartile(s) of a {int(duration)}s transcript; need 3"
                )
        if inventory:
            need = hits_required(len(inventory))
            hits = sum(1 for line in inventory if line_represented(line, quotes))
            if hits < need:
                reasons.append(
                    "C03 FAIL: "
                    f"{hits} of {len(inventory)} inventory lines are in the note; "
                    f"need {need} (9/10 of the lines, at least 3)"
                )
    delivery_letters = None
    note_letters = prose_letters(note_text) if note_text else 0
    ratio = None
    if delivery is not None:
        if not delivery.is_file():
            reasons.append("C04 FAIL: delivery file is missing")
        elif note_path.is_file():
            delivery_letters = prose_letters(_read(delivery))
            if note_letters <= 0:
                reasons.append("C04 FAIL: note prose has no CJK or Latin letters to compare")
            else:
                ratio = delivery_letters / note_letters
                if delivery_letters < DELIVERY_RATIO * note_letters:
                    reasons.append(
                        "C04 FAIL: delivery prose letters "
                        f"{delivery_letters} are under {DELIVERY_RATIO} × "
                        f"note prose letters {note_letters}"
                    )
    skipped = not long and not any(reason.startswith("C00") for reason in reasons)
    return {
        "ok": not reasons,
        "long": long,
        "skipped": skipped,
        "reasons": reasons,
        "duration_seconds": duration,
        "quartiles": quartiles,
        "inventory_lines": len(inventory),
        "inventory_hits": hits,
        "inventory_need": need,
        "note_letters": note_letters,
        "delivery_letters": delivery_letters,
        "delivery_ratio": ratio,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coverage gate C for a job directory.")
    parser.add_argument("--job", type=Path, required=True, help="Job directory")
    parser.add_argument(
        "--delivery",
        type=Path,
        default=None,
        help="Feishu or chat body. Refuses a thin stub against note.md.",
    )
    parser.add_argument("--json", action="store_true", help="Print the result JSON")
    args = parser.parse_args(argv)
    job = args.job
    if not job.is_dir():
        print(f"C00 FAIL: job directory is missing: {job}", file=sys.stderr)
        return 2
    result = check_job(job, args.delivery)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["reasons"]:
        print("\n".join(result["reasons"]))
    elif result["skipped"]:
        duration = result["duration_seconds"]
        if duration is None:
            print(
                "C SKIP: duration is unknown and the job is a single stretch; "
                "quartile and inventory checks not applied"
            )
        else:
            print(
                "C SKIP: at or under 5 minutes "
                f"({int(duration)}s); quartile and inventory checks not applied"
            )
    else:
        print("coverage ok")
    return 1 if result["reasons"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
