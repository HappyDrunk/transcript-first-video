#!/usr/bin/env python3
"""Finished-note shape checks, plus the blank scaffold hosts write.

A finished note is not a path, a status, or a blockquote. It has YAML
frontmatter and at least these sections:

- 问题与做法
- 完整怎么做
- 翻车或别用
- 今天立刻动手一步

Each section must quote a contiguous window of the transcript and add a
claim that is not the quote itself. The quality gate still decides whether
the transcript is usable. This module does not listen to audio, and it does
not write that analysis.

Hosts call ``render_scaffold``. ``verify_note`` calls ``knowledge_reasons``.
"""

from __future__ import annotations

import re

QUOTE_WINDOW = 40
_MIN_ANALYSIS = 40
_GROUND_SPAN = 12

SECTIONS = (
    "问题与做法",
    "完整怎么做",
    "翻车或别用",
    "今天立刻动手一步",
)

FRONTMATTER_KEYS = (
    "title",
    "source_url",
    "video_id",
    "acquisition",
    "gate_passed",
    "transcript_path",
    "quoted_window",
)

_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_STUB = re.compile(
    r"("
    r"this note is allowed because"
    r"|quoted window is copied"
    r"|match these lines"
    r"|copied from that file"
    r"|passed the quality gate"
    r"|file this as finished"
    r"|the title is the method"
    r"|fully processed"
    r"|see the quote"
    r"|as shown above"
    r"|the quote above"
    r"|本笔记因为"
    r"|引用是从文稿抄的"
    r"|只需要引用"
    r")",
    re.IGNORECASE,
)

SCAFFOLD_QUOTED_WINDOW = (
    f"FILL: paste one contiguous transcript quote of at least {QUOTE_WINDOW} characters"
)

_SCAFFOLD_INSTRUCTIONS = (
    "Scaffold only. This file is not a finished knowledge note. "
    "Read every file in chunks/ and write the analysis in note.md. "
    "Under each heading, state a claim in your own words and quote a contiguous "
    f"passage of the transcript, at least {QUOTE_WINDOW} characters. "
    "When the transcript line has a clock, quote it as > [mm:ss] followed by the words. "
    "A section with nothing to extract is one line, 本节不适用：<reason>, plus one quote. "
    "Leave that section unused rather than inventing a step the transcript does not contain. "
    "If every section is 本节不适用, do not keep note.md."
)


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def yaml_double(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _speech_count(text: str) -> int:
    return sum(1 for char in text if char.isalpha())


def render_scaffold(
    *,
    job_id: str,
    video_id: str,
    source: str,
    acquisition: str,
    transcript_cite: str,
    caption_language: str | None = None,
    caption_kind: str | None = None,
    caption_trust: str | None = None,
) -> str:
    """Frontmatter, four empty section headings, and fill instructions.

    The body does not analyze a transcript and does not copy one in.
    """
    lines = [
        "---",
        f"title: {yaml_double(job_id)}",
        f"source_url: {yaml_double(source)}",
        f"video_id: {yaml_double(video_id)}",
        f"acquisition: {yaml_double(acquisition)}",
        "gate_passed: true",
        f"transcript_path: {yaml_double(transcript_cite)}",
        "quoted_window: |-",
        f"  {SCAFFOLD_QUOTED_WINDOW}",
    ]
    if caption_language:
        lines.append(f"caption_language: {yaml_double(caption_language)}")
    if caption_kind:
        lines.append(f"caption_kind: {yaml_double(caption_kind)}")
    if caption_trust:
        lines.append(f"caption_trust: {yaml_double(caption_trust)}")
    lines.extend(
        [
            "---",
            "",
            f"# {job_id}",
            "",
            _SCAFFOLD_INSTRUCTIONS,
            "",
            f"Transcript: `{transcript_cite}`.",
            "",
        ]
    )
    for heading in SECTIONS:
        lines.extend([f"## {heading}", ""])
    return "\n".join(lines).rstrip() + "\n"


def parse_frontmatter(note: str) -> dict | None:
    """Parse the small YAML subset the hosts write. Return None when it is absent."""
    if not note.startswith("---\n"):
        return None
    end = note.find("\n---\n", 4)
    if end < 0:
        return None
    block = note[4:end]
    fields: dict[str, str] = {}
    lines = block.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if ":" not in line:
            index += 1
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if raw in {"|", "|-", ">", ">"}:
            collected: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith(" ") or lines[index].startswith("\t") or lines[index] == ""):
                collected.append(lines[index].strip())
                index += 1
            fields[key] = " ".join(part for part in collected if part)
            continue
        if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
            raw = (
                raw[1:-1]
                .replace('\\"', '"')
                .replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\\\", "\\")
            )
        elif raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
            raw = raw[1:-1]
        fields[key] = raw
        index += 1
    return fields


def _section_bodies(note: str) -> list[tuple[str, str]]:
    matches = list(_H2.finditer(note))
    bodies: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(note)
        bodies.append((match.group(1).strip(), note[start:end]))
    return bodies


def _prose_outside_quotes(body: str) -> str:
    kept = [line for line in body.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(kept).strip()


def _mask_transcript_spans(prose: str, transcript: str, span: int = _GROUND_SPAN) -> str:
    """Drop slices of ``prose`` that are contiguous transcript text."""
    folded = compact(prose)
    haystack = compact(transcript).casefold()
    if not folded or not haystack:
        return folded
    mask = [False] * len(folded)
    index = 0
    while index < len(folded):
        if index + span <= len(folded) and folded[index : index + span].casefold() in haystack:
            end = index + span
            while end < len(folded) and folded[index : end + 1].casefold() in haystack:
                end += 1
            for cursor in range(index, end):
                mask[cursor] = True
            index = end
        else:
            index += 1
    return "".join(char for cursor, char in enumerate(folded) if not mask[cursor])


def _grounded(prose: str, transcript: str) -> bool:
    folded = compact(prose).casefold()
    haystack = compact(transcript).casefold()
    if len(folded) < _GROUND_SPAN or len(haystack) < _GROUND_SPAN:
        return False
    for index in range(len(folded) - _GROUND_SPAN + 1):
        if folded[index : index + _GROUND_SPAN] in haystack:
            return True
    return False


def _quotes_window(body: str, transcript: str, window: int = QUOTE_WINDOW) -> bool:
    folded_body = compact(body).casefold()
    folded = compact(transcript).casefold()
    if window <= 0 or len(folded) < window or len(folded_body) < window:
        return False
    source, haystack = (folded_body, folded) if len(folded_body) <= len(folded) else (folded, folded_body)
    last = len(source) - window + 1
    for index in range(last):
        if source[index : index + window] in haystack:
            return True
    return False


def _truthy(value: str) -> bool:
    return value.strip().casefold() in {"true", "yes", "1"}


def knowledge_reasons(note: str, transcript_text: str) -> list[str]:
    """Reasons a passing transcript still must not be deposited as this note.

    Empty when the note has the frontmatter, the four sections, a real quote in
    each section, and analysis that is not a stub. This is a shape check. It is
    not a grade of summary quality and it is not an audio check.
    """
    reasons: list[str] = []
    fields = parse_frontmatter(note)
    if fields is None:
        reasons.append(
            "note is missing Obsidian frontmatter "
            "(title, source_url, video_id, acquisition, gate_passed, transcript_path, quoted_window)"
        )
    else:
        missing = [key for key in FRONTMATTER_KEYS if not compact(str(fields.get(key, "")))]
        if missing:
            reasons.append("note frontmatter is missing " + ", ".join(missing))
        elif not _truthy(str(fields.get("gate_passed", ""))):
            reasons.append("frontmatter gate_passed is not true")
        else:
            window = compact(str(fields.get("quoted_window", "")))
            folded = compact(transcript_text).casefold()
            if len(window) < QUOTE_WINDOW or window.casefold() not in folded:
                reasons.append(
                    "frontmatter quoted_window is not a contiguous transcript quote "
                    f"of at least {QUOTE_WINDOW} characters"
                )
    bodies = dict(_section_bodies(note))
    missing_sections = [heading for heading in SECTIONS if heading not in bodies]
    if missing_sections:
        reasons.append(
            "finished note is missing knowledge section " + ", ".join(missing_sections)
        )
    order = [heading for heading, _body in _section_bodies(note) if heading in SECTIONS]
    if not missing_sections and order != list(SECTIONS):
        reasons.append("knowledge sections are not in the required order")
    remainders: list[str] = []
    for heading in SECTIONS:
        body = bodies.get(heading)
        if body is None:
            continue
        if not _quotes_window(body, transcript_text):
            reasons.append(
                f"section {heading} does not quote a contiguous transcript window "
                f"of at least {QUOTE_WINDOW} characters"
            )
        prose = _prose_outside_quotes(body)
        if _STUB.search(prose):
            reasons.append(
                f"boilerplate analysis in section {heading}: "
                "the section is a quote stub rather than a reusable claim"
            )
        remainder = _mask_transcript_spans(prose, transcript_text)
        remainders.append(compact(remainder).casefold())
        if _speech_count(remainder) < _MIN_ANALYSIS:
            reasons.append(
                f"section {heading} does not analyze the transcript "
                "(too little text beyond the quoted words)"
            )
        elif not _grounded(prose, transcript_text):
            reasons.append(
                f"section {heading} is not grounded in the transcript "
                "(the analysis never uses a stretch of the transcript's words)"
            )
    nonempty = [item for item in remainders if item]
    if len(nonempty) >= 2 and len(set(nonempty)) < len(nonempty):
        reasons.append("finished note repeats the same analysis in more than one knowledge section")
    return reasons
