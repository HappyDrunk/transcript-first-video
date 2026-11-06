#!/usr/bin/env python3
"""Fail-closed note gate.

A note is allowed only when all of these hold:

- The transcript file exists and passes the quality gate.
- The note cites that file and quotes a real window of it.
- The note is Obsidian Markdown with the knowledge sections
  问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步.
- Each section quotes the transcript and adds analysis that is not a stub.
- A section may instead be one line, ``本节不适用：`` plus a reason, and one quote.
- Four sections in that form are not a deposit. ``--job`` archives note.md and
  sets status ``no-extractable-content``.

A path, a status line, or a blockquote alone is not a finished note.
The gate does not listen to audio. It does not grade an LLM summary.
Analyzer essays about a failed transcription are refused unless the transcript
itself passed and the note quotes it.

Exit 0 allowed. Exit 2 refused. Exit 1 usage or read error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import knowledge_note  # noqa: E402
try:
    import verify_rules  # noqa: E402
except ModuleNotFoundError as exc:
    if exc.name != "verify_rules":
        raise
    print("missing required script file: scripts/verify_rules.py", file=sys.stderr)
    raise SystemExit(2) from exc

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
REPAIR_LIMIT_MESSAGE = "未交：已超过 2 轮"


def read_job_status(job: Path) -> dict:
    status_path = job / "status.json"
    if not status_path.is_file():
        return {}
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_job_status(job: Path, data: dict) -> None:
    (job / "status.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def repair_lock(status: dict) -> bool:
    repair_rounds = status.get("repair_rounds", 0)
    edit_rounds = status.get("edit_rounds", 0)
    return (
        status.get("status") == "not_deposited"
        or (isinstance(repair_rounds, int) and not isinstance(repair_rounds, bool) and repair_rounds > 2)
        or (isinstance(edit_rounds, int) and not isinstance(edit_rounds, bool) and edit_rounds > 2)
    )


def current_skill_version() -> str:
    root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        version = result.stdout.strip()
        if version:
            return version
    except (OSError, subprocess.SubprocessError):
        pass
    version_file = root / "VERSION"
    if version_file.is_file():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version
    return "unknown"


def record_note_revision(job: Path, note: str) -> dict:
    """Count distinct note revisions so repeated edits cannot bypass the shared cap."""
    data = read_job_status(job)
    digest = hashlib.sha256(note.encode("utf-8")).hexdigest()
    previous = data.get("note_digest")
    rounds = data.get("edit_rounds", 0)
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 0:
        rounds = 0
    if digest != previous:
        rounds += 1
        data["note_digest"] = digest
        data["edit_rounds"] = rounds
        data["finished"] = False
        data["coverage"] = {"allowed": False, "reasons": ["note changed after verification"]}
        if data.get("status") == "finished":
            data["status"] = "transcript_ready"
        if rounds > 2:
            data["status"] = "not_deposited"
            data["locked"] = True
            data["reason"] = REPAIR_LIMIT_MESSAGE
    write_job_status(job, data)
    return data


def record_gate_result(job: Path, gate: str, allowed: bool, reasons: list[str]) -> dict:
    """Persist one verify or coverage outcome and the shared repair budget."""
    data = read_job_status(job)
    rounds = data.get("repair_rounds", 0)
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 0:
        rounds = 0
    data["repair_rounds"] = rounds
    data["finished"] = False
    if gate == "verify":
        data["verifier"] = {
            "allowed": allowed,
            "at": datetime.now(timezone.utc).isoformat(),
            "skill_version": current_skill_version(),
            **({"reasons": reasons} if reasons else {}),
        }
        if not allowed:
            data["coverage"] = {"allowed": False, "reasons": ["verify failed"]}
    else:
        data["coverage"] = {"allowed": allowed, "reasons": reasons}
    if not allowed:
        data["repair_rounds"] = rounds + 1
        data["failure_lines"] = reasons
        if data["repair_rounds"] > 2:
            data["status"] = "not_deposited"
            data["locked"] = True
            data["reason"] = REPAIR_LIMIT_MESSAGE
        elif data.get("status") == "finished":
            data["status"] = "transcript_ready"
    elif gate == "coverage" and (data.get("verifier") or {}).get("allowed") is True:
        data["finished"] = True
        data["status"] = "finished"
        data.pop("failure_lines", None)
    write_job_status(job, data)
    return data


def archive_file(path: Path) -> Path | None:
    """Keep a replaced document under a stable .prev name, adding a number as needed."""
    if not path.is_file():
        return None
    first = path.with_name(f"{path.stem}.prev{path.suffix}")
    target = first
    number = 2
    while target.exists():
        target = path.with_name(f"{path.stem}.prev.{number}{path.suffix}")
        number += 1
    path.replace(target)
    return target


def apply_no_extractable(job: Path, reason: str) -> dict:
    """Record that the note must not be deposited, archiving prior documents."""
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
    archive_file(note_path)
    archive_file(job / "delivery.md")
    data["status"] = NO_EXTRACTABLE
    data["finished"] = False
    rounds = data.get("repair_rounds", 0)
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 0:
        rounds = 0
    data["repair_rounds"] = rounds + 1
    data["note"] = None
    data["delivery"] = None
    data["note_stale"] = True
    data["reason"] = reason
    data["next_step"] = "stop"
    data["verifier"] = {
        "allowed": False,
        "at": datetime.now(timezone.utc).isoformat(),
        "skill_version": current_skill_version(),
        "reasons": [reason],
    }
    data["failure_lines"] = [reason]
    if data["repair_rounds"] > 2:
        data["status"] = "not_deposited"
        data["locked"] = True
        data["reason"] = REPAIR_LIMIT_MESSAGE
    write_job_status(job, data)
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
        help="Job directory. Uses transcript.txt and note.md. All-N/A archives the documents.",
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
        current_status = read_job_status(job)
        if repair_lock(current_status):
            return _emit_verify(
                {"allowed": False, "reasons": [REPAIR_LIMIT_MESSAGE]}, as_json=args.json
            )
        transcript = job / "transcript.txt"
        note_path = job / "note.md" if note_arg is None else Path(note_arg)
        if note_path.is_file():
            note = note_path.read_text(encoding="utf-8", errors="replace")
            if knowledge_note.all_sections_inapplicable(note):
                reason = knowledge_note.ALL_INAPPLICABLE_REASON
                updated = apply_no_extractable(job, reason)
                if repair_lock(updated):
                    return _emit_verify(
                        {"allowed": False, "reasons": [REPAIR_LIMIT_MESSAGE]},
                        as_json=args.json,
                    )
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
            record_gate_result(job, "verify", False, [message])
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
    if args.job is not None:
        status = record_note_revision(args.job, note)
        if repair_lock(status):
            return _emit_verify(
                {"allowed": False, "reasons": [REPAIR_LIMIT_MESSAGE]}, as_json=args.json
            )
    result = verify(
        transcript,
        note,
        expected_lang=expected,
        confidence=args.confidence,
        job_status=status_name,
    )
    if args.job is not None:
        status = record_gate_result(
            args.job, "verify", bool(result.get("allowed")), result.get("reasons") or []
        )
        if repair_lock(status):
            result["allowed"] = False
            result["reasons"] = [REPAIR_LIMIT_MESSAGE]
    return _emit_verify(result, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
