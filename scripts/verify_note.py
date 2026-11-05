#!/usr/bin/env python3
"""Fail-closed note gate.

A note is allowed only when all of these hold:

- The transcript file exists and passes the quality gate.
- The note cites that file and quotes a real window of it.
- The note is Obsidian Markdown with the knowledge sections
  问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步.
- Each section quotes the transcript and adds analysis that is not a stub.
- A section may instead be one line, ``本节不适用：`` plus a reason, and one quote.
- Four sections in that form are not a deposit. ``--job`` deletes note.md and
  sets status ``no-extractable-content``.

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
import verify_rules  # noqa: E402

QUOTE_WINDOW = knowledge_note.QUOTE_WINDOW


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
    job_status: str | None = None,
) -> dict:
    """Run R01–R17. ``reasons`` are ``Rxx FAIL: ...`` lines."""
    ctx = verify_rules.build_context(
        transcript,
        note,
        expected_lang=expected_lang,
        confidence=confidence,
        job_status=job_status,
    )
    results = verify_rules.run_rules(ctx)
    reasons = verify_rules.failure_lines(results)
    gate = ctx.gate
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "rules": [
            {"id": rule_id, "ok": ok, "message": message}
            for rule_id, ok, message in results
        ],
        "transcript": transcript.as_posix(),
        "cited": ctx.cited,
        "quoted": ctx.quoted,
        "gate": None if gate is None else gate.to_dict(),
    }


NO_EXTRACTABLE = "no-extractable-content"


def apply_no_extractable(job: Path, reason: str) -> dict:
    """Record that the note must not be deposited, and delete note.md."""
    status_path = job / "status.json"
    data: dict = {}
    if status_path.is_file():
        try:
            loaded = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            data = loaded
    note_path = job / "note.md"
    if note_path.is_file():
        note_path.unlink()
    data["status"] = NO_EXTRACTABLE
    data["finished"] = False
    data["note"] = None
    data["reason"] = reason
    data["next_step"] = "stop"
    data["verifier"] = {"allowed": False, "reasons": [reason]}
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


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


def _emit_verify(result: dict, *, as_json: bool) -> int:
    if as_json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print("allowed" if result.get("allowed") else "refused")
        for reason in result.get("reasons") or []:
            print(reason, file=sys.stderr)
    return 0 if result.get("allowed") else 2


def _job_expected_lang(job: Path, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    status_path = job / "status.json"
    if not status_path.is_file():
        return None
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data.get("gate_lang") or data.get("expected_lang")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Allow a note only when it cites a transcript that passes the quality gate, "
            "quotes that transcript in each knowledge section, and analyzes it. "
            "A path plus a quote is not enough. "
            "--job reads transcript.txt and note.md in a host directory."
        )
    )
    parser.add_argument(
        "--job",
        type=Path,
        help="Job directory. Uses transcript.txt and note.md. All-N/A deletes note.md.",
    )
    parser.add_argument("--transcript", type=Path)
    parser.add_argument(
        "--note",
        default=None,
        help="Note file. Use - to read stdin. Defaults to note.md inside --job, otherwise stdin.",
    )
    parser.add_argument("--expected-lang", default=None)
    parser.add_argument("--confidence", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    transcript = args.transcript
    note_arg = args.note
    if args.job is not None:
        job = args.job
        if not job.is_dir():
            message = f"job directory does not exist: {job}"
            _emit_verify({"allowed": False, "reasons": [message]}, as_json=args.json)
            return 1
        transcript = job / "transcript.txt"
        note_path = job / "note.md" if note_arg is None else Path(note_arg)
        if note_path.is_file():
            note = note_path.read_text(encoding="utf-8", errors="replace")
            if knowledge_note.all_sections_inapplicable(note):
                reason = knowledge_note.ALL_INAPPLICABLE_REASON
                apply_no_extractable(job, reason)
                return _emit_verify(
                    {
                        "allowed": False,
                        "reasons": [f"R03 FAIL: {reason}"],
                        "status": NO_EXTRACTABLE,
                        "note_deleted": True,
                    },
                    as_json=args.json,
                )
        elif note_arg is None:
            message = f"note.md is missing in {job}"
            return _emit_verify({"allowed": False, "reasons": [message]}, as_json=args.json)
        else:
            note_arg = str(note_path)
        if note_arg is None:
            note_arg = str(note_path)
        expected = _job_expected_lang(job, args.expected_lang)
        status_name = None
        status_path = job / "status.json"
        if status_path.is_file():
            try:
                loaded = json.loads(status_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                status_name = loaded.get("status")
    else:
        if transcript is None:
            parser.error("pass --transcript, or pass --job")
        if note_arg is None:
            note_arg = "-"
        expected = args.expected_lang
        status_name = None
    try:
        note = _read_note(note_arg)
    except SystemExit as exc:
        message = str(exc)
        _emit_verify({"allowed": False, "reasons": [message]}, as_json=args.json)
        return 1
    result = verify(
        transcript,
        note,
        expected_lang=expected,
        confidence=args.confidence,
        job_status=status_name,
    )
    return _emit_verify(result, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
