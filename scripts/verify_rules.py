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
from datetime import date
from decimal import Decimal
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
_PARENTHESIZED_ORIGINAL = re.compile(
    r"(?<=[\u3400-\u4dbf\u4e00-\u9fff”」])(?:[ \t]*（([^（）\n]+)）|[ \t]*\(([^()\n]+)\))"
)
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
    words = re.findall(r"[a-z]+", text.casefold())
    middle = len(words) // 2
    if words[:middle] == words[middle:]:
        words = words[:middle]
    for index, word in enumerate(words):
        if index and word == words[index - 1]:
            continue
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
        elif word in _EN_MAGNITUDE:
            scale = _EN_MAGNITUDE[word]
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


_EN_MAGNITUDE = {"thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}
_EN_ABBREVIATED_MAGNITUDE = {"k": 10**3, "M": 10**6, "B": 10**9}
_ZH_MAGNITUDE = {"万": 10**4, "亿": 10**8, "万亿": 10**12}
_ARABIC_MAGNITUDE = re.compile(
    r"(?<![A-Za-z0-9_.,])(?P<count>[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)"
    r"(?:[ \t]*(?P<zh>万亿|万|亿)(?![万亿])|(?P<en>[kKMB])"
    r"(?:(?![A-Za-z0-9_])|(?=(?:GPUh|vCPUh)\b)))"
)
_ZH_APPROXIMATE_COUNT = re.compile(r"(?P<prefix>上|成|数|约|大约)(?P<scale>十万|万亿|百万|千万|百|千|万|亿)")
_EN_APPROXIMATE_COUNT = re.compile(
    r"\b(?P<scale>hundreds|thousands|millions|billions)"
    r"(?:[ \t]+of[ \t]+(?P<of>thousands|millions|billions))?\b", re.IGNORECASE,
)
_APPROXIMATE_SCALE = {"百": 100, "千": 1_000, "十万": 100_000, "百万": 1_000_000,
                      "千万": 10_000_000, "hundred": 100, **_ZH_MAGNITUDE, **_EN_MAGNITUDE}
_INDEFINITE_PERCENT = re.compile(r"百分之几(?![十百千万亿])")
_MULTIPLIER_SUFFIX = re.compile(r"(?<=\d)[xX×](?![A-Za-z0-9_])")
_ACCELERATOR_HOUR = re.compile(r"(?<![A-Za-z0-9])(GPU|vCPU)h(?![A-Za-z0-9])", re.IGNORECASE)
_COMPOUND_NAME_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])")
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)[^\n]+?(?<!`)\1(?!`)")
_FENCED_CODE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
_URL = re.compile(r"https?://[^\s`<>。！？、，；）]+", re.IGNORECASE)


_EN_SOURCE_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])(?:\d+(?:,\d{3})*(?:\.\d+)?%?"
    r"(?:[ -]+(?:hundred|thousand|million|billion|trillion|dozen|dozens|decade|decades))?%?)(?![A-Za-z0-9]|[.,][0-9])",
    re.IGNORECASE,
)
_EN_PLUS_SCALE = re.compile(
    r"(?<![A-Za-z0-9])(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)[ \t]+plus[ \t]+"
    r"(?P<scale>hundred|thousand|million|billion|trillion)\b",
    re.IGNORECASE,
)


def _arabic_number_value(raw: str) -> float:
    parsed = re.match(r"(\d+(?:\.\d+)?)(?:[ -]+([a-z]+))?", raw.replace(",", ""), re.IGNORECASE)
    assert parsed is not None
    value = float(parsed.group(1))
    scale = (parsed.group(2) or "").casefold()
    return value * {
        "hundred": 100, **_EN_MAGNITUDE, "dozen": 12, "dozens": 12,
        "decade": 10, "decades": 10,
    }.get(scale, 1)


_EN_NUMBER_WORD_PATTERN = (
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"couple|hundred|thousand|million|billion|trillion|dozens?|decades?"
)
# A scale may introduce the rest of one number. A plain "one and two"
# enumerates two values, so neither endpoint can be replaced with their sum.
_EN_SCALE_AND = r"(?:(?<=hundred)|(?<=thousand)|(?<=million)|(?<=billion)|(?<=trillion))[ -]+and[ -]+"
_EN_NUMBER = re.compile(
    rf"\b(?:{_EN_NUMBER_WORD_PATTERN})(?:(?:[ -]+|{_EN_SCALE_AND})(?:{_EN_NUMBER_WORD_PATTERN}))*\b",
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


_EN_COUNT_RANGE = re.compile(
    rf"({_EN_NUMBER.pattern})[ \t]+(?:or|to)[ \t]+({_EN_NUMBER.pattern})",
    re.IGNORECASE,
)


_SPOKEN_DIGITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_SPOKEN_DIGIT = "|".join(_SPOKEN_DIGITS)
_EN_OPEN_COUNT = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight)[ \t]+or[ \t]+(?:more|multiple)\b", re.IGNORECASE,
)
_SPOKEN_HALF = re.compile(rf"({_EN_NUMBER.pattern})[ \t]+and[ \t]+a[ \t]+half\b", re.IGNORECASE)
_MIXED_DECIMAL = re.compile(rf"(?<![A-Za-z0-9])({_SPOKEN_DIGIT})\.([0-9]+)(?![A-Za-z0-9])", re.IGNORECASE)
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
_CAPTION_CORRECTION = re.compile(r"^(?:字幕|画面)写作\s*[:：]?\s*(.+?)[，,]\s*实为\s*[:：]?\s*(.+)$")
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
_CONFERENCE_LEGACY = _C04_MIDDLE["大会"][-1]
_CONFERENCE_MAIN = "主线讲了什么"
_CONFERENCE_CLAIMS = "只是口头声称"


def middle_headings(kind: str, sections: list[DeliverySection]) -> tuple[str, ...]:
    middle = _C04_MIDDLE.get(kind, ())
    if kind == "大会" and any(section.level == 2 and section.heading == _CONFERENCE_MAIN
                            for section in sections):
        return (middle[0], _CONFERENCE_MAIN)
    return middle



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
    expected_middle = middle_headings(kind, sections)
    if not expected_middle:
        issues.append("frontmatter type must be 讲座, 访谈, 大会 or 演示")
    else:
        expected = _C04_START + expected_middle + _C04_END
        actual = tuple(section.heading for section in sections if section.level == 2)
        if actual != expected:
            issues.append(f"expected H2 sections in order: {' / '.join(expected)}")
    parent = ""
    children: list[str] = []
    middle = expected_middle
    for index, section in enumerate(sections[1:], 1):
        if section.level == 2:
            parent = section.heading
        elif section.level != 3 or parent not in middle:
            issues.append(f"unexpected heading: {section.heading}")
        elif parent in {_CONFERENCE_LEGACY, _CONFERENCE_MAIN}:
            children.append(section.heading)
        has_subheading = (
            section.level == 2 and section.heading in middle
            and index + 1 < len(sections) and sections[index + 1].level == 3
        )
        if section.level == 2 and section.heading in {"话题", _CONFERENCE_LEGACY, _CONFERENCE_MAIN} and not has_subheading:
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
    if kind == "大会":
        legacy = _CONFERENCE_MAIN not in middle
        claims = children.count(_CONFERENCE_CLAIMS)
        if legacy and (len(children) < 2 or claims != 1 or children[-1] != _CONFERENCE_CLAIMS):
            issues.append(f"{_CONFERENCE_LEGACY} needs at least one evidence subheading followed by {_CONFERENCE_CLAIMS}")
        elif not legacy and (
            not any(child != _CONFERENCE_CLAIMS for child in children)
            or claims > 1 or (claims and children[-1] != _CONFERENCE_CLAIMS)
        ):
            issues.append(f"{_CONFERENCE_MAIN} needs topic subheadings, with {_CONFERENCE_CLAIMS} last when present")
    return issues


def _term_pattern(term: str) -> str:
    pattern = r"\s+".join(map(re.escape, term.split()))
    if re.match(r"[A-Za-z0-9]", term):
        pattern = r"(?<![A-Za-z0-9])" + pattern
    if re.search(r"[A-Za-z0-9]$", term):
        pattern += r"(?![A-Za-z0-9])"
    return pattern


def term_occurs(term: str, source: str) -> bool:
    if not re.search(r"[A-Za-z0-9]", term):
        return _fold(term) in _fold(source)
    return bool(re.search(_term_pattern(term), source, re.IGNORECASE))


def caption_correction_pair(line: str) -> tuple[str, str] | None:
    correction = _CAPTION_CORRECTION.fullmatch(line)
    if correction is None:
        return None
    original = correction[1].strip().strip(_CORRECTION_QUOTES).strip()
    target = _CORRECTION_TARGET.match(correction[2].strip())
    corrected = target[0].strip().strip(_CORRECTION_QUOTES).strip() if target else ""
    return (original, corrected) if original and corrected else None


def caption_corrections(
    blocks: list[list[str]], transcript: str, screen: tuple[str, ...] = (),
) -> list[tuple[str, str]]:
    """Return corrections backed by the transcript or cited trusted screen text."""
    corrections: list[tuple[str, str]] = []
    for header, *lines in blocks:
        match = _CALLOUT.fullmatch(header)
        if match is None or match.groups() != ("warning", "字幕更正"):
            continue
        for line in lines:
            pair = caption_correction_pair(line)
            sources = screen if line.startswith("画面") else (transcript,)
            if pair and any(term_occurs(pair[0], source) for source in sources):
                corrections.append(pair)
    return corrections


def explanation_issues(
    blocks: list[list[str]], transcript: str, corrections: list[str], screen: tuple[str, ...] = (),
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
            if not caption_corrections([[header, *lines]], transcript, screen):
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

    def plus_scale(match: re.Match[str]) -> str:
        value = _arabic_number_value(f"{match['number']} {match['scale']}")
        mentions.append((value, value, match[0]))
        # The full phrase supplies the count, not either component on its own.
        return " "

    def decimal(match: re.Match[str]) -> str:
        whole = source_number_mentions(match[1])[0][0]
        fraction = "".join(str(_SPOKEN_DIGITS.index(word)) for word in match[2].lower().split())
        value = float(f"{int(whole)}.{fraction}")
        mentions.append((value, value, match[0]))
        return " "

    def mixed_decimal(match: re.Match[str]) -> str:
        value = float(f"{_EN_NUMBER_WORDS[match[1].casefold()]}.{match[2]}")
        mentions.append((value, value, match[0]))
        return " "

    def half(match: re.Match[str]) -> str:
        whole = _english_integer(match[1])
        words = match[1].casefold().split()
        # ASR can preserve the two alternatives as "seven seven and a half".
        if len(words) > 1 and words[-2] == words[-1]:
            mentions.append((whole, whole, words[-1]))
        mentions.append((whole + 0.5, whole + 0.5, match[0]))
        return " "

    text = _EN_PLUS_SCALE.sub(plus_scale, text)
    text = _MIXED_DECIMAL.sub(mixed_decimal, text)
    text = _SPOKEN_HALF.sub(half, text)
    text = _SPOKEN_DECIMAL.sub(decimal, text)
    return mentions + body_number_mentions(text) + source_number_mentions(text)


_MONTH_NAMES = "January February March April May June July August September October November December".split()
_EN_MONTHS = {
    spelling.casefold(): number
    for number, month in enumerate(_MONTH_NAMES, 1)
    for spelling in (month, month[:3])
}
_EN_MONTHS["sept"] = 9
_MONTH = re.compile(
    rf"(?<![\d{_ZH_NUMERAL}])(?P<zh>0?[1-9]|1[0-2]|[一二三四五六七八九]|十[一二]?)[ \t]*月"
    r"(?![内內]|以[内內]|时间|時間)"
    rf"|(?<![A-Za-z0-9])(?P<en>{'|'.join(sorted(_EN_MONTHS, key=len, reverse=True))})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_DAY_BEFORE_MONTH = re.compile(r"\b[0-9]{1,2}(?:st|nd|rd|th)?[ \t]+\Z", re.I)
_MONTH_DATE_BEFORE = re.compile(r"\b(?:in|of|during|since|until|by|from)[ \t]+\Z", re.I)
_MONTH_DATE_AFTER = re.compile(r"\.?[ \t]*[0-9]+\b")
_CAPITALIZED_FOLLOWING_WORD = re.compile(r"[ \t]+[A-Z][a-z]")


def split_months(text: str) -> tuple[str, dict[int, str]]:
    """Treat calendar months as months, so they cannot stand in for quantities."""
    months: dict[int, str] = {}

    def extract(match: re.Match[str]) -> str:
        label = match["zh"]
        if label is not None:
            month = int(label) if label.isascii() else _chinese_integer(label)
        else:
            label = match["en"]
            key = label.casefold()
            before = text[:match.start()]
            has_day = bool(_DAY_BEFORE_MONTH.search(before) or _MONTH_DATE_AFTER.match(text, match.end()))
            if not has_day and _CAPITALIZED_FOLLOWING_WORD.match(text, match.end()):
                return label
            date_context = has_day or (
                key != "mar" and (key != "may" or not label.islower())
                and bool(_MONTH_DATE_BEFORE.search(before))
            )
            # "may" is usually a modal verb; short "mar" can also be a verb.
            if not date_context and (
                label.islower() or (key in {"mar", "may"} and not label.isupper())
            ):
                return label
            month = _EN_MONTHS[key]
        months[month] = label
        return " " * len(match[0])

    return _MONTH.sub(extract, text), months


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
    latin = len(_LATIN_WORD.findall(text))
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
SLIDE_MARKER = re.compile(r"^\[幻灯片 ([1-9][0-9]*)\](?:[ \t]+frame-[0-9]+\.png)?$")
SLIDE_SELECTION = re.compile(r"^\[幻灯片 ([1-9][0-9]*)\](?:[ \t]+.+)?$")
OMISSION_LINE = re.compile(r"^本文略去[｜|]\s*(.*?)\s*$")
TIME_TOLERANCE = 15
MISSING_TIMESTAMPS = "缺时间戳，请用带时间戳的转写重跑"
_NO_DISAGREEMENT = re.compile(r"不适用[（(]文稿中未出现意见分歧[）)][。.]?")
_ENGLISH_WORD = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]+(?:['’‐‑-][A-Za-z]+)*(?![A-Za-z0-9])")


@dataclass(frozen=True)
class QuoteMatch:
    # Character offset for speech, physical line index for screen evidence.
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


def screen_mode(job: Path | None = None) -> str:
    screen = _screen_status(job) if job is not None else None
    if screen is not None and "requested_mode" in screen:
        mode = screen.get("mode")
        if mode in ("slides", "nameplate") and _screen_source(job / SCREEN_FILE, screen) is not None:
            return mode
        return "off"
    # Archives before the host recorded its choice retain the older override.
    if "TFV_SCREEN_MODE" in os.environ or job is None:
        value = os.environ.get("TFV_SCREEN_MODE", "").strip().casefold()
        return value if value in {"slides", "nameplate"} else "off"
    source = _screen_source(job / SCREEN_FILE)
    screen = source[1] if source is not None else None
    mode = screen.get("mode") if screen is not None else None
    return mode if isinstance(mode, str) and mode in {"slides", "nameplate"} else "off"


def screen_tag(text: str) -> str:
    return next((tag for tag in (SCREEN_TAG, UNCERTAIN_SCREEN_TAG) if text.startswith(tag)), "")


def _screen_status(job: Path) -> dict | None:
    try:
        status = json.loads((job / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    screen = status.get("screen_ocr") if isinstance(status, dict) else None
    return screen if isinstance(screen, dict) else None


def _screen_source(path: Path, screen: dict | None = None) -> tuple[list[str], dict | None] | None:
    try:
        content = path.read_bytes()
        lines = content.decode("utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return None
    if screen is None:
        screen = _screen_status(path.parent)
    if screen is not None and (
        screen.get("state") != "ready" or screen.get("sha256") != hashlib.sha256(content).hexdigest()
    ):
        return None
    return lines, screen


def _screen_lines(path: Path, *, require_slides: bool = False) -> list[str] | None:
    source = _screen_source(path)
    if source is None:
        return None
    lines, screen = source
    if require_slides and (screen is None or screen.get("mode") != "slides"):
        return None
    return lines


def screen_slide_groups(path: Path) -> list[tuple[int, int]]:
    if screen_mode(path.parent) != "slides":
        return []
    lines = _screen_lines(path, require_slides=True)
    if lines is None:
        return []
    groups = []
    for line in lines:
        stamp, tagged = parse_stamp(line)
        marker = SLIDE_MARKER.fullmatch(tagged)
        if stamp is not None and marker:
            groups.append((int(marker[1]), stamp))
    if not groups:
        try:
            screen = json.loads(path.with_name("status.json").read_text(encoding="utf-8"))["screen_ocr"]
        except (OSError, ValueError, KeyError, TypeError):
            return []
        if type(screen.get("slide_count")) is int and screen["slide_count"] == 1:
            for line in lines:
                stamp, tagged = parse_stamp(line)
                tag = screen_tag(tagged)
                if stamp is not None and tag and tagged[len(tag):].strip():
                    return [(1, stamp)]
    return groups


def _screen_index(path: Path) -> dict[str, tuple[QuoteMatch, ...]]:
    matches: dict[str, list[QuoteMatch]] = {}
    for line_index, line in enumerate(_screen_lines(path) or []):
        stamp, tagged = parse_stamp(line)
        if stamp is None or not tagged.startswith(SCREEN_TAG):
            continue
        text = tagged[len(SCREEN_TAG):].strip()
        if text:
            cue = quality_gate.Segment(stamp, stamp, text)
            matches.setdefault(text, []).append(QuoteMatch(line_index, (cue,)))
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


def selection_endpoint(segments: list[quality_gate.Segment], duration: object) -> int | None:
    """Return the exclusive end of the last selection unit."""
    latest = max((cue.start for cue in segments if cue.start is not None), default=None)
    if latest is None:
        return None
    clock_end = max((cue.end for cue in segments if cue.end is not None
                     and cue.start is not None and cue.end > cue.start), default=0)
    return max(math.ceil(max(_checked_clock(duration) or 0, clock_end)), math.floor(latest) + 1)


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


def delivery_evidence(body: str) -> tuple[str, str | None, str | None]:
    evidence = next((heading for heading in _HEADING.finditer(body)
                     if heading.groups() == ("##", EVIDENCE_HEADING)), None)
    if evidence is None:
        return body, None, None
    before = body[:evidence.start()].rstrip()
    lines = before.splitlines()
    omitted = OMISSION_LINE.fullmatch(lines[-1]) if lines else None
    if omitted and omitted[1]:
        return "\n".join(lines[:-1]), body[evidence.end():], omitted[1]
    return before, body[evidence.end():], None


def caption_structure(note: str) -> tuple[str | None, list[str]]:
    body, _, omission = delivery_evidence(_FRONTMATTER.sub("", note, count=1))
    _, blocks = delivery_parts(body)
    issues = []
    for header, *lines in blocks:
        if "字幕更正" in header and (
            not re.fullmatch(r">\s*\[!warning\]\s*字幕更正", header)
            or not any(caption_correction_pair(line) for line in lines)
        ):
            issues.append("note.md 字幕更正 needs [!warning] 字幕更正 and a 字幕写作 X，实为 Y pair")
    return omission, issues


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
    body, evidence, omission = delivery_evidence(_FRONTMATTER.sub("", note, count=1))
    quotes, evidence_errors = [], []
    screen_path = transcript.with_name(SCREEN_FILE)
    screen_enabled = job and screen_mode(transcript.parent) != "off"
    screen = _screen_index(screen_path) if screen_enabled else None
    if evidence is not None:
        quotes, evidence_errors = _end_quotes(evidence, TranscriptIndex(segments), screen)
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
    middle = middle_headings(ctx.fields.get("type"), ctx.sections)
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


_ZH_VERSION = re.compile(rf"第[ \t]*([0-9]+|[{_ZH_NUMERAL}]+)[ \t]*版")
_V_VERSION = re.compile(r"(?<![A-Za-z0-9_])v([0-9]+)(?![A-Za-z0-9_]|\.[0-9])", re.IGNORECASE)
_DATE_INTEGER = rf"(?:[0-9]{{1,2}}|[{_ZH_NUMERAL}]+)"
_EN_MONTH_NAME = "|".join(sorted(_EN_MONTHS, key=len, reverse=True))
_CALENDAR_DATES = (
    re.compile(r"(?<![0-9])(?P<year>(?:19|20)[0-9]{2})-(?P<month>[0-9]{1,2})-(?P<day>[0-9]{1,2})(?![0-9])"),
    re.compile(
        rf"(?<![0-9{_ZH_NUMERAL}])(?:(?P<year>(?:19|20)[0-9]{{2}})[ \t]*年[ \t]*)?"
        rf"(?P<month>{_DATE_INTEGER})[ \t]*月[ \t]*(?P<day>{_DATE_INTEGER})[ \t]*[日号]"
    ),
    re.compile(
        rf"(?<![A-Za-z0-9])(?P<month>{_EN_MONTH_NAME})\.?[ \t]+"
        r"(?P<day>[0-9]{1,2})(?:st|nd|rd|th)?(?![0-9])"
        r"(?:,?[ \t]+(?P<year>(?:19|20)[0-9]{2})(?![0-9]))?", re.IGNORECASE,
    ),
    re.compile(
        rf"(?<![A-Za-z0-9])(?P<day>[0-9]{{1,2}})(?:st|nd|rd|th)?[ \t]+(?P<month>{_EN_MONTH_NAME})(?![A-Za-z])"
        r"(?:,?[ \t]+(?P<year>(?:19|20)[0-9]{2})(?![0-9]))?", re.IGNORECASE,
    ),
)
_OCR_DATE_SEPARATOR = re.compile(
    rf"(?<![A-Za-z0-9])((?:{_EN_MONTH_NAME})\.?[ \t]+[0-9]{{1,2}})\.(?=[ \t]+(?:19|20)[0-9]{{2}}"
    r"(?:[ \t]+[0-9]{1,2}:[0-5][0-9]\b|[ \t]*$))", re.IGNORECASE,
)
_MILLISECONDS_SUFFIX = re.compile(r"(?<=\d)[ \t]*ms(?![A-Za-z0-9_])", re.IGNORECASE)
_SPOKEN_YEAR = re.compile(
    r"(?<![A-Za-z0-9])(?:(?:early|mid|late|in)[ \t-]+)+(?P<year>(?:19|20)?[0-9]{2})(?![A-Za-z0-9]|\.[0-9])",
    re.IGNORECASE,
)
_ZH_YEAR = re.compile(
    rf"(?<![A-Za-z0-9$€£¥{_ZH_NUMERAL}])(?P<year>(?:19|20)[0-9]{{2}}|[二两][〇零一二三四五六七八九]{{3}})[ \t]*年"
)
_BARE_YEAR = re.compile(r"(?<![A-Za-z0-9_.,$€£¥+\-])(?:19|20)[0-9]{2}(?![A-Za-z0-9_%]|[.,][0-9])")
_QUANTITY_SUFFIX = re.compile(
    r"^[ \t]*(?:%|[个個家人项項次秒分天周月元块塊张張份本台件名位条條行篇倍种種万萬亿億多余餘]|美元|小时|小時"
    r"|(?:hours?|minutes?|seconds?|days?|weeks?|months?|years?|images?|recordings?|stores?|markets?"
    r"|models?|systems?|items?|users?|engineers?|employees?|people|boxes|tests?|requests?|countries|pieces?"
    r"|PRs?|repos?|repositor(?:y|ies)|lines?|files?|agents?|teams?"
    r"|tokens?|percent|dollars?|bytes?|[KMGT]B|hundred|thousand|million|billion|dozens?|decades?|plus)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NumberRange:
    low: float
    high: float


@dataclass(frozen=True)
class NumericValue:
    kind: str
    value: int | tuple[int, ...] | NumberRange
    label: str

    def supports(self, claim: NumericValue) -> bool:
        if claim.kind == "count_range":
            return ((self.kind == claim.kind and self.value == claim.value)
                    or (self.kind == "open_count" and self.value == claim.value.low))
        if self.kind == "approximate_count" and (
            not isinstance(claim.value, NumberRange) or claim.value.low == claim.value.high
        ):
            return False
        if {self.kind, claim.kind} == {"year", "bare_year"}:
            return self.value == claim.value
        source_value = NumberRange(self.value, self.value) if self.kind == "bare_year" else self.value
        claim_value = NumberRange(claim.value, claim.value) if claim.kind == "bare_year" else claim.value
        if isinstance(source_value, NumberRange) and isinstance(claim_value, NumberRange):
            if self.kind == "count_range":
                return any(claim_value.low <= endpoint <= claim_value.high
                           for endpoint in (source_value.low, source_value.high))
            return source_value.low <= claim_value.high and source_value.high >= claim_value.low
        # Older notes can already cite a literal number for their version label.
        if isinstance(source_value, NumberRange) and claim.kind == "version" and isinstance(claim_value, int):
            return source_value.low <= claim_value <= source_value.high
        return self.kind == claim.kind and self.value == claim.value


def _integer_label(label: str) -> int:
    return int(label) if label.isascii() else _chinese_integer(label)


def canonical_numbers(text: str, *, screen: bool = False) -> tuple[str, list[NumericValue]]:
    """Separate calendar values and versions before comparing ordinary quantities."""
    if screen:
        text = _OCR_DATE_SEPARATOR.sub(r"\1,", text)
    # Keep the whole decimal before the number lexer meets a Latin suffix.
    text = _MULTIPLIER_SUFFIX.sub(" ", _MILLISECONDS_SUFFIX.sub(" 毫秒", text))
    text = _INDEFINITE_PERCENT.sub(" ", text)
    values: list[NumericValue] = []

    def magnitude(match: re.Match[str]) -> str:
        if match["zh"]:
            scale = _ZH_MAGNITUDE[match["zh"]]
        else:
            abbreviation = "k" if match["en"] == "K" else match["en"]
            scale = _EN_ABBREVIATED_MAGNITUDE[abbreviation]
        value = float(Decimal(match["count"].replace(",", "")) * scale)
        values.append(NumericValue("number", NumberRange(value, value), match[0]))
        return " " * len(match[0])

    def approximate(match: re.Match[str]) -> str:
        if match.re is _ZH_APPROXIMATE_COUNT:
            low = _APPROXIMATE_SCALE[match["scale"]]
            label = match["scale"] if match["prefix"] == "上" else match[0]
        else:
            low = _APPROXIMATE_SCALE[match["scale"].casefold()[:-1]]
            if match["of"]:
                low *= _APPROXIMATE_SCALE[match["of"].casefold()[:-1]]
            label = match[0]
        values.append(NumericValue("approximate_count", NumberRange(low, 10 * low - 1), label))
        return " " * len(match[0])

    text = _ARABIC_MAGNITUDE.sub(magnitude, text)
    text = _ZH_APPROXIMATE_COUNT.sub(approximate, text)
    text = _EN_APPROXIMATE_COUNT.sub(approximate, text)

    def calendar_date(match: re.Match[str]) -> str:
        month_label, day_label = match["month"], match["day"]
        month = _EN_MONTHS.get(month_label.casefold())
        if month is None:
            month = _integer_label(month_label)
        day = _integer_label(day_label)
        year = int(match["year"]) if match["year"] else None
        try:
            date(year or 2000, month, day)
        except ValueError:
            return match[0]
        calendar = (year, month, day) if year is not None else (month, day)
        values.append(NumericValue("date", calendar, match[0]))
        values.append(NumericValue("month", month, month_label))
        if year is not None:
            values.append(NumericValue("year", year, match["year"]))
            values.append(NumericValue("date", (month, day), match[0]))
        return " " * len(match[0])

    for pattern in _CALENDAR_DATES:
        text = pattern.sub(calendar_date, text)

    def version(match: re.Match[str]) -> str:
        values.append(NumericValue("version", _integer_label(match[1]), match[1]))
        return " " * len(match[0])

    text = _V_VERSION.sub(version, _ZH_VERSION.sub(version, text))

    def year_value(match: re.Match[str]) -> str:
        if _QUANTITY_SUFFIX.match(text[match.end():]):
            return match[0]
        label = match["year"]
        year = _integer_label(label)
        if len(label) == 2:
            year += 2000
        values.append(NumericValue("year", year, label))
        return " " * len(match[0])

    text = _SPOKEN_YEAR.sub(year_value, text)
    text = _ZH_YEAR.sub(year_value, text)
    text, months = split_months(text)
    values.extend(NumericValue("month", month, label) for month, label in months.items())

    def bare_year(match: re.Match[str]) -> str:
        if _QUANTITY_SUFFIX.match(text[match.end():]) or re.search(r"[$€£¥][ \t]*$", text[:match.start()]):
            return match[0]
        values.append(NumericValue("bare_year", int(match[0]), match[0]))
        return " " * len(match[0])

    text = _BARE_YEAR.sub(bare_year, text)

    def count_range(low: float, high: float, label: str) -> str:
        if 1 <= low < high <= 9 and high == low + 1:
            values.append(NumericValue("count_range", NumberRange(low, high), label))
            return " " * len(label)
        return label

    def chinese_count_range(match: re.Match[str]) -> str:
        label = match[0]
        if len(label) != 2:
            return label
        return count_range(_chinese_integer(label[0]), _chinese_integer(label[1]), label)

    def english_count_range(match: re.Match[str]) -> str:
        if re.match(r"[ \t]+point\b", text[match.end():], re.IGNORECASE):
            return match[0]
        return count_range(_english_integer(match[1]), _english_integer(match[2]), match[0])

    def english_open_count(match: re.Match[str]) -> str:
        low = _EN_NUMBER_WORDS[match[1].casefold()]
        values.append(NumericValue("open_count", low, match[0]))
        values.append(NumericValue("number", NumberRange(low, low), match[1]))
        return " " * len(match[0])

    text = _ZH_NUMBER.sub(chinese_count_range, text)
    text = _EN_COUNT_RANGE.sub(english_count_range, text)
    text = _EN_OPEN_COUNT.sub(english_open_count, text)
    values.extend(NumericValue("number", NumberRange(low, high), label) for low, high, label in number_mentions(text))
    return text, values


def _adjacent_screen_excerpts(quotes: list[Quote]) -> list[str]:
    """Join cited, consecutive physical screen lines at a single timestamp."""
    positions = {
        (quote.stamp, quote.anchor.start, quote.match.offset): quote.text
        for quote in quotes if quote.screen
    }
    joined, run = [], []
    previous = None
    for (stamp, anchor, line), text in sorted(positions.items()):
        if previous != (stamp, anchor, line - 1):
            if len(run) > 1:
                joined.append(" ".join(run))
            run = []
        run.append(text)
        previous = (stamp, anchor, line)
    if len(run) > 1:
        joined.append(" ".join(run))
    return joined


def _grounding_word(match: re.Match[str]) -> str:
    word = match[0].casefold().replace("’", "'")
    if word.endswith("'s"):
        word = word[:-2]
    elif word.endswith("s'"):
        word = word[:-1]
    short_acronym_plural = len(word) == 3 and match[0][:2].isupper() and match[0][2:3] == "s"
    if (len(word) < 4 and not short_acronym_plural) or word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("ies") and word[-4] not in "aeiou":
        return word[:-3] + "y"
    if word.endswith(("sses", "shes", "ches", "xes", "zzes")):
        return word[:-2]
    return word[:-1] if word.endswith("s") else word


def _grounded_term_occurs(term: str, source: str) -> bool:
    """Accept regular English plurals and possessives in the same evidence."""
    source = _ACCELERATOR_HOUR.sub(r"\1 hours", source) if term.casefold() in {"gpu", "vcpu"} else source
    if term_occurs(term, source) or term_occurs(
        _LATIN_WORD.sub(_grounding_word, term), _LATIN_WORD.sub(_grounding_word, source)
    ):
        return True
    split_term = _COMPOUND_NAME_BOUNDARY.sub(" ", term)
    return " " in split_term and term_occurs(split_term, _COMPOUND_NAME_BOUNDARY.sub(" ", source))


def c04c_grounding(ctx: RuleContext) -> tuple[str, bool, str]:
    issues, unknown_quoted = [], {}
    valid = ctx.valid_quotes
    blocks = [block for section in ctx.sections for block in section.blocks]
    corrections = [corrected for _, corrected in caption_corrections(blocks, ctx.speech)]
    screen_corrections = caption_corrections(blocks, "", tuple(quote.text for quote in valid if quote.screen))

    for parent, section in _with_parents(ctx.sections):
        for claim in [*([section.heading] if section.level == 3 else []), *section.prose]:
            if _fixed_explanation(parent, claim):
                continue
            source_claims = section.prose if claim == section.heading else [claim]
            times = delivery_times(claim).union(*(delivery_times(item) for item in source_claims))
            linked = [quote for stamp in times for quote in match_link(stamp, valid)[0]]
            if times and not linked:
                continue
            evidence = linked if times else valid
            excerpts = [quote.text for quote in evidence]
            screen_excerpts = [quote.text for quote in evidence if quote.screen]
            local_corrections = [corrected for original, corrected in screen_corrections
                                 if any(term_occurs(original, line) for line in screen_excerpts)]
            source = excerpts + corrections + local_corrections
            prose = _INLINE_LIST_ITEM.sub(r"\1 ", prose_without_times(claim))
            if parent == _C04_START[1]:
                prose = _remove_properties(prose, ctx.fields)
            support = [value for quote in evidence for value in canonical_numbers(quote.text, screen=quote.screen)[1]]
            if not ctx.has_screen_file:
                support.extend(value for excerpt in corrections for value in canonical_numbers(excerpt)[1])
            numeric_text = prose
            for quote in evidence:
                if quote.screen and quote.text in numeric_text:
                    # An exact reproduction of the cited OCR text is the same date.
                    numeric_text = numeric_text.replace(quote.text, _OCR_DATE_SEPARATOR.sub(r"\1,", quote.text))
            numeric_prose, numeric_claims = canonical_numbers(numeric_text)
            missing_numbers = {
                claim.label for claim in numeric_claims
                if not any(value.supports(claim) for value in support)
            }
            missing_names = {
                name for name in proper_names(numeric_prose)
                if not any(_grounded_term_occurs(name, excerpt) for excerpt in source)
            }
            if missing_names:
                # A complete, contiguous split spelling can back its name
                # tokens. A token alone still cannot match inside a compound.
                for excerpt in source:
                    for compound in _LATIN_WORD.findall(excerpt):
                        expanded = _COMPOUND_NAME_BOUNDARY.sub(" ", compound)
                        if expanded != compound and term_occurs(expanded, numeric_prose):
                            missing_names.difference_update(expanded.split())
            supported_originals = set()
            original_excerpts = [*excerpts, *local_corrections, *_adjacent_screen_excerpts(evidence)]
            for match in _PARENTHESIZED_ORIGINAL.finditer(prose):
                original = (match[1] or match[2]).strip()
                if not re.search(r"[A-Za-z]", original) or _CJK_RUN.search(original):
                    continue
                if any(_grounded_term_occurs(original, excerpt) for excerpt in original_excerpts):
                    supported_originals.add(match.start())
                else:
                    issues.append(f"{section.heading}: original {original!r} is absent from the end evidence")
            for match in _QUOTED_TERM.finditer(prose):
                if match.end() in supported_originals:
                    continue
                term = (match[1] or match[2]).strip()
                if term and not term.startswith("[") and term.casefold() not in _PROPER_SKIP:
                    if not any(_grounded_term_occurs(term, excerpt) for excerpt in source):
                        unknown_quoted.setdefault(term.casefold(), term)
            issues.extend(f"{section.heading}: number {label!r} is absent from the end evidence"
                          for label in sorted(missing_numbers))
            issues.extend(f"{section.heading}: name {name!r} is absent from the end evidence"
                          for name in sorted(missing_names))
    if len(unknown_quoted) > 2:
        issues.append(f"quoted names are absent from the end evidence: {', '.join(list(unknown_quoted.values())[:6])}")
    return _result("C04c", issues, "numbers and names have end evidence")


_NOTE_CHECKING_PROCESS = re.compile(
    r"(?:后半句|前半句|原句|这句话|这段文字)[^。！？\n]{0,20}(?:没(?:有|能)?|未(?:能)?)[^。！？\n]{0,6}识别"
    r"|(?:这里|本文)[^。！？\n]{0,12}(?:不补写|不补全|不当作成绩|只按口头说法记录)"
    r"|(?:部分|这部分|这些文字|画面文字|字幕)[^。！？\n]{0,8}识别[^。！？\n]{0,8}(?:不确定|不完整|不清楚)"
    r"|(?:口播|名字|姓名|术语|词语)[^。！？\n]{0,20}(?:自动字幕|字幕)[^。！？\n]{0,8}(?:写错|听错|识别错|误写)"
)


def c04d_explanations(ctx: RuleContext) -> tuple[str, bool, str]:
    blocks = [block for section in ctx.sections for block in section.blocks]
    cited_screen = tuple(quote.text for quote in ctx.valid_quotes if quote.screen)
    corrections = caption_corrections(blocks, ctx.speech, cited_screen)
    corrected_spellings = [corrected for _, corrected in corrections]
    issues = explanation_issues(blocks, ctx.speech, [*corrected_spellings, *cited_screen], cited_screen)
    searchable = [
        (section.heading, _INLINE_CODE.sub(" ", _FENCED_CODE.sub(" ", "\n\n".join([section.heading, *section.prose]))))
        for section in ctx.sections
    ]
    for section in ctx.sections:
        for prose in [section.heading, *section.prose]:
            checking = _NOTE_CHECKING_PROCESS.search(prose)
            if checking:
                issues.append(f"{section.heading or '正文'}: remove note-checking commentary from prose: {checking[0]}")
    for original, corrected in dict.fromkeys(corrections):
        if original == corrected:
            continue
        # For a capitalization correction, check the recorded spelling itself.
        # Lowercase identifiers such as a repository slug can be valid.
        case_only = original.casefold() == corrected.casefold()
        original_pattern = re.compile(_term_pattern(original)) if case_only else None
        corrected_pattern = re.compile(_term_pattern(corrected))
        for heading, prose in searchable:
            wrong = (original_pattern.search(prose) if original_pattern is not None
                     else term_occurs(original, corrected_pattern.sub(" ", prose)))
            if wrong:
                issues.append(f"{heading or '正文'}: incorrect caption spelling {original!r} must stay in 字幕更正")
    return _result("C04d", issues, "explanations use marked blocks")


def r13_today_step(ctx: RuleContext) -> tuple[str, bool, str]:
    section = next((section for section in ctx.sections if section.heading == ACTION_HEADING), None)
    if section is None:
        return ("R13", False, f"missing {ACTION_HEADING}")
    prose = "\n".join(section.prose)
    evidence = linked_quotes(prose, ctx.valid_quotes)
    if not evidence:
        return ("R13", False, f"{ACTION_HEADING} needs a supporting ⏱ link")
    clean = re.sub(r"[（(]改写讲者做法[）)]", "", prose_without_times(prose))
    def mask_url(match: re.Match[str]) -> str:
        url = match[0].rstrip(".!?;")
        return " " * len(url) + match[0][len(url):]

    separators = list(_SENTENCE_SPLIT.finditer(_URL.sub(mask_url, clean)))
    starts = [0, *(match.end() for match in separators)]
    ends = [*(match.start() for match in separators), len(clean)]
    sentences = [sentence for start, end in zip(starts, ends) if (sentence := clean[start:end].strip())]
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
