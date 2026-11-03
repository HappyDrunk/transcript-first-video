#!/usr/bin/env python3
"""Fail-closed note gate.

A note is allowed only when all of these hold:

- The transcript file exists and passes the quality gate.
- The note cites that file and quotes a real window of it.
- The note is Obsidian Markdown with the knowledge sections
  问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步.
- Each section quotes the transcript and adds analysis that is not a stub.

A path, a status line, or a blockquote alone is not a finished note.
The gate does not listen to audio. It does not grade an LLM summary.
Analyzer essays about a failed transcription are refused unless the transcript
itself passed and the note quotes it.

Exit 0 allowed. Exit 2 refused. Exit 1 usage or read error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import knowledge_note  # noqa: E402
import quality_gate  # noqa: E402

QUOTE_WINDOW = knowledge_note.QUOTE_WINDOW

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


def citation_forms(transcript: Path) -> set[str]:
    forms: set[str] = set()
    raw = str(transcript)
    forms.add(raw)
    forms.add(raw.replace("\\", "/"))
    forms.add("./" + raw.replace("\\", "/").lstrip("./"))
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


def note_cites(note: str, transcript: Path) -> bool:
    folded = note.replace("\\", "/")
    for form in citation_forms(transcript):
        if form.replace("\\", "/") in folded:
            return True
    return False


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold().strip()


def quotes_transcript(note: str, transcript_text: str, window: int = QUOTE_WINDOW) -> bool:
    """True when the note contains a contiguous transcript window.

    Whitespace is collapsed and case is folded. The window may start at any
    offset, so a real sentence quote counts. A path, a title, or a paraphrase
    does not.
    """
    compact_note = _compact(note)
    compact = _compact(transcript_text)
    if window <= 0 or len(compact) < window or len(compact_note) < window:
        return False
    # Slide the shorter side. A hit means the note holds a real snippet.
    if len(compact_note) <= len(compact):
        source, haystack = compact_note, compact
    else:
        source, haystack = compact, compact_note
    last = len(source) - window + 1
    for index in range(last):
        if source[index : index + window] in haystack:
            return True
    return False


def quote_refusal(transcript_text: str) -> str:
    compact = _compact(transcript_text)
    if len(compact) < QUOTE_WINDOW:
        return (
            "note does not quote a transcript window "
            f"(transcript is shorter than {QUOTE_WINDOW} characters after cleanup, "
            "so there is no quotable window)"
        )
    return (
        "note does not quote a transcript window "
        f"(need {QUOTE_WINDOW} contiguous characters from the transcript; "
        "a path or a title is not a quote)"
    )


def verify(
    transcript: Path,
    note: str,
    *,
    expected_lang: str | None = None,
    confidence: float | None = None,
) -> dict:
    reasons: list[str] = []
    gate = None
    exists = transcript.is_file()
    if not exists:
        reasons.append(f"missing transcript path: {transcript} does not exist")
    else:
        raw = transcript.read_text(encoding="utf-8", errors="replace")
        gate = quality_gate.assess(raw, expected_lang=expected_lang, confidence=confidence)
        if not gate.passed:
            for reason in gate.reasons:
                reasons.append(f"quality gate failed: {reason}")
    cited = note_cites(note, transcript)
    quoted = bool(exists and gate is not None and quotes_transcript(note, gate.text))
    if exists and gate is not None and gate.passed:
        if not cited:
            display = transcript.as_posix() if not transcript.is_absolute() else str(transcript)
            reasons.append(f"note does not cite transcript path {display}")
        if not quoted:
            reasons.append(quote_refusal(gate.text))
        reasons.extend(knowledge_note.knowledge_reasons(note, gate.text))
        fields = knowledge_note.parse_frontmatter(note) or {}
        cited_path = str(fields.get("transcript_path") or "").replace("\\", "/")
        forms = {form.replace("\\", "/") for form in citation_forms(transcript)}
        if cited_path and cited_path not in forms:
            reasons.append(
                f"frontmatter transcript_path does not match the transcript file {transcript.as_posix()}"
            )
    elif not exists and not cited:
        reasons.append(f"note does not cite transcript path {transcript.as_posix()}")
    laundering = bool(_LAUNDER.search(note))
    if laundering:
        usable = gate is not None and gate.passed
        if not usable:
            reasons.append(
                "analyzer-laundering: the note is an essay about ASR or transcription "
                "failure without a usable transcript"
            )
        elif not quoted:
            reasons.append(
                "analyzer-laundering: the note discusses ASR or transcription failure "
                "and does not quote the transcript"
            )
    allowed = not reasons
    return {
        "allowed": allowed,
        "reasons": reasons,
        "transcript": transcript.as_posix(),
        "cited": cited,
        "quoted": quoted,
        "gate": None if gate is None else gate.to_dict(),
    }


def _read_note(note_arg: str) -> str:
    if note_arg == "-":
        if sys.stdin.isatty():
            raise SystemExit(
                "pass --note PATH, or pipe the note on stdin (refusing an empty tty read)"
            )
        return sys.stdin.read()
    path = Path(note_arg)
    if not path.is_file():
        raise SystemExit(f"note path does not exist: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Allow a note only when it cites a transcript that passes the quality gate, "
            "quotes that transcript in each knowledge section, and analyzes it. "
            "A path plus a quote is not enough."
        )
    )
    parser.add_argument("--transcript", required=True, type=Path)
    parser.add_argument(
        "--note",
        default="-",
        help="Note file. Use - or omit to read stdin.",
    )
    parser.add_argument("--expected-lang", default=None)
    parser.add_argument("--confidence", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        note = _read_note(args.note)
    except SystemExit as exc:
        message = str(exc)
        if args.json:
            json.dump({"allowed": False, "reasons": [message]}, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        else:
            print(message, file=sys.stderr)
        return 1
    result = verify(
        args.transcript,
        note,
        expected_lang=args.expected_lang,
        confidence=args.confidence,
    )
    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print("allowed" if result["allowed"] else "refused")
        for reason in result["reasons"]:
            print(reason, file=sys.stderr)
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    sys.exit(main())
