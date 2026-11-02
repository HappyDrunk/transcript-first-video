#!/usr/bin/env python3
"""Run the verifier and host against fixtures, plus a live YouTube attempt.

Writes evals/results/gate-evidence.json and gate-evidence.md.
Fixture mismatches exit 1. A live fetch that fails is recorded, not fatal.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
VERIFY = [PY, str(ROOT / "scripts" / "verify_note.py")]
HOST = [PY, str(ROOT / "scripts" / "youtube_host.py")]
LIVE_URL = "https://www.youtube.com/watch?v=KwhgfwOSToQ"
LIVE_ID = "KwhgfwOSToQ"

CASES = [
    {
        "id": "usable-en",
        "eval_id": 1,
        "transcript": "evals/fixtures/usable_en_transcript.txt",
        "note": "evals/fixtures/usable_en_note.md",
        "expected_lang": "en",
        "expect_allowed": True,
        "summary": "Usable English transcript, note cites the path.",
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
        "summary": "Usable Chinese transcript passes the same language gate.",
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
        "command": " ".join(cmd[1:]),
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
    return results


def live_case() -> dict:
    out = ROOT / "evals" / "results" / "live"
    if out.exists():
        for path in out.rglob("*"):
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
        "Without a gate, a fluent note looks depositable (40 or more letters). With the gate, a note is allowed only when it cites a transcript file that passes the quality gate.",
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
        why = "; ".join(case["reasons"]) if case["reasons"] else "cites a transcript that passed the gate"
        lines.append(f"- `{case['id']}`: {why}")
    lines.extend(
        [
            "",
            "## Host deposit behavior",
            "",
            "These rows call `youtube_host.py --settle-transcript` (no network). That path still runs the gate and does not pretend a fetch happened.",
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
                "The note cites the transcript path. Title and description are not stored."
            )
        elif live.get("acquisition") == "yt-dlp":
            lines.append("Captions came from yt-dlp. The note cites the transcript path.")
        else:
            lines.append(f"Acquisition was `{live.get('acquisition')}`. The note cites the transcript path.")
        lines.append("")
        if live.get("excerpt"):
            lines.append("Excerpt:")
            lines.append("")
            lines.append(f"> {live['excerpt']}")
    else:
        lines.append(f"Result: {live.get('status')} (exit {live.get('exit_code')}).")
        lines.append("")
        lines.append(live.get("reason") or "no reason recorded")
    lines.extend(["", "Attempts:", ""])
    for attempt in live.get("attempts") or []:
        flag = "ok" if attempt.get("ok") else "failed"
        detail = attempt.get("detail") or ""
        if len(detail) > 240:
            detail = detail[:240].rstrip() + "…"
        lines.append(f"- {attempt.get('source')}: {flag}. {detail}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    verifier = [verifier_case(case) for case in CASES]
    host = host_cases()
    live = live_case()
    mismatches = [case["id"] for case in verifier if not case["matched"]]
    host_ok = (
        host[0]["finished"] is True
        and host[0]["note_exists"] is True
        and host[1]["note_exists"] is False
        and host[1]["transcript_exists"] is False
        and host[2]["finished"] is False
        and host[2]["note_exists"] is False
        and host[3]["status"] == "quality_gate_failed"
        and host[3]["note_exists"] is False
    )
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verifier": verifier,
        "host_settle": host,
        "live": live,
        "fixture_mismatches": mismatches,
        "host_settle_ok": host_ok,
    }
    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "gate-evidence.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "gate-evidence.md").write_text(markdown(report), encoding="utf-8")
    print(f"wrote {out_dir / 'gate-evidence.md'}")
    print(f"fixture mismatches: {mismatches or 'none'}")
    print(f"host settle ok: {host_ok}")
    print(f"live status: {live.get('status')} acquisition={live.get('acquisition')}")
    if mismatches or not host_ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
