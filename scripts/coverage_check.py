#!/usr/bin/env python3
"""Coverage gate C. Deterministic. No language model.

Faithfulness is not coverage. A long note can pass R01–R17 and
``claim_ground_check.py`` and still leave method-bearing arcs out. This
script refuses that deposit. It does not change R01–R17 or any Hall threshold.

Long means ``duration_seconds`` is greater than 300, or no clock exists and
the job has two or more ``chunks/NN.txt`` files (the host already split the
transcript). At or under 300 seconds, C01–C03 are skipped. ``verify_note.py``
still requires section quotes; this script does not add a second short-video
quote rule. R12 inside verify still treats exactly 300 seconds as long. C
uses a strict ``> 300`` so it matches the skill's inventory step.

On a long job:

- C01. Every ``chunks/NN.txt`` has ``chunks/NN.notes.md``, or the job has one
  ``inventory.md`` whose lines are ``[mm:ss] excerpt | restatement``.
  Untimed excerpts can use ``[--:--]``. A usable ``inventory.md`` replaces
  the per-chunk files. Empty inventory fails.
- C02. Note quotes hit at least 3 quartiles, measured by time when duration
  is known and by character position in the full transcript otherwise.
- C03. At least 9/10 of the inventory lines are represented in the note,
  and never fewer than 3. ``need = max(3, ceil(0.9 × lines))``. A line counts
  when a quote stamp equals that line's stamp in whole seconds, or the quote
  and the excerpt share 40 contiguous characters after whitespace is removed
  and case is folded. This is the detail-depth floor. It is not a 9/10 grade.

C03 counts lines the job already wrote. It does not measure inventory
coverage of the full transcript. A thin inventory can still pass. The gate stops
"wrote an inventory and then ignored it." It does not stop "under-extracted
when the inventory was written."

A long job with a loaded inventory may also print ``C WARN``. That line is
not a failure and does not change the exit code. It fires when the row count
is under one line per 10 minutes (``THIN_SECONDS_PER_LINE``), or when two or
more ``chunks/NN.txt`` files exist and there are fewer inventory lines than
those files. Silence is not a completeness proof.

``--delivery PATH`` checks the reader-facing article against ``note.md``.
C04 checks the structure for its declared type, the time links on middle
claims, grounding of numbers and names, the marked explanation blocks, and
coverage of at least 90% of distinct note quote times. Time links allow a
15-second difference. With no delivery path, C04 is not checked.

Quotes prefer ``> [mm:ss]`` or ``> [hh:mm:ss]``. A quote with no stamp takes
the start of the first ``segments.json`` cue whose text overlaps it by 40
characters, or the same overlap against a stamped transcript or chunk line
when ``segments.json`` has no timed cues.

``check_job`` only reads the job; the CLI records coverage, finished, and repair
state in ``status.json``. Exit 0 when allowed, 1 on FAIL, and 2 on usage.
FAIL, WARN and NOT CHECKED diagnostics are reported separately.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import knowledge_note  # noqa: E402
import verify_note  # noqa: E402
import verify_rules  # noqa: E402

LONG_AFTER = 300
OVERLAP = 40
MIN_HITS = 3
# 9/10 of inventory lines, and 9/10 of local quote times.
HIT_RATE_NUMERATOR = 9
HIT_RATE_DENOMINATOR = 10
DELIVERY_RATIO = 0.9
DELIVERY_TIME_TOLERANCE = 15
# Warning floor only. Not a C01–C04 threshold and not a pass/fail change.
# One inventory line per 10 minutes, or fewer lines than chunk files.
THIN_SECONDS_PER_LINE = 600
_FRONTMATTER = re.compile(r"\A---\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$", re.MULTILINE)
_LIST_ITEM = re.compile(r"^\s*(?:[-+*][ \t]+(?:\d+[.)][ \t]+)?|\d+[.)][ \t]+)")
_INLINE_LIST_ITEM = re.compile(r"([：:；;])[ \t]*\d+[.)][ \t]+")
_DELIVERY_TIME = re.compile(r"⏱\ufe0f?[ \t]+((?:\d{1,2}:)?\d{1,2}:[0-5]\d)(?![\d:])")
_CALLOUT = re.compile(r"^>\s*\[!(note|tip|warning)\]\s*(.*)$")
_TERM_TITLE = re.compile(r"^术语\s*[:：]\s*(.*)$")
_TERM_ALIAS_SEPARATOR = re.compile(r"[/／()（）]")
_HYPHEN = re.compile(r"[-\u2010\u2011]")
_CAPTION_CORRECTION = re.compile(r"^字幕写作\s*[:：]?\s*(.+?)[，,]\s*实为\s*[:：]?\s*(.+)$")
_CORRECTION_TARGET = re.compile(
    r'^(?:`[^`]+`|“[^”]+”|「[^」]+」|"[^"]+")|^.+?(?=[，,。；;！？（(]|\.(?:\s|$)|$)'
)
_CORRECTION_QUOTES = "`“”「」\""
_ANALOGY_LIMIT = re.compile(r"^不成立的地方\s*[:：]\s*\S")
_NAMED_ZH_TERM = re.compile(
    r"(?:名为|名叫|公司|项目|品牌|机构)[ \t]*[“「]([^”」]+)[”」]"
)
_SPOKEN_DIGITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_SPOKEN_DIGIT = "|".join(_SPOKEN_DIGITS)
_SPOKEN_DECIMAL = re.compile(
    rf"({verify_rules._EN_NUMBER.pattern})[ \t]+point[ \t]+"
    rf"((?:{_SPOKEN_DIGIT})(?:[ \t]+(?:{_SPOKEN_DIGIT}))*)\b",
    re.IGNORECASE,
)
_C04_START = ("先记住一句话", "这场在谈什么、谁")
_C04_END = ("可复用做法", "翻车或别用", "今天立刻动手一步")
_C04_MIDDLE = {
    "讲座": ("主线论点",),
    "访谈": ("话题", "意见不一致的地方"),
    "大会": ("发布或主张了什么", "有证据的 / 只是说法"),
    "演示": ("演示了什么", "关键数字与条件"),
}
_CONFERENCE_SUBHEADINGS = ("演示过或给出数据", "只是口头声称")


@dataclass(frozen=True)
class InventoryLine:
    stamp: int | None
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
    return _FRONTMATTER.sub("", text, count=1)


def chunk_txts(job: Path) -> list[Path]:
    folder = job / "chunks"
    if not folder.is_dir():
        return []
    found = [path for path in folder.glob("*.txt") if path.stem.isdigit()]
    return sorted(found, key=lambda path: int(path.stem))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


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
    return max((value for value in values if value > 0), default=None)


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
        if stripped.startswith("[--:--]"):
            stamp, rest = None, stripped.removeprefix("[--:--]").strip()
        else:
            stamp, rest = verify_rules.parse_stamp(stripped)
            if stamp is None:
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
            return [], "C01 FAIL: inventory has no [mm:ss] or [--:--] excerpt lines"
        return lines, None
    if not inventory_path.is_file():
        return [], "C01 FAIL: long video has no inventory.md and no chunks/NN.notes.md"
    return [], "C01 FAIL: inventory has no [mm:ss] or [--:--] excerpt lines"


def quotes_in(note: str) -> list[tuple[int | None, str]]:
    found: list[tuple[int | None, str]] = []
    for line in strip_yaml(note).splitlines():
        stripped = line.strip()
        if not stripped.startswith(">"):
            continue
        raw = stripped.lstrip(">").strip()
        if not raw:
            continue
        stamp, text = verify_rules.parse_stamp(raw.removeprefix("[--:--]"))
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


def transcript_text(job: Path) -> str:
    transcript = job / "transcript.txt"
    if transcript.is_file():
        body = _read(transcript)
        if body.strip():
            return body
    return "\n".join(_read(path) for path in chunk_txts(job))


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


def inventory_thin_warning(
    line_count: int,
    duration: float | None,
    chunk_count: int,
) -> str | None:
    """Sparse-inventory notice. Not a fail, and not a completeness proof."""
    if line_count <= 0:
        return None
    parts: list[str] = []
    if (
        duration is not None
        and duration > LONG_AFTER
        and line_count * THIN_SECONDS_PER_LINE < duration
    ):
        parts.append(
            f"{line_count} inventory lines for a {int(duration)}s transcript "
            f"(under one line per {THIN_SECONDS_PER_LINE // 60} minutes)"
        )
    if chunk_count >= 2 and line_count < chunk_count:
        parts.append(
            f"{line_count} inventory lines for {chunk_count} chunks "
            "(fewer lines than chunk files)"
        )
    if not parts:
        return None
    return (
        "C WARN: "
        + "; ".join(parts)
        + ". Coverage C checks the note against this inventory; "
        "it does not prove the inventory listed the transcript"
    )


def line_represented(
    line: InventoryLine, quotes: list[QuoteHit], positions: dict[str, int],
) -> bool:
    if line.stamp is None and line.excerpt not in positions:
        return False
    for quote in quotes:
        if quote.moment is not None and int(quote.moment) == line.stamp:
            return True
        if quote.stamp is not None and quote.stamp == line.stamp:
            return True
        if overlaps(quote.text, line.excerpt):
            return True
    return False


def delivery_parts(body: str) -> tuple[list[str], list[list[str]]]:
    """Split Markdown into prose paragraphs/list items and explicit callouts."""
    prose: list[str] = []
    blocks: list[list[str]] = []
    paragraph: list[str] = []
    block: list[str] | None = None
    for raw in body.splitlines() + [""]:
        line = raw.strip()
        if block is not None and line.startswith(">") and not line.lstrip("> ").startswith("[!"):
            block.append(line[1:].strip())
            continue
        block = None
        is_callout = line.startswith(">") and line.lstrip("> ").startswith("[!")
        item = _LIST_ITEM.match(line)
        if (not line or item or is_callout) and paragraph:
            prose.append("\n".join(paragraph))
            paragraph = []
        if is_callout:
            block = [line]
            blocks.append(block)
        elif line:
            paragraph.append(line[item.end() :] if item else line)
    return prose, blocks


@dataclass
class DeliverySection:
    level: int
    heading: str
    prose: list[str]
    blocks: list[list[str]]


def delivery_sections(body: str) -> list[DeliverySection]:
    headings = list(_HEADING.finditer(body))
    starts = [heading.start() for heading in headings] + [len(body)]
    prose, blocks = delivery_parts(body[:starts[0]])
    sections = [DeliverySection(0, "", prose, blocks)]
    for index, heading in enumerate(headings):
        prose, blocks = delivery_parts(body[heading.end() : starts[index + 1]])
        sections.append(DeliverySection(len(heading[1]), heading[2], prose, blocks))
    return sections


def delivery_structure(sections: list[DeliverySection], kind: str) -> list[str]:
    issues: list[str] = []
    if sections[0].prose or sections[0].blocks:
        issues.append("orphan content before the first heading")
    expected_middle = _C04_MIDDLE.get(kind)
    if expected_middle is None:
        issues.append("frontmatter type must be 讲座, 访谈, 大会 or 演示")
    else:
        expected = _C04_START + expected_middle + _C04_END
        actual = tuple(section.heading for section in sections if section.level == 2)
        if actual != expected:
            issues.append(f"expected H2 sections in order: {' / '.join(expected)}")
    parent = ""
    children: list[str] = []
    middle_headings = expected_middle or ()
    for index, section in enumerate(sections[1:], 1):
        if section.level == 2:
            parent = section.heading
        elif section.level != 3 or parent not in middle_headings:
            issues.append(f"unexpected heading: {section.heading}")
        elif parent == "有证据的 / 只是说法" and section.heading in _CONFERENCE_SUBHEADINGS:
            children.append(section.heading)
        has_subheading = (
            section.level == 2 and section.heading in middle_headings
            and index + 1 < len(sections) and sections[index + 1].level == 3
        )
        if section.level == 2 and section.heading in {"话题", "有证据的 / 只是说法"} and not has_subheading:
            issues.append(f"section needs subheadings: {section.heading}")
        elif not has_subheading and not any(
            char.isalnum() for char in _DELIVERY_TIME.sub("", "\n".join(section.prose))
        ):
            issues.append(f"empty section: {section.heading}")
        if section.heading == _C04_END[-1] and len(section.prose) > 1:
            orphan = section.prose[1].splitlines()[0]
            issues.append(f"orphan text after {_C04_END[-1]}: {orphan[:80]}")
    if kind == "大会" and tuple(children) != _CONFERENCE_SUBHEADINGS:
        issues.append("有证据的 / 只是说法 needs 演示过或给出数据 and 只是口头声称 in order")
    return issues


def delivery_times(prose: str) -> set[int]:
    return {
        sum(int(part) * 60**index for index, part in enumerate(reversed(clock.split(":"))))
        for clock in _DELIVERY_TIME.findall(prose)
    }


def time_is_covered(stamp: int, times: set[int]) -> bool:
    return any(abs(stamp - other) <= DELIVERY_TIME_TOLERANCE for other in times)


def delivery_trace(
    sections: list[DeliverySection], note_times: set[int], kind: str,
) -> list[str]:
    issues: list[str] = []
    parent = ""
    for section in sections[1:]:
        if section.level == 2:
            parent = section.heading
        if parent not in _C04_MIDDLE.get(kind, ()):
            continue
        for index, claim in enumerate(section.prose, 1):
            if parent == "意见不一致的地方" and re.fullmatch(
                r"不适用(?:[（(][^）)]+[）)])?[。.]?", claim,
            ):
                continue
            times = delivery_times(claim)
            label = f"{section.heading}, claim {index}"
            if not times:
                issues.append(f"{label} is missing a ⏱ time link")
            for stamp in sorted(times):
                if not time_is_covered(stamp, note_times):
                    minutes, seconds = divmod(stamp, 60)
                    issues.append(f"{label}: ⏱ {minutes:02d}:{seconds:02d} has no note quote within 15s")
    return issues


def term_occurs(term: str, source: str) -> bool:
    if not re.search(r"[A-Za-z0-9]", term):
        return fold(term) in fold(source)
    pattern = r"\s+".join(map(re.escape, term.split()))
    if re.match(r"[A-Za-z0-9]", term):
        pattern = r"(?<![A-Za-z0-9])" + pattern
    if re.search(r"[A-Za-z0-9]$", term):
        pattern += r"(?![A-Za-z0-9])"
    return bool(re.search(pattern, source, re.IGNORECASE))


def caption_corrections(blocks: list[list[str]], transcript: str) -> list[str]:
    """Return corrected spellings from marked blocks backed by the transcript."""
    corrections: list[str] = []
    for header, *lines in blocks:
        match = _CALLOUT.fullmatch(header)
        if match is None or match.groups() != ("warning", "字幕更正"):
            continue
        for line in lines:
            correction = _CAPTION_CORRECTION.fullmatch(line)
            if correction is None:
                continue
            original = correction[1].strip().strip(_CORRECTION_QUOTES).strip()
            target = _CORRECTION_TARGET.match(correction[2].strip())
            if not original or target is None or not term_occurs(original, transcript):
                continue
            corrected = target[0].strip().strip(_CORRECTION_QUOTES).strip()
            if corrected:
                corrections.append(corrected)
    return corrections


def explanation_issues(
    blocks: list[list[str]], transcript: str, corrections: list[str],
) -> list[str]:
    issues: list[str] = []
    sources = [_HYPHEN.sub(" ", text) for text in (transcript, *corrections)]
    for header, *lines in blocks:
        match = _CALLOUT.fullmatch(header)
        if match is None:
            issues.append(f"unknown explanation block: {header}")
            continue
        kind, title = match.groups()
        term = _TERM_TITLE.fullmatch(title)
        if kind == "note" and term and term[1].strip():
            word = term[1].strip()
            aliases = _TERM_ALIAS_SEPARATOR.split(_HYPHEN.sub(" ", word))
            if not any(term_occurs(alias, source) for alias in map(str.strip, aliases) if alias for source in sources):
                issues.append(f"term {word!r} is absent from the transcript")
        elif kind == "tip" and title in {"类比（Claude 补充）", "类比"}:
            if not any(_ANALOGY_LIMIT.match(line) for line in lines):
                issues.append("analogy block needs 不成立的地方 and a description")
        elif kind != "warning" or title != "字幕更正":
            issues.append(f"unknown explanation block: {header}")
    return issues


def proper_names(text: str) -> list[str]:
    """Find capitalized Latin names, marked titles and explicitly named entities."""
    names = [match[1].strip() for match in verify_rules._BOOK.finditer(text)]
    names.extend(match[1].strip() for match in _NAMED_ZH_TERM.finditer(text))
    for match in verify_rules._LATIN_WORD.finditer(text):
        word = match[0]
        if len(word) < 2 or not word[0].isupper() or word.casefold() in verify_rules._PROPER_SKIP:
            continue
        if word[1:].islower() and verify_rules._is_sentence_start(text, match.start()):
            continue
        names.append(word)
    return names


def number_mentions(text: str) -> list[tuple[float, float, str]]:
    mentions: list[tuple[float, float, str]] = []

    def decimal(match: re.Match[str]) -> str:
        whole = verify_rules.source_number_mentions(match[1])[0][0]
        fraction = "".join(str(_SPOKEN_DIGITS.index(word)) for word in match[2].lower().split())
        value = float(f"{int(whole)}.{fraction}")
        mentions.append((value, value, match[0]))
        return " "

    # Phase 1B recognizes the integer words on each side of a spoken decimal.
    # Read them together so "three point eight" supports 3.8.
    text = _SPOKEN_DECIMAL.sub(decimal, text)
    return mentions + verify_rules.body_number_mentions(text) + verify_rules.source_number_mentions(text)


def delivery_grounding(
    prose: str, note_text: str, quotes: list[QuoteHit], corrections: list[str],
) -> list[str]:
    note_body = "\n".join(
        line for line in strip_yaml(note_text).splitlines() if not line.lstrip().startswith(">")
    )
    fields = knowledge_note.parse_frontmatter(note_text) or {}
    source = "\n".join([
        note_body, *(quote.text for quote in quotes),
        *(fields.get(field, "") for field in ("title", "channel", "published", "duration_seconds")),
    ])
    support = number_mentions(source)
    for corrected in corrections:
        support.extend(number_mentions(corrected))
    missing_numbers = {
        label for low, high, label in number_mentions(prose)
        if not any(source_low <= high and source_high >= low for source_low, source_high, _ in support)
    }
    missing_names = {
        name for name in proper_names(prose)
        if name and not any(term_occurs(name, evidence) for evidence in (source, *corrections))
    }
    return [
        *(f"number {label!r} is absent from note.md" for label in sorted(missing_numbers)),
        *(f"name {name!r} is absent from note.md" for name in sorted(missing_names)),
    ]


def check_delivery(
    delivery: str, note: str, quotes: list[QuoteHit], transcript: str,
) -> tuple[list[str], int, int]:
    sections = delivery_sections(strip_yaml(delivery))
    fields = knowledge_note.parse_frontmatter(delivery) or {}
    kind = fields.get("type", "")
    note_times = {quote.stamp for quote in quotes if quote.stamp is not None}
    prose = "\n".join(part for section in sections for part in section.prose)
    blocks = [block for section in sections for block in section.blocks]
    corrections = caption_corrections(blocks, transcript)
    issues_d = explanation_issues(blocks, transcript, corrections)
    prose_for_grounding = _INLINE_LIST_ITEM.sub(r"\1", _DELIVERY_TIME.sub("", prose))
    marked_headings = {*_C04_START, *_C04_END, *_C04_MIDDLE.get(kind, ()), *_CONFERENCE_SUBHEADINGS}
    prose_for_grounding += "\n" + "\n".join(
        section.heading for section in sections if section.heading not in marked_headings
    )
    times = delivery_times(prose)
    covered = sum(time_is_covered(stamp, times) for stamp in note_times)
    issues_e: list[str] = []
    if not note_times:
        issues_e.append("note.md has no stamped quotes")
    elif covered / len(note_times) < DELIVERY_RATIO:
        issues_e.append(f"{covered} of {len(note_times)} note quote times covered; need 9/10 within 15s")
    checks = (
        ("C04a", delivery_structure(sections, kind)),
        ("C04b", delivery_trace(sections, note_times, kind)),
        ("C04c", delivery_grounding(prose_for_grounding, note, quotes, corrections)),
        ("C04d", issues_d),
        ("C04e", issues_e),
    )
    reasons = [f"C04 FAIL: {code} {issue}" for code, issues in checks for issue in issues]
    return reasons, covered, len(note_times)


def check_job(job: Path, delivery: Path | None = None) -> dict:
    """Run coverage gate C. ``reasons`` are ``Cxx FAIL`` lines.

    ``warnings`` and ``not_checked`` describe non-failing outcomes.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    not_checked: list[str] = []
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
        not_checked.append("C01–C03 NOT CHECKED: note or transcript missing")
    elif long:
        inventory, inventory_reason = load_inventory(job)
        if inventory_reason:
            reasons.append(inventory_reason)
        untimed_excerpts = [line.excerpt for line in inventory if line.stamp is None]
        positions: dict[str, int] = {}
        if duration is None or untimed_excerpts:
            transcript = transcript_text(job)
            excerpts = untimed_excerpts.copy()
            if duration is None:
                excerpts += [quote.text for quote in quotes]
            positions = text_positions(transcript, excerpts)
        if duration is None:
            quartiles = sorted({
                quartile(positions[quote.text], len(transcript))
                for quote in quotes if quote.text in positions
            })
            basis = "transcript character positions"
        else:
            quartiles = sorted({
                quartile(quote.moment, duration)
                for quote in quotes if quote.moment is not None
            })
            basis = f"{int(duration)}s transcript"
        if len(quartiles) < 3:
            reasons.append(f"C02 FAIL: quotes cover {len(quartiles)} quartile(s) by {basis}; need 3")
        if inventory:
            need = hits_required(len(inventory))
            hits = sum(line_represented(line, quotes, positions) for line in inventory)
            if hits < need:
                reasons.append(
                    "C03 FAIL: "
                    f"{hits} of {len(inventory)} inventory lines are in the note; "
                    f"need {need} (9/10 of the lines, at least 3)"
                )
            warning = inventory_thin_warning(
                len(inventory),
                duration,
                len(chunk_txts(job)),
            )
            if warning:
                warnings.append(warning)
        else:
            not_checked.append("C03 NOT CHECKED: no usable inventory")
    else:
        not_checked.append("C01–C03 NOT CHECKED: short job")
    covered = total_times = None
    if delivery is None:
        not_checked.append("C04 NOT CHECKED: no --delivery path provided")
    elif not delivery.is_file():
        reasons.append("C04 FAIL: delivery file is missing")
    elif not note_path.is_file() or not has_transcript:
        not_checked.append("C04 NOT CHECKED: note or transcript missing")
    else:
        speech = "\n".join(verify_rules.parse_stamp(line)[1] for line in transcript_text(job).splitlines())
        delivery_reasons, covered, total_times = check_delivery(_read(delivery), note_text, quotes, speech)
        reasons.extend(delivery_reasons)
    skipped = not long and not any(reason.startswith("C00") for reason in reasons)
    return {
        "ok": not reasons,
        "long": long,
        "skipped": skipped,
        "reasons": reasons,
        "warnings": warnings,
        "not_checked": not_checked,
        "duration_seconds": duration,
        "quartiles": quartiles,
        "inventory_lines": len(inventory),
        "inventory_hits": hits,
        "inventory_need": need,
        "delivery_quote_times_covered": covered,
        "note_quote_times": total_times,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coverage gate C for a job directory.")
    parser.add_argument("--job", type=Path, required=True, help="Job directory")
    parser.add_argument(
        "--delivery",
        type=Path,
        default=None,
        help="Delivery article to check against note.md and the transcript.",
    )
    parser.add_argument("--json", action="store_true", help="Print the result JSON")
    args = parser.parse_args(argv)
    job = args.job
    if not job.is_dir():
        print(f"C00 FAIL: job directory is missing: {job}", file=sys.stderr)
        return 2
    status = verify_note.read_job_status(job)
    if verify_note.repair_lock(status):
        result = {
            "ok": False,
            "reasons": [verify_note.REPAIR_LIMIT_MESSAGE],
            "warnings": [],
            "not_checked": ["C00–C04 NOT CHECKED: repair limit reached"],
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print("C FAIL: " + verify_note.REPAIR_LIMIT_MESSAGE)
            print(*result["not_checked"], sep="\n")
        return 1
    note_path = job / "note.md"
    if note_path.is_file():
        status = verify_note.record_note_revision(job, _read(note_path))
        if verify_note.repair_lock(status):
            result = {
                "ok": False,
                "reasons": [verify_note.REPAIR_LIMIT_MESSAGE],
                "warnings": [],
                "not_checked": ["C00–C04 NOT CHECKED: repair limit reached"],
            }
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            else:
                print("C FAIL: " + verify_note.REPAIR_LIMIT_MESSAGE)
                print(*result["not_checked"], sep="\n")
            return 1
    result = check_job(job, args.delivery)
    status = verify_note.record_gate_result(
        job, "coverage", bool(result["ok"]), result.get("reasons") or []
    )
    if verify_note.repair_lock(status):
        result["ok"] = False
        result["reasons"] = [verify_note.REPAIR_LIMIT_MESSAGE]
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["reasons"]:
            print(*result["reasons"], sep="\n")
        elif not result["skipped"] or result["delivery_quote_times_covered"] is not None:
            print("coverage ok")
        for line in result["warnings"] + result["not_checked"]:
            print(line)
    return 1 if result["reasons"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
