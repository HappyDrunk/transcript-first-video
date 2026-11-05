#!/usr/bin/env python3
"""Deterministic note rules R01–R17.

Each rule returns ``(rule_id, ok, message)``. Callers prefix a failure as
``R07 FAIL: ...``. No rule calls a language model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import knowledge_note
import quality_gate

QUOTE_WINDOW = knowledge_note.QUOTE_WINDOW
_STAMP = re.compile(r"^\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*")
_DIGIT = re.compile(r"\d+(?:\.\d+)?%?")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_BOOK = re.compile(r"《([^》]{1,40})》")
_QUOTED_TERM = re.compile(r"[“\"]([^”\"]{2,40})[”\"]|「([^」]{2,40})」")
_SENTENCE_SPLIT = re.compile(r"[.!?。！？]+")
_LAUNDER = re.compile(
    r"("
    r"asr[\s-]*(quality|fail)"
    r"|transcription fail"
    r"|transcript (failed|failure|is garbage|is unusable|is nonsense)"
    r"|quality[-\s]*gate failure"
    r"|speech recognition failed"
    r"|转写失败"
    r"|识别失败"
    r"|hallucinat"
    r")",
    re.IGNORECASE,
)
_SALAD_PHRASE = re.compile(
    r"("
    r"uses these words"
    r"|marking words"
    r"|the spoken move"
    r"|concrete pieces are"
    r"|situation worth keeping"
    r"|能点名的是"
    r"|涉及到的具体东西"
    r"|今天只做这一步"
    r"|标记词"
    r")",
    re.IGNORECASE,
)
_FAILED_STATUS = {
    "failed",
    "not_finished",
    "quality_gate_failed",
    "no-extractable-content",
}
_EN_VERBS = {
    "ask", "call", "check", "copy", "count", "cut", "do", "don't", "drop",
    "export", "fill", "get", "keep", "leave", "list", "loosen", "mark",
    "move", "name", "open", "paste", "pick", "publish", "put", "raise",
    "read", "review", "send", "set", "skip", "slide", "snip", "start",
    "stop", "turn", "wait", "water", "write",
}
_ZH_VERB_PREFIX = (
    "不要", "别再", "别", "请", "倒", "拨", "剪", "写", "问", "停", "开",
    "关", "放", "拿", "浇", "垫", "移", "记",
)
_EN_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "your", "you", "are",
    "was", "not", "but", "its", "they", "them", "then", "than", "into", "about",
    "just", "what", "when", "where", "which", "who", "how", "can", "our",
    "their", "there", "here", "all", "have", "has", "had", "been", "being",
    "will", "would", "should", "could", "after", "before", "until", "only",
    "today", "again", "once", "over", "under", "into", "onto", "per",
}
_PROPER_SKIP = _EN_STOP | _EN_VERBS | {
    "a", "an", "or", "if", "so", "as", "at", "by", "in", "of", "on", "to",
    "is", "it", "we", "be", "do", "no", "yes", "new", "old", "out", "up",
}


@dataclass
class Quote:
    raw: str
    text: str
    stamp: int | None


@dataclass
class SectionView:
    heading: str
    body: str
    prose: str
    quotes: list[Quote]
    inapplicable: str | None


@dataclass
class RuleContext:
    transcript_path: Path
    note: str
    expected_lang: str | None = None
    confidence: float | None = None
    job_status: str | None = None
    exists: bool = False
    raw: str = ""
    gate: quality_gate.GateResult | None = None
    fields: dict | None = None
    sections: list[SectionView] = field(default_factory=list)
    segments: list = field(default_factory=list)
    cited: bool = False
    quoted: bool = False


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _fold(text: str) -> str:
    return _compact(text).casefold()


def parse_stamp(text: str) -> tuple[int | None, str]:
    match = _STAMP.match(text.strip())
    if not match:
        return None, text.strip()
    if match.group(3) is not None:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
    else:
        hours = 0
        minutes = int(match.group(1))
        seconds = int(match.group(2))
    return hours * 3600 + minutes * 60 + seconds, text.strip()[match.end() :].strip()


def _quotes_in(body: str) -> list[Quote]:
    found: list[Quote] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith(">"):
            continue
        raw = stripped.lstrip(">").strip()
        if not raw:
            continue
        stamp, text = parse_stamp(raw)
        found.append(Quote(raw=raw, text=text, stamp=stamp))
    return found


def build_context(
    transcript: Path,
    note: str,
    *,
    expected_lang: str | None = None,
    confidence: float | None = None,
    job_status: str | None = None,
) -> RuleContext:
    exists = transcript.is_file()
    raw = ""
    gate = None
    if exists:
        raw = transcript.read_text(encoding="utf-8", errors="replace")
        gate = quality_gate.assess(raw, expected_lang=expected_lang, confidence=confidence)
    fields = knowledge_note.parse_frontmatter(note)
    if job_status is None and fields:
        job_status = fields.get("job_status") or None
    sections: list[SectionView] = []
    for heading, body in knowledge_note._section_bodies(note):
        if heading not in knowledge_note.SECTIONS:
            continue
        prose = knowledge_note._prose_outside_quotes(body)
        sections.append(
            SectionView(
                heading=heading,
                body=body,
                prose=prose,
                quotes=_quotes_in(body),
                inapplicable=knowledge_note.inapplicable_reason(prose),
            )
        )
    speech = gate.text if gate is not None else ""
    segments = _stamped_lines(raw) or (quality_gate.prepare_segments(raw) if raw else [])
    quoted = bool(
        exists and gate is not None and _window_in(note, _verbatim_haystack(segments, speech))
    )
    return RuleContext(
        transcript_path=transcript,
        note=note,
        expected_lang=expected_lang,
        confidence=confidence,
        job_status=(job_status or "").strip() or None,
        exists=exists,
        raw=raw,
        gate=gate,
        fields=fields,
        sections=sections,
        segments=segments,
        cited=_cites(note, transcript),
        quoted=quoted,
    )


def _cites(note: str, transcript: Path) -> bool:
    folded = note.replace("\\", "/")
    for form in _citation_forms(transcript):
        if form.replace("\\", "/") in folded:
            return True
    return False


def _citation_forms(transcript: Path) -> set[str]:
    forms = {str(transcript), str(transcript).replace("\\", "/")}
    forms.add("./" + str(transcript).replace("\\", "/").lstrip("./"))
    try:
        resolved = transcript.resolve()
    except OSError:
        resolved = None
    if resolved is not None:
        forms.add(str(resolved))
        forms.add(resolved.as_posix())
        try:
            relative = resolved.relative_to(Path.cwd().resolve())
            forms.add(relative.as_posix())
            forms.add("./" + relative.as_posix())
        except ValueError:
            pass
    return {form for form in forms if form and form not in {".", "./"} and len(form) >= 3}


def _window_in(note: str, speech: str, window: int = QUOTE_WINDOW) -> bool:
    compact_note = _fold(note)
    compact = _fold(speech)
    if window <= 0 or len(compact) < window or len(compact_note) < window:
        return False
    source, haystack = (compact_note, compact) if len(compact_note) <= len(compact) else (compact, compact_note)
    last = len(source) - window + 1
    for index in range(last):
        if source[index : index + window] in haystack:
            return True
    return False


def _stamped_lines(raw: str) -> list:
    rows = []
    for line in raw.splitlines():
        stamp, text = parse_stamp(line.strip())
        if stamp is None or not text:
            continue
        rows.append(quality_gate.Segment(float(stamp), float(stamp), text))
    return rows


def _speech(ctx: RuleContext) -> str:
    return ctx.gate.text if ctx.gate is not None else ""


def _cue_body(text: str) -> str:
    """Drop one leading ``[mm:ss]`` or ``[hh:mm:ss]``. Cue clocks are not speech."""
    _stamp, body = parse_stamp(text or "")
    return body


def _indexed_cues(segments: list) -> tuple[str, list[tuple[int, int, object]]]:
    """Cue texts joined by one space, plus each cue's span in that string."""
    parts: list[str] = []
    spans: list[tuple[int, int, object]] = []
    cursor = 0
    for segment in segments:
        body = _fold(_cue_body(segment.text))
        if not body:
            continue
        if parts:
            cursor += 1
        start = cursor
        parts.append(body)
        cursor += len(body)
        spans.append((start, cursor, segment))
    return " ".join(parts), spans


def _verbatim_haystack(segments: list, speech: str) -> str:
    """Speech fold for verbatim quotes. Adjacent cues join; clocks stay out."""
    if segments:
        joined, _spans = _indexed_cues(segments)
        if joined:
            return joined
    return _fold(speech)


def _verbatim_covers(quote_text: str, segments: list) -> list[list]:
    """Each hit is the adjacent cues overlapped by one exact copy of the quote."""
    needle = _fold(quote_text)
    if len(needle) < 12:
        return []
    joined, spans = _indexed_cues(segments)
    covers: list[list] = []
    start = 0
    while True:
        index = joined.find(needle, start)
        if index < 0:
            break
        end = index + len(needle)
        covered = [
            segment
            for cue_start, cue_end, segment in spans
            if cue_start < end and cue_end > index
        ]
        if covered:
            covers.append(covered)
        start = index + 1
    return covers


def _stamp_anchor(quote_text: str, segments: list, stamp: int) -> tuple[int, object] | None:
    """Closest covered cue start to ``stamp``. Equal distances keep the earlier cue.

    A cue is covered when the verbatim span overlaps its text. The delta is
    ``abs(stamp - int(cue.start))``.
    """
    best: tuple[int, object] | None = None
    for covered in _verbatim_covers(quote_text, segments):
        for segment in covered:
            if segment.start is None:
                continue
            delta = abs(stamp - int(segment.start))
            if best is None or delta < best[0]:
                best = (delta, segment)
    return best


def _section_map(ctx: RuleContext) -> dict[str, SectionView]:
    return {section.heading: section for section in ctx.sections}



OPTIONAL_NA_NO_QUOTE = frozenset({"翻车或别用", "今天立刻动手一步"})
REQUIRED_CONTENT_SECTIONS = frozenset({"问题与做法", "完整怎么做"})


def _cjk_ratio(text: str) -> float:
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    denom = cjk + latin
    return (cjk / denom) if denom else 0.0


def _latin_ratio(text: str) -> float:
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    denom = cjk + latin
    return (latin / denom) if denom else 0.0


def _cross_lingual_zh_on_en(ctx: "RuleContext") -> bool:
    """Chinese-majority note prose against Latin-majority transcript speech."""
    speech = _speech(ctx)
    if _latin_ratio(speech) < 0.70:
        return False
    prose_parts = []
    for section in ctx.sections:
        if section.inapplicable:
            continue
        prose_parts.append(section.prose or "")
    prose = chr(10).join(prose_parts)
    return _cjk_ratio(prose) >= 0.30


def r01_gate(ctx: RuleContext) -> tuple[str, bool, str]:
    """Transcript exists and passes the quality gate."""
    parts: list[str] = []
    if not ctx.exists:
        parts.append(f"missing transcript path: {ctx.transcript_path} does not exist")
    elif ctx.gate is None or not ctx.gate.passed:
        reasons = ctx.gate.reasons if ctx.gate is not None else ["unreadable transcript"]
        parts.extend(f"quality gate failed: {reason}" for reason in reasons)
    if _LAUNDER.search(ctx.note):
        usable = ctx.gate is not None and ctx.gate.passed
        if not usable:
            parts.append(
                "analyzer-laundering: the note is an essay about ASR or transcription "
                "failure without a usable transcript"
            )
        elif not ctx.quoted:
            parts.append(
                "analyzer-laundering: the note discusses ASR or transcription failure "
                "and does not quote the transcript"
            )
    if parts:
        return ("R01", False, "; ".join(parts))
    return ("R01", True, "transcript passed the quality gate")


def r02_frontmatter(ctx: RuleContext) -> tuple[str, bool, str]:
    """Required frontmatter is present, gate_passed is true, and the path is cited."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R02", True, "skipped because the transcript is not usable")
    parts: list[str] = []
    if not ctx.cited:
        display = ctx.transcript_path.as_posix()
        parts.append(f"note does not cite transcript path {display}")
    fields = ctx.fields
    if fields is None:
        parts.append(
            "note is missing Obsidian frontmatter "
            "(title, source_url, video_id, acquisition, gate_passed, transcript_path, quoted_window)"
        )
    else:
        missing = [key for key in knowledge_note.FRONTMATTER_KEYS if not _compact(str(fields.get(key, "")))]
        if missing:
            parts.append("note frontmatter is missing " + ", ".join(missing))
        elif str(fields.get("gate_passed", "")).strip().casefold() not in {"true", "yes", "1"}:
            parts.append("frontmatter gate_passed is not true")
        else:
            window = _compact(str(fields.get("quoted_window", "")))
            _stamp, window_text = parse_stamp(window)
            window_text = window_text or window
            folded = _fold(_speech(ctx))
            if len(_compact(window_text)) < QUOTE_WINDOW or _fold(window_text) not in folded:
                parts.append(
                    "frontmatter quoted_window is not a contiguous transcript quote "
                    f"of at least {QUOTE_WINDOW} characters"
                )
        cited_path = str(fields.get("transcript_path") or "").replace("\\", "/")
        forms = {form.replace("\\", "/") for form in _citation_forms(ctx.transcript_path)}
        if cited_path and cited_path not in forms:
            parts.append(
                "frontmatter transcript_path does not match the transcript file "
                f"{ctx.transcript_path.as_posix()}"
            )
    if parts:
        return ("R02", False, "; ".join(parts))
    return ("R02", True, "frontmatter is complete")


def r03_sections(ctx: RuleContext) -> tuple[str, bool, str]:
    """Four sections, legal 本节不适用 lines, and no all-N/A deposit."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R03", True, "skipped because the transcript is not usable")
    parts: list[str] = []
    present = _section_map(ctx)
    missing = [heading for heading in knowledge_note.SECTIONS if heading not in present]
    if missing:
        parts.append("finished note is missing knowledge section " + ", ".join(missing))
    order = [section.heading for section in ctx.sections]
    if not missing and order != list(knowledge_note.SECTIONS):
        parts.append("knowledge sections are not in the required order")
    for heading in knowledge_note.SECTIONS:
        section = present.get(heading)
        if section is None:
            continue
        if "本节不适用" in section.prose and section.inapplicable is None:
            parts.append(
                f"section {heading} uses 本节不适用 but is not a single line "
                "本节不适用：<reason>"
            )
        elif section.inapplicable is not None and heading in REQUIRED_CONTENT_SECTIONS:
            parts.append(
                f"section {heading} must not be whole-section 本节不适用; "
                "write grounded claims from quotes instead"
            )
        elif (
            section.inapplicable is not None
            and heading not in OPTIONAL_NA_NO_QUOTE
            and not section.quotes
        ):
            parts.append(f"section {heading} is 本节不适用 and does not include one quote")
    if not missing and knowledge_note.all_sections_inapplicable(ctx.note):
        parts.append(knowledge_note.ALL_INAPPLICABLE_REASON)
    if parts:
        return ("R03", False, "; ".join(parts))
    return ("R03", True, "four sections are present")


def _quote_in_speech(text: str, speech: str) -> bool:
    folded = _fold(text)
    if len(folded) < QUOTE_WINDOW:
        return False
    return folded in _fold(speech)


def r04_quotes_verbatim(ctx: RuleContext) -> tuple[str, bool, str]:
    """Every blockquote is a verbatim span of at least 40 characters.

    Adjacent cue texts are one string. Leading cue clocks are not part of it.
    The quote has to be an exact substring of that string after whitespace
    collapse and case fold.
    """
    if ctx.gate is None or not ctx.gate.passed:
        return ("R04", True, "skipped because the transcript is not usable")
    speech = _verbatim_haystack(ctx.segments, _speech(ctx))
    parts: list[str] = []
    if not ctx.quoted:
        if len(speech) < QUOTE_WINDOW:
            parts.append(
                "note does not quote a transcript window "
                f"(transcript is shorter than {QUOTE_WINDOW} characters after cleanup, "
                "so there is no quotable window)"
            )
        else:
            parts.append(
                "note does not quote a transcript window "
                f"(need {QUOTE_WINDOW} contiguous characters from the transcript; "
                "a path or a title is not a quote)"
            )
    present = _section_map(ctx)
    for heading in knowledge_note.SECTIONS:
        section = present.get(heading)
        if section is None:
            continue
        if (
            section.inapplicable is not None
            and heading in OPTIONAL_NA_NO_QUOTE
            and not section.quotes
        ):
            continue
        if not section.quotes:
            parts.append(
                f"section {heading} does not quote a contiguous transcript window "
                f"of at least {QUOTE_WINDOW} characters"
            )
            continue
        for quote in section.quotes:
            if not _quote_in_speech(quote.text, speech):
                shown = quote.text[:80]
                parts.append(
                    f"section {heading} quote is not verbatim in the transcript: {shown}"
                )
    if parts:
        return ("R04", False, "; ".join(parts))
    return ("R04", True, "quotes are verbatim")


def _segment_for(quote_text: str, segments: list) -> object | None:
    needle = _fold(quote_text)
    if len(needle) < 12:
        return None
    for segment in segments:
        if needle in _fold(segment.text):
            return segment
    return None


def r05_timestamps(ctx: RuleContext) -> tuple[str, bool, str]:
    """A stamped quote sits within 15 seconds of its stamp anchor.

    The anchor is the start of the covered cue closest to the stamp. A span
    across adjacent cues covers every cue whose text the span overlaps. Equal
    distances keep the earlier cue. Quotes with no stamp are not timed.
    """
    if ctx.gate is None or not ctx.gate.passed:
        return ("R05", True, "skipped because the transcript is not usable")
    parts: list[str] = []
    for section in ctx.sections:
        for quote in section.quotes:
            if quote.stamp is None:
                continue
            anchor = _stamp_anchor(quote.text, ctx.segments, quote.stamp)
            if anchor is None:
                parts.append(
                    f"section {section.heading} quote stamp [{_fmt(quote.stamp)}] "
                    "does not match a timed cue"
                )
                continue
            delta, segment = anchor
            if delta > 15:
                parts.append(
                    f"section {section.heading} quote stamp [{_fmt(quote.stamp)}] "
                    f"is {delta}s from the cue at [{_fmt(int(segment.start))}]"
                )
    if parts:
        return ("R05", False, "; ".join(parts))
    return ("R05", True, "quote stamps match the transcript")


def _fmt(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def r06_distinct_quotes(ctx: RuleContext) -> tuple[str, bool, str]:
    """Blockquotes are not reused across sections."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R06", True, "skipped because the transcript is not usable")
    seen: dict[str, str] = {}
    for section in ctx.sections:
        for quote in section.quotes:
            key = _fold(quote.text)
            if len(key) < QUOTE_WINDOW:
                continue
            prior = seen.get(key)
            if prior is not None and prior != section.heading:
                return (
                    "R06",
                    False,
                    f"section {section.heading} repeats a quote already used in {prior}",
                )
            seen.setdefault(key, section.heading)
    return ("R06", True, "section quotes are distinct")


def r07_numbers(ctx: RuleContext) -> tuple[str, bool, str]:
    """Digits and percents in prose also appear in the transcript."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R07", True, "skipped because the transcript is not usable")
    speech = _speech(ctx)
    missing: list[str] = []
    for section in ctx.sections:
        if section.inapplicable:
            continue
        for token in _DIGIT.findall(section.prose):
            if token not in speech and token.rstrip("%") not in speech:
                missing.append(token)
    if missing:
        shown = ", ".join(f'"{token}"' for token in missing[:6])
        return ("R07", False, f"prose number not in the transcript: {shown}")
    return ("R07", True, "prose numbers appear in the transcript")


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in re.finditer(r"[.!?。！？]", text):
        spans.append((start, match.end()))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans or [(0, len(text))]


def _is_sentence_start(text: str, index: int) -> bool:
    previous = text[:index]
    return not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", previous) or bool(
        re.search(r"[.!?。！？]\s*$", previous)
    )


def r08_proper_nouns(ctx: RuleContext) -> tuple[str, bool, str]:
    """More than two unknown proper nouns in the prose fails."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R08", True, "skipped because the transcript is not usable")
    speech = _fold(_speech(ctx))
    unknown: list[str] = []

    def consider(token: str) -> None:
        key = token.casefold().strip()
        if len(key) < 2 or key in _PROPER_SKIP:
            return
        if key in speech or token in _speech(ctx):
            return
        if key not in {item.casefold() for item in unknown}:
            unknown.append(token)

    for section in ctx.sections:
        if section.inapplicable:
            continue
        for match in _LATIN_WORD.finditer(section.prose):
            word = match.group(0)
            if not word[0].isupper():
                continue
            if _is_sentence_start(section.prose, match.start()):
                continue
            consider(word)
        for match in _BOOK.finditer(section.prose):
            consider(match.group(1).strip())
        for match in _QUOTED_TERM.finditer(section.prose):
            term = (match.group(1) or match.group(2) or "").strip()
            if term and not term.startswith("["):
                consider(term)
    if len(unknown) > 2:
        shown = ", ".join(unknown[:6])
        return ("R08", False, f"proper nouns not in the transcript ({len(unknown)}): {shown}")
    return ("R08", True, "proper nouns are grounded")


def _short_fragment(piece: str) -> bool:
    text = piece.strip()
    if not text:
        return False
    words = _LATIN_WORD.findall(text)
    cjk = len(_CJK_RUN.findall(text) and "".join(_CJK_RUN.findall(text)) or "")
    if words and cjk == 0:
        return len(words) <= 3 and len(text) <= 24
    if cjk and not words:
        return cjk <= 4
    return len(text) <= 12


def r09_keyword_salad(ctx: RuleContext) -> tuple[str, bool, str]:
    """Comma-stacked fragments or template salad phrasing."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R09", True, "skipped because the transcript is not usable")
    for section in ctx.sections:
        if section.inapplicable:
            continue
        if _SALAD_PHRASE.search(section.prose):
            return (
                "R09",
                False,
                f"section {section.heading} uses keyword-salad phrasing",
            )
        pieces = re.split(r"[,，]", section.prose)
        run = 0
        for piece in pieces:
            if _short_fragment(piece):
                run += 1
                if run >= 4:
                    return (
                        "R09",
                        False,
                        f"section {section.heading} stacks short comma-separated fragments",
                    )
            else:
                run = 0
    return ("R09", True, "prose is not a keyword salad")


def _sentences(text: str) -> list[str]:
    kept: list[str] = []
    for part in _SENTENCE_SPLIT.split(text):
        part = part.strip()
        if not part:
            continue
        words = re.findall(r"[A-Za-z']+|[\u4e00-\u9fff]", part)
        if len(words) >= 4 or len(part) >= 12:
            kept.append(part)
    return kept


def r10_original_prose(ctx: RuleContext) -> tuple[str, bool, str]:
    """Grounded prose: ZH-on-EN skips 60-char own-words pressure; same-script allows short quote compression."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R10", True, "skipped because the transcript is not usable")
    speech = _speech(ctx)
    cross = _cross_lingual_zh_on_en(ctx)
    parts: list[str] = []
    remainders: list[str] = []
    for section in ctx.sections:
        if section.inapplicable:
            continue
        if knowledge_note._STUB.search(section.prose):
            parts.append(
                f"boilerplate analysis in section {section.heading}: "
                "the section is a quote stub rather than a reusable claim"
            )
            continue
        sentences = _sentences(section.prose)
        if cross:
            if not section.quotes:
                parts.append(
                    f"section {section.heading} needs at least one transcript quote "
                    "before Chinese prose can stand"
                )
            elif len(sentences) < 1:
                parts.append(
                    f"section {section.heading} has no prose sentence beside its quotes"
                )
            remainders.append(_fold(section.prose))
            continue
        quote = " ".join(item.text for item in section.quotes)
        coverage = _coverage(section.prose, quote) if quote else 0.0
        remainder = knowledge_note._mask_transcript_spans(section.prose, speech, span=12)
        remainders.append(_fold(remainder))
        letters = sum(1 for char in remainder if char.isalpha() or "一" <= char <= "鿿")
        if coverage >= 0.50 and 1 <= len(sentences) <= 3:
            continue
        if letters < 60 or len(_sentences(remainder)) < 2:
            parts.append(
                f"section {section.heading} does not analyze the transcript "
                f"(after removing transcript overlap, {letters} characters and "
                f"{len(_sentences(remainder))} sentences remain; need 60 and 2, "
                "or a short compression covered by the section quotes)"
            )
    nonempty = [item for item in remainders if item]
    if len(nonempty) >= 2 and len(set(nonempty)) < len(nonempty):
        parts.append("finished note repeats the same analysis in more than one knowledge section")
    if parts:
        return ("R10", False, "; ".join(parts))
    return ("R10", True, "prose is grounded without unsupported elaboration pressure")


def _coverage(prose: str, quote: str, span: int = 12) -> float:
    folded = _compact(prose)
    needle = _compact(quote).casefold()
    if not folded or len(needle) < span:
        return 0.0
    mask = [False] * len(folded)
    hay = folded.casefold()
    index = 0
    while index < len(folded):
        if index + span <= len(folded) and hay[index : index + span] in needle:
            end = index + span
            while end < len(folded) and hay[index : end + 1] in needle:
                end += 1
            for cursor in range(index, end):
                mask[cursor] = True
            index = end
        else:
            index += 1
    return sum(mask) / len(folded)


def r11_quote_overlap(ctx: RuleContext) -> tuple[str, bool, str]:
    """Prose must not be mostly the quote pasted; skipped for Chinese prose on Latin transcripts."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R11", True, "skipped because the transcript is not usable")
    if _cross_lingual_zh_on_en(ctx):
        return ("R11", True, "skipped for Chinese prose on a Latin transcript")
    for section in ctx.sections:
        if section.inapplicable or not section.quotes:
            continue
        quote = " ".join(item.text for item in section.quotes)
        ratio = _coverage(section.prose, quote)
        if ratio > 0.85:
            return (
                "R11",
                False,
                f"section {section.heading} prose overlaps its quote by {ratio:.0%}",
            )
    return ("R11", True, "prose is not a restatement of the quote")


def _duration(ctx: RuleContext) -> float | None:
    timed = [segment.start for segment in ctx.segments if segment.start is not None]
    ends = [segment.end for segment in ctx.segments if segment.end is not None]
    if ends:
        return max(ends)
    if timed:
        return max(timed)
    return None


def _quote_time(quote: Quote, ctx: RuleContext) -> float | None:
    if quote.stamp is not None:
        return float(quote.stamp)
    segment = _segment_for(quote.text, ctx.segments)
    if segment is not None and segment.start is not None:
        return float(segment.start)
    speech = _fold(_speech(ctx))
    needle = _fold(quote.text)
    index = speech.find(needle) if needle else -1
    if index < 0 or not speech:
        return None
    duration = _duration(ctx)
    if duration is None:
        return None
    return duration * (index / max(len(speech), 1))


def r12_quartiles(ctx: RuleContext) -> tuple[str, bool, str]:
    """A video longer than 5 minutes needs quotes in at least 3 quartiles."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R12", True, "skipped because the transcript is not usable")
    duration = _duration(ctx)
    if duration is None or duration < 300:
        return ("R12", True, "video is under 5 minutes or has no clock")
    quartiles: set[int] = set()
    for section in ctx.sections:
        for quote in section.quotes:
            moment = _quote_time(quote, ctx)
            if moment is None:
                continue
            quartiles.add(min(3, int(moment / duration * 4)))
    if len(quartiles) < 3:
        return (
            "R12",
            False,
            f"quotes cover {len(quartiles)} quartile(s) of a {int(duration)}s transcript; need 3",
        )
    return ("R12", True, "quotes are spread through the transcript")


def _tokens(text: str) -> list[str]:
    latin = [
        word.casefold()
        for word in _LATIN_WORD.findall(text)
        if len(word) >= 3 and word.casefold() not in _EN_STOP
    ]
    cjk: list[str] = []
    for run in _CJK_RUN.findall(text):
        # Non-overlapping pairs, so a short action can still share a third of its words.
        cjk.extend(run[index : index + 2] for index in range(0, len(run) - 1, 2))
    return latin + cjk


def _imperatives(speech: str) -> list[str]:
    pieces = re.split(r"[。！？.!?；;\n]+", speech)
    kept: list[str] = []
    for piece in pieces:
        line = piece.strip()
        if len(line) < 8:
            continue
        head = _fold(line)
        first = _LATIN_WORD.findall(line)
        zh = _CJK_RUN.findall(line)
        starts_en = bool(first) and first[0].casefold() in _EN_VERBS
        starts_zh = bool(zh) and any(zh[0].startswith(prefix) for prefix in _ZH_VERB_PREFIX)
        marked = any(cue in head for cue in ("do not", "don't", "不要", "别"))
        if starts_en or starts_zh or marked:
            kept.append(line)
    return kept


def _starts_with_verb(prose: str) -> bool:
    text = prose.strip()
    latin = _LATIN_WORD.findall(text)
    if latin and not _CJK_RUN.search(text[:8]):
        return latin[0].casefold() in _EN_VERBS
    for prefix in _ZH_VERB_PREFIX:
        if text.startswith(prefix):
            return True
    return False


def r13_today_step(ctx: RuleContext) -> tuple[str, bool, str]:
    """今天立刻动手一步 starts with a verb, stays within two sentences, and overlaps an imperative."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R13", True, "skipped because the transcript is not usable")
    section = _section_map(ctx).get("今天立刻动手一步")
    if section is None or section.inapplicable:
        return ("R13", True, "today step is absent or marked inapplicable")
    prose = section.prose.strip()
    if not _starts_with_verb(prose):
        return ("R13", False, "今天立刻动手一步 does not start with a verb")
    sentences = [part for part in _SENTENCE_SPLIT.split(prose) if part.strip()]
    if len(sentences) > 2:
        return ("R13", False, f"今天立刻动手一步 has {len(sentences)} sentences; maximum is 2")
    action = sentences[0]
    if _cross_lingual_zh_on_en(ctx):
        if not section.quotes:
            return (
                "R13",
                False,
                "今天立刻动手一步 needs a supporting quote when the transcript is not Chinese",
            )
        return ("R13", True, "today step is a short grounded action (cross-lingual)")
    today = _tokens(action)
    if not today:
        return ("R13", False, "今天立刻动手一步 has no content words")
    best = 0.0
    for imperative in _imperatives(_speech(ctx)):
        hits = [token for token in set(today) if token in imperative]
        overlap = len(hits) / len(set(today))
        best = max(best, overlap)
    if best < 0.30:
        return (
            "R13",
            False,
            f"今天立刻动手一步 overlaps an imperative in the transcript by {best:.0%}; need 30%",
        )
    return ("R13", True, "today step is a short grounded action")


def r14_platform_title(ctx: RuleContext) -> tuple[str, bool, str]:
    """Words that appear only in platform_title, more than three, fail."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R14", True, "skipped because the transcript is not usable")
    title = ""
    if ctx.fields:
        title = str(ctx.fields.get("platform_title") or "")
    if not _compact(title):
        return ("R14", True, "no platform_title")
    speech = _fold(_speech(ctx))
    stray = []
    for token in _tokens(title):
        if token.casefold() not in speech and token not in speech:
            stray.append(token)
    # Unique, stable order.
    seen: list[str] = []
    for token in stray:
        if token not in seen:
            seen.append(token)
    if len(seen) > 3:
        return (
            "R14",
            False,
            f"platform_title words missing from the transcript ({len(seen)}): "
            + ", ".join(seen[:8]),
        )
    return ("R14", True, "platform_title is not driving the note")


def r15_failed_status(ctx: RuleContext) -> tuple[str, bool, str]:
    """A failed or no-extractable status must not keep a note."""
    status = (ctx.job_status or "").strip().casefold().replace("_", "-")
    normalized = {
        "not-finished": "not_finished",
        "quality-gate-failed": "quality_gate_failed",
        "no-extractable-content": "no-extractable-content",
        "failed": "failed",
        "not_finished": "not_finished",
        "quality_gate_failed": "quality_gate_failed",
    }.get(status, status)
    if normalized in _FAILED_STATUS or status in _FAILED_STATUS:
        return (
            "R15",
            False,
            f"status is {ctx.job_status} so note.md must not be deposited",
        )
    return ("R15", True, "status does not forbid a note")


def r16_quote_anchored_nouns(ctx: RuleContext) -> tuple[str, bool, str]:
    """Proper nouns in prose must appear in that section's quotes (tolerance 0). Skips sentence-initial caps; no cross-lingual lexical gate."""
    if ctx.gate is None or not ctx.gate.passed:
        return ("R16", True, "skipped because the transcript is not usable")
    missing: list[str] = []
    for section in ctx.sections:
        if section.inapplicable:
            continue
        if not section.quotes:
            continue
        quote_blob = " ".join(q.text for q in section.quotes)
        quote_fold = _fold(quote_blob)
        for match in _LATIN_WORD.finditer(section.prose):
            word = match.group(0)
            if not word[0].isupper():
                continue
            if _is_sentence_start(section.prose, match.start()):
                continue
            key = word.casefold().strip()
            if len(key) < 2 or key in _PROPER_SKIP:
                continue
            if key in quote_fold or word in quote_blob:
                continue
            label = f"{section.heading}:{word}"
            if label not in missing:
                missing.append(label)
        for match in _BOOK.finditer(section.prose):
            term = match.group(1).strip()
            key = term.casefold()
            if key and key not in quote_fold and term not in quote_blob:
                label = f"{section.heading}:{term}"
                if label not in missing:
                    missing.append(label)
    if missing:
        return (
            "R16",
            False,
            "proper nouns in prose missing from that section's quotes (tol=0): "
            + ", ".join(missing[:8]),
        )
    return ("R16", True, "section prose nouns are anchored in section quotes")


_R17_MIN_TOKENS = 3


def _content_tokens(text: str) -> set[str]:
    """Latin words of length >= 4, plus every consecutive CJK pair."""
    latin = {
        word.casefold()
        for word in _LATIN_WORD.findall(text)
        if len(word) >= 4 and word.casefold() not in _EN_STOP
    }
    pairs: set[str] = set()
    for run in _CJK_RUN.findall(text):
        pairs.update(run[index : index + 2] for index in range(len(run) - 1))
    return latin | pairs


def _script_counts(text: str) -> tuple[int, int]:
    cjk = sum(len(run) for run in _CJK_RUN.findall(text))
    latin = sum(len(word) for word in _LATIN_WORD.findall(text))
    return cjk, latin


def _cross_script(prose: str, quote: str) -> bool:
    """True when the prose and the quote are not the same majority script."""
    prose_cjk, prose_latin = _script_counts(prose)
    quote_cjk, quote_latin = _script_counts(quote)
    prose_zh = prose_cjk > prose_latin and prose_cjk > 0
    quote_zh = quote_cjk > quote_latin and quote_cjk > 0
    prose_en = prose_latin > prose_cjk and prose_latin > 0
    quote_en = quote_latin > quote_cjk and quote_latin > 0
    return (prose_zh and quote_en) or (prose_en and quote_zh)


def r17_same_section_overlap(ctx: RuleContext) -> tuple[str, bool, str]:
    """Prose must share content tokens with that section's own quotes.

    A number in the prose has to appear in those quotes. Same-script prose
    also needs at least three content tokens in common (a Latin word of four
    letters, or a CJK pair). Chinese prose on a Latin quote skips the token
    floor, same as R16, and still checks numbers. Cross-section quotes fail.
    """
    if ctx.gate is None or not ctx.gate.passed:
        return ("R17", True, "skipped because the transcript is not usable")
    parts: list[str] = []
    for section in ctx.sections:
        if section.inapplicable or not section.quotes:
            continue
        quote = " ".join(item.text for item in section.quotes)
        for number in _DIGIT.findall(section.prose):
            if number not in quote:
                parts.append(
                    f"section {section.heading} number {number} "
                    "is absent from that section's quotes"
                )
        if _cross_script(section.prose, quote):
            continue
        shared = _content_tokens(section.prose) & _content_tokens(quote)
        if len(shared) < _R17_MIN_TOKENS:
            parts.append(
                f"section {section.heading} shares {len(shared)} content "
                f"tokens with its quotes; need {_R17_MIN_TOKENS}"
            )
    if parts:
        return ("R17", False, "; ".join(parts))
    return ("R17", True, "section prose overlaps that section's quotes")


RULES = (
    r01_gate,
    r02_frontmatter,
    r03_sections,
    r04_quotes_verbatim,
    r05_timestamps,
    r06_distinct_quotes,
    r07_numbers,
    r08_proper_nouns,
    r09_keyword_salad,
    r10_original_prose,
    r11_quote_overlap,
    r12_quartiles,
    r13_today_step,
    r14_platform_title,
    r15_failed_status,
    r16_quote_anchored_nouns,
    r17_same_section_overlap,
)


def run_rules(ctx: RuleContext) -> list[tuple[str, bool, str]]:
    return [rule(ctx) for rule in RULES]


def failure_lines(results: list[tuple[str, bool, str]]) -> list[str]:
    return [f"{rule_id} FAIL: {message}" for rule_id, ok, message in results if not ok]
