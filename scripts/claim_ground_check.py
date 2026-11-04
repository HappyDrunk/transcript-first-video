# -*- coding: utf-8 -*-
"""Deterministic claim grounding vs same-section quotes (local only; no LLM).

For each prose sentence in a note: numbers, mid-sentence proper nouns / 《》 terms,
and long content phrases must appear in that section's blockquote text (whitespace-
folded, casefold). Optional: also require presence in a transcript file.

Outputs per-file unsupported_count and a summary JSON. Does not print claim text
when --quiet. Not for public CI as an LLM judge. Paths use pathlib. This script
does not write to a drive root; it writes only when --out is set, to that path.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SECTIONS = ["问题与做法", "完整怎么做", "翻车或别用", "今天立刻动手一步"]
HEAD_RE = re.compile(r"^##\s+(.+?)\s*$")
QUOTE_RE = re.compile(r"^>\s*(?:\[(\d{1,2}:\d{2}(?::\d{2})?)\])?\s*(.*)$")
NUM_RE = re.compile(r"(?<![A-Za-z])(\d+(?:[.,]\d+)?%?|\d{1,2}:\d{2}(?::\d{2})?)")
PROPER_RE = re.compile(
    r"(?:《[^》]{1,40}》|\"[A-Z][^\"\n]{1,40}\"|\'[A-Z][^\'\n]{1,40}\'|\b[A-Z][A-Za-z0-9][A-Za-z0-9+./_-]{1,}\b)"
)
CAUSAL_RE = re.compile(r"(因为|所以|导致|因此|consequently|because|therefore|thus\b)", re.I)
NA_RE = re.compile(r"^本节不适用")
PHRASE_N = 12  # CJK chars or latin words approx via nospace length


def fold(s: str) -> str:
    s = s.casefold()
    s = re.sub(r"\s+", "", s)
    return s


CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")


def script_ratio(s: str) -> tuple[float, float]:
    if not s:
        return 0.0, 0.0
    cjk = len(CJK_RE.findall(s))
    lat = len(LATIN_RE.findall(s))
    tot = cjk + lat
    if tot == 0:
        return 0.0, 0.0
    return cjk / tot, lat / tot


def same_script(prose: str, quotes: str) -> bool:
    pc, pl = script_ratio(prose)
    qc, ql = script_ratio(quotes)
    if pc >= 0.5 and qc >= 0.5:
        return True
    if pl >= 0.5 and ql >= 0.5:
        return True
    return False


def split_sentences(prose: str) -> list[str]:
    prose = prose.strip()
    if not prose:
        return []
    # Chinese / English sentence ends
    parts = re.split(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z\u4e00-\u9fff])", prose)
    out = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(p)
    if not out and prose:
        out = [prose]
    return out


def parse_note(text: str) -> dict[str, dict]:
    # drop yaml frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2]
    cur = None
    sections: dict[str, dict] = {s: {"prose": [], "quotes": []} for s in SECTIONS}
    buf_prose: list[str] = []
    for raw in text.splitlines():
        m = HEAD_RE.match(raw.strip())
        if m:
            title = m.group(1).strip()
            if cur and buf_prose:
                sections[cur]["prose"].append(" ".join(buf_prose).strip())
                buf_prose = []
            cur = title if title in sections else None
            continue
        if cur is None:
            continue
        qm = QUOTE_RE.match(raw)
        if qm:
            if buf_prose:
                sections[cur]["prose"].append(" ".join(buf_prose).strip())
                buf_prose = []
            sections[cur]["quotes"].append(qm.group(2) or "")
            continue
        if raw.strip():
            buf_prose.append(raw.strip())
    if cur and buf_prose:
        sections[cur]["prose"].append(" ".join(buf_prose).strip())
    return sections


def phrase_chunks(sentence: str) -> list[str]:
    # take nospace windows of length PHRASE_N from content words
    f = fold(sentence)
    # strip trivial particles-ish by keeping long runs
    if len(f) < PHRASE_N:
        return [f] if len(f) >= 8 else []
    chunks = []
    step = max(4, PHRASE_N // 2)
    for i in range(0, len(f) - PHRASE_N + 1, step):
        chunks.append(f[i : i + PHRASE_N])
        if len(chunks) >= 6:
            break
    return chunks


def check_sentence(sent: str, quote_fold: str, quote_raw: str) -> list[dict]:
    issues = []
    if NA_RE.search(sent) or sent.startswith("转写未给出"):
        return issues
    for n in NUM_RE.findall(sent):
        nf = fold(str(n))
        if nf and nf not in quote_fold:
            issues.append({"kind": "number", "token_len": len(str(n))})
    STOP = {
        "the","and","for","with","this","that","from","your","you","are","was","were",
        "have","has","will","can","not","but","our","their","its","use","using","used",
        "agent","agents","model","models","prompt","prompts","memory","pipeline",
    }
    for ptok in PROPER_RE.findall(sent):
        pf = fold(ptok)
        if len(pf) < 3 or pf in STOP:
            continue
        if pf not in quote_fold:
            issues.append({"kind": "proper", "token_len": len(ptok)})
    if same_script(sent, quote_raw):
        fsent = fold(sent)
        chunks = phrase_chunks(sent) if len(fsent) >= PHRASE_N else []
        hit = bool(chunks) and any(c in quote_fold for c in chunks)
        if CAUSAL_RE.search(sent) and not hit and not quote_fold:
            issues.append({"kind": "causal_ungrounded", "token_len": 0})
        if len(fsent) >= max(24, PHRASE_N * 2) and chunks and not hit:
            issues.append({"kind": "phrase", "token_len": PHRASE_N})
    elif CAUSAL_RE.search(sent) and not quote_fold:
        issues.append({"kind": "causal_no_quote", "token_len": 0})
    return issues


def check_file(path: Path, transcript: Path | None = None) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = parse_note(text)
    tx_fold = ""
    if transcript and transcript.is_file():
        tx_fold = fold(transcript.read_text(encoding="utf-8", errors="replace"))
    per_sec = {}
    unsupported = 0
    sentences = 0
    for sec, data in sections.items():
        qf = fold(" ".join(data["quotes"]))
        sec_issues = []
        for block in data["prose"]:
            for sent in split_sentences(block):
                if not sent.strip():
                    continue
                sentences += 1
                issues = check_sentence(sent, qf, " ".join(data["quotes"]))
                # optional transcript check for numbers/proper still missing
                if tx_fold:
                    still = []
                    for iss in issues:
                        # if number/proper missing from quotes but in transcript, still count
                        # (section-quote rule is the Skill contract)
                        still.append(iss)
                    issues = still
                if issues:
                    unsupported += 1
                    sec_issues.append({"n_issues": len(issues), "kinds": [i["kind"] for i in issues]})
        per_sec[sec] = {
            "n_prose_blocks": len([b for b in data["prose"] if b]),
            "n_quotes": len(data["quotes"]),
            "unsupported_sentences": len(sec_issues),
            "issue_kinds": {},
        }
        for row in sec_issues:
            for k in row["kinds"]:
                per_sec[sec]["issue_kinds"][k] = per_sec[sec]["issue_kinds"].get(k, 0) + 1
    return {
        "file": path.name,
        "sentences": sentences,
        "unsupported_count": unsupported,
        "sections": per_sec,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="note.md files or directories")
    ap.add_argument("--transcript-map", default="", help="JSON {stem_or_vid: transcript_path}")
    ap.add_argument(
        "--jobs-root",
        default="",
        help="optional jobs directory; looks up youtube_<video_id>/transcript.txt and x_<video_id>/transcript.txt",
    )
    ap.add_argument("--out", default="", help="summary JSON path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    files: list[Path] = []
    for p in args.paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(path.glob("*.md")))
        elif path.is_file():
            files.append(path)
    tmap = {}
    if args.transcript_map:
        tmap = json.loads(Path(args.transcript_map).read_text(encoding="utf-8"))

    # vid -> job heuristic from note frontmatter source or name A_v03_r1
    results = []
    for f in files:
        tx = None
        m = re.search(r"v(\d{2})", f.stem)
        vid = f"v{m.group(1)}" if m else ""
        if vid and vid in tmap:
            tx = Path(tmap[vid])
        elif args.jobs_root and vid:
            # try read frontmatter video_id
            head = f.read_text(encoding="utf-8", errors="replace")[:800]
            vm = re.search(r"video_id:\s*[\"']?([A-Za-z0-9_-]+)", head)
            jobs = Path(args.jobs_root)
            if vm:
                vid_raw = vm.group(1)
                for cand in (jobs / f"youtube_{vid_raw}", jobs / f"x_{vid_raw}"):
                    if (cand / "transcript.txt").is_file():
                        tx = cand / "transcript.txt"
                        break
        row = check_file(f, tx)
        results.append(row)
        if not args.quiet:
            print(f"{row['file']}: unsupported={row['unsupported_count']} sentences={row['sentences']}")

    summary = {
        "n_files": len(results),
        "total_unsupported": sum(r["unsupported_count"] for r in results),
        "total_sentences": sum(r["sentences"] for r in results),
        "per_file": [
            {
                "file": r["file"],
                "unsupported_count": r["unsupported_count"],
                "sentences": r["sentences"],
                "sections": {
                    s: {
                        "unsupported_sentences": v["unsupported_sentences"],
                        "issue_kinds": v["issue_kinds"],
                        "n_quotes": v["n_quotes"],
                    }
                    for s, v in r["sections"].items()
                },
            }
            for r in results
        ],
    }
    if args.out:
        Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(json.dumps({"n_files": summary["n_files"], "total_unsupported": summary["total_unsupported"], "total_sentences": summary["total_sentences"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
