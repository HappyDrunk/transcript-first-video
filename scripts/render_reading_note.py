#!/usr/bin/env python3
"""Render a reading copy after checking the current evidence note and its inputs."""

from __future__ import annotations

import argparse
import hashlib
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


INTRO = "竖线行是 AI 补充解释"
SCREEN_HINT = "标明来自画面的内容由机器识别，可能有误差"
LEVEL_DESCRIPTIONS = {
    "zh": {
        "plain": "讲解方式：通俗版——术语和背景都做了解释。",
        "concise": "讲解方式：精炼版——默认读者有相关背景，只解释少见的词。",
    },
    "en": {
        "plain": "Reading level: Plain — terms and background are explained.",
        "concise": "Reading level: Concise — assumes relevant background; only uncommon terms are explained.",
    },
}
OUTRO = "每句话对应的视频原话和时间点，保存在这条视频的证据版里。"
FRONTMATTER = re.compile(r"\A---(?:\r\n|\r|\n).*?(?:\r\n|\r|\n)---(?:\r\n|\r|\n)", re.DOTALL)
TIME_GROUP = re.compile(
    rf"(?P<before>[ \t]*){rules._DELIVERY_TIME.pattern}"
    rf"(?:[ \t]*{rules._DELIVERY_TIME.pattern})*(?P<after>[ \t]*)"
)
CALLOUT_START = re.compile(r"^>\s*\[!")
AI_CREDIT = re.compile(r"[（(]Claude[ \t]+补充(?:[，,][ \t]*非视频内容)?[）)]")
EMPTY_SECTION = re.compile(
    r"(?:不适用(?:（文稿中未出现意见分歧）|\(文稿中未出现意见分歧\))"
    r"|本节没有补充中间部分之外的情况)[。.]?"
)
OMISSION = re.compile(r"^本文略去[｜|]([^\n]*)(?=[ \t\n]*\Z)", re.MULTILINE)
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


def render_lines(body: str) -> tuple[str, set[int]]:
    lines = body.split("\n")
    rendered: list[str] = []
    times: set[int] = set()
    index = 0
    while index < len(lines):
        raw = lines[index]
        index += 1
        if not CALLOUT_START.match(raw.strip()):
            times.update(rules.delivery_times(raw))
            cleaned = remove_times(raw)
            if cleaned or not raw:
                rendered.append(cleaned)
            continue

        header = rules._CALLOUT.fullmatch(raw.strip())
        if header is None:
            raise RenderError(f"unknown explanation block: {raw.strip()}")
        kind, title = header.groups()
        content = []
        while index < len(lines):
            quoted = lines[index].strip()
            if not quoted.startswith(">") or CALLOUT_START.match(quoted):
                break
            cleaned = AI_CREDIT.sub("", remove_times(quoted[1:])).strip()
            if cleaned:
                content.append(cleaned)
            index += 1

        if kind == "warning" and title == "字幕更正":
            if rendered and index < len(lines) - 1:
                if rendered[-1].strip() and lines[index].strip():
                    rendered.append("")
                elif not rendered[-1].strip() and not lines[index].strip():
                    index += 1
            continue
        term = rules._TERM_TITLE.fullmatch(title)
        if kind == "note" and term:
            label = AI_CREDIT.sub("", remove_times(term[1])).strip()
        elif kind == "tip" and title in {"类比（Claude 补充）", "类比"}:
            label = "打个比方"
        else:
            raise RenderError(f"unknown explanation block: {raw.strip()}")
        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.append(f"> **{label}**：{' '.join(content)}")
        if index < len(lines) and lines[index].strip():
            rendered.append("")

    return "\n".join(rendered), times


@dataclass
class Section:
    level: int
    title: str
    body: str
    times: set[int]


def render_body(body: str) -> str:
    headings = rules.markdown_headings(body)
    ends = [start for _, _, start, _ in headings[1:]] + [len(body)]
    sections: list[Section] = []
    for (level, title, _, heading_end), end in zip(headings, ends):
        content, times = render_lines(body[heading_end:end])
        sections.append(Section(level, title, content, times | rules.delivery_times(title)))

    kept: list[Section] = []
    for index, section in enumerate(sections):
        has_child = index + 1 < len(sections) and sections[index + 1].level > section.level
        if has_child or not EMPTY_SECTION.fullmatch(section.body.strip()):
            kept.append(section)

    parts = []
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
                title += f"（{time_label}）"
        content = section.body
        if content == "\n" or (content.startswith("\n") and content.split("\n", 2)[1].strip()):
            content = "\n" + content
        parts.extend((f"{'#' * section.level} {title}", content))
    return "".join(parts).strip("\n")


def _delivery_language(body: str, requested: str | None) -> str:
    if requested in ("英文", "en"):
        return "en"
    if requested in ("中文", "中英文对照", "zh"):
        return "zh"
    parts: list[str] = []
    offset = 0
    for _, _, start, end in rules.markdown_headings(body):
        parts.append(body[offset:start])
        offset = end
    parts.append(body[offset:])
    prose = re.sub(r"(?m)^(?:[ \t]*>|本文略去[｜|]).*$", "", "\n".join(parts))
    cjk, latin = rules._script_counts(prose)
    return "en" if latin > 0 and cjk < 4 and cjk * 20 < latin else "zh"


def render_note(note: bytes, *, keep_frontmatter: bool, self_review: bool = False,
                reading_level: str | None = None, delivery_language: str | None = None) -> bytes:
    if reading_level is not None and reading_level not in knowledge_note.READING_LEVELS:
        raise RenderError(f"invalid reading_level: {reading_level!r}")
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
    evidence_start, evidence_end = evidence
    screen_quote = re.compile(r"^\s*>[ \t]+\[(?:\d+:)?\d{2,}:[0-5]\d\]\[画面\]", re.MULTILINE)
    has_screen = bool(screen_quote.search(body, evidence_end))
    body = body[:evidence_start]
    omission = OMISSION.search(body)
    if omission is None:
        raise RenderError("note.md is missing the 本文略去 line")

    intro = ("未经独立复核" if self_review else None, INTRO, SCREEN_HINT if has_screen else None)
    notices = ["说明：" + "；".join(part for part in intro if part is not None) + "。"]
    if reading_level is not None:
        prose = body[:omission.start()]
        language = _delivery_language(prose, delivery_language)
        notices.append(LEVEL_DESCRIPTIONS[language][reading_level])
    markdown = "\n\n".join((
        f"# {fields['title']}",
        f"{fields['channel'] or '—'} · {fields['published'] or '—'} · [原视频]({fields['source']})",
        *notices,
        render_body(body[:omission.start()]),
        "---",
        f"没写进来的部分：{omission[1]}",
        OUTRO,
    )) + "\n"
    if "⏱" in markdown or "[!" in markdown:
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


def render_job(job: Path, output: Path | None, *, keep_frontmatter: bool, require_review: bool = False,
               output_dir: Path | None = None, delivery_language: str | None = None) -> Path:
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
        markdown = render_note(note, keep_frontmatter=keep_frontmatter, self_review=self_review,
                               reading_level=reading_level, delivery_language=delivery_language)
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
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as staged:
                temp = Path(staged.name)
                staged.write(markdown)
            check_destination(job, output)
            check_finished(job, inputs, verifier, review)
            temp.replace(output)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        status = verify_note.read_job_status(job)
        status["next_step"] = "deliver"
        verify_note.write_job_status(job, status)
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
                        help="Delivery language for reading-level header")
    parser.add_argument("--require-review", action="store_true",
                        help="Require a bound review receipt (self-review allowed, marked 未经独立复核)")
    args = parser.parse_args(argv)
    try:
        path = render_job(args.task_dir, args.output, keep_frontmatter=args.keep_frontmatter,
                          require_review=args.require_review, output_dir=args.output_dir,
                          delivery_language=args.language)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Reading note not written: {exc}", file=sys.stderr)
        return 1
    if args.output_dir is not None:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
