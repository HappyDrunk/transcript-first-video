#!/usr/bin/env python3
"""Deterministic verification of the reader's note and its transcript evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path

import knowledge_note
import quality_gate

QUOTE_WINDOW = knowledge_note.QUOTE_WINDOW
_STAMP = re.compile(r"^\[((?:[0-9]+:)?[0-9]{2,}:[0-5][0-9])\]([ \t]*)")
_ZH_NUMERAL = "零〇一二两三四五六七八九十百千万亿"
_ZH_NUMBER = re.compile(rf"[{_ZH_NUMERAL}]+")
_ZH_FUZZY = re.compile(r"几十万|几百万|几千万|几亿|几十|几百|几千|几万")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_BOOK = re.compile(r"《([^》]{1,40})》")
_QUOTED_TERM = re.compile(r"[“\"]([^”\"]{2,40})[”\"]|「([^」]{2,40})」")
_SENTENCE_SPLIT = re.compile(r"(?<!\d)\.|\.(?!\d)|[!?。！？]+")
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


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _fold(text: str) -> str:
    return _compact(text).casefold()


def _chinese_integer(text: str) -> int:
    digits = {
        "\u96f6": 0, "\u3007": 0, "\u4e00": 1, "\u4e8c": 2,
        "\u4e24": 2, "\u4e09": 3, "\u56db": 4, "\u4e94": 5,
        "\u516d": 6, "\u4e03": 7, "\u516b": 8, "\u4e5d": 9,
    }
    if not any(char in "\u5341\u767e\u5343\u4e07\u4ebf" for char in text):
        return int("".join(str(digits[char]) for char in text))
    total = section = pending = 0
    for char in text:
        if char in digits:
            pending = digits[char]
        elif char in "\u5341\u767e\u5343":
            unit = {"\u5341": 10, "\u767e": 100, "\u5343": 1000}[char]
            section += (pending or 1) * unit
            pending = 0
        elif char == "\u4e07":
            total += (section + pending) * 10_000
            section = pending = 0
        elif char == "\u4ebf":
            total = (total + section + pending) * 100_000_000
            section = pending = 0
    return total + section + pending


_EN_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}


def _english_integer(text: str) -> float:
    total = section = 0
    for word in re.findall(r"[a-z]+", text.casefold()):
        if word == "and":
            continue
        if word in _EN_NUMBER_WORDS:
            section += _EN_NUMBER_WORDS[word]
        elif word == "couple":
            section += 2
        elif word == "hundred":
            section = max(section, 1) * 100
        elif word in {"dozen", "dozens"}:
            section = max(section, 1) * 12
        elif word in {"decade", "decades"}:
            section = max(section, 1) * 10
        elif word in {"thousand", "million", "billion"}:
            scale = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}[word]
            total += max(section, 1) * scale
            section = 0
    return float(total + section)


def body_number_mentions(text: str) -> list[tuple[float, float, str]]:
    """Arabic digits and qualifying Chinese numeric claims in note prose."""
    mentions: list[tuple[float, float, str]] = []
    occupied: list[tuple[int, int]] = []
    fuzzy_ranges = {
        "\u51e0\u5341\u4e07": (100_000, 999_999),
        "\u51e0\u767e\u4e07": (1_000_000, 9_999_999),
        "\u51e0\u5343\u4e07": (10_000_000, 99_999_999),
        "\u51e0\u4ebf": (100_000_000, 999_999_999),
        "\u51e0\u5341": (10, 99), "\u51e0\u767e": (100, 999),
        "\u51e0\u5343": (1_000, 9_999), "\u51e0\u4e07": (10_000, 99_999),
    }
    for match in _ZH_FUZZY.finditer(text):
        low, high = fuzzy_ranges[match.group()]
        mentions.append((low, high, match.group()))
        occupied.append(match.span())
    for match in _EN_SOURCE_NUMBER.finditer(text):
        if any(start < match.end() and end > match.start() for start, end in occupied):
            continue
        value = _arabic_number_value(match.group())
        mentions.append((value, value, match.group()))
        occupied.append(match.span())
    for match in _ZH_NUMBER.finditer(text):
        token = match.group()
        if any(start < match.end() and end > match.start() for start, end in occupied):
            continue
        has_unit = any(char in "\u5341\u767e\u5343\u4e07\u4ebf" for char in token)
        value = _chinese_integer(token)
        if value < 10 and not has_unit:
            continue
        mentions.append((float(value), float(value), token))
        occupied.append(match.span())
    return mentions


_EN_SOURCE_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])(?:\d+(?:,\d{3})*(?:\.\d+)?%?"
    r"(?:[ -]+(?:hundred|thousand|million|billion|dozen|dozens|decade|decades))?%?)(?![A-Za-z])",
    re.IGNORECASE,
)


def _arabic_number_value(raw: str) -> float:
    parsed = re.match(r"(\d+(?:\.\d+)?)(?:[ -]+([a-z]+))?", raw.replace(",", ""), re.IGNORECASE)
    assert parsed is not None
    value = float(parsed.group(1))
    scale = (parsed.group(2) or "").casefold()
    return value * {
        "hundred": 100, "thousand": 1_000, "million": 1_000_000,
        "billion": 1_000_000_000, "dozen": 12, "dozens": 12,
        "decade": 10, "decades": 10,
    }.get(scale, 1)


_EN_NUMBER_WORD_PATTERN = (
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"couple|hundred|thousand|million|billion|dozens?|decades?"
)
_EN_NUMBER = re.compile(
    rf"\b(?:{_EN_NUMBER_WORD_PATTERN})(?:[ -]+(?:(?:and)[ -]+)?(?:{_EN_NUMBER_WORD_PATTERN}))*\b",
    re.IGNORECASE,
)


def source_number_mentions(text: str) -> list[tuple[float, float, str]]:
    """Arabic digits and English number phrases found in a transcript or quote."""
    mentions: list[tuple[float, float, str]] = []
    occupied: list[tuple[int, int]] = []
    for match in _EN_SOURCE_NUMBER.finditer(text):
        if any(start < match.end() and end > match.start() for start, end in occupied):
            continue
        value = _arabic_number_value(match.group())
        mentions.append((value, value, match.group()))
        occupied.append(match.span())
    for match in _EN_NUMBER.finditer(text):
        if any(start < match.end() and end > match.start() for start, end in occupied):
            continue
        value = _english_integer(match.group())
        mentions.append((value, value, match.group().strip()))
        occupied.append(match.span())
    return mentions


def number_is_supported(
    mention: tuple[float, float, str], source: str
) -> bool:
    low, high, _label = mention
    return any(
        source_low <= high and source_high >= low
        for source_low, source_high, _ in source_number_mentions(source)
    )


_SPOKEN_DIGITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_SPOKEN_DIGIT = "|".join(_SPOKEN_DIGITS)
_SPOKEN_DECIMAL = re.compile(
    rf"({_EN_NUMBER.pattern})[ \t]+point[ \t]+"
    rf"((?:{_SPOKEN_DIGIT})(?:[ \t]+(?:{_SPOKEN_DIGIT}))*)\b",
    re.IGNORECASE,
)
_FRONTMATTER = re.compile(r"\A---\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$", re.MULTILINE)
_LIST_ITEM = re.compile(r"^\s*(?:[-+*][ \t]+(?:\d+[.)][ \t]+)?|\d+[.)][ \t]+)")
_INLINE_LIST_ITEM = re.compile(r"([：:；;])[ \t]*\d+[.)][ \t]+")
_DELIVERY_TIME = re.compile(r"⏱\ufe0f?[ \t]+((?:[0-9]+:)?[0-9]{2,}:[0-5][0-9])(?![\d:])")
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
_C04_START = ("先记住一句话", "这场在谈什么、谁")
_C04_END = ("可复用做法", "翻车或别用", "今天立刻动手一步")
_C04_MIDDLE = {
    "讲座": ("主线论点",),
    "访谈": ("话题", "意见不一致的地方"),
    "大会": ("发布或主张了什么", "有证据的 / 只是说法"),
    "演示": ("演示了什么", "关键数字与条件"),
}
_CONFERENCE_SUBHEADINGS = ("演示过或给出数据", "只是口头声称")



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
        elif section.level == 2 and not has_subheading and not any(
            char.isalnum() for claim in section.prose if not claim.startswith(">")
            for char in _DELIVERY_TIME.sub("", claim)
        ):
            issues.append(f"empty section: {section.heading}")
        if has_subheading:
            group_end = next((i for i in range(index + 1, len(sections))
                              if sections[i].level == 2), len(sections))
            if not any(child.prose for child in sections[index:group_end]):
                issues.append(f"empty section: {section.heading}")
        if section.heading == _C04_END[-1] and len(section.prose) > 1:
            orphan = section.prose[1].splitlines()[0]
            issues.append(f"orphan text after {_C04_END[-1]}: {orphan[:80]}")
    if kind == "大会" and tuple(children) != _CONFERENCE_SUBHEADINGS:
        issues.append("有证据的 / 只是说法 needs 演示过或给出数据 and 只是口头声称 in order")
    return issues


def term_occurs(term: str, source: str) -> bool:
    if not re.search(r"[A-Za-z0-9]", term):
        return _fold(term) in _fold(source)
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
        elif kind == "warning" and title == "字幕更正":
            if not caption_corrections([[header, *lines]], transcript):
                issues.append("字幕更正 needs the original spelling from the transcript and its correction")
        else:
            issues.append(f"unknown explanation block: {header}")
    return issues


def proper_names(text: str) -> list[str]:
    """Find capitalized Latin names, marked titles and explicitly named entities."""
    names = [match[1].strip() for match in _BOOK.finditer(text)]
    names.extend(match[1].strip() for match in _NAMED_ZH_TERM.finditer(text))
    for match in _LATIN_WORD.finditer(text):
        word = match[0]
        if len(word) < 2 or not word[0].isupper() or word.casefold() in _PROPER_SKIP:
            continue
        if word[1:].islower() and _is_sentence_start(text, match.start()):
            continue
        names.append(word)
    return names


def number_mentions(text: str) -> list[tuple[float, float, str]]:
    mentions: list[tuple[float, float, str]] = []

    def decimal(match: re.Match[str]) -> str:
        whole = source_number_mentions(match[1])[0][0]
        fraction = "".join(str(_SPOKEN_DIGITS.index(word)) for word in match[2].lower().split())
        value = float(f"{int(whole)}.{fraction}")
        mentions.append((value, value, match[0]))
        return " "

    # Phase 1B recognizes the integer words on each side of a spoken decimal.
    # Read them together so "three point eight" supports 3.8.
    text = _SPOKEN_DECIMAL.sub(decimal, text)
    return mentions + body_number_mentions(text) + source_number_mentions(text)


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


def _is_sentence_start(text: str, index: int) -> bool:
    previous = text[:index]
    return not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", previous) or bool(
        re.search(r"[.!?。！？]\s*$", previous)
    )


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
        marked = any(cue in head for cue in ("do not", "don't", "不要", "别", "必须"))
        if starts_en or starts_zh or marked:
            kept.append(line)
    return kept


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
    failed = {name.replace("_", "-") for name in _FAILED_STATUS} | {"not-deposited"}
    forbidden = [status for status in ctx.job_statuses
                 if status.strip().casefold().replace("_", "-") in failed]
    return _result("R15", [f"status is {status} so note.md must not be deposited" for status in forbidden],
                   "status does not forbid a note")


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
    # An untranslated proper name does not change the language of a sentence.
    for name in proper_names(prose):
        prose = prose.replace(name, " ")
    for name in proper_names(quote):
        quote = quote.replace(name, " ")
    prose_cjk, prose_latin = _script_counts(prose)
    quote_cjk, quote_latin = _script_counts(quote)
    prose_zh = prose_cjk > prose_latin and prose_cjk > 0
    quote_zh = quote_cjk > quote_latin and quote_cjk > 0
    prose_en = prose_latin > prose_cjk and prose_latin > 0
    quote_en = quote_latin > quote_cjk and quote_latin > 0
    return (prose_zh and quote_en) or (prose_en and quote_zh)


EVIDENCE_HEADING = "原文依据"
ACTION_HEADING = _C04_END[-1]
SCREEN_TAG = "[画面]"
UNCERTAIN_SCREEN_TAG = "[画面?]"
SCREEN_FILE = "screen.txt"
SCREEN_FRAMES = "screen-frames"
OMISSION_LINE = re.compile(r"^本文略去[｜|]\s*(.*?)\s*$")
TIME_TOLERANCE = 15
MISSING_TIMESTAMPS = "缺时间戳，请用带时间戳的转写重跑"
_NO_DISAGREEMENT = re.compile(r"不适用[（(]文稿中未出现意见分歧[）)][。.]?")
_ENGLISH_WORD = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]+(?:['’‐‑-][A-Za-z]+)*(?![A-Za-z0-9])")


@dataclass(frozen=True)
class QuoteMatch:
    offset: int
    cues: tuple[quality_gate.Segment, ...]


@dataclass(frozen=True)
class Quote:
    raw: str
    text: str
    stamp: int | None
    matches: tuple[QuoteMatch, ...]
    anchor: quality_gate.Segment | None
    match: QuoteMatch | None
    screen: bool = False

    @property
    def timed(self) -> bool:
        return (
            self.anchor is not None and self.stamp is not None
            and abs(self.stamp - int(self.anchor.start)) <= TIME_TOLERANCE
        )


@dataclass
class RuleContext:
    transcript_path: Path
    note: str
    job_statuses: tuple[str, ...]
    gate: quality_gate.GateResult | None
    fields: dict
    segments: list[quality_gate.Segment]
    speech: str
    sections: list[DeliverySection]
    quotes: list[Quote]
    evidence_errors: list[str]
    omission: str | None
    cited: bool
    has_screen_file: bool = False

    @property
    def exists(self) -> bool:
        return self.gate is not None

    @property
    def quoted(self) -> bool:
        return any(quote.matches for quote in self.quotes)

    @property
    def has_clock(self) -> bool:
        return any(cue.start is not None for cue in self.segments)

    @property
    def valid_quotes(self) -> list[Quote]:
        return [quote for quote in self.quotes if quote.timed]


def clock_seconds(clock: str) -> int | None:
    parts = clock.split(":")
    if not 2 <= len(parts) <= 3 or not all(part.isascii() and part.isdigit() for part in parts):
        return None
    if len(parts[-1]) != 2 or int(parts[-1]) >= 60 or len(parts[-2]) < 2:
        return None
    if len(parts) == 3 and (len(parts[1]) != 2 or int(parts[1]) >= 60):
        return None
    return sum(int(part) * 60**index for index, part in enumerate(reversed(parts)))


def parse_stamp(text: str) -> tuple[int | None, str]:
    match = _STAMP.match(text.strip())
    stamp = clock_seconds(match[1]) if match else None
    return (stamp, text.strip()[match.end():].strip()) if stamp is not None else (None, text.strip())


def screen_mode() -> str:
    value = os.environ.get("TFV_SCREEN_MODE", "").strip().casefold()
    return value if value in {"slides", "nameplate"} else "off"


def screen_tag(text: str) -> str:
    return next((tag for tag in (SCREEN_TAG, UNCERTAIN_SCREEN_TAG) if text.startswith(tag)), "")


def _screen_index(path: Path) -> dict[str, tuple[QuoteMatch, ...]]:
    try:
        content = path.read_bytes()
        lines = content.decode("utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return {}
    try:
        status = json.loads(path.with_name("status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = None
    screen = status.get("screen_ocr") if isinstance(status, dict) else None
    if isinstance(screen, dict) and (
        screen.get("state") != "ready" or screen.get("sha256") != hashlib.sha256(content).hexdigest()
    ):
        return {}
    matches: dict[str, list[QuoteMatch]] = {}
    for line in lines:
        stamp, tagged = parse_stamp(line)
        if stamp is None or not tagged.startswith(SCREEN_TAG):
            continue
        text = tagged[len(SCREEN_TAG):].strip()
        if text:
            cue = quality_gate.Segment(stamp, stamp, text)
            matches.setdefault(text, []).append(QuoteMatch(0, (cue,)))
    return {text: tuple(locations) for text, locations in matches.items()}


def _fmt(seconds: int) -> str:
    return quality_gate.format_stamp(seconds)[1:-1]


def _speech(ctx: RuleContext) -> str:
    return ctx.speech


def _checked_clock(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def transcript_segments(raw: str, sidecar: Path) -> list[quality_gate.Segment]:
    """Use real cue clocks. A sidecar must describe the same current transcript."""
    lines = []
    for line in raw.lstrip("\ufeff").splitlines():
        stamp, text = parse_stamp(line)
        if text:
            lines.append(quality_gate.Segment(stamp, stamp, text))
    if not any(cue.start is not None for cue in lines):
        parsed = quality_gate.prepare_segments(raw)
        if any(cue.start is not None for cue in parsed):
            return parsed
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return lines
    if not isinstance(data, list) or len(data) != len(lines):
        return lines
    cues = []
    for row, line in zip(data, lines):
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            return lines
        start, end = _checked_clock(row.get("start")), _checked_clock(row.get("end"))
        if (
            _fold(row["text"]) != _fold(line.text)
            or (line.start is not None and (start is None or int(start) != line.start))
            or (end is not None and (start is None or end < start))
        ):
            return lines
        cues.append(quality_gate.Segment(start, end, line.text))
    return cues


class TranscriptIndex:
    """Fold whitespace and case once. Keep cue spans for each exact occurrence."""

    def __init__(self, segments: list[quality_gate.Segment]):
        self.cues = [segment for segment in segments if segment.text.strip()]
        parts = [_fold(cue.text) for cue in self.cues]
        self.text = " ".join(parts)
        self.starts, self.ends = [], []
        cursor = 0
        for part in parts:
            self.starts.append(cursor)
            cursor += len(part)
            self.ends.append(cursor)
            cursor += 1

    def matches(self, text: str) -> tuple[QuoteMatch, ...]:
        needle = _fold(text)
        if len(needle) < QUOTE_WINDOW:
            return ()
        found = []
        offset = self.text.find(needle)
        while offset >= 0:
            first = bisect_right(self.ends, offset)
            last = bisect_left(self.starts, offset + len(needle))
            found.append(QuoteMatch(offset, tuple(self.cues[first:last])))
            offset = self.text.find(needle, offset + 1)
        return tuple(found)


def _verbatim_haystack(segments: list[quality_gate.Segment], speech: str) -> str:
    return TranscriptIndex(segments).text if segments else _fold(speech)


def _end_quotes(
    body: str, index: TranscriptIndex, screen: dict[str, tuple[QuoteMatch, ...]] | None,
) -> tuple[list[Quote], list[str]]:
    quotes, errors = [], []
    for line in body.splitlines():
        if not line.strip():
            continue
        raw = re.fullmatch(r">[ \t]+([^\n]+)", line.strip())
        if raw is None:
            errors.append(f"expected one blockquote per evidence line: {line.strip()[:80]}")
            continue
        stamp, text = parse_stamp(raw[1])
        tag = screen_tag(text) if screen is not None else ""
        if tag:
            text = text[len(tag):].strip()
            matches = screen.get(text, ()) if tag == SCREEN_TAG else ()
        else:
            matches = index.matches(text.removeprefix("[--:--]").strip())
        if not tag and stamp is not None and not _STAMP.match(raw[1])[2]:
            errors.append(f"add a space after quote timestamp [{_fmt(stamp)}]")
        nearest = min(
            ((abs(stamp - int(cue.start)), cue.start, match.offset, cue, match)
             for match in matches for cue in match.cues
             if stamp is not None and cue.start is not None),
            default=None,
            key=lambda candidate: candidate[:3],
        )
        quotes.append(Quote(raw[1], text, stamp, matches,
                            nearest[3] if nearest else None, nearest[4] if nearest else None,
                            screen=bool(tag)))
    return quotes, errors


def _cites(fields: dict, transcript: Path, *, job: bool) -> bool:
    value = fields.get("transcript_path")
    if not value:
        return False
    declared = Path(value)
    expected = transcript.resolve()
    if declared.is_absolute():
        return declared.resolve() == expected
    if (transcript.parent / declared).resolve() == expected:
        return True
    # Standalone callers also use a repository-relative --transcript and note.
    return not job and declared.resolve() == expected


def build_context(
    transcript: Path,
    note: str,
    *,
    expected_lang: str | None = None,
    confidence: float | None = None,
    job_status: str | None = None,
    job: bool = False,
    raw: str | None = None,
) -> RuleContext:
    if raw is None and transcript.is_file():
        raw = transcript.read_text(encoding="utf-8-sig", errors="replace")
    gate = quality_gate.assess(raw, expected_lang=expected_lang, confidence=confidence) if raw is not None else None
    segments = transcript_segments(raw or "", transcript.with_name("segments.json"))
    note = note.lstrip("\ufeff")
    # The standalone evaluator can put its Markdown annotations above the note.
    note = re.sub(r"\A(?:# (?:expect|fixture_[a-z]+):[^\n]*\n)+", "", note)
    fields = knowledge_note.parse_frontmatter(note) or {}
    speech = "\n".join(cue.text for cue in segments)
    body = _FRONTMATTER.sub("", note, count=1)
    evidence_heading = next((heading for heading in _HEADING.finditer(body)
                             if heading.groups() == ("##", EVIDENCE_HEADING)), None)
    quotes, evidence_errors = [], []
    screen_path = transcript.with_name(SCREEN_FILE)
    screen_enabled = job and screen_mode() != "off"
    screen = _screen_index(screen_path) if screen_enabled else None
    omission = None
    if evidence_heading:
        quotes, evidence_errors = _end_quotes(body[evidence_heading.end():], TranscriptIndex(segments), screen)
        body = body[:evidence_heading.start()].rstrip()
        lines = body.splitlines()
        omitted = OMISSION_LINE.fullmatch(lines[-1]) if lines else None
        if omitted and omitted[1]:
            omission = omitted[1]
            body = "\n".join(lines[:-1])
    sections = delivery_sections(body)
    return RuleContext(
        transcript, note, tuple(status for status in (job_status, fields.get("job_status")) if status),
        gate, fields, segments, speech, sections, quotes, evidence_errors, omission,
        _cites(fields, transcript, job=job), screen_enabled and screen_path.is_file(),
    )


def _result(rule: str, issues: list[str], success: str) -> tuple[str, bool, str]:
    return (rule, not issues, "; ".join(issues) if issues else success)


def r04_quotes_verbatim(ctx: RuleContext) -> tuple[str, bool, str]:
    issues = list(ctx.evidence_errors)
    if not ctx.quotes:
        issues.append(f"{EVIDENCE_HEADING} needs at least one contiguous transcript quote")
    for quote in ctx.quotes:
        if not quote.matches:
            if quote.screen:
                issues.append(f"screen quote must match a complete [画面] line in screen.txt: {quote.raw[:100]}")
            else:
                issues.append(f"quote is not verbatim for at least {QUOTE_WINDOW} characters: {quote.raw[:100]}")
    return _result("R04", issues, "end quotes are verbatim and contiguous")


def r05_timestamps(ctx: RuleContext) -> tuple[str, bool, str]:
    if ctx.exists and not ctx.has_clock:
        return ("R05", False, MISSING_TIMESTAMPS)
    issues = []
    for quote in ctx.quotes:
        if quote.stamp is None:
            issues.append(f"missing or invalid quote timestamp: {quote.raw[:80]}")
        elif quote.matches and quote.anchor is None:
            issues.append(f"quote [{_fmt(quote.stamp)}] does not match a timed cue")
        elif quote.anchor is not None and not quote.timed:
            anchor = int(quote.anchor.start)
            delta = abs(quote.stamp - anchor)
            issues.append(f"quote [{_fmt(quote.stamp)}] is {delta}s from the cue at [{_fmt(anchor)}]")
    return _result("R05", issues, "quote stamps match the transcript")


def delivery_times(prose: str) -> set[int]:
    return {seconds for clock in _DELIVERY_TIME.findall(prose)
            if (seconds := clock_seconds(clock)) is not None}


def prose_without_times(prose: str) -> str:
    return _DELIVERY_TIME.sub(
        lambda match: "" if clock_seconds(match[1]) is not None else match[0], prose,
    ).strip()


def match_link(stamp: int, quotes: list[Quote]) -> tuple[list[Quote], str]:
    exact = [quote for quote in quotes if stamp == quote.stamp]
    if exact and sum(not quote.screen for quote in exact) <= 1:
        return exact, ""
    nearest = sorted(
        (quote for quote in quotes if abs(stamp - quote.stamp) <= TIME_TOLERANCE),
        key=lambda quote: abs(stamp - quote.stamp),
    )
    if not nearest:
        return [], "has no end quote within 15s"
    if len(nearest) > 1 and abs(stamp - nearest[0].stamp) == abs(stamp - nearest[1].stamp):
        return [], "has no unique nearest end quote"
    return nearest[:1], ""


def linked_quotes(prose: str, quotes: list[Quote]) -> list[Quote]:
    return [quote for stamp in sorted(delivery_times(prose))
            for quote in match_link(stamp, quotes)[0]]


def _with_parents(sections: list[DeliverySection]):
    parent = ""
    for section in sections[1:]:
        if section.level == 2:
            parent = section.heading
        yield parent, section


def _fixed_explanation(parent: str, claim: str) -> bool:
    return parent == "意见不一致的地方" and bool(_NO_DISAGREEMENT.fullmatch(claim))


def c04a_structure(ctx: RuleContext) -> tuple[str, bool, str]:
    fields = ctx.fields
    issues = delivery_structure(ctx.sections, fields.get("type", ""))
    required = ("title", "source", "channel", "published", "type", "caption_kind",
                "skill_version", "transcript_path", "tags")
    absent = [name for name in required if name not in fields
              or (not fields[name].strip() and name not in {"channel", "published"})]
    if absent:
        issues.append(f"missing frontmatter properties: {', '.join(absent)}")
    if not ctx.cited:
        issues.append(f"transcript_path must resolve to {ctx.transcript_path.as_posix()}")
    if "note_path" in fields:
        issues.append("note_path is no longer a single-note property")
    if "gate_passed" in fields and not knowledge_note._truthy(fields["gate_passed"]):
        issues.append("gate_passed must be true when supplied")
    if ctx.omission is None:
        issues.append(f"expected 本文略去 on its own line after {ACTION_HEADING}, before {EVIDENCE_HEADING}")
    for parent, section in _with_parents(ctx.sections):
        for claim in section.prose:
            if claim.startswith(">") or any(line.startswith("本文略去") for line in claim.splitlines()):
                issues.append(f"orphan text in {section.heading}: {claim.splitlines()[0][:80]}")
            elif knowledge_note._STUB.search(claim) or "FILL:" in claim or re.search(r"〈[^〉]+〉", claim):
                issues.append(f"placeholder text in {section.heading}: {claim.splitlines()[0][:80]}")
            elif knowledge_note.inapplicable_reason(claim) and not _fixed_explanation(parent, claim):
                issues.append(f"empty content in {section.heading}: {claim.splitlines()[0][:80]}")
    return _result("C04a", issues, "single-note properties and structure are present")


def c04b_trace(ctx: RuleContext) -> tuple[str, bool, str]:
    issues = []
    stamps, used, used_screen, source_starts = set(), set(), set(), {}
    for quote in ctx.quotes:
        if quote.stamp is None or quote.screen:
            continue
        if quote.stamp in stamps:
            issues.append(f"duplicate end quote timestamp [{_fmt(quote.stamp)}]")
        stamps.add(quote.stamp)
        if quote.timed:
            first = quote.match.cues[0].start
            if first is not None:
                earlier = source_starts.setdefault(int(first), quote.stamp)
                if earlier != quote.stamp:
                    issues.append(f"end quotes starting at source second [{_fmt(first)}] need one continuous quote")
    valid = ctx.valid_quotes
    middle = _C04_MIDDLE.get(ctx.fields.get("type"), ())
    for parent, section in _with_parents(ctx.sections):
        for claim in [section.heading, *section.prose]:
            is_middle_claim = parent in middle and claim != section.heading and not _fixed_explanation(parent, claim)
            times = delivery_times(claim)
            clean = prose_without_times(claim)
            if "⏱" in clean:
                issues.append(f"{section.heading}: malformed ⏱ time link")
            if not times and is_middle_claim:
                issues.append(f"{section.heading}: claim is missing a ⏱ time link: {clean[:80]}")
            for stamp in sorted(times):
                linked, issue = match_link(stamp, valid)
                if issue:
                    issues.append(f"{section.heading}: ⏱ {_fmt(stamp)} {issue}")
                    continue
                for quote in linked:
                    if quote.screen:
                        used_screen.add(quote.raw)
                        continue
                    used.add(quote.stamp)
                    if is_middle_claim and not _cross_script(clean, quote.text):
                        if len(_content_tokens(clean) & _content_tokens(quote.text)) < 3:
                            issues.append(f"{section.heading}: ⏱ {_fmt(stamp)} needs three shared content tokens")
    for stamp in sorted(stamps - used):
        issues.append(f"unused end quote [{_fmt(stamp)}]")
    for quote in ctx.quotes:
        if quote.screen and quote.stamp is not None and quote.raw not in used_screen:
            issues.append(f"unused screen quote [{_fmt(quote.stamp)}]: {quote.text[:80]}")
    return _result("C04b", issues, "body time links and end quotes match in both directions")


def _remove_properties(text: str, fields: dict) -> str:
    for value in sorted((fields.get(key, "") for key in ("title", "channel", "published")), key=len, reverse=True):
        if not value:
            continue
        pattern = re.escape(value)
        if re.match(r"[A-Za-z0-9]", value):
            pattern = r"(?<![A-Za-z0-9])" + pattern
        if re.search(r"[A-Za-z0-9]$", value):
            pattern += r"(?![A-Za-z0-9])"
        text = re.sub(pattern, lambda match: " " * len(match[0]), text)
    return text


def c04c_grounding(ctx: RuleContext) -> tuple[str, bool, str]:
    issues, unknown_quoted = [], {}
    valid = ctx.valid_quotes
    blocks = [block for section in ctx.sections for block in section.blocks]
    corrections = caption_corrections(blocks, ctx.speech)

    def mentions(text: str) -> list[tuple[float, float, str]]:
        if ctx.has_screen_file:
            text = re.sub(r"(?<=\d)[xX](?![A-Za-z0-9])", "×", text)
        return number_mentions(text)

    for parent, section in _with_parents(ctx.sections):
        for claim in [*([section.heading] if section.level == 3 else []), *section.prose]:
            if _fixed_explanation(parent, claim):
                continue
            source_claims = section.prose if claim == section.heading else [claim]
            times = delivery_times(claim).union(*(delivery_times(item) for item in source_claims))
            linked = [quote for stamp in times for quote in match_link(stamp, valid)[0]]
            if times and not linked:
                continue
            excerpts = [quote.text for quote in (linked if times else valid)]
            source = excerpts + corrections
            prose = _INLINE_LIST_ITEM.sub(r"\1 ", prose_without_times(claim))
            if parent == _C04_START[1]:
                prose = _remove_properties(prose, ctx.fields)
            numeric_source = excerpts if ctx.has_screen_file else source
            support = [mention for excerpt in numeric_source for mention in mentions(excerpt)]
            missing_numbers = {
                label for low, high, label in mentions(prose)
                if not any(slow <= high and shigh >= low for slow, shigh, _ in support)
            }
            missing_names = {
                name for name in proper_names(prose)
                if not any(term_occurs(name, excerpt) for excerpt in source)
            }
            for match in _QUOTED_TERM.finditer(prose):
                term = (match[1] or match[2]).strip()
                if term and not term.startswith("[") and term.casefold() not in _PROPER_SKIP:
                    if not any(term_occurs(term, excerpt) for excerpt in source):
                        unknown_quoted.setdefault(term.casefold(), term)
            issues.extend(f"{section.heading}: number {label!r} is absent from the end evidence"
                          for label in sorted(missing_numbers))
            issues.extend(f"{section.heading}: name {name!r} is absent from the end evidence"
                          for name in sorted(missing_names))
    if len(unknown_quoted) > 2:
        issues.append(f"quoted names are absent from the end evidence: {', '.join(list(unknown_quoted.values())[:6])}")
    return _result("C04c", issues, "numbers and names have end evidence")


def c04d_explanations(ctx: RuleContext) -> tuple[str, bool, str]:
    blocks = [block for section in ctx.sections for block in section.blocks]
    corrections = caption_corrections(blocks, ctx.speech)
    cited_screen = [quote.text for quote in ctx.valid_quotes if quote.screen]
    return _result("C04d", explanation_issues(blocks, ctx.speech, [*corrections, *cited_screen]),
                   "explanations use marked blocks")


def r13_today_step(ctx: RuleContext) -> tuple[str, bool, str]:
    section = next((section for section in ctx.sections if section.heading == ACTION_HEADING), None)
    if section is None:
        return ("R13", False, f"missing {ACTION_HEADING}")
    prose = "\n".join(section.prose)
    evidence = linked_quotes(prose, ctx.valid_quotes)
    if not evidence:
        return ("R13", False, f"{ACTION_HEADING} needs a supporting ⏱ link")
    clean = re.sub(r"[（(]改写讲者做法[）)]", "", prose_without_times(prose))
    sentences = [sentence.strip() for sentence in _SENTENCE_SPLIT.split(clean) if sentence.strip()]
    if not sentences or len(sentences) > 2:
        return ("R13", False, f"{ACTION_HEADING} needs one action in at most two sentences")
    action = sentences[0]
    if any(_cross_script(action, quote.text) or _fold(action) in _fold(quote.text) for quote in evidence):
        return ("R13", True, "today step is short and links to its evidence")
    tokens = set(_tokens(action))
    overlap = max(
        (sum(token in imperative for token in tokens) / len(tokens)
         for quote in evidence for imperative in _imperatives(quote.text) if tokens),
        default=0,
    )
    return _result("R13", [] if overlap >= 0.30 else [
        f"{ACTION_HEADING} overlaps an imperative in its linked evidence by {overlap:.0%}; need 30%",
    ], "today step is a short grounded action")


def warnings(ctx: RuleContext) -> list[str]:
    if ctx.gate is None:
        return []
    lang = ctx.gate.metrics["expected_lang"]
    if lang and lang.split("-")[0] != "en":
        return []
    if ctx.gate.metrics["latin_ratio"] < 0.70:
        return []
    prose = "\n".join(
        prose_without_times(part) for section in ctx.sections
        for part in [section.heading, *section.prose] if not part.startswith(">")
    )
    han = sum(
        char == "〇" or unicodedata.name(char, "").startswith(("CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-"))
        for char in prose
    )
    speech = "".join(char for char in unicodedata.normalize("NFKD", ctx.speech)
                     if not unicodedata.combining(char))
    words = len(_ENGLISH_WORD.findall(speech))
    if han * 5 > words * 6:
        return [f"长度 WARN: 中文正文 {han} 个汉字，超过英文文稿 {words} 词的 1.2 倍"]
    return []


RULES = (r01_gate, r04_quotes_verbatim, r05_timestamps, r13_today_step, r14_platform_title,
         r15_failed_status, c04a_structure, c04b_trace, c04c_grounding, c04d_explanations)


def run_rules(ctx: RuleContext) -> list[tuple[str, bool, str]]:
    return [rule(ctx) for rule in RULES]


def failure_lines(results: list[tuple[str, bool, str]]) -> list[str]:
    return [f"{rule_id} FAIL: {message}" for rule_id, ok, message in results if not ok]
