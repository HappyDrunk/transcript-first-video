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
from collections.abc import Sequence
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
import c04c_review  # noqa: E402

QUOTE_WINDOW = knowledge_note.QUOTE_WINDOW
SCREEN_PENDING = "screen_pending"
SCREEN_PENDING_MESSAGE = "Screen acquisition is pending; wait for the host or rerun acquisition if it stopped."


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
    c04c = []
    results = verify_rules.run_rules(ctx, c04c)
    reasons = verify_rules.failure_lines([item for item in results if item[0] != "C04c"])
    gate = ctx.gate
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "warnings": [*verify_rules.warnings(ctx), *(c04c_review.warning(row) for row in c04c)],
        "c04c": c04c,
        "c04c_sha256": c04c_review.digest(c04c),
        "rules": [
            {"id": rule_id, "ok": ok, "message": message,
             **({"severity": "WARN"} if rule_id == "C04c" and not ok else {})}
            for rule_id, ok, message in results
        ],
        "transcript": transcript.as_posix(),
        "cited": ctx.cited,
        "quoted": ctx.quoted,
        "gate": None if gate is None else gate.to_dict(),
    }


NO_EXTRACTABLE = "no-extractable-content"
NEEDS_USER = "needs_user_input"
REPAIR_LIMIT_MESSAGE = "未交：本批修订已用完"
MAX_ORDINARY_DRAFTS = 3
DRAFT_LIMIT_MESSAGE = f"未交：普通稿超过 {MAX_ORDINARY_DRAFTS} 份"


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


_FORMAT_CLOCK = r"(?:[0-9]+[:：])?[0-9]{2,}[:：][0-5][0-9]"
_FORMAT_QUOTE = re.compile(
    rf"^(?P<prefix>[ \t]{{0,3}}[>＞])(?P<gap>[ \t\u3000]*)[\[［](?P<clock>{_FORMAT_CLOCK})[\]］](?P<tail>[^\r\n]*)(?P<end>\r\n|\r|\n)?$"
)
_FORMAT_SCREEN_TAG = re.compile(r"^(?P<gap>[ \t\u3000]*)[\[［](?P<tag>画面[?？]?)[\]］](?P<text>.*)$")
_FORMAT_FRONTMATTER = re.compile(r"\A\ufeff?---(?:\r\n|\r|\n).*?(?:\r\n|\r|\n)---(?:\r\n|\r|\n)", re.DOTALL)


def _format_clock(clock: str) -> str | None:
    canonical = clock.replace("：", ":")
    return canonical if verify_rules.clock_seconds(canonical) is not None else None


def _format_separator(text: str) -> str:
    gap = re.match(r"[ \t\u3000]*", text)[0]
    payload = text[len(gap):]
    return (gap.replace("\u3000", " ") or (" " if payload else "")) + payload


def _format_quote_line(line: str) -> str:
    match = _FORMAT_QUOTE.fullmatch(line)
    if match is None or (clock := _format_clock(match["clock"])) is None:
        return line
    tail = match["tail"]
    screen = _FORMAT_SCREEN_TAG.fullmatch(tail)
    if screen:
        tag = screen["tag"].replace("？", "?")
        tag_gap = screen["gap"].replace("\u3000", " ")
        tail = f"{tag_gap}[{tag}]{_format_separator(screen['text'])}"
    else:
        tail = _format_separator(tail)
    gap = match["gap"].replace("\u3000", " ") or " "
    return f"{match['prefix'].replace('＞', '>')}{gap}[{clock}]{tail}{match['end'] or ''}"


def format_note_text(note: str) -> str:
    """Normalize quote headers in the final evidence section, preserving payloads."""
    frontmatter = _FORMAT_FRONTMATTER.match(note)
    if frontmatter is None:
        return note
    prefix = frontmatter[0]
    body = note[len(prefix):]
    evidence = next((end for level, title, _, end in reversed(verify_rules.markdown_headings(body))
                     if level == 2 and title == verify_rules.EVIDENCE_HEADING), None)
    if evidence is None:
        return note
    lines = body[evidence:].splitlines(keepends=True)
    if any(
        line.strip() and not line.lstrip().startswith((">", "＞")) for line in lines
    ):
        return note
    return prefix + body[:evidence] + "".join(_format_quote_line(line) for line in lines)


def _normalized_note_text(content: bytes) -> str:
    return content.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def prepare_job_note(job: Path) -> None:
    """Write formatting under the job lock before fingerprints or revision counts."""
    path = job / "note.md"
    try:
        original = path.read_bytes()
    except FileNotFoundError:
        return
    try:
        formatted = format_note_text(original.decode("utf-8")).encode("utf-8")
    except UnicodeDecodeError:
        return
    if formatted == original:
        return
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=job, delete=False) as output:
            staged = Path(output.name)
            output.write(formatted)
        if path.read_bytes() != original:
            raise RuntimeError("note.md changed during formatting; rerun submission")
        status = read_job_status(job)
        if status.get("note_digest") == _note_digest(_normalized_note_text(original)):
            # Commit the digest first so a failed note replacement is safe to retry.
            status["note_digest"] = _note_digest(_normalized_note_text(formatted))
            status["finished"] = False
            status["verifier"] = None
            status["coverage"] = {"allowed": False, "reasons": ["note formatting changed after verification"]}
            if status.get("status") == "finished":
                status["status"] = "transcript_ready"
            write_job_status(job, status)
        staged.replace(path)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


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
            normalized = _normalized_note_text(content)
            inputs["note_file"] = digest
            inputs[key] = _note_digest(normalized)
        else:
            inputs[key] = digest
    status = read_job_status(job)
    level = knowledge_note.read_reading_level(status)
    if level is not None:
        inputs["reading_level"] = level
    mode = verify_rules.screen_mode(job)
    if mode != "off":
        screen = job / verify_rules.SCREEN_FILE
        try:
            inputs["screen"] = hashlib.sha256(screen.read_bytes()).hexdigest()
        except FileNotFoundError:
            inputs["screen"] = None
        screen_status = status.get("screen_ocr")
        if (mode == "slides" and isinstance(screen_status, dict)
                and "slide_count" in screen_status):
            inputs["slide_count"] = screen_status["slide_count"]
    inputs["duration_seconds"] = status.get("duration_seconds")
    inputs["expected_lang"] = status.get("gate_lang") or status.get("expected_lang")
    return inputs


def draft_limit_exceeded(status: dict) -> bool:
    drafts = status.get("edit_rounds", 0)
    return type(drafts) is int and drafts > MAX_ORDINARY_DRAFTS


def lock_message(status: dict) -> str:
    if status.get("status") == NEEDS_USER and status.get("reason"):
        return status["reason"]
    return DRAFT_LIMIT_MESSAGE if draft_limit_exceeded(status) else REPAIR_LIMIT_MESSAGE


def repair_lock(status: dict, *, review: bool = False) -> bool:
    repair_rounds = status.get("repair_rounds", 0)
    return (
        status.get("status") in {"not_deposited", NEEDS_USER}
        or (isinstance(repair_rounds, int) and not isinstance(repair_rounds, bool) and repair_rounds > 2
            and not (review and _review_retry(status)))
        or draft_limit_exceeded(status)
    )


def _review_retry(status: dict) -> bool:
    batch = status.get("review")
    return (
        isinstance(batch, dict) and batch.get("result") == "changes"
        and batch.get("failures") == 1
        and type(batch.get("initial_repair_rounds")) is int
        and 0 <= batch["initial_repair_rounds"] <= 2
        and status.get("repair_rounds") == batch["initial_repair_rounds"] + 1
    )


def check_closing_heading_pair(note_bytes: bytes, reading_level: str | None) -> None:
    text = _normalized_note_text(note_bytes)
    body = _FORMAT_FRONTMATTER.sub("", text, count=1)
    delivery, _, _ = verify_rules.delivery_evidence(body)
    headings = [heading for level, heading, _, _ in verify_rules.markdown_headings(delivery) if level == 2]
    expected = knowledge_note.closing_heading_for_level(reading_level)
    recognized = {knowledge_note.PLAIN_ACTION_HEADING, knowledge_note.CONCISE_ACTION_HEADING}
    closing_headings = [heading for heading in headings if heading in recognized]
    if closing_headings != [expected] or headings[-1] != expected:
        raise ValueError(f"note.md closing H2 must be {expected} for this reading level")


def prepare_review_submission(job: Path, *, required: bool = False) -> tuple[bytes, dict] | None:
    """Bind one independent review to its prior two-gate receipt, under the job lock."""
    path = job / "review.md"
    content = path.read_bytes() if path.exists() else b""
    lines = content.splitlines()
    first = lines[0].decode("utf-8-sig", errors="replace") if lines else ""
    if not first.startswith("<!-- tfv-review:"):
        status = read_job_status(job)
        batch = status.get("review")
        if batch is not None and not isinstance(batch, dict):
            raise ValueError("stored review batch in status.json is malformed")
        if required or batch is not None:
            raise ValueError("a Task review.md receipt is required before reading delivery")
        return None
    header = re.fullmatch(r"<!-- tfv-review: (.+) -->", first)
    try:
        receipt = json.loads(header[1]) if header else None
    except ValueError:
        receipt = None
    if (not isinstance(receipt, dict) or not isinstance(receipt.get("inputs"), dict)
            or receipt.get("result") not in ("changes", "clear")):
        raise ValueError("invalid tfv-review receipt")
    reviewer = receipt.get("reviewer", "independent")
    if reviewer not in ("independent", "self"):
        raise ValueError("reviewer must be independent or self")

    status = read_job_status(job)
    if repair_lock(status, review=True):
        raise ValueError(lock_message(status))
    inputs = job_inputs(job)
    batch = status.get("review")
    if batch is None:
        if inputs.get("reading_level") != receipt["inputs"].get("reading_level"):
            raise ValueError("review source evidence changed; the receipt is stale")
        verifier, coverage = status.get("verifier"), status.get("coverage")
        if (not isinstance(verifier, dict) or not isinstance(coverage, dict)
                or verifier.get("allowed") is not True or coverage.get("allowed") is not True
                or verifier.get("inputs") != receipt["inputs"]
                or coverage.get("inputs") != receipt["inputs"]
                or verifier.get("skill_version") != current_skill_version()):
            raise ValueError("review inputs must first pass verify and coverage together")
        batch = {
            "inputs": receipt["inputs"], "result": receipt["result"], "revisions": [],
            "failures": 0, "initial_repair_rounds": status.get("repair_rounds", 0),
            "c04c": verifier.get("c04c", []),
            "c04c_sha256": receipt.get("c04c_sha256"),
            "reviewer": reviewer,
        }
    elif (not isinstance(batch, dict) or batch.get("inputs") != receipt["inputs"]
          or batch.get("result") != receipt["result"] or batch.get("reviewer", "independent") != reviewer):
        raise ValueError("only the original review batch may be processed")

    baseline = batch["inputs"]

    def sources(values: dict) -> dict:
        return {key: value for key, value in values.items()
                if key not in {"note", "note_file", "selection"}}

    if sources(inputs) != sources(baseline):
        raise ValueError("review source evidence changed; the receipt is stale")
    check_closing_heading_pair((job / "note.md").read_bytes(), knowledge_note.read_reading_level(status))
    original = batch.get("c04c", [])
    if receipt.get("c04c_sha256") != batch.get("c04c_sha256"):
        raise ValueError("only the original C04c warning snapshot may be processed")
    decisions = c04c_review.initial(content, original, receipt.get("c04c_sha256"), batch["result"])
    if batch.get("c04c_decisions", decisions) != decisions:
        raise ValueError("initial C04c verdicts changed during this review batch")
    if inputs == baseline:
        c04c_review.final(content, original, decisions, original, (job / "note.md").read_text(encoding="utf-8"))
    batch["c04c_decisions"] = decisions
    if batch["result"] == "clear" and inputs != baseline:
        raise ValueError("a clear review only covers the unchanged reviewed inputs")
    if batch.get("final_inputs") is not None and inputs != batch["final_inputs"]:
        raise ValueError("this review batch is complete; no further review revision is allowed")

    revisions = batch["revisions"]
    previous = revisions[-1] if revisions else baseline
    if inputs != previous:
        if (len(revisions) >= 2 or (revisions and batch["failures"] != 1)
                or inputs in revisions):
            raise ValueError("the review correction allowance is exhausted")
        revisions.append(inputs)
        # The ordinary revision recorder must see this authorized review draft
        # as already registered. No ordinary edit or failure count is removed.
        status["note_digest"] = inputs["note"]
        status["finished"] = False
        status["verifier"] = None
        status["coverage"] = {"allowed": False, "reasons": ["review draft awaits final checks"]}
        if status.get("status") in {"finished", NO_EXTRACTABLE}:
            status["status"] = "transcript_ready"
    status["review"] = batch
    status["review_rounds"] = 1 if batch["result"] == "changes" else 0
    write_job_status(job, status)
    return content, inputs


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
        if rounds > MAX_ORDINARY_DRAFTS:
            stop_for_user(job, data, DRAFT_LIMIT_MESSAGE, job_inputs(job), unchecked=True)
    write_job_status(job, data)
    return data


def _record_failure(data: dict, reasons: list[str], *, review: bool = False) -> bool:
    rounds = data.get("repair_rounds", 0)
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 0:
        rounds = 0
    data["repair_rounds"] = rounds + 1
    data["failure_lines"] = reasons
    if review:
        data["review"]["failures"] += 1
    review_failed = review and data["review"]["failures"] >= 2
    return review_failed or (data["repair_rounds"] > 2 and not (review and _review_retry(data)))


def stop_for_user(job: Path, data: dict, reason: str, inputs: dict | None, *, unchecked: bool = False) -> None:
    data.update(status=NEEDS_USER, finished=False, locked=False, reason=reason,
                next_step="return-draft-and-issues", issues="issues.md")
    checked = (("verify", data.get("verifier")), ("coverage", data.get("coverage")))
    lines = ["# 未通过检查 · 草稿", "", f"稿件：note.md · SHA-256 {(inputs or {}).get('note_file') or '未核对'}",
             f"稿次：{data.get('edit_rounds', 0)} · 失败次数：{data.get('repair_rounds', 0)}", "", reason]
    for gate, entry in checked:
        if unchecked or not isinstance(entry, dict) or entry.get("checked_inputs") != inputs:
            lines.extend(("", f"## {gate} · 未检查"))
            continue
        lines.extend(("", f"## {gate} · " + ("通过" if entry.get("allowed") else "FAIL")))
        lines.extend(f"- {reason}" for reason in entry.get("reasons", []))
    verifier = data.get("verifier") or {}
    if not unchecked and verifier.get("checked_inputs") == inputs and (warnings := verifier.get("c04c")):
        lines.extend(("", "## 待裁定的 C04c WARN"))
        for row in warnings:
            lines.append(f"- {c04c_review.warning(row)}")
            lines.extend(f'  - {quote["time"]} {quote["text"]}' for quote in row["citations"])
    with tempfile.NamedTemporaryFile(dir=job, delete=False) as staged:
        temp = Path(staged.name)
    try:
        temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temp.replace(job / "issues.md")
    finally:
        temp.unlink(missing_ok=True)


def resume_job(job: Path) -> None:
    status = read_job_status(job)
    if status.get("status") not in {NEEDS_USER, "not_deposited"}:
        raise ValueError("only a stopped job can be resumed")
    archive_file(job / "issues.md")
    archive_file(job / "review.md")
    history = list(status.pop("previous_attempts", []))
    root = {key: value for key, value in status.items()
            if key not in {"note_digest", "verifier", "coverage", "review", "review_rounds", "reason",
                           "issues", "failure_lines"}}
    root.update(status="transcript_ready", finished=False, locked=False, next_step="write-note",
                edit_rounds=0, repair_rounds=0, previous_attempts=[*history, status])
    write_job_status(job, root)


def record_gate_result(
    job: Path, gate: str, allowed: bool, reasons: list[str], *, inputs: dict | None = None,
    coverage: dict | None = None, review: bool = False, c04c: list[dict] | None = None,
    review_error: ValueError | None = None, note_inputs: dict | None = None,
) -> dict:
    """Persist a single submission, optionally containing both gate results."""
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
            "checked_inputs": note_inputs or inputs,
            "at": datetime.now(timezone.utc).isoformat(),
            "skill_version": current_skill_version(),
            "inputs": inputs if allowed else None,
            "c04c": c04c or [],
            "c04c_sha256": c04c_review.digest(c04c or []),
            **({"reasons": reasons} if reasons else {}),
        }
        data["coverage"] = {
            "allowed": False, "reasons": ["coverage pending" if allowed else "verify failed"],
        }
    if coverage is not None:
        data["coverage"] = {
            "allowed": coverage["ok"], "reasons": coverage["reasons"], "checked_inputs": note_inputs or inputs,
            "inputs": inputs if coverage["ok"] else None,
        }
        allowed = allowed and coverage["ok"]
        reasons = reasons + coverage["reasons"]
    elif gate == "coverage":
        data["coverage"] = {"allowed": allowed, "reasons": reasons, "checked_inputs": inputs,
                            "inputs": inputs if allowed else None}
    if not allowed:
        if _record_failure(data, reasons, review=review):
            stop_for_user(job, data, REPAIR_LIMIT_MESSAGE, note_inputs or inputs)
    elif (gate == "coverage" or coverage is not None) and inputs is not None:
        verifier = data.get("verifier") or {}
        if (
            verifier.get("allowed") is True
            and verifier.get("inputs") == inputs
            and verifier.get("skill_version") == current_skill_version()
        ):
            pending = bool(review_error) or (not review and bool(verifier.get("c04c")))
            data["finished"] = not pending
            data["status"] = "transcript_ready" if pending else "finished"
            data["note"] = "note.md"
            data["note_stale"] = False
            if pending:
                data["next_step"] = "review"
            data.pop("failure_lines", None)
            if review and not pending:
                data["review"]["final_inputs"] = inputs
            if isinstance(review_error, c04c_review.ConfirmedError):
                batch = data["review"]
                if batch.get("c04c_rejected_inputs") != inputs:
                    batch["c04c_rejected_inputs"] = inputs
                    batch["failures"] += 1
                if batch["failures"] >= 2:
                    stop_for_user(job, data, str(review_error), note_inputs or inputs)
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


def apply_no_extractable(
    job: Path, reason: str, *, coverage_reasons: Sequence[str] = (), review: bool = False,
) -> dict:
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
    data["note"] = None
    data["delivery"] = None
    data["note_stale"] = True
    data["reason"] = reason
    data["next_step"] = "stop"
    data["coverage"] = {"allowed": False, "reasons": [reason, *coverage_reasons]}
    data["verifier"] = {
        "allowed": False,
        "at": datetime.now(timezone.utc).isoformat(),
        "skill_version": current_skill_version(),
        "reasons": [reason],
    }
    _record_failure(data, [reason, *coverage_reasons], review=review)
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
        for line in result.get("warnings", []) + result.get("coverage", {}).get("not_checked", []):
            print(line, file=sys.stderr)
        for label in ("draft", "issues"):
            if result.get(label):
                print(f"{label}: {result[label]}", file=sys.stderr)
    return 0 if result.get("allowed") else 2


def check_job_submission(
    job: Path, *, note_arg: str | None = None, confidence: float | None = None,
    expected_lang: str | None = None, with_coverage: bool = False, reviewed_inputs: dict | None = None,
    review_content: bytes | None = None,
) -> dict:
    """Check and record one submission while the caller holds the job lock."""
    review = reviewed_inputs is not None
    status = read_job_status(job)
    if status.get("status") == SCREEN_PENDING:
        return {"allowed": False, "reasons": [SCREEN_PENDING_MESSAGE]}
    if repair_lock(status, review=review):
        return stopped_result(job, status)

    try:
        prepare_job_note(job)
    except (OSError, RuntimeError) as exc:
        return {"allowed": False, "reasons": [str(exc)]}
    inputs = job_inputs(job)
    if review and inputs != reviewed_inputs:
        return {"allowed": False, "reasons": ["review draft changed before verification; rerun submission"]}
    try:
        note = _read_note(note_arg or str(job / "note.md"))
        if note_arg is not None and inputs["note"] != _note_digest(note):
            note = format_note_text(note)
    except SystemExit as exc:
        note = None
        result = {"allowed": False, "reasons": [str(exc)]}
    canonical_note = note is not None and inputs["note"] == _note_digest(note)
    no_extractable = canonical_note and knowledge_note.all_sections_inapplicable(note)
    if no_extractable:
        result = {"allowed": False, "reasons": [f"C04a FAIL: {knowledge_note.ALL_INAPPLICABLE_REASON}"]}
    elif note is not None:
        status = record_note_revision(job, note)
        if repair_lock(status, review=review):
            return stopped_result(job, status)
        result = verify(
            job / "transcript.txt", note, job=True, confidence=confidence,
            expected_lang=expected_lang or inputs["expected_lang"], job_status=status.get("status"),
        )

    coverage = None
    if with_coverage:
        # Local import: coverage_check uses the standalone job/status helpers above.
        import coverage_check
        coverage = coverage_check.check_job(job)
    changed = (with_coverage or (note is not None and not no_extractable)) and inputs != job_inputs(job)
    if changed:
        result["allowed"] = False
        result["reasons"].append("job files changed during verification; rerun both checks")
        if coverage is not None:
            coverage["ok"] = False
            coverage["reasons"].append("C00 FAIL: job files changed during coverage; rerun both checks")
    review_error = None
    if review_content is not None and result["allowed"] and coverage and coverage["ok"]:
        batch = status["review"]
        try:
            c04c_review.final(review_content, batch.get("c04c", []), batch.get("c04c_decisions", {}),
                              result.get("c04c", []), note)
        except ValueError as exc:
            review_error = exc
    if no_extractable and not changed:
        coverage_reasons = coverage["reasons"] if coverage is not None else []
        status = apply_no_extractable(
            job, knowledge_note.ALL_INAPPLICABLE_REASON, coverage_reasons=coverage_reasons, review=review,
        )
        result.update(status=NO_EXTRACTABLE, note_deleted=True)
    else:
        status = record_gate_result(
            job, "verify", result["allowed"], result["reasons"],
            inputs=inputs if canonical_note else None, coverage=coverage, review=review,
            c04c=result.get("c04c"), review_error=review_error, note_inputs=inputs,
        )
    if coverage is not None:
        coverage["finished"] = status["finished"]
        result["coverage"] = coverage
        result["allowed"] = result["allowed"] and coverage["ok"] and canonical_note and not review_error
        result["allowed"] = bool(result["allowed"])
        result["reasons"].extend(coverage["reasons"])
        result.setdefault("warnings", []).extend(coverage["warnings"])
    if repair_lock(status, review=review) and (note is not None or with_coverage):
        stopped = stopped_result(job, status)
        result["reasons"].extend(stopped.pop("reasons"))
        result.update(stopped)
    if review_error:
        result["reasons"].append(str(review_error))
    return result


def stopped_result(job: Path, status: dict) -> dict:
    result = {"allowed": False, "reasons": [lock_message(status)]}
    if status.get("status") == NEEDS_USER:
        result.update(status=NEEDS_USER, draft=str(job / "note.md"), issues=str(job / "issues.md"))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the single note against its transcript.")
    parser.add_argument("--job", type=Path, help="Job directory containing transcript.txt and note.md")
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--note", help="Note path or - for stdin. Defaults to note.md with --job.")
    parser.add_argument("--expected-lang")
    parser.add_argument("--confidence", type=float)
    parser.add_argument("--with-coverage", action="store_true", help="Run both checks on the canonical job files.")
    parser.add_argument("--structure-only", action="store_true", help="Read-only draft structure preflight.")
    parser.add_argument("--resume", action="store_true", help="Start a new batch on a stopped job by user request.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.structure_only and (args.job is None or args.note is not None or args.transcript is not None
                                or args.with_coverage):
        parser.error("--structure-only requires only the canonical --job files")
    if args.with_coverage and (args.job is None or args.note is not None):
        parser.error("--with-coverage requires --job and does not accept --note")
    if args.resume and not args.with_coverage:
        parser.error("--resume requires --job and --with-coverage")
    if args.job is not None:
        if not args.job.is_dir():
            _emit_verify({"allowed": False, "reasons": [f"job directory does not exist: {args.job}"]}, as_json=args.json)
            return 1
        try:
            if args.structure_only:
                import coverage_check
                knowledge_note.read_reading_level(read_job_status(args.job))
                return _emit_verify(coverage_check.check_structure(args.job), as_json=args.json)
            with job_lock(args.job):
                status = read_job_status(args.job)
                knowledge_note.read_reading_level(status)
                if args.resume:
                    resume_job(args.job)
                    status = read_job_status(args.job)
                receipt = None
                if (args.with_coverage and status.get("status") != SCREEN_PENDING
                        and not repair_lock(status, review=True)):
                    prepare_job_note(args.job)
                    receipt = prepare_review_submission(args.job)
                review_content, reviewed_inputs = receipt if receipt else (None, None)
                result = check_job_submission(
                    args.job, note_arg=args.note, confidence=args.confidence,
                    expected_lang=args.expected_lang, with_coverage=args.with_coverage,
                    reviewed_inputs=reviewed_inputs, review_content=review_content,
                )
        except (OSError, RuntimeError, ValueError) as exc:
            return _emit_verify({"allowed": False, "reasons": [str(exc)]}, as_json=args.json)
        return _emit_verify(result, as_json=args.json)
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
