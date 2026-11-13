#!/usr/bin/env python3
"""Render a reading copy after checking the current evidence note and its inputs."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import coverage_check
import knowledge_note
import verify_note
import verify_rules as rules


INTRO = "带竖线的行是 AI 补充的名词解释或比方，不是视频里说的话。"
SCREEN_HINT = "标明来自画面的内容由机器识别，可能有个别字符误差。"
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
    rules.SCREEN_FILE,
)
ARCHIVED_NOTE = re.compile(r"(?:note|delivery)\.prev(?:\.[0-9]+)?\.md", re.IGNORECASE)


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
    heading: re.Match[str]
    body: str
    times: set[int]

    @property
    def level(self) -> int:
        return len(self.heading[1])


def render_body(body: str) -> str:
    headings = list(rules._HEADING.finditer(body))
    ends = [heading.start() for heading in headings[1:]] + [len(body)]
    sections: list[Section] = []
    for heading, end in zip(headings, ends):
        content, times = render_lines(body[heading.end():end])
        sections.append(Section(heading, content, times | rules.delivery_times(heading[2])))

    kept: list[Section] = []
    for index, section in enumerate(sections):
        has_child = index + 1 < len(sections) and sections[index + 1].level > section.level
        if has_child or not EMPTY_SECTION.fullmatch(section.body.strip()):
            kept.append(section)

    parts = []
    for index, section in enumerate(kept):
        heading = section.heading
        title = remove_times(heading[2])
        if section.level == 3:
            times = section.times.copy()
            for child in kept[index + 1:]:
                if child.level <= section.level:
                    break
                times.update(child.times)
            if times:
                title += f"（{rules._fmt(min(times))}–{rules._fmt(max(times))}）"
        content = section.body
        if content == "\n" or (content.startswith("\n") and content.split("\n", 2)[1].strip()):
            content = "\n" + content
        parts.extend((heading.string[heading.start():heading.start(2)], title,
                      heading.string[heading.end(2):heading.end()], content))
    return "".join(parts).strip("\n")


def render_note(note: bytes, *, keep_frontmatter: bool) -> bytes:
    text = note.decode("utf-8-sig")
    frontmatter = FRONTMATTER.match(text)
    if frontmatter is None:
        raise RenderError("note.md is missing its opening YAML block")
    fields = knowledge_note.parse_frontmatter(normalize_newlines(frontmatter[0]))
    if fields is None:
        raise RenderError("could not read note.md properties")

    body = normalize_newlines(text[frontmatter.end():])
    evidence = next((heading for heading in rules._HEADING.finditer(body)
                     if heading.groups() == ("##", rules.EVIDENCE_HEADING)), None)
    if evidence is None:
        raise RenderError("note.md is missing the 原文依据 section")
    screen_quote = re.compile(r"^\s*>[ \t]+\[(?:\d+:)?\d{2,}:[0-5]\d\]\[画面\]", re.MULTILINE)
    has_screen = bool(screen_quote.search(body, evidence.end()))
    body = body[:evidence.start()]
    omission = OMISSION.search(body)
    if omission is None:
        raise RenderError("note.md is missing the 本文略去 line")

    markdown = "\n\n".join((
        f"# {fields['title']}",
        f"{fields['channel'] or '—'} · {fields['published'] or '—'} · [原视频]({fields['source']})",
        f"{INTRO}\n\n{SCREEN_HINT}" if has_screen else INTRO,
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
    if any(path.is_relative_to(job / rules.SCREEN_FRAMES) for path in (output, resolved)):
        raise RenderError(f"--output would use the screenshot directory: {output}")
    if any(path.parent == job and ARCHIVED_NOTE.fullmatch(path.name) for path in (output, resolved)):
        raise RenderError(f"--output would use a job archive path: {output}")
    for name in JOB_FILES:
        protected = job / name
        if (output == protected or resolved == protected.resolve()
                or (output.exists() and protected.exists() and output.samefile(protected))):
            raise RenderError(f"--output would overwrite {name}: {output}")


def check_finished(job: Path, inputs: dict, verifier: dict) -> None:
    if verify_note.job_inputs(job) != inputs:
        raise RenderError("job files changed during rendering; rerun both checks")
    status = verify_note.read_job_status(job)
    coverage = status.get("coverage")
    if (status.get("finished") is not True or status.get("verifier") != verifier
            or not isinstance(coverage, dict)
            or coverage.get("allowed") is not True or coverage.get("inputs") != inputs):
        raise RenderError("verify and coverage must finish on the current job files")


def render_job(job: Path, output: Path, *, keep_frontmatter: bool) -> None:
    job = job.resolve(strict=True)
    if not job.is_dir():
        raise RenderError(f"--task-dir is not a directory: {job}")
    output = output.parent.resolve() / output.name
    check_destination(job, output)

    with verify_note.job_lock(job):
        inputs = verify_note.job_inputs(job)
        # These are the same job checks as the CLI, under one lock through publication.
        verify_args = argparse.Namespace(note=None, confidence=None, expected_lang=None, json=False)
        if verify_note._verify_job(job, verify_args):
            raise RenderError("verify failed")
        verifier = verify_note.read_job_status(job).get("verifier")
        if not isinstance(verifier, dict) or verifier.get("allowed") is not True or verifier.get("inputs") != inputs:
            raise RenderError("job files changed during verification; rerun both checks")

        coverage = coverage_check._check_and_record(job, None)
        for line in coverage["reasons"] + coverage["warnings"] + coverage["not_checked"]:
            print(line, file=sys.stderr)
        if not coverage["ok"]:
            raise RenderError("coverage failed")
        check_finished(job, inputs, verifier)
        note = (job / "note.md").read_bytes()
        if hashlib.sha256(note).hexdigest() != inputs["note_file"]:
            raise RenderError("note.md changed during rendering; rerun both checks")
        markdown = render_note(note, keep_frontmatter=keep_frontmatter)

        output.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as staged:
                temp = Path(staged.name)
                staged.write(markdown)
            check_destination(job, output)
            check_finished(job, inputs, verifier)
            temp.replace(output)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True, help="Job directory containing the evidence note")
    parser.add_argument("--output", type=Path, required=True, help="Full path for the reading Markdown file")
    parser.add_argument("--keep-frontmatter", action="store_true", help="Keep the evidence note's opening YAML block")
    args = parser.parse_args(argv)
    try:
        render_job(args.task_dir, args.output, keep_frontmatter=args.keep_frontmatter)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Reading note not written: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
