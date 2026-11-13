#!/usr/bin/env python3
"""Verify a reader-facing single note. Exit 0 allowed, 2 refused, 1 usage/read error."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
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
    job: bool = False,
) -> dict:
    """Run the single-note R and C04 rules. ``reasons`` are ``Rxx FAIL: ...`` lines."""
    ctx = verify_rules.build_context(
        transcript,
        note,
        expected_lang=expected_lang,
        confidence=confidence,
        job_status=job_status,
        job=job,
    )
    results = verify_rules.run_rules(ctx)
    reasons = verify_rules.failure_lines(results)
    gate = ctx.gate
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "warnings": verify_rules.warnings(ctx),
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
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=job, delete=False) as staged:
        temp = Path(staged.name)
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(job / "status.json")
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def job_lock(job: Path):
    """Serialize acquisition and the two state-writing checks for one job."""
    with (job / ".status.lock").open("a+b") as lock:
        if sys.platform == "win32":
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _note_digest(note: str) -> str:
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


def job_inputs(job: Path) -> dict:
    """Identify the exact note and context checked by both gates."""
    inputs = {}
    for key, name in (("note", "note.md"), ("transcript", "transcript.txt"),
                      ("selection", "selection.md"), ("segments", "segments.json")):
        path = job / name
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            inputs[key] = None
            if key == "note":
                inputs["note_file"] = None
            continue
        digest = hashlib.sha256(content).hexdigest()
        if key == "note":
            normalized = content.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
            inputs["note_file"] = digest
            inputs[key] = _note_digest(normalized)
        else:
            inputs[key] = digest
    status = read_job_status(job)
    if verify_rules.screen_mode() != "off":
        screen = job / verify_rules.SCREEN_FILE
        try:
            inputs["screen"] = hashlib.sha256(screen.read_bytes()).hexdigest()
        except FileNotFoundError:
            inputs["screen"] = None
    inputs["duration_seconds"] = status.get("duration_seconds")
    inputs["expected_lang"] = status.get("gate_lang") or status.get("expected_lang")
    return inputs


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


def record_note_revision(job: Path, note: str | None = None, *, digest: str | None = None) -> dict:
    """Count distinct note revisions so repeated edits cannot bypass the shared cap."""
    data = read_job_status(job)
    if digest is None:
        if note is None:
            raise ValueError("note text or digest is required")
        digest = _note_digest(note)
    previous = data.get("note_digest")
    rounds = data.get("edit_rounds", 0)
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 0:
        rounds = 0
    if digest != previous:
        rounds += 1
        data["note_digest"] = digest
        data["edit_rounds"] = rounds
        data["finished"] = False
        data["verifier"] = None
        data["coverage"] = {"allowed": False, "reasons": ["note changed after verification"]}
        if data.get("status") == "finished":
            data["status"] = "transcript_ready"
        if rounds > 2:
            data["status"] = "not_deposited"
            data["locked"] = True
            data["reason"] = REPAIR_LIMIT_MESSAGE
    write_job_status(job, data)
    return data


def record_gate_result(
    job: Path, gate: str, allowed: bool, reasons: list[str], *, inputs: dict | None = None,
) -> dict:
    """Persist one verify or coverage outcome and the shared repair budget."""
    data = read_job_status(job)
    rounds = data.get("repair_rounds", 0)
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 0:
        rounds = 0
    data["repair_rounds"] = rounds
    data["finished"] = False
    if data.get("status") == "finished":
        data["status"] = "transcript_ready"
    if gate == "verify":
        data["verifier"] = {
            "allowed": allowed,
            "at": datetime.now(timezone.utc).isoformat(),
            "skill_version": current_skill_version(),
            "inputs": inputs if allowed else None,
            **({"reasons": reasons} if reasons else {}),
        }
        data["coverage"] = {
            "allowed": False, "reasons": ["coverage pending" if allowed else "verify failed"],
        }
    else:
        data["coverage"] = {"allowed": allowed, "reasons": reasons, "inputs": inputs if allowed else None}
    if not allowed:
        data["repair_rounds"] = rounds + 1
        data["failure_lines"] = reasons
        if data["repair_rounds"] > 2:
            data["status"] = "not_deposited"
            data["locked"] = True
            data["reason"] = REPAIR_LIMIT_MESSAGE
    elif gate == "coverage" and inputs is not None:
        verifier = data.get("verifier") or {}
        if (
            verifier.get("allowed") is True
            and verifier.get("inputs") == inputs
            and verifier.get("skill_version") == current_skill_version()
        ):
            data["finished"] = True
            data["status"] = "finished"
            data["note"] = "note.md"
            data["note_stale"] = False
            data.pop("failure_lines", None)
    write_job_status(job, data)
    return data


def archive_file(path: Path) -> Path | None:
    """Keep a replaced document under a stable .prev name, adding a number as needed."""
    if not path.exists():
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
    data["coverage"] = {"allowed": False, "reasons": [reason]}
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
        for warning in result.get("warnings") or []:
            print(warning, file=sys.stderr)
    return 0 if result.get("allowed") else 2


def _verify_job(job: Path, args: argparse.Namespace) -> int:
    status = read_job_status(job)
    if repair_lock(status):
        return _emit_verify({"allowed": False, "reasons": [REPAIR_LIMIT_MESSAGE]}, as_json=args.json)

    inputs = job_inputs(job)
    try:
        note = _read_note(args.note or str(job / "note.md"))
    except SystemExit as exc:
        reason = str(exc)
        record_gate_result(job, "verify", False, [reason])
        return _emit_verify({"allowed": False, "reasons": [reason]}, as_json=args.json)

    canonical_note = inputs["note"] == _note_digest(note)
    if canonical_note and knowledge_note.all_sections_inapplicable(note):
        reason = knowledge_note.ALL_INAPPLICABLE_REASON
        updated = apply_no_extractable(job, reason)
        reasons = [f"C04a FAIL: {reason}"]
        if repair_lock(updated):
            reasons.append(REPAIR_LIMIT_MESSAGE)
        return _emit_verify(
            {"allowed": False, "reasons": reasons, "status": NO_EXTRACTABLE, "note_deleted": True},
            as_json=args.json,
        )

    status = record_note_revision(job, note)
    if repair_lock(status):
        return _emit_verify({"allowed": False, "reasons": [REPAIR_LIMIT_MESSAGE]}, as_json=args.json)
    result = verify(
        job / "transcript.txt", note, job=True, confidence=args.confidence,
        expected_lang=args.expected_lang or inputs["expected_lang"], job_status=status.get("status"),
    )
    if inputs != job_inputs(job):
        result["allowed"] = False
        result["reasons"].append("job files changed during verification; rerun both checks")
    checked_inputs = inputs if canonical_note else None
    status = record_gate_result(job, "verify", result["allowed"], result["reasons"], inputs=checked_inputs)
    if repair_lock(status):
        result["allowed"] = False
        result["reasons"].append(REPAIR_LIMIT_MESSAGE)
    return _emit_verify(result, as_json=args.json)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the single note against its transcript.")
    parser.add_argument("--job", type=Path, help="Job directory containing transcript.txt and note.md")
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--note", help="Note path or - for stdin. Defaults to note.md with --job.")
    parser.add_argument("--expected-lang")
    parser.add_argument("--confidence", type=float)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.job is not None:
        if not args.job.is_dir():
            _emit_verify({"allowed": False, "reasons": [f"job directory does not exist: {args.job}"]}, as_json=args.json)
            return 1
        with job_lock(args.job):
            return _verify_job(args.job, args)
    if args.transcript is None:
        parser.error("pass --transcript, or pass --job")
    try:
        note = _read_note(args.note or "-")
    except SystemExit as exc:
        _emit_verify({"allowed": False, "reasons": [str(exc)]}, as_json=args.json)
        return 1
    return _emit_verify(
        verify(args.transcript, note, expected_lang=args.expected_lang, confidence=args.confidence),
        as_json=args.json,
    )


if __name__ == "__main__":
    sys.exit(main())
