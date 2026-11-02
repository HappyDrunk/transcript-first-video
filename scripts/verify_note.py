#!/usr/bin/env python3
"""Fail-closed note gate.

A note is allowed only when it cites an existing transcript file and that
file passes the quality gate. Analyzer essays about a failed transcription
are refused unless the transcript itself passed and the note quotes it.

Exit 0 allowed. Exit 2 refused. Exit 1 usage or read error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quality_gate  # noqa: E402

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


def quotes_transcript(note: str, transcript_text: str) -> bool:
    compact_note = re.sub(r"\s+", " ", note).casefold()
    compact = re.sub(r"\s+", " ", transcript_text).casefold()
    if len(compact) < 40:
        return False
    step = 40
    for index in range(0, len(compact) - 39, step):
        if compact[index : index + 40] in compact_note:
            return True
    return False


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
    if exists and gate is not None and gate.passed and not cited:
        display = transcript.as_posix() if not transcript.is_absolute() else str(transcript)
        reasons.append(f"note does not cite transcript path {display}")
    elif not exists and not cited:
        reasons.append(f"note does not cite transcript path {transcript.as_posix()}")
    laundering = bool(_LAUNDER.search(note))
    if laundering:
        usable = gate is not None and gate.passed
        quoted = usable and quotes_transcript(note, gate.text)
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
        description="Allow a note only when it cites a transcript that passes the quality gate."
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
