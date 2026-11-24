#!/usr/bin/env python3
"""Render a reading copy after checking the current evidence note and its inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import knowledge_note
import user_prefs
import verify_note
import verify_rules as rules


DISCREPANCY_TITLE = "原文出入"
SPOKEN_CODE_NOTICE = "部分代码按讲者口述整理"
GLOSSARY_HEADING = "## 术语速查"
GLOSSARY_NOTICE = "以下为整理者补充，非讲者原话。"
EMPTY_OMISSION = {"", "无", "无。", "无.", "none"}

FRONTMATTER = re.compile(r"\A---(?:\r\n|\r|\n).*?(?:\r\n|\r|\n)---(?:\r\n|\r|\n)", re.DOTALL)
TIME_GROUP = re.compile(
    rf"(?P<before>[ \t]*){rules._DELIVERY_TIME.pattern}"
    rf"(?:[ \t]*{rules._DELIVERY_TIME.pattern})*(?P<after>[ \t]*)"
)
CALLOUT_START = re.compile(r"^>\s*\[!")
AI_CREDIT = rules._AI_CREDIT
EMPTY_SECTION = re.compile(
    r"(?:不适用(?:（文稿中未出现意见分歧）|\(文稿中未出现意见分歧\))"
    r"|本节没有补充中间部分之外的情况)[。.]?"
)
OMISSION = re.compile(r"^本文略去[｜|]([^\n]*)(?=[ \t\n]*\Z)", re.MULTILINE)
ANY_OMISSION_LINE = re.compile(r"^本文略去[｜|]", re.MULTILINE)
DOUBT_NOTE_RE = re.compile(r"（存疑：[^）\n]+）")
DISCREPANCY_TYPE1 = re.compile(r"^(?:字幕|画面)写作\s*[:：]?\s*.+?[，,]\s*实为\s*[:：]?\s*\S.*$")
DISCREPANCY_TYPE2 = re.compile(r"^口述代码[｜|]\s*\S.*$")
DISCREPANCY_TYPE3 = re.compile(r"^存疑[｜|]\s*「([^」\n]+)」\s*[｜|]\s*([^\n]+)$")
FENCE_RE = rules._FENCE_OPEN
INLINE_CODE_RE = re.compile(r"(`+)([^`\n]+?)\1")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]\n]+\]\([^)\n]+\)")
PAREN_SPAN_RE = re.compile(r"（[^）\n]*）|\([^)\n]*\)")
TABLE_SEP_RE = re.compile(r"^[ \t]*\|?[\s:-]+\|[\s|:-]*$")
JOB_FILES = (
    "note.md", "transcript.txt", "selection.md", "status.json", "segments.json", ".status.lock", "delivery.md",
    rules.SCREEN_FILE, "review.md", "issues.md",
)
ARCHIVED_NOTE = re.compile(r"(?:note|delivery|review|issues)\.prev(?:\.[0-9]+)?\.md", re.IGNORECASE)


class RenderError(ValueError):
    """A job cannot be rendered or published."""


def remove_times(line: str) -> str:
    def replace(match: re.Match[str]) -> str:
        before, after = match["before"], match["after"]
        if match.end() == len(line):
            return ""
        if match.start() == 0:
            return before
        return (before or after) if after else ""

    return TIME_GROUP.sub(replace, line)


def _absorb_hidden_block(rendered: list[str], lines: list[str], index: int) -> int:
    if rendered and index < len(lines) - 1:
        if rendered[-1].strip() and lines[index].strip():
            rendered.append("")
        elif not rendered[-1].strip() and not lines[index].strip():
            index += 1
    return index


def _is_table_block(block_lines: list[str]) -> bool:
    if any(line.lstrip().startswith("|") for line in block_lines):
        return True
    return len(block_lines) >= 2 and any(TABLE_SEP_RE.fullmatch(line) for line in block_lines)


def _scan_balanced(
    text: str,
    start: int,
    open_ch: str,
    close_ch: str,
    skip_spans: list[tuple[int, int]] = (),
) -> int | None:
    depth = 0
    pos = start
    length = len(text)
    while pos < length:
        if pos > start:
            jumped = False
            for span_start, span_end in skip_spans:
                if span_start <= pos < span_end:
                    pos = span_end
                    jumped = True
                    break
            if jumped:
                continue
        ch = text[pos]
        if ch == "\n":
            return None
        if ch == "\\":
            pos += 2
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    return None


def _protected_spans(text: str, *, include_parens: bool = False) -> list[tuple[int, int]]:
    code_spans: list[tuple[int, int]] = [(m.start(), m.end()) for m in INLINE_CODE_RE.finditer(text)]
    spans: list[tuple[int, int]] = list(code_spans)
    # Balanced Markdown links: [label](dest with balanced (parens))
    length = len(text)
    pos = 0
    while pos < length:
        jumped = False
        for span_start, span_end in code_spans:
            if span_start <= pos < span_end:
                pos = span_end
                jumped = True
                break
        if jumped:
            continue
        if text[pos] == "[":
            label_end = _scan_balanced(text, pos, "[", "]", code_spans)
            if label_end is not None and label_end < length and text[label_end] == "(":
                dest_end = _scan_balanced(text, label_end, "(", ")")
                if dest_end is not None:
                    spans.append((pos, dest_end))
                    pos = dest_end
                    continue
        if include_parens and text[pos] in "（(":
            close_ch = "）" if text[pos] == "（" else ")"
            paren_end = _scan_balanced(text, pos, text[pos], close_ch, code_spans)
            if paren_end is not None:
                spans.append((pos, paren_end))
                pos = paren_end
                continue
        pos += 1
    spans.sort()
    return spans


def _overlaps_forbidden_span(text: str, start: int, end: int) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in _protected_spans(text))


def _sentence_insertion_index(text: str, anchor_end: int) -> int:
    protected = _protected_spans(text, include_parens=True)
    pos = anchor_end
    length = len(text)
    while pos < length:
        jumped = False
        for span_start, span_end in protected:
            if span_start <= pos < span_end:
                pos = span_end
                jumped = True
                break
        if jumped:
            continue
        ch = text[pos]
        if ch == "\n":
            return pos
        if ch in "。！？!?":
            return pos
        if ch == ".":
            next_ch = text[pos + 1] if pos + 1 < length else ""
            if not next_ch or next_ch.isspace() or next_ch in "\"'”’）)]":
                return pos
        pos += 1
    return length


def _resolve_doubt_insertion(block_text: str, anchor: str, explanation: str) -> tuple[int, str]:
    if not anchor or not explanation or "\n" in explanation or "）" in explanation:
        raise RenderError(f"invalid 存疑 entry: anchor={anchor!r}, explanation={explanation!r}")
    count = block_text.count(anchor)
    if count != 1:
        raise RenderError(f"存疑 anchor {anchor!r} must occur exactly once in preceding block (found {count})")
    start = block_text.index(anchor)
    end = start + len(anchor)
    if _overlaps_forbidden_span(block_text, start, end):
        raise RenderError(f"存疑 anchor {anchor!r} must not fall inside code or link")
    return _sentence_insertion_index(block_text, end), f"（存疑：{explanation}）"


def _insert_doubt_note(block_text: str, anchor: str, explanation: str) -> str:
    insert_at, annotation = _resolve_doubt_insertion(block_text, anchor, explanation)
    return f"{block_text[:insert_at]}{annotation}{block_text[insert_at:]}"


def _apply_doubt_notes(block_text: str, doubts: list[tuple[str, str]]) -> tuple[str, list[tuple[int, int]]]:
    """Resolve all anchors against original block_text, then apply stably and return generated spans."""
    if len(doubts) == 1:
        anchor, explanation = doubts[0]
        insert_at, annotation = _resolve_doubt_insertion(block_text, anchor, explanation)
        updated = _insert_doubt_note(block_text, anchor, explanation)
        return updated, [(insert_at, insert_at + len(annotation))]

    resolved: list[tuple[int, int, str]] = []
    for order, (anchor, explanation) in enumerate(doubts):
        insert_at, annotation = _resolve_doubt_insertion(block_text, anchor, explanation)
        resolved.append((insert_at, order, annotation))

    # Build left-to-right so we know exact final (start, end) spans in updated block_text.
    resolved.sort(key=lambda item: (item[0], item[1]))
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    cursor = 0
    out_len = 0
    for insert_at, _, annotation in resolved:
        chunk = block_text[cursor:insert_at]
        parts.append(chunk)
        out_len += len(chunk)
        span_start = out_len
        parts.append(annotation)
        out_len += len(annotation)
        spans.append((span_start, out_len))
        cursor = insert_at
    parts.append(block_text[cursor:])
    return "".join(parts), spans


def _parse_discrepancy_lines(content: list[str]) -> tuple[bool, list[tuple[str, str]]]:
    if not content:
        raise RenderError("empty 原文出入 block")
    has_spoken_code = False
    doubts: list[tuple[str, str]] = []
    for line in content:
        if DISCREPANCY_TYPE1.fullmatch(line):
            continue
        if DISCREPANCY_TYPE2.fullmatch(line):
            has_spoken_code = True
            continue
        match = DISCREPANCY_TYPE3.fullmatch(line)
        if match:
            anchor = match[1].strip()
            explanation = match[2].strip()
            if not anchor or not explanation or "）" in explanation:
                raise RenderError(f"invalid 存疑 line in 原文出入: {line}")
            doubts.append((anchor, explanation))
            continue
        raise RenderError(f"unknown line in 原文出入: {line}")
    return has_spoken_code, doubts


def _with_note_suffix(label: str) -> str:
    return label if label.endswith("（注）") else f"{label}（注）"


def render_lines(
    body: str,
    *,
    inline_terms: bool = False,
    terms: list[tuple[str, str]] | None = None,
    seen_terms: set[str] | None = None,
    strip_discrepancy: bool = False,
) -> tuple[str, set[int], bool, int]:
    lines = body.split("\n")
    rendered: list[str] = []
    times: set[int] = set()
    has_spoken_code = False
    doubt_count = 0

    in_fence_char: str | None = None
    in_fence_len = 0
    block_open = False
    last_block_start: int | None = None
    last_block_end: int | None = None
    last_block_raw: list[str] = []
    last_block_original: str = ""
    last_block_doubts: list[tuple[str, str]] = []
    last_block_kind: str | None = None  # "prose" or "forbidden"

    index = 0
    while index < len(lines):
        raw = lines[index]
        index += 1

        if in_fence_char is not None:
            rendered.append(raw)
            if rules.is_fence_close(raw, in_fence_char, in_fence_len):
                in_fence_char = None
                in_fence_len = 0
                block_open = False
            last_block_kind = "forbidden"
            continue

        opened = rules.match_fence_open(raw)
        if opened is not None:
            in_fence_char, in_fence_len, _ = opened
            rendered.append(raw)
            block_open = False
            last_block_kind = "forbidden"
            continue

        if not CALLOUT_START.match(raw.strip()):
            times.update(rules.delivery_times(raw))
            cleaned = remove_times(raw)
            if not raw.strip():
                block_open = False
                rendered.append(cleaned)
                continue
            if cleaned:
                starts_list_item = bool(rules._LIST_ITEM.match(raw.strip()))
                if not block_open or starts_list_item:
                    block_open = True
                    last_block_start = len(rendered)
                    last_block_raw = [raw]
                    last_block_doubts = []
                else:
                    last_block_raw.append(raw)
                rendered.append(cleaned)
                last_block_end = len(rendered)
                block_slice = rendered[last_block_start:last_block_end]
                last_block_original = "\n".join(block_slice)
                last_block_kind = "forbidden" if _is_table_block(block_slice) else "prose"
            continue

        block_open = False
        header = rules._CALLOUT.fullmatch(raw.strip())
        if header is None:
            raise RenderError(f"unknown explanation block: {raw.strip()}")
        kind, title = header.groups()
        raw_content: list[str] = []
        content: list[str] = []
        while index < len(lines):
            quoted = lines[index].strip()
            if not quoted.startswith(">") or CALLOUT_START.match(quoted):
                break
            raw_line = remove_times(quoted[1:]).strip()
            if raw_line:
                raw_content.append(raw_line)
            cleaned = AI_CREDIT.sub("", raw_line).strip()
            if cleaned:
                content.append(cleaned)
            index += 1

        if kind == "warning" and title == "字幕更正":
            index = _absorb_hidden_block(rendered, lines, index)
            continue

        if kind == "warning" and title == DISCREPANCY_TITLE:
            if not strip_discrepancy:
                spoken, doubts = _parse_discrepancy_lines(raw_content)
                has_spoken_code = has_spoken_code or spoken
                if doubts:
                    if last_block_kind != "prose" or last_block_start is None or last_block_end is None:
                        raise RenderError(
                            "存疑 entry must follow a non-callout paragraph or list item。"
                            "请将含存疑的 原文出入 放在说明段落与代码块之间"
                        )
                    raw_block_text = "\n".join(last_block_raw)
                    for anchor, _ in doubts:
                        if raw_block_text.count(anchor) != 1:
                            raise RenderError(
                                f"存疑 anchor {anchor!r} must occur exactly once verbatim without crossing ⏱"
                            )
                    last_block_doubts.extend(doubts)
                    updated_block, generated_spans = _apply_doubt_notes(last_block_original, last_block_doubts)
                    # Local invariant check: removing exact generated spans must restore original block verbatim.
                    reconstructed: list[str] = []
                    pos = 0
                    for s_start, s_end in generated_spans:
                        reconstructed.append(updated_block[pos:s_start])
                        pos = s_end
                    reconstructed.append(updated_block[pos:])
                    if "".join(reconstructed) != last_block_original:
                        raise RenderError("invariant #7 failed: generated doubt spans did not restore original block")
                    rendered[last_block_start:last_block_end] = updated_block.split("\n")
                    doubt_count += len(doubts)
            index = _absorb_hidden_block(rendered, lines, index)
            continue

        term = rules._TERM_TITLE.fullmatch(title)
        if kind == "note" and term:
            label = AI_CREDIT.sub("", remove_times(term[1])).strip()
            body_text = " ".join(content)
            if not inline_terms:
                if terms is not None and seen_terms is not None:
                    norm = " ".join(label.split()).casefold()
                    if norm not in seen_terms:
                        seen_terms.add(norm)
                        terms.append((label, body_text))
                index = _absorb_hidden_block(rendered, lines, index)
                continue
            display_label = _with_note_suffix(label)
        elif kind == "tip" and title in {"类比（Claude 补充）", "类比"}:
            display_label = "打个比方（注）"
            body_text = " ".join(content)
        else:
            raise RenderError(f"unknown explanation block: {raw.strip()}")

        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.append(f"> **{display_label}**：{body_text}")
        if index < len(lines) and lines[index].strip():
            rendered.append("")

    if in_fence_char is not None:
        raise RenderError("unclosed fenced code block")
    return "\n".join(rendered), times, has_spoken_code, doubt_count


@dataclass
class Section:
    level: int
    title: str
    body: str
    times: set[int]


def _render_body_details(
    body: str,
    *,
    inline_terms: bool = False,
    strip_discrepancy: bool = False,
) -> tuple[str, bool, int]:
    headings = rules.markdown_headings(body)
    ends = [start for _, _, start, _ in headings[1:]] + [len(body)]
    sections: list[Section] = []
    terms: list[tuple[str, str]] = []
    seen_terms: set[str] = set()
    has_spoken_code = False
    doubt_count = 0

    for (level, title, _, heading_end), end in zip(headings, ends):
        content, times, spoken, doubts = render_lines(
            body[heading_end:end],
            inline_terms=inline_terms,
            terms=terms,
            seen_terms=seen_terms,
            strip_discrepancy=strip_discrepancy,
        )
        has_spoken_code = has_spoken_code or spoken
        doubt_count += doubts
        sections.append(Section(level, title, content, times | rules.delivery_times(title)))

    kept: list[Section] = []
    for index, section in enumerate(sections):
        has_child = index + 1 < len(sections) and sections[index + 1].level > section.level
        if has_child or not EMPTY_SECTION.fullmatch(section.body.strip()):
            kept.append(section)

    parts: list[str] = []
    for index, section in enumerate(kept):
        title = remove_times(section.title)
        if section.level == 3:
            times = section.times.copy()
            for child in kept[index + 1:]:
                if child.level <= section.level:
                    break
                times.update(child.times)
            if times:
                start, end = min(times), max(times)
                time_label = rules._fmt(start)
                if end > start:
                    time_label += f"–{rules._fmt(end)}"
                title += f" · {time_label}"
        content = section.body
        if content == "\n" or (content.startswith("\n") and content.split("\n", 2)[1].strip()):
            content = "\n" + content
        parts.extend((f"{'#' * section.level} {title}", content))

    rendered = "".join(parts).strip("\n")
    if not inline_terms and terms:
        glossary_lines = [GLOSSARY_HEADING, "", GLOSSARY_NOTICE, ""]
        glossary_lines.extend(f"- **{label}**：{definition}" for label, definition in terms)
        glossary = "\n".join(glossary_lines)
        rendered = f"{rendered}\n\n{glossary}" if rendered else glossary
    return rendered, has_spoken_code, doubt_count


def render_body(body: str, *, inline_terms: bool = False) -> str:
    rendered, _, _ = _render_body_details(body, inline_terms=inline_terms)
    return rendered


def _outside_fences(text: str) -> str:
    kept: list[str] = []
    in_fence_char: str | None = None
    in_fence_len = 0
    for raw in text.splitlines():
        if in_fence_char is not None:
            if rules.is_fence_close(raw, in_fence_char, in_fence_len):
                in_fence_char = None
                in_fence_len = 0
            continue
        opened = rules.match_fence_open(raw)
        if opened is not None:
            in_fence_char, in_fence_len, _ = opened
            continue
        kept.append(raw)
    return "\n".join(kept)


def render_note(
    note: bytes,
    *,
    keep_frontmatter: bool,
    self_review: bool = False,
    reading_level: str | None = None,
    delivery_language: str | None = None,
    inline_terms: bool = False,
) -> bytes:
    if reading_level is not None and reading_level not in knowledge_note.READING_LEVELS:
        raise RenderError(f"invalid reading_level: {reading_level!r}")
    _ = delivery_language  # Compatibility no-op; Phase 6 omits reading-level headers.
    text = note.decode("utf-8-sig")
    frontmatter = FRONTMATTER.match(text)
    if frontmatter is None:
        raise RenderError("note.md is missing its opening YAML block")
    fields = knowledge_note.parse_frontmatter(normalize_newlines(frontmatter[0]))
    if fields is None:
        raise RenderError("could not read note.md properties")

    body = normalize_newlines(text[frontmatter.end():])
    evidence = next(((start, end) for level, title, start, end in rules.markdown_headings(body)
                     if level == 2 and title == rules.EVIDENCE_HEADING), None)
    if evidence is None:
        raise RenderError("note.md is missing the 原文依据 section")
    evidence_start, _ = evidence
    body = body[:evidence_start]
    omission = OMISSION.search(body)
    if omission is not None:
        in_f_ch: str | None = None
        in_f_len = 0
        for ln in body[:omission.start()].splitlines():
            if in_f_ch is not None:
                if rules.is_fence_close(ln, in_f_ch, in_f_len):
                    in_f_ch = None
                    in_f_len = 0
            else:
                opened = rules.match_fence_open(ln)
                if opened is not None:
                    in_f_ch, in_f_len, _ = opened
        if in_f_ch is not None:
            omission = None
    if omission is None:
        if ANY_OMISSION_LINE.search(_outside_fences(body)):
            raise RenderError("本文略去 must appear at the end before 原文依据")
        prose_body = body
        omission_text = ""
    else:
        prose_body = body[:omission.start()]
        omission_text = omission[1].strip()
        if ANY_OMISSION_LINE.search(_outside_fences(prose_body)):
            raise RenderError("本文略去 must appear at the end before 原文依据")

    rendered_body, has_spoken_code, doubt_count = _render_body_details(
        prose_body, inline_terms=inline_terms, strip_discrepancy=False
    )
    baseline_body, _, _ = _render_body_details(
        prose_body, inline_terms=inline_terms, strip_discrepancy=True
    )
    stripped_rendered, n_rendered = DOUBT_NOTE_RE.subn("", rendered_body)
    stripped_base, n_base = DOUBT_NOTE_RE.subn("", baseline_body)
    if (n_rendered - n_base) != doubt_count or stripped_rendered != stripped_base:
        raise RenderError("invariant #7 failed: stripping doubt notes did not match baseline body")

    notice_parts = [
        part for part in (
            "未经独立复核" if self_review else None,
            SPOKEN_CODE_NOTICE if has_spoken_code else None,
        )
        if part is not None
    ]
    blocks: list[str] = [
        f"# {fields['title']}",
        f"{fields['channel'] or '—'} · {fields['published'] or '—'} · [原视频]({fields['source']})",
    ]
    if notice_parts:
        blocks.append("说明：" + "；".join(notice_parts) + "。")
    blocks.append(rendered_body)
    if omission_text.casefold() not in EMPTY_OMISSION:
        blocks.extend(("---", f"没写进来的部分：{omission_text}"))
    markdown = "\n\n".join(blocks) + "\n"
    if "⏱" in markdown or "[!" in _outside_fences(markdown):
        raise RenderError("reading copy still contains an evidence time marker or callout")
    if keep_frontmatter:
        original = frontmatter[0]
        separator = "\r\n" if original.endswith("\r\n") else original[-1]
        markdown = original + separator + markdown
    return markdown.encode("utf-8")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def check_destination(job: Path, output: Path) -> None:
    resolved = output.resolve()
    placeholder = r"^(?:—(?:\s+.+?)?|[0-9]{4}-[0-9]{2}-[0-9]{2}\s+—)\s+-\s+"
    if any(re.match(placeholder, name) for name in (output.name, resolved.name)):
        raise RenderError("--output contains a metadata placeholder; omit missing fields or use the title or video ID")
    if any(path.is_relative_to(job / rules.SCREEN_FRAMES) for path in (output, resolved)):
        raise RenderError(f"--output would use the screenshot directory: {output}")
    if any(path.parent == job and ARCHIVED_NOTE.fullmatch(path.name) for path in (output, resolved)):
        raise RenderError(f"--output would use a job archive path: {output}")
    for name in JOB_FILES:
        protected = job / name
        if (output == protected or resolved == protected.resolve()
                or (output.exists() and protected.exists() and output.samefile(protected))):
            raise RenderError(f"--output would overwrite {name}: {output}")


def check_finished(job: Path, inputs: dict, verifier: dict, review: bytes | None = None) -> None:
    if verify_note.job_inputs(job) != inputs:
        raise RenderError("job files changed during rendering; rerun both checks")
    status = verify_note.read_job_status(job)
    coverage = status.get("coverage")
    if (status.get("finished") is not True or status.get("verifier") != verifier
            or not isinstance(coverage, dict)
            or coverage.get("allowed") is not True or coverage.get("inputs") != inputs):
        raise RenderError("verify and coverage must finish on the current job files")
    if review is not None:
        if (job / "review.md").read_bytes() != review:
            raise RenderError("review.md changed during rendering")
        if status.get("review", {}).get("final_inputs") != inputs:
            raise RenderError("review processing must finish on the current job files")


def reading_path(directory: Path, job: Path, note: bytes) -> Path:
    fields = knowledge_note.parse_frontmatter(normalize_newlines(note.decode("utf-8-sig"))) or {}

    def component(value: str) -> str:
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
        return " ".join(value.split()).strip(" .-—")

    prefix = " ".join(filter(None, (component(fields.get("published", "")), component(fields.get("channel", "")))))
    title = component(fields.get("title", "")) or component(job.name) or "reading"
    stem = (f"{prefix} - {title}" if prefix else title).encode("utf-8")[:200].decode("utf-8", "ignore").rstrip(" .-")
    if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", stem, re.IGNORECASE):
        stem = "_" + stem
    return directory.resolve() / (stem + ".md")


def owns_generated_output(output: Path, source: str) -> bool:
    try:
        if not stat.S_ISREG(output.lstat().st_mode):
            return False
        raw = output.read_bytes().decode("utf-8")
    except (UnicodeDecodeError, OSError):
        return False

    lines = [line[:-1] if line.endswith("\r") else line for line in raw.split("\n")]
    if raw.startswith(("---\n", "---\r\n")):
        try:
            closing = lines.index("---", 1)
        except ValueError:
            return False
        lines = lines[closing + 1:]

    header = [line for line in lines if line.strip(" \t")][:2]
    return len(header) == 2 and header[0].startswith("# ") and f"[原视频]({source})" in header[1]


def render_job(
    job: Path,
    output: Path | None,
    *,
    keep_frontmatter: bool,
    require_review: bool = False,
    output_dir: Path | None = None,
    delivery_language: str | None = None,
    inline_terms: bool = False,
) -> Path:
    job = job.resolve(strict=True)
    if not job.is_dir():
        raise RenderError(f"--task-dir is not a directory: {job}")
    if output is not None:
        output = output.parent.resolve() / output.name
        check_destination(job, output)
    elif output_dir is None:
        raise RenderError("pass an output file or directory")

    with verify_note.job_lock(job):
        status = verify_note.read_job_status(job)
        if status.get("status") == verify_note.SCREEN_PENDING:
            raise RenderError(verify_note.SCREEN_PENDING_MESSAGE)
        if verify_note.repair_lock(status, review=True):
            stopped = verify_note.stopped_result(job, status)
            raise RenderError(" · ".join([*stopped["reasons"], *(stopped[key] for key in ("draft", "issues") if key in stopped)]))
        reading_level = knowledge_note.read_reading_level(status)
        verify_note.prepare_job_note(job)
        note_path = job / "note.md"
        try:
            receipt = verify_note.prepare_review_submission(job, required=require_review)
            if receipt is None and note_path.is_file():
                verify_note.check_closing_heading_pair(note_path.read_bytes(), reading_level)
        except ValueError as exc:
            raise RenderError(str(exc)) from exc
        review, reviewed_inputs = receipt if receipt is not None else (None, None)
        result = verify_note.check_job_submission(job, with_coverage=True, reviewed_inputs=reviewed_inputs,
                                                  review_content=review)
        coverage = result.get("coverage", {})
        for line in result["reasons"] + result.get("warnings", []) + coverage.get("not_checked", []):
            print(line, file=sys.stderr)
        if not result["allowed"]:
            for key in ("draft", "issues"):
                if key in result:
                    print(f"{key}: {result[key]}", file=sys.stderr)
            raise RenderError("verify or coverage failed")
        if result.get("c04c") and review is None:
            raise RenderError("C04c warnings require a bound review before reading delivery")
        inputs = verify_note.job_inputs(job)
        status = verify_note.read_job_status(job)
        verifier = status.get("verifier")
        if not isinstance(verifier, dict) or verifier.get("allowed") is not True or verifier.get("inputs") != inputs:
            raise RenderError("job files changed during verification; rerun both checks")
        check_finished(job, inputs, verifier, review)
        note = note_path.read_bytes()
        if hashlib.sha256(note).hexdigest() != inputs["note_file"]:
            raise RenderError("note.md changed during rendering; rerun both checks")
        self_review = review is not None and status.get("review", {}).get("reviewer") == "self"
        try:
            reading_level = knowledge_note.read_reading_level(status)
            verify_note.check_closing_heading_pair(note, reading_level)
        except ValueError as exc:
            raise RenderError(str(exc)) from exc
        markdown = render_note(
            note,
            keep_frontmatter=keep_frontmatter,
            self_review=self_review,
            reading_level=reading_level,
            delivery_language=delivery_language,
            inline_terms=inline_terms,
        )
        if output is None:
            output = reading_path(output_dir, job, note)
            check_destination(job, output)
            if output.exists() or output.is_symlink():
                source = (knowledge_note.parse_frontmatter(normalize_newlines(note.decode("utf-8-sig"))) or {})["source"]
                if not owns_generated_output(output, source):
                    raise RenderError(f"cannot verify ownership of generated output: {output}. "
                                      "Pass --output <路径> to save elsewhere.")

        output.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        status_temp = None
        rollback_temp = None
        status_path = job / "status.json"
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as staged:
                temp = Path(staged.name)
                staged.write(markdown)
            check_destination(job, output)
            check_finished(job, inputs, verifier, review)
            original_status = status_path.read_bytes()
            delivered = verify_note.read_job_status(job)
            delivered["next_step"] = "deliver"
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=job, delete=False) as staged_status:
                status_temp = Path(staged_status.name)
                staged_status.write(json.dumps(delivered, ensure_ascii=False, indent=2) + "\n")
            with tempfile.NamedTemporaryFile(dir=job, delete=False) as staged_rollback:
                rollback_temp = Path(staged_rollback.name)
                staged_rollback.write(original_status)
            status_temp.replace(status_path)
            status_temp = None
            try:
                temp.replace(output)
                temp = None
            except BaseException:
                rollback_temp.replace(status_path)
                rollback_temp = None
                raise
        finally:
            for path in (temp, status_temp, rollback_temp):
                if path is not None:
                    path.unlink(missing_ok=True)
        return output


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True, help="Job directory containing the evidence note")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path, help="Full path for the reading Markdown file")
    destination.add_argument("--output-dir", type=Path, help="Folder for a filename generated from the note properties")
    parser.add_argument("--keep-frontmatter", action="store_true", help="Keep the evidence note's opening YAML block")
    parser.add_argument("--language", choices=user_prefs.VALID_LANGUAGES, default=None,
                        help="Delivery language (kept for CLI compatibility)")
    parser.add_argument("--require-review", action="store_true",
                        help="Require a bound review receipt (self-review allowed, marked 未经独立复核)")
    parser.add_argument("--inline-terms", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        path = render_job(
            args.task_dir,
            args.output,
            keep_frontmatter=args.keep_frontmatter,
            require_review=args.require_review,
            output_dir=args.output_dir,
            delivery_language=args.language,
            inline_terms=args.inline_terms,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Reading note not written: {exc}", file=sys.stderr)
        return 1
    if args.output_dir is not None:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
