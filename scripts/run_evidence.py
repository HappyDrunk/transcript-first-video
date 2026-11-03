#!/usr/bin/env python3
"""Run the verifier and host against fixtures, plus a live YouTube attempt.

Writes evals/results/gate-evidence.json and gate-evidence.md.
Paths in those files are repo-relative. A machine path such as /workspace/...
is a failure. Fixture mismatches exit 1. A live fetch that fails is recorded,
not fatal.

--skip-live does not fetch, and it keeps the checked-in live sample when one
is already in gate-evidence.json. The generated_at stamp stays put when the
rest of the report is unchanged, so a second offline run does not dirty git.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
VERIFY = [PY, str(ROOT / "scripts" / "verify_note.py")]
HOST = [PY, str(ROOT / "scripts" / "youtube_host.py")]
XHOST = [PY, str(ROOT / "scripts" / "x_host.py")]
LIVE_URL = "https://www.youtube.com/watch?v=KwhgfwOSToQ"
LIVE_ID = "KwhgfwOSToQ"
EVIDENCE_JSON = ROOT / "evals" / "results" / "gate-evidence.json"
EVIDENCE_MD = ROOT / "evals" / "results" / "gate-evidence.md"
_MACHINE_PATH = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"/(?:workspace|home|Users|tmp|private|var|opt|agent|root)(?:/[^\s\"'`<>|]*)?"
    r"|[A-Za-z]:\\[^\s\"'`<>|]*"
    r")"
)


def relativize_text(text: str) -> str:
    """Rewrite this checkout's absolute prefix to a repo-relative path."""
    root = ROOT.as_posix()
    if root and root in text:
        text = text.replace(root + "/", "")
        text = text.replace(root, ".")
    return text


def relativize_tree(value):
    if isinstance(value, str):
        return relativize_text(value)
    if isinstance(value, list):
        return [relativize_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: relativize_tree(item) for key, item in value.items()}
    return value


def recorded_command(argv: list[str]) -> str:
    """Command line as a reader would type it. No checkout path, no venv path."""
    shown: list[str] = []
    for index, part in enumerate(argv):
        if index == 0:
            name = Path(part).name
            shown.append("python3" if name.startswith("python") else name)
            continue
        shown.append(relativize_text(part) if Path(part).is_absolute() else part)
    return " ".join(shown)


def assert_relative_evidence(text: str, label: str) -> None:
    root = ROOT.as_posix()
    if root and root in text:
        raise SystemExit(f"{label} contains this checkout's path ({root})")
    match = _MACHINE_PATH.search(text)
    if match:
        raise SystemExit(f"{label} contains a machine path ({match.group(0)})")


def load_evidence() -> dict | None:
    if not EVIDENCE_JSON.is_file():
        return None
    try:
        data = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def load_checked_in_live() -> dict | None:
    """Keep a real live sample across --skip-live. A skipped block is not a sample."""
    data = load_evidence()
    if not data:
        return None
    live = data.get("live")
    if not isinstance(live, dict):
        return None
    if live.get("skipped") or live.get("status") == "skipped":
        return None
    return live


def with_stable_stamp(report: dict) -> dict:
    """Reuse generated_at when the report body is unchanged, so CI can git-diff."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    previous = load_evidence()
    if previous:
        prev_body = {key: value for key, value in previous.items() if key != "generated_at"}
        new_body = {key: value for key, value in report.items() if key != "generated_at"}
        if prev_body == new_body and isinstance(previous.get("generated_at"), str):
            stamp = previous["generated_at"]
    report["generated_at"] = stamp
    return report

CASES = [
    {
        "id": "usable-en",
        "eval_id": 1,
        "transcript": "evals/fixtures/usable_en_transcript.txt",
        "note": "evals/fixtures/usable_en_note.md",
        "expected_lang": "en",
        "expect_allowed": True,
        "summary": "Usable English transcript. The note cites it and analyzes it in the four knowledge sections.",
    },
    {
        "id": "empty-asr",
        "eval_id": 2,
        "transcript": "evals/fixtures/empty_transcript.txt",
        "note": "evals/fixtures/empty_finished_note.md",
        "expected_lang": "en",
        "expect_allowed": False,
        "summary": "Empty / music-only transcript with a fluent finished note.",
    },
    {
        "id": "zh-en-loop-launder",
        "eval_id": 3,
        "transcript": "evals/fixtures/en_loop_transcript.txt",
        "note": "evals/fixtures/laundered_essay_note.md",
        "expected_lang": "zh",
        "expect_allowed": False,
        "summary": "Expected Chinese, English loop transcript, laundered ASR essay cites the path.",
    },
    {
        "id": "usable-zh",
        "eval_id": 3,
        "transcript": "evals/fixtures/usable_zh_transcript.txt",
        "note": "evals/fixtures/usable_zh_note.md",
        "expected_lang": "zh",
        "expect_allowed": True,
        "summary": "Usable Chinese transcript. The note cites it and analyzes the repotting method.",
    },
    {
        "id": "clean-en-expected-zh",
        "eval_id": 3,
        "transcript": "evals/fixtures/usable_en_transcript.txt",
        "note": "evals/fixtures/usable_en_note.md",
        "expected_lang": "zh",
        "expect_allowed": False,
        "summary": "Fluent English is still a ratio fail when Chinese is expected.",
    },
    {
        "id": "gibberish",
        "eval_id": None,
        "transcript": "evals/fixtures/gibberish_transcript.txt",
        "note": "evals/fixtures/gibberish_note.md",
        "expected_lang": "en",
        "expect_allowed": False,
        "summary": "Consonant gibberish with a fluent deposit note.",
    },
    {
        "id": "missing-path",
        "eval_id": None,
        "transcript": "evals/fixtures/does_not_exist.txt",
        "note": "evals/fixtures/laundered_essay_note.md",
        "expected_lang": "zh",
        "expect_allowed": False,
        "summary": "Essay cites a transcript path that is not on disk.",
    },
    {
        "id": "missing-citation",
        "eval_id": 1,
        "transcript": "evals/fixtures/usable_en_transcript.txt",
        "note": "evals/fixtures/uncited_note.md",
        "expected_lang": "en",
        "expect_allowed": False,
        "summary": "Usable transcript, note never names the file.",
    },
    {
        "id": "path-only",
        "eval_id": 1,
        "transcript": "evals/fixtures/usable_en_transcript.txt",
        "note": "evals/fixtures/path_only_note.md",
        "expected_lang": "en",
        "expect_allowed": False,
        "summary": "Usable transcript. The note pastes the path and a title, and does not quote the transcript.",
    },
    {
        "id": "quote-stub",
        "eval_id": 1,
        "transcript": "evals/fixtures/usable_en_transcript.txt",
        "note": "evals/fixtures/quote_stub_note.md",
        "expected_lang": "en",
        "expect_allowed": False,
        "summary": "Usable transcript. The note has frontmatter and a real quote, and no knowledge sections.",
    },
    {
        "id": "boilerplate-sections",
        "eval_id": 1,
        "transcript": "evals/fixtures/usable_en_transcript.txt",
        "note": "evals/fixtures/boilerplate_note.md",
        "expected_lang": "en",
        "expect_allowed": False,
        "summary": "Four section headings and real quotes, with the same quote-stub sentence in each.",
    },
]


def naive_would_deposit(note: str) -> bool:
    letters = sum(1 for char in note if char.isalpha())
    return letters >= 40


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)


def parse_json(blob: str) -> dict:
    start = blob.find("{")
    end = blob.rfind("}")
    if start < 0 or end < start:
        raise ValueError(blob[:500])
    return json.loads(blob[start : end + 1])


def verifier_case(case: dict) -> dict:
    cmd = [
        *VERIFY,
        "--transcript",
        case["transcript"],
        "--note",
        case["note"],
        "--expected-lang",
        case["expected_lang"],
        "--json",
    ]
    completed = run(cmd)
    try:
        payload = parse_json(completed.stdout)
    except ValueError:
        payload = {"allowed": False, "reasons": [completed.stderr.strip() or completed.stdout.strip()]}
    note_text = (ROOT / case["note"]).read_text(encoding="utf-8")
    allowed = bool(payload.get("allowed"))
    return {
        **case,
        "command": recorded_command(cmd),
        "exit_code": completed.returncode,
        "allowed": allowed,
        "reasons": payload.get("reasons") or [],
        "naive_would_deposit": naive_would_deposit(note_text),
        "matched": allowed is case["expect_allowed"] and (completed.returncode == 0) is case["expect_allowed"],
    }


def host_settle(video_id: str, transcript: str, expected_lang: str, out: Path) -> dict:
    cmd = [
        *HOST,
        "--settle-transcript",
        transcript,
        "--video-id",
        video_id,
        "--expected-lang",
        expected_lang,
        "--out",
        str(out),
        "--json",
    ]
    completed = run(cmd)
    payload = parse_json(completed.stdout)
    job = out / f"youtube_{video_id}"
    return {
        "video_id": video_id,
        "exit_code": completed.returncode,
        "status": payload.get("status"),
        "finished": payload.get("finished"),
        "reason": payload.get("reason"),
        "next_step": payload.get("next_step"),
        "note_exists": (job / "note.md").is_file(),
        "transcript_exists": (job / "transcript.txt").is_file(),
        "verifier": payload.get("verifier"),
    }


def x_host_settle(status_id: str, transcript: str, expected_lang: str, out: Path) -> dict:
    cmd = [
        *XHOST,
        "--settle-transcript",
        transcript,
        "--status-id",
        status_id,
        "--expected-lang",
        expected_lang,
        "--out",
        str(out),
        "--json",
    ]
    completed = run(cmd)
    payload = parse_json(completed.stdout)
    job = out / f"x_{status_id}"
    return {
        "id": "x-usable",
        "video_id": status_id,
        "exit_code": completed.returncode,
        "status": payload.get("status"),
        "finished": payload.get("finished"),
        "reason": payload.get("reason"),
        "next_step": payload.get("next_step"),
        "note_exists": (job / "note.md").is_file(),
        "transcript_exists": (job / "transcript.txt").is_file(),
        "verifier": payload.get("verifier"),
    }


def host_cases() -> list[dict]:
    results = []
    with tempfile.TemporaryDirectory(prefix="tfv-evidence-") as tmp:
        out = Path(tmp)
        usable = host_settle("usable-en", "evals/fixtures/usable_en_transcript.txt", "en", out)
        usable["expect"] = "finished deposit, verifier allows"
        results.append(usable)
        stale = host_settle("usable-en", "evals/fixtures/empty_transcript.txt", "en", out)
        stale["id"] = "stale-deposit-removed"
        stale["expect"] = "rerun with empty text deletes the previous note and transcript"
        results.append(stale)
        empty = host_settle("empty-asr", "evals/fixtures/empty_transcript.txt", "en", out)
        empty["expect"] = "empty transcript writes status only"
        results.append(empty)
        loop = host_settle("zh-loop", "evals/fixtures/en_loop_transcript.txt", "zh", out)
        loop["expect"] = "expected Chinese plus English loop writes status only"
        results.append(loop)
        x_usable = x_host_settle(
            "123456789012345678",
            "evals/fixtures/usable_en_transcript.txt",
            "en",
            out,
        )
        x_usable["expect"] = "x_host settle uses the same gate and writes a knowledge note"
        results.append(x_usable)
    return results


def live_case() -> dict:
    """Refetch the one URL this script records. Leave sibling receipts in place."""
    job = ROOT / "evals" / "results" / "live" / f"youtube_{LIVE_ID}"
    if job.exists():
        for path in job.rglob("*"):
            if path.is_file():
                path.unlink()
    cmd = [*HOST, LIVE_URL, "--out", "evals/results/live", "--json"]
    completed = run(cmd)
    record: dict = {
        "url": LIVE_URL,
        "video_id": LIVE_ID,
        "substitute": None,
        "command": "python3 scripts/youtube_host.py " + LIVE_URL + " --out evals/results/live --json",
        "exit_code": completed.returncode,
    }
    try:
        payload = parse_json(completed.stdout)
    except ValueError:
        record["status"] = "not_finished"
        record["reason"] = (completed.stderr or completed.stdout)[:500]
        return record
    record.update(
        {
            "status": payload.get("status"),
            "finished": payload.get("finished"),
            "reason": payload.get("reason"),
            "next_step": payload.get("next_step"),
            "acquisition": payload.get("acquisition"),
            "caption_language": payload.get("caption_language"),
            "caption_kind": payload.get("caption_kind"),
            "mirror_host": payload.get("mirror_host"),
            "attempts": payload.get("attempts"),
            "gate": (payload.get("gate") or {}).get("metrics"),
            "gate_passed": (payload.get("gate") or {}).get("passed"),
            "verifier": payload.get("verifier"),
            "transcript": payload.get("transcript"),
            "note": payload.get("note"),
        }
    )
    transcript = payload.get("transcript")
    if transcript and (ROOT / transcript).is_file():
        text = (ROOT / transcript).read_text(encoding="utf-8")
        record["transcript_chars"] = len(text)
        record["excerpt"] = text.strip().replace("\n", " ")[:240]
    return record


def markdown(report: dict) -> str:
    lines = [
        "# Gate evidence",
        "",
        f"Generated {report['generated_at']} by `python3 scripts/run_evidence.py`.",
        "",
        "Two bars, both required. (A) No note without a usable transcript: the file has to exist and pass the quality gate. (B) A finished note has to analyze that transcript into reusable knowledge. The four sections are 问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步, and each one quotes a 40-character window of the transcript. A path, a status, or a quote with no analysis is refused.",
        "",
        "This table is that mechanical check. It does not listen to the audio, so a fluent wrong caption can still pass. It does not send the note to a model, and it does not score how good a summary is. Those readings are evals/results/spotcheck.md, which CI does not score.",
        "",
        "## Verifier",
        "",
        "| case | eval | naive deposit | gate | exit |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for case in report["verifier"]:
        naive = "would allow" if case["naive_would_deposit"] else "would refuse"
        gate = "allow" if case["allowed"] else "refuse"
        eval_id = case["eval_id"] if case["eval_id"] is not None else ""
        lines.append(f"| `{case['id']}` | {eval_id} | {naive} | {gate} | {case['exit_code']} |")
    lines.extend(["", "Reasons:", ""])
    for case in report["verifier"]:
        why = (
            "; ".join(case["reasons"])
            if case["reasons"]
            else "cites a usable transcript, quotes it in each knowledge section, and the analysis is not a stub"
        )
        lines.append(f"- `{case['id']}`: {why}")
    lines.extend(
        [
            "",
            "## Host deposit behavior",
            "",
            "YouTube rows call `youtube_host.py --settle-transcript`. The `x-usable` row calls `x_host.py --settle-transcript`. No network. Both still run the gate and do not pretend a fetch happened.",
            "",
            "| video id | status | note written | transcript written | exit | expect |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    for case in report["host_settle"]:
        lines.append(
            f"| `{case.get('id') or case['video_id']}` | {case['status']} | {str(case['note_exists']).lower()} | "
            f"{str(case['transcript_exists']).lower()} | {case['exit_code']} | {case.get('expect', '')} |"
        )
    live = report["live"]
    lines.extend(["", "## Live YouTube", ""])
    lines.append(
        "Other committed public-URL receipts are listed in `evals/results/live/README.md`. "
        "This section records only the one URL this script fetches."
    )
    lines.append("")
    if live.get("skipped"):
        lines.append("Skipped (`--skip-live`). Offline fixture checks do not use the network.")
        lines.append("")
        lines.append(
            "An X/Twitter live fetch is not part of this file. "
            "`scripts/x_host.py` is covered by the offline settle row above and by any receipt under `evals/results/live/`."
        )
        lines.append("")
        return "\n".join(lines)
    lines.append(f"URL: `{live['url']}`. Substitute: {live['substitute'] or 'none; this is eval id 1'}.")
    lines.append("")
    lines.append(f"Command: `{live['command']}`.")
    lines.append("")
    if live.get("finished"):
        lines.append(
            f"Result: finished via `{live.get('acquisition')}` "
            f"({live.get('caption_language')} {live.get('caption_kind')}). "
            f"Verifier allowed: {(live.get('verifier') or {}).get('allowed')}. "
            f"Transcript characters: {live.get('transcript_chars')}."
        )
        lines.append("")
        if live.get("acquisition") == "caption-mirror":
            lines.append(
                "yt-dlp did not return captions. The text came from the public mirror fallback. "
                "The note analyzes the transcript into the four knowledge sections and quotes each one. "
                "The note title is the job id. The platform title and description are not stored. "
                "Passing this check is not a claim that the captions match the audio."
            )
        elif live.get("acquisition") == "yt-dlp":
            lines.append(
                "Captions came from yt-dlp. The note analyzes the transcript into the four knowledge sections and quotes each one. "
                "The note title is the job id. The platform title and description are not stored. "
                "Passing this check is not a claim that the captions match the audio."
            )
        else:
            lines.append(
                f"Acquisition was `{live.get('acquisition')}`. The note analyzes the transcript into the four knowledge sections and quotes each one. "
                "The note title is the job id. The platform title and description are not stored. "
                "Passing this check is not a claim that the captions match the audio."
            )
        lines.append("")
        if live.get("excerpt"):
            lines.append("Excerpt:")
            lines.append("")
            lines.append(f"> {live['excerpt']}")
    else:
        lines.append(f"Result: {live.get('status')} (exit {live.get('exit_code')}).")
        lines.append("")
        lines.append(live.get("reason") or "no reason recorded")
    lines.append("")
    lines.append(
        "X/Twitter live fetch is not part of this run. The `x-usable` settle row covers that host offline."
    )
    lines.extend(["", "Attempts:", ""])
    for attempt in live.get("attempts") or []:
        flag = "ok" if attempt.get("ok") else "failed"
        detail = attempt.get("detail") or ""
        if len(detail) > 240:
            detail = detail[:240].rstrip() + "…"
        lines.append(f"- {attempt.get('source')}: {flag}. {detail}")
    lines.append("")
    return "\n".join(lines)


def host_settle_ok(cases: list[dict]) -> bool:
    by_id = {case.get("id") or case["video_id"]: case for case in cases}
    checks = {
        "usable-en": lambda case: case["finished"] is True and case["note_exists"] is True,
        "stale-deposit-removed": lambda case: case["note_exists"] is False and case["transcript_exists"] is False,
        "empty-asr": lambda case: case["finished"] is False and case["note_exists"] is False,
        "zh-loop": lambda case: case["status"] == "quality_gate_failed" and case["note_exists"] is False,
        "x-usable": lambda case: case["finished"] is True and case["note_exists"] is True and case["exit_code"] == 0,
    }
    return all(key in by_id and check(by_id[key]) for key, check in checks.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate gate evidence. Live YouTube is optional.")
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help=(
            "Do not fetch YouTube. Fixture and settle checks still run and still fail the "
            "process on mismatch. A checked-in live sample in gate-evidence.json is kept."
        ),
    )
    args = parser.parse_args(argv)
    verifier = [verifier_case(case) for case in CASES]
    host = host_cases()
    if args.skip_live:
        # Preserve the committed live sample so offline CI can git-diff the file.
        # A checkout with no real sample records an explicit skip.
        live = load_checked_in_live()
        if live is None:
            live = {
                "skipped": True,
                "url": LIVE_URL,
                "video_id": LIVE_ID,
                "substitute": None,
                "status": "skipped",
                "finished": False,
                "reason": "live fetch skipped (--skip-live)",
                "command": "python3 scripts/run_evidence.py --skip-live",
                "exit_code": None,
                "attempts": [],
            }
    else:
        live = live_case()
    mismatches = [case["id"] for case in verifier if not case["matched"]]
    host_ok = host_settle_ok(host)
    report = with_stable_stamp(
        relativize_tree(
            {
                "schema_version": 1,
                "generated_at": "",
                "verifier": verifier,
                "host_settle": host,
                "live": live,
                "fixture_mismatches": mismatches,
                "host_settle_ok": host_ok,
            }
        )
    )
    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    md_text = markdown(report)
    if not md_text.endswith("\n"):
        md_text += "\n"
    assert_relative_evidence(json_text, "evals/results/gate-evidence.json")
    assert_relative_evidence(md_text, "evals/results/gate-evidence.md")
    EVIDENCE_JSON.write_text(json_text, encoding="utf-8")
    EVIDENCE_MD.write_text(md_text, encoding="utf-8")
    print("wrote evals/results/gate-evidence.md")
    print(f"fixture mismatches: {mismatches or 'none'}")
    print(f"host settle ok: {host_ok}")
    print(f"live status: {live.get('status')} acquisition={live.get('acquisition')}")
    if mismatches or not host_ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
