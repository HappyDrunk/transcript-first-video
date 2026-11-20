"""Bind a reviewer's C04c decisions to the exact claims and cited evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from verify_rules import canonical_numbers, delivery_evidence, prose_without_times

HEADING = "## C04c 告警裁定"
HINT = "所链引文里没有这个词或数：补挂出处，或改正文"
ID = r"C04c-\d{3,}"


def digest(findings: list[dict]) -> str:
    content = json.dumps(findings, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def warning(row: dict) -> str:
    values = ", ".join(value for quote in row["citations"] for value in quote["values"])
    sources = ", ".join(f'{quote["time"]}#{quote["source_line"]}' if quote["screen"] else quote["time"]
                        for quote in row["citations"])
    return (f'{row["id"]} WARN | {row["section"]} L{row["line"]} | 正文={row["term"]!r} '
            f'| 引文数值=[{values}] | 引文={sources or "无"} | {HINT}')


def _section(content: bytes) -> list[str] | None:
    text = "\n".join(content.decode("utf-8-sig").splitlines())
    parts = re.split(rf"(?m)^{HEADING}[ \t]*$", text)
    if len(parts) > 2:
        raise ValueError("duplicate C04c 告警裁定 section")
    if len(parts) == 1:
        return None
    section = re.split(r"(?m)^#{1,2}[ \t]+", parts[1], maxsplit=1)[0]
    return [line.strip() for line in section.splitlines() if line.strip()]


def _row(line: str, findings: dict, seen: dict) -> None:
    if not line.startswith("- "):
        raise ValueError("C04c decisions must be one bullet per warning")
    parts = [part.strip().replace(r"\|", "|") for part in re.split(r"(?<!\\)\|", line[2:])]
    if len(parts) != 4:
        raise ValueError("C04c decision needs ID | hit | linked excerpt | 真错 or 误报")
    key, term, fragment, result = parts
    row = findings.get(key)
    if row is None or key in seen:
        raise ValueError(f"unknown or duplicate C04c warning ID: {key}")
    if term != row["term"] or term not in row["claim"]:
        raise ValueError(f"{key}: the hit must match the located claim")
    fragment = " ".join(fragment.split())
    cites = [quote for quote in row["citations"] if fragment and fragment in " ".join(quote["text"].split())]
    if not cites:
        raise ValueError(f"{key}: excerpt is not part of a linked quote")
    if row["kind"] == "number" and not any(canonical_numbers(fragment, screen=q["screen"])[1] for q in cites):
        raise ValueError(f"{key}: excerpt has no numeric value")
    if result not in {"真错", "误报"}:
        raise ValueError(f"{key}: decision must be 真错 or 误报")
    seen[key] = result


def initial(content: bytes, findings: list[dict], bound: str | None, result: str) -> dict:
    lines = _section(content)
    if not findings and bound is None and lines is None:
        return {}
    if bound != digest(findings) or lines is None:
        raise ValueError("C04c warning snapshot or decision section is missing or stale")
    rows = {row["id"]: row for row in findings}
    verdicts = {}
    for line in lines:
        if line == "无" or line.startswith(("- 已修 ", "- 终稿 ", "<!-- tfv-c04c-final:")):
            continue
        missing = re.fullmatch(rf"- 待补 ({ID})", line)
        if missing:
            key = missing[1]
            row = rows.get(key)
            if (row is None or key in verdicts or row["kind"] != "number"
                    or any(quote["values"] for quote in row["citations"])):
                raise ValueError(f"{key}: 待补 requires a numeric warning without linked values")
            verdicts[key] = "待补"
        else:
            _row(line, rows, verdicts)
    if set(verdicts) != set(rows) or (not rows and "无" not in lines) or (rows and "无" in lines):
        missing = ", ".join(sorted(set(rows) - set(verdicts)))
        raise ValueError(f"C04c decisions must cover all warning IDs: {missing}")
    if result == "clear" and any(verdict != "误报" for verdict in verdicts.values()):
        raise ValueError("C04c true or unsupported findings need a changes review")
    return verdicts


def _identity(row: dict) -> tuple:
    return (row["section"], row["claim"], row["kind"], row["term"], row["offset"],
            json.dumps(row["citations"], sort_keys=True))


class ConfirmedError(ValueError):
    """A bound follow-up has identified a true error in the current draft."""


def final(content: bytes, original: list[dict], verdicts: dict,
          current: list[dict], note: str) -> None:
    original_by_id = {row["id"]: row for row in original}
    carried = Counter(_identity(row) for row in original if verdicts[row["id"]] == "误报")
    remaining = {}
    for row in current:
        identity = _identity(row)
        if carried[identity]:
            carried[identity] -= 1
        else:
            remaining[row["id"]] = row
    needed = {key for key, verdict in verdicts.items() if verdict != "误报"}
    unresolved = {_identity(original_by_id[key]) for key in needed}
    body = " ".join(prose_without_times(delivery_evidence(note)[0]).split())
    confirmed, final_verdicts = set(), {}
    final_digest = None
    for line in _section(content) or ():
        if mark := re.fullmatch(r"<!-- tfv-c04c-final: ([0-9a-f]{64}) -->", line):
            if final_digest is not None:
                raise ValueError("duplicate final C04c warning signature")
            final_digest = mark[1]
        elif change := re.fullmatch(rf"- 已修 ({ID}) \| (.+)", line):
            key, anchor = change.groups()
            if key not in needed or key in confirmed:
                raise ValueError(f"{key}: unknown or duplicate correction confirmation")
            old = " ".join(prose_without_times(original_by_id[key]["claim"]).split())
            if (anchor == "已删除" and old in body) or (anchor != "已删除" and " ".join(anchor.split()) not in body):
                raise ValueError(f"{key}: confirmed change cannot be located in the current note")
            confirmed.add(key)
        elif line.startswith("- 终稿 "):
            _row("- " + line.removeprefix("- 终稿 "), remaining, final_verdicts)
    if set(final_verdicts) != set(remaining):
        raise ValueError("uncleared C04c warnings need decisions on the current draft")
    if remaining and final_digest != digest(current):
        raise ValueError("final C04c warning snapshot is missing or stale")
    if any(verdict == "误报" and _identity(remaining[key]) in unresolved
           for key, verdict in final_verdicts.items()):
        raise ValueError("an unresolved C04c finding remains in the current note")
    if any(value == "真错" for value in final_verdicts.values()):
        raise ConfirmedError("the C04c follow-up found a true error in this review draft")
    if confirmed != needed:
        raise ValueError("C04c true or unsupported warnings need confirmed corrections")
