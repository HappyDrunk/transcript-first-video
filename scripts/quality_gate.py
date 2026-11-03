#!/usr/bin/env python3
"""Quality gate for a transcript. Universal garbage checks, plus a script
check when the expected language is known.

Exit 0 when the transcript is usable speech. Exit 2 when it is not.
A passing transcript is still not a note: pair this with verify_note.py.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

MIN_SPEECH_CHARS = 20
# Expected-Chinese script check. A real Chinese talk dense with English
# technical terms can fall under ZH_MIN_CJK_RATIO and fail closed. That is
# intentional. Thresholds are not CLI flags; omit --expected-lang to skip
# the script check. See SKILL.md and scripts/README.md.
ZH_MIN_CJK = 8
ZH_MIN_CJK_RATIO = 0.35
JA_MAX_LATIN_RATIO = 0.75
KO_MIN_HANGUL = 8
LATIN_MAX_CJK_RATIO = 0.65
# Used only when assess() is given a numeric confidence. The whisper CLI
# path does not read a score, so an omitted confidence is not a floor.
CONFIDENCE_FLOOR = 0.40
MIN_VOWEL_RATIO = 0.22
MIN_LATIN_FOR_VOWEL = 40
LOOP_MIN_SEG_CHARS = 15
LOOP_MIN_COUNT = 4
LOOP_MIN_SHARE = 0.34
LOOP_FORCE_COUNT = 8
NGRAM_MIN_COUNT = 4
NGRAM_MIN_COVERAGE = 0.34
TOKEN_MIN_WORDS = 30
TOKEN_DOMINANCE = 0.50
UNIQUE_WORD_FLOOR = 0.12
MICRO_CUE_SECONDS = 0.08
CHUNK_MAX_SECONDS = 8 * 60
CHUNK_MAX_CHARS = 6000

LATIN_LANGS = {
    "en", "es", "fr", "de", "pt", "it", "nl", "pl", "sv", "id", "vi", "tr",
    "ro", "cs", "da", "fi", "no", "nb", "nn", "hu", "ca", "af", "sw", "tl",
    "hr", "sk", "sl", "et", "lv", "lt",
}

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_KANA = re.compile(r"[\u3040-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7af]")
_VOWEL = re.compile(r"[AEIOUaeiou]")
_TAG = re.compile(r"<[^>]+>")
_MUSIC = re.compile(
    r"\[(?:music|applause|laughter|音乐|掌声|笑声)\]|（(?:音乐|掌声|笑声)）|♪+",
    re.IGNORECASE,
)
_TS_LINE = re.compile(
    r"(?P<a>(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?P<b>(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})"
)
_HALLUCINATION = (
    "thank you for watching",
    "thanks for watching",
    "please like and subscribe",
    "like and subscribe",
    "i hope you enjoyed this video",
    "see you in the next video",
    "subtitles by the amara.org community",
    "amara.org",
)


@dataclass
class Segment:
    """One cue after caption cleanup. ``start`` and ``end`` are seconds.

    Plain text and ASR output that has no clock leave both as None.
    """

    start: float | None
    end: float | None
    text: str

    def to_dict(self) -> dict:
        return {
            "start": None if self.start is None else round(float(self.start), 3),
            "end": None if self.end is None else round(float(self.end), 3),
            "text": self.text,
        }


@dataclass
class GateResult:
    passed: bool
    reasons: list[str]
    metrics: dict
    text: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reasons": list(self.reasons),
            "metrics": self.metrics,
        }


def normalize_lang(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip().lower().replace("_", "-")
    if raw in {"", "auto", "und", "unknown", "any"}:
        return None
    names = {
        "english": "en",
        "chinese": "zh",
        "mandarin": "zh",
        "japanese": "ja",
        "korean": "ko",
    }
    if raw in names:
        return names[raw]
    base = raw.split("-")[0]
    if base in {"zh", "cmn", "yue", "wuu"} or raw.startswith("zh"):
        return "zh"
    if base in {"ja", "jp"}:
        return "ja"
    if base in {"ko", "kor"}:
        return "ko"
    if base in LATIN_LANGS:
        return base
    return base


def script_family(lang: str | None) -> str | None:
    if lang == "zh":
        return "han"
    if lang == "ja":
        return "ja"
    if lang == "ko":
        return "ko"
    if lang in LATIN_LANGS:
        return "latin"
    return None


def _stamp_to_seconds(stamp: str) -> float:
    stamp = stamp.replace(",", ".")
    parts = [float(part) for part in stamp.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def _clean_cue(text: str) -> str:
    text = html.unescape(text.replace("\u00a0", " "))
    text = _TAG.sub("", text)
    text = _MUSIC.sub(" ", text)
    text = text.replace(">>", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_caption_cues(raw: str) -> list[Segment]:
    """Return timed cues from VTT, SRT, or similar timed text."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cues: list[Segment] = []
    for block in re.split(r"\n\s*\n", raw):
        match = None
        lines = block.split("\n")
        text_at = None
        for index, line in enumerate(lines):
            found = _TS_LINE.search(line.strip())
            if found:
                match = found
                text_at = index + 1
                break
        if not match or text_at is None:
            continue
        text = _clean_cue(" ".join(lines[text_at:]))
        if not text:
            continue
        start = _stamp_to_seconds(match.group("a"))
        end = _stamp_to_seconds(match.group("b"))
        if end < start:
            end = start
        cues.append(Segment(start, end, text))
    return cues


def _parse_json3(raw: str) -> list[Segment]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    segments: list[Segment] = []
    for event in data.get("events") or []:
        if not isinstance(event, dict):
            continue
        parts = []
        for seg in event.get("segs") or []:
            if isinstance(seg, dict):
                parts.append(str(seg.get("utf8") or ""))
        text = _clean_cue("".join(parts).replace("\n", " "))
        if not text:
            continue
        start_ms = event.get("tStartMs")
        dur_ms = event.get("dDurationMs")
        start = float(start_ms) / 1000 if isinstance(start_ms, (int, float)) else None
        end = None
        if start is not None and isinstance(dur_ms, (int, float)):
            end = start + float(dur_ms) / 1000
        segments.append(Segment(start, end, text))
    return segments


def _xml_attr(attrs: str, name: str) -> float | None:
    found = re.search(rf"\b{name}\s*=\s*['\"]([^'\"]+)['\"]", attrs)
    if not found:
        return None
    try:
        return float(found.group(1))
    except ValueError:
        return None


def _parse_xml_captions(raw: str) -> list[Segment]:
    tagged = list(re.finditer(r"<text\b([^>]*)>([^<]*)</text>", raw, re.IGNORECASE))
    if tagged:
        segments: list[Segment] = []
        for match in tagged:
            text = _clean_cue(match.group(2))
            if not text or re.fullmatch(r"[\d:.,\s]+", text):
                continue
            start = _xml_attr(match.group(1), "start")
            dur = _xml_attr(match.group(1), "dur")
            end = start + dur if start is not None and dur is not None else None
            segments.append(Segment(start, end, text))
        return segments
    segments = []
    for chunk in re.findall(r">([^<]+)<", raw):
        text = _clean_cue(chunk)
        if text and not re.fullmatch(r"[\d:.,\s]+", text):
            segments.append(Segment(None, None, text))
    return segments


def _drop_prefix_segments(segments: list[Segment]) -> list[Segment]:
    """YouTube rolling captions repeat a line, then the same line plus new words."""
    kept: list[Segment] = []
    index = 0
    while index < len(segments):
        if (
            index + 1 < len(segments)
            and segments[index + 1].text.startswith(segments[index].text)
            and len(segments[index + 1].text) > len(segments[index].text) + 2
        ):
            index += 1
            continue
        kept.append(segments[index])
        index += 1
    return kept


def _merge_overlap_segments(segments: list[Segment]) -> list[Segment]:
    if not segments:
        return []
    merged = [segments[0]]
    for segment in segments[1:]:
        previous = merged[-1].text.split()
        current = segment.text.split()
        best = 0
        limit = min(len(previous), len(current))
        for size in range(limit, 3, -1):
            left = [word.lower().strip(".,;:!?") for word in previous[-size:]]
            right = [word.lower().strip(".,;:!?") for word in current[:size]]
            if left == right:
                best = size
                break
        shorter = min(len(previous), len(current))
        if best >= 4 and shorter > 0 and best >= 0.45 * shorter:
            merged[-1] = Segment(
                merged[-1].start,
                segment.end if segment.end is not None else merged[-1].end,
                " ".join(previous + current[best:]),
            )
        else:
            merged.append(segment)
    return merged


def _collapse_segment_runs(segments: list[Segment]) -> list[Segment]:
    """Collapse 2–3 identical caption repeats. Keep runs of 4 or more so a
    real ASR loop is still visible to the gate."""
    output: list[Segment] = []
    index = 0
    while index < len(segments):
        end = index + 1
        key = segments[index].text.casefold()
        while end < len(segments) and segments[end].text.casefold() == key:
            end += 1
        run = end - index
        if run >= 4:
            output.extend(segments[index:end])
        else:
            kept = segments[index]
            last = segments[end - 1]
            if last is not kept and last.end is not None:
                kept = Segment(kept.start, last.end, kept.text)
            output.append(kept)
        index = end
    return output


def _looks_like_timed_text(raw: str) -> bool:
    head = raw.lstrip("\ufeff").lstrip()[:300]
    upper = head.upper()
    if upper.startswith("WEBVTT"):
        return True
    if "-->" in raw[:4000]:
        return True
    if head.startswith("{") and "events" in raw[:1500]:
        return True
    if head.startswith("<") and ("<text" in raw[:1500].lower() or "<p " in raw[:1500].lower()):
        return True
    return False


def prepare_segments(raw: str) -> list[Segment]:
    """Caption cues with start/end kept. Plain text has no clock.

    The joined ``text`` fields match ``prepare_transcript``. Timestamps are
    not folded into the gate text.
    """
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if not raw.strip():
        return []
    timed: list[Segment] | None = None
    if raw.lstrip().startswith("{") and "events" in raw[:1500]:
        timed = _parse_json3(raw)
    elif raw.lstrip().startswith("<") and ("<text" in raw[:1500].lower() or "<p " in raw[:1500].lower()):
        timed = _parse_xml_captions(raw)
    elif _looks_like_timed_text(raw):
        cues = _parse_caption_cues(raw)
        micros = [cue for cue in cues if (cue.end - cue.start) <= MICRO_CUE_SECONDS]
        # YouTube auto-captions insert ~10ms cues that hold the stable line.
        if len(micros) >= 4 and len(cues) > 0 and len(micros) >= 0.3 * len(cues):
            timed = micros
        else:
            timed = cues
    if timed is None:
        plain: list[Segment] = []
        for line in raw.split("\n"):
            cleaned = _clean_cue(line)
            if cleaned:
                plain.append(Segment(None, None, cleaned))
        return _collapse_segment_runs(plain)
    timed = _drop_prefix_segments(timed)
    timed = _merge_overlap_segments(timed)
    return _collapse_segment_runs(timed)


def prepare_transcript(raw: str) -> str:
    """Turn caption formats into plain speech lines. Plain text is only trimmed."""
    return "\n".join(segment.text for segment in prepare_segments(raw)).strip()


def format_stamp(seconds: float) -> str:
    """``[mm:ss]`` until one hour, then ``[hh:mm:ss]``."""
    whole = max(0, int(seconds))
    if whole >= 3600:
        hours, rem = divmod(whole, 3600)
        minutes, secs = divmod(rem, 60)
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    minutes, secs = divmod(whole, 60)
    return f"[{minutes:02d}:{secs:02d}]"


def format_transcript(segments: list[Segment]) -> str:
    """One line per cue. Timed cues lead with the start stamp."""
    lines: list[str] = []
    for segment in segments:
        if segment.start is None:
            lines.append(segment.text)
        else:
            lines.append(f"{format_stamp(segment.start)} {segment.text}")
    return "\n".join(lines).strip()


def duration_seconds(segments: list[Segment]) -> float | None:
    ends = [segment.end for segment in segments if segment.end is not None]
    if ends:
        return round(max(ends), 3)
    starts = [segment.start for segment in segments if segment.start is not None]
    if starts:
        return round(max(starts), 3)
    return None


def chunk_segments(segments: list[Segment]) -> list[list[Segment]]:
    """Split on about 8 minutes or about 6000 characters, whichever comes first.

    A single cue longer than the character budget stays intact. Untimed text
    splits on characters only.
    """
    chunks: list[list[Segment]] = []
    current: list[Segment] = []
    chars = 0
    origin: float | None = None

    def flush() -> None:
        nonlocal current, chars, origin
        if current:
            chunks.append(current)
        current = []
        chars = 0
        origin = None

    for segment in segments:
        if current:
            elapsed = None
            if origin is not None and segment.start is not None:
                elapsed = segment.start - origin
            over_time = elapsed is not None and elapsed >= CHUNK_MAX_SECONDS
            over_chars = chars >= CHUNK_MAX_CHARS
            if over_time or over_chars:
                flush()
        if not current:
            origin = segment.start
        current.append(segment)
        chars += len(segment.text) + (1 if len(current) > 1 else 0)
    flush()
    return chunks


def caption_trust(
    kind: str | None,
    caption_language: str | None,
    expected_lang: str | None,
) -> str | None:
    """``low`` when automatic captions are not in the expected language.

    No expected language means there is nothing to mismatch. Manual captions
    are not marked here.
    """
    if (kind or "").strip().casefold() != "auto":
        return None
    expected = normalize_lang(expected_lang)
    got = normalize_lang(caption_language)
    if expected and got and expected != got:
        return "low"
    return None


def _counts(text: str) -> dict[str, int]:
    return {
        "cjk": len(_CJK.findall(text)),
        "latin": len(_LATIN.findall(text)),
        "kana": len(_KANA.findall(text)),
        "hangul": len(_HANGUL.findall(text)),
        "vowels": len(_VOWEL.findall(text)),
    }


def _sentence_parts(text: str) -> list[str]:
    parts = re.split(r"[。！？!?；;\n]+", text)
    cleaned = []
    for part in parts:
        normalized = re.sub(r"\s+", " ", part).strip().casefold()
        if len(normalized) >= LOOP_MIN_SEG_CHARS:
            cleaned.append(normalized)
    return cleaned


def _language_reasons(counts: dict[str, int], family: str | None, lang: str | None) -> list[str]:
    cjk = counts["cjk"]
    latin = counts["latin"]
    kana = counts["kana"]
    hangul = counts["hangul"]
    cjk_ratio = cjk / (cjk + latin) if (cjk + latin) else 0.0
    latin_ratio = latin / (cjk + latin) if (cjk + latin) else 0.0
    reasons: list[str] = []
    if family == "han":
        if cjk < ZH_MIN_CJK or cjk_ratio < ZH_MIN_CJK_RATIO:
            reasons.append(
                "language/ratio fail for expected Chinese: "
                f"cjk={cjk}, cjk_ratio={cjk_ratio:.2f}, latin_ratio={latin_ratio:.2f} "
                f"(need cjk>={ZH_MIN_CJK} and cjk_ratio>={ZH_MIN_CJK_RATIO:.2f})"
            )
    elif family == "ja":
        script = kana + cjk
        pool = script + latin
        latin_share = latin / pool if pool else 1.0
        if script < 8 or latin_share > JA_MAX_LATIN_RATIO:
            reasons.append(
                "language/ratio fail for expected Japanese: "
                f"kana+cjk={script}, latin_share={latin_share:.2f}"
            )
    elif family == "ko":
        pool = hangul + latin + cjk
        hangul_share = hangul / pool if pool else 0.0
        if hangul < KO_MIN_HANGUL or hangul_share < 0.35:
            reasons.append(
                "language/ratio fail for expected Korean: "
                f"hangul={hangul}, hangul_share={hangul_share:.2f}"
            )
    elif family == "latin":
        if cjk >= 12 and cjk_ratio >= LATIN_MAX_CJK_RATIO:
            reasons.append(
                f"language/ratio fail for expected Latin-script language {lang}: "
                f"cjk_ratio={cjk_ratio:.2f}, cjk={cjk}"
            )
    return reasons


def assess(
    raw: str,
    *,
    expected_lang: str | None = None,
    confidence: float | None = None,
) -> GateResult:
    lang = normalize_lang(expected_lang)
    family = script_family(lang)
    text = prepare_transcript(raw or "")
    counts = _counts(text)
    speech = sum(1 for char in text if char.isalpha())
    cjk_ratio = (
        counts["cjk"] / (counts["cjk"] + counts["latin"])
        if (counts["cjk"] + counts["latin"])
        else 0.0
    )
    latin_ratio = (
        counts["latin"] / (counts["cjk"] + counts["latin"])
        if (counts["cjk"] + counts["latin"])
        else 0.0
    )
    vowel_ratio = counts["vowels"] / counts["latin"] if counts["latin"] else 0.0
    latin_words = re.findall(r"[A-Za-z']+", text)
    unique_ratio = (
        len({word.casefold() for word in latin_words}) / len(latin_words)
        if latin_words
        else 1.0
    )
    metrics = {
        "speech_chars": speech,
        "cjk": counts["cjk"],
        "latin": counts["latin"],
        "kana": counts["kana"],
        "hangul": counts["hangul"],
        "cjk_ratio": round(cjk_ratio, 4),
        "latin_ratio": round(latin_ratio, 4),
        "vowel_ratio": round(vowel_ratio, 4) if counts["latin"] else None,
        "latin_words": len(latin_words),
        "unique_word_ratio": round(unique_ratio, 4) if latin_words else None,
        "expected_lang": lang,
        "confidence": confidence,
    }
    reasons: list[str] = []
    if speech == 0:
        reasons.append("empty or unusable transcript (no speech text after cleanup)")
    elif speech < MIN_SPEECH_CHARS:
        reasons.append(f"transcript too short to be usable ({speech} speech characters)")
    else:
        parts = _sentence_parts(text)
        sentence_loop = False
        if parts:
            seg, count = Counter(parts).most_common(1)[0]
            share = count / len(parts)
            if (count >= LOOP_MIN_COUNT and share >= LOOP_MIN_SHARE) or count >= LOOP_FORCE_COUNT:
                sentence_loop = True
                reasons.append(
                    f"looping repeats: the same segment appears {count} times "
                    f"({share:.0%} of segments)"
                )
            else:
                hits = sum(1 for part in parts if any(phrase in part for phrase in _HALLUCINATION))
                if len(parts) >= 3 and hits / len(parts) >= 0.5:
                    sentence_loop = True
                    reasons.append(
                        "looping repeats: hallucination phrases dominate the transcript "
                        f"({hits}/{len(parts)} segments)"
                    )
        if len(latin_words) >= 12 and not sentence_loop:
            grams = Counter(
                tuple(word.casefold() for word in latin_words[index : index + 4])
                for index in range(max(len(latin_words) - 3, 0))
            )
            if grams:
                _gram, count = grams.most_common(1)[0]
                coverage = count * 4 / len(latin_words)
                if count >= NGRAM_MIN_COUNT and coverage >= NGRAM_MIN_COVERAGE:
                    sentence_loop = True
                    reasons.append(
                        f"looping repeats: a 4-word phrase repeats {count} times "
                        f"({coverage:.0%} of words)"
                    )
        if len(latin_words) >= TOKEN_MIN_WORDS:
            word, count = Counter(word.casefold() for word in latin_words).most_common(1)[0]
            share = count / len(latin_words)
            if share >= TOKEN_DOMINANCE:
                reasons.append(f"looping repeats: '{word}' is {share:.0%} of words")
            elif unique_ratio < UNIQUE_WORD_FLOOR:
                reasons.append(
                    f"looping repeats: unique-word ratio {unique_ratio:.2f} is too low"
                )
        if counts["latin"] >= MIN_LATIN_FOR_VOWEL and vowel_ratio < MIN_VOWEL_RATIO:
            reasons.append(
                f"gibberish: Latin vowel ratio {vowel_ratio:.2f} is too low to be speech"
            )
        reasons.extend(_language_reasons(counts, family, lang))
    if confidence is not None and confidence < CONFIDENCE_FLOOR:
        reasons.append(
            f"model confidence {confidence:.2f} is below the floor {CONFIDENCE_FLOOR:.2f}"
        )
    # Preserve order while dropping duplicates.
    deduped: list[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return GateResult(passed=not deduped, reasons=deduped, metrics=metrics, text=text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quality-gate a transcript file.")
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--expected-lang", default=None)
    parser.add_argument("--confidence", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.transcript.is_file():
        payload = {
            "passed": False,
            "reasons": [f"missing transcript path: {args.transcript} does not exist"],
            "metrics": {},
        }
        if args.json:
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        else:
            print("fail", file=sys.stderr)
            print(payload["reasons"][0], file=sys.stderr)
        return 2
    raw = args.transcript.read_text(encoding="utf-8", errors="replace")
    result = assess(raw, expected_lang=args.expected_lang, confidence=args.confidence)
    if args.json:
        json.dump(result.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print("pass" if result.passed else "fail")
        for reason in result.reasons:
            print(reason, file=sys.stderr)
    return 0 if result.passed else 2


if __name__ == "__main__":
    sys.exit(main())
