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
ZH_MIN_CJK = 8
ZH_MIN_CJK_RATIO = 0.35
JA_MAX_LATIN_RATIO = 0.75
KO_MIN_HANGUL = 8
LATIN_MAX_CJK_RATIO = 0.65
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


def _parse_caption_cues(raw: str) -> list[tuple[float, str]]:
    """Return (duration, text) cues from VTT, SRT, or similar timed text."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cues: list[tuple[float, str]] = []
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
        duration = _stamp_to_seconds(match.group("b")) - _stamp_to_seconds(match.group("a"))
        cues.append((max(duration, 0.0), text))
    return cues


def _parse_json3(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    lines: list[str] = []
    for event in data.get("events") or []:
        parts = []
        for seg in event.get("segs") or []:
            parts.append(str(seg.get("utf8") or ""))
        text = _clean_cue("".join(parts).replace("\n", " "))
        if text:
            lines.append(text)
    return lines


def _parse_xml_captions(raw: str) -> list[str]:
    lines = []
    for chunk in re.findall(r">([^<]+)<", raw):
        text = _clean_cue(chunk)
        if text and not re.fullmatch(r"[\d:.,\s]+", text):
            lines.append(text)
    return lines


def _drop_prefix_lines(lines: list[str]) -> list[str]:
    """YouTube rolling captions repeat a line, then the same line plus new words."""
    kept: list[str] = []
    index = 0
    while index < len(lines):
        if (
            index + 1 < len(lines)
            and lines[index + 1].startswith(lines[index])
            and len(lines[index + 1]) > len(lines[index]) + 2
        ):
            index += 1
            continue
        kept.append(lines[index])
        index += 1
    return kept


def _merge_overlap(lines: list[str]) -> list[str]:
    if not lines:
        return []
    merged = [lines[0]]
    for line in lines[1:]:
        previous = merged[-1].split()
        current = line.split()
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
            merged[-1] = " ".join(previous + current[best:])
        else:
            merged.append(line)
    return merged


def _collapse_runs(lines: list[str]) -> list[str]:
    """Collapse 2–3 identical caption repeats. Keep runs of 4 or more so a
    real ASR loop is still visible to the gate."""
    output: list[str] = []
    index = 0
    while index < len(lines):
        end = index + 1
        key = lines[index].casefold()
        while end < len(lines) and lines[end].casefold() == key:
            end += 1
        run = end - index
        if run >= 4:
            output.extend(lines[index:end])
        else:
            output.append(lines[index])
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


def prepare_transcript(raw: str) -> str:
    """Turn caption formats into plain speech lines. Plain text is only trimmed."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if not raw.strip():
        return ""
    lines: list[str]
    if raw.lstrip().startswith("{") and "events" in raw[:1500]:
        lines = _parse_json3(raw)
    elif raw.lstrip().startswith("<") and ("<text" in raw[:1500].lower() or "<p " in raw[:1500].lower()):
        lines = _parse_xml_captions(raw)
    elif _looks_like_timed_text(raw):
        cues = _parse_caption_cues(raw)
        micros = [text for duration, text in cues if duration <= MICRO_CUE_SECONDS]
        # YouTube auto-captions insert ~10ms cues that hold the stable line.
        if len(micros) >= 4 and len(cues) > 0 and len(micros) >= 0.3 * len(cues):
            lines = micros
        else:
            lines = [text for _duration, text in cues]
    else:
        lines = []
        for line in raw.split("\n"):
            cleaned = _clean_cue(line)
            if cleaned:
                lines.append(cleaned)
        return "\n".join(_collapse_runs(lines)).strip()

    lines = _drop_prefix_lines(lines)
    lines = _merge_overlap(lines)
    lines = _collapse_runs(lines)
    return "\n".join(lines).strip()


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
