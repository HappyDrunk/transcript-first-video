#!/usr/bin/env python3
"""Unit tests for the quality gate, verifier, and host deposit rules."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import quality_gate  # noqa: E402
import verify_note  # noqa: E402
import youtube_host  # noqa: E402

os.chdir(ROOT)

ROLLING_VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:02.500
Hello<00:00:01.200><c> there,</c><00:00:01.400><c> this</c><00:00:01.600><c> is</c><00:00:01.800><c> a</c>

00:00:02.500 --> 00:00:02.510
Hello there, this is a

00:00:02.510 --> 00:00:04.000
Hello there, this is a
real<00:00:02.800><c> spoken</c><00:00:03.200><c> sentence</c><00:00:03.600><c> about</c>

00:00:04.000 --> 00:00:04.010
real spoken sentence about

00:00:04.010 --> 00:00:05.500
real spoken sentence about
repotting<00:00:04.400><c> a</c><00:00:04.600><c> plant</c><00:00:04.900><c> today</c><00:00:05.100><c> outside.</c>

00:00:05.500 --> 00:00:05.510
repotting a plant today outside.
"""


class QualityGateTests(unittest.TestCase):
    def test_usable_english_and_chinese(self) -> None:
        english = (ROOT / "evals/fixtures/usable_en_transcript.txt").read_text(encoding="utf-8")
        chinese = (ROOT / "evals/fixtures/usable_zh_transcript.txt").read_text(encoding="utf-8")
        self.assertTrue(quality_gate.assess(english, expected_lang="en").passed)
        self.assertTrue(quality_gate.assess(english).passed)
        self.assertTrue(quality_gate.assess(chinese, expected_lang="zh").passed)

    def test_english_fails_expected_chinese(self) -> None:
        english = (ROOT / "evals/fixtures/usable_en_transcript.txt").read_text(encoding="utf-8")
        result = quality_gate.assess(english, expected_lang="zh-CN")
        self.assertFalse(result.passed)
        self.assertTrue(any("expected Chinese" in reason for reason in result.reasons))

    def test_empty_music_and_short(self) -> None:
        empty = quality_gate.assess((ROOT / "evals/fixtures/empty_transcript.txt").read_text(encoding="utf-8"))
        self.assertFalse(empty.passed)
        self.assertTrue(any("empty" in reason for reason in empty.reasons))
        short = quality_gate.assess("Hello.")
        self.assertFalse(short.passed)

    def test_english_loop_and_gibberish(self) -> None:
        loop = quality_gate.assess(
            (ROOT / "evals/fixtures/en_loop_transcript.txt").read_text(encoding="utf-8"),
            expected_lang="zh",
        )
        self.assertFalse(loop.passed)
        self.assertTrue(any("looping repeats" in reason for reason in loop.reasons))
        self.assertTrue(any("expected Chinese" in reason for reason in loop.reasons))
        junk = quality_gate.assess(
            (ROOT / "evals/fixtures/gibberish_transcript.txt").read_text(encoding="utf-8"),
            expected_lang="en",
        )
        self.assertFalse(junk.passed)
        self.assertTrue(any("gibberish" in reason for reason in junk.reasons))

    def test_paragraph_loop_without_newlines(self) -> None:
        text = "Thank you for watching. " * 6
        result = quality_gate.assess(text, expected_lang="en")
        self.assertFalse(result.passed)

    def test_confidence_floor(self) -> None:
        english = (ROOT / "evals/fixtures/usable_en_transcript.txt").read_text(encoding="utf-8")
        low = quality_gate.assess(english, expected_lang="en", confidence=0.1)
        self.assertFalse(low.passed)
        self.assertTrue(any("confidence" in reason for reason in low.reasons))

    def test_rolling_captions_collapse(self) -> None:
        result = quality_gate.assess(ROLLING_VTT, expected_lang="en")
        self.assertTrue(result.passed, result.reasons)
        self.assertIn("repotting a plant today", result.text)
        self.assertLess(result.text.lower().count("hello there"), 3)


class VerifierTests(unittest.TestCase):
    def test_allow_when_cited_and_usable(self) -> None:
        transcript = ROOT / "evals/fixtures/usable_en_transcript.txt"
        note = (ROOT / "evals/fixtures/usable_en_note.md").read_text(encoding="utf-8")
        result = verify_note.verify(transcript, note, expected_lang="en")
        self.assertTrue(result["allowed"], result["reasons"])

    def test_refuse_empty_missing_citation_and_laundering(self) -> None:
        empty = verify_note.verify(
            ROOT / "evals/fixtures/empty_transcript.txt",
            (ROOT / "evals/fixtures/empty_finished_note.md").read_text(encoding="utf-8"),
            expected_lang="en",
        )
        self.assertFalse(empty["allowed"])
        self.assertTrue(any("empty" in reason for reason in empty["reasons"]))

        missing = verify_note.verify(
            ROOT / "evals/fixtures/does_not_exist.txt",
            (ROOT / "evals/fixtures/laundered_essay_note.md").read_text(encoding="utf-8"),
            expected_lang="zh",
        )
        self.assertFalse(missing["allowed"])
        self.assertTrue(any("missing transcript path" in reason for reason in missing["reasons"]))
        self.assertTrue(any("analyzer-laundering" in reason for reason in missing["reasons"]))

        uncited = verify_note.verify(
            ROOT / "evals/fixtures/usable_en_transcript.txt",
            (ROOT / "evals/fixtures/uncited_note.md").read_text(encoding="utf-8"),
            expected_lang="en",
        )
        self.assertFalse(uncited["allowed"])
        self.assertTrue(any("does not cite" in reason for reason in uncited["reasons"]))

        laundered = verify_note.verify(
            ROOT / "evals/fixtures/en_loop_transcript.txt",
            (ROOT / "evals/fixtures/laundered_essay_note.md").read_text(encoding="utf-8"),
            expected_lang="zh",
        )
        self.assertFalse(laundered["allowed"])
        self.assertTrue(any("quality gate failed" in reason for reason in laundered["reasons"]))
        self.assertTrue(any("analyzer-laundering" in reason for reason in laundered["reasons"]))

    def test_basename_alone_is_not_a_citation(self) -> None:
        note = "The transcript file is usable_en_transcript.txt and the plant was repotted."
        result = verify_note.verify(
            ROOT / "evals/fixtures/usable_en_transcript.txt",
            note,
            expected_lang="en",
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("does not cite" in reason for reason in result["reasons"]))


class HostTests(unittest.TestCase):
    def test_parse_youtube_ref(self) -> None:
        video_id, url = youtube_host.parse_youtube_ref("https://www.youtube.com/watch?v=KwhgfwOSToQ")
        self.assertEqual(video_id, "KwhgfwOSToQ")
        self.assertEqual(url, "https://www.youtube.com/watch?v=KwhgfwOSToQ")
        video_id, _url = youtube_host.parse_youtube_ref("https://youtu.be/KwhgfwOSToQ?t=3")
        self.assertEqual(video_id, "KwhgfwOSToQ")
        video_id, _url = youtube_host.parse_youtube_ref("https://m.youtube.com/shorts/KwhgfwOSToQ")
        self.assertEqual(video_id, "KwhgfwOSToQ")
        with self.assertRaises(youtube_host.HostError):
            youtube_host.parse_youtube_ref("https://notyoutube.com/watch?v=KwhgfwOSToQ")
        with self.assertRaises(youtube_host.HostError):
            youtube_host.parse_youtube_ref("https://evil.example/watch?v=KwhgfwOSToQ")

    def test_select_caption_language_ignores_title(self) -> None:
        info = {
            "title": "do not use this title as a transcript",
            "description": "do not use this description",
            "language": "zh",
            "subtitles": {"zh-Hans": [{"ext": "vtt", "url": "https://example.test/a"}]},
            "automatic_captions": {
                "en": [{"ext": "vtt", "url": "https://example.test/en?tlang=en"}],
                "zh-Hans": [{"ext": "vtt", "url": "https://example.test/zh"}],
            },
        }
        self.assertEqual(youtube_host.select_caption_language(info, "zh"), ("zh-Hans", "manual"))
        self.assertEqual(youtube_host.select_caption_language(info, None), ("zh-Hans", "manual"))
        auto_only = {
            "language": "en",
            "subtitles": {},
            "automatic_captions": {
                "de": [{"ext": "vtt", "url": "https://example.test/de?tlang=de"}],
                "en": [{"ext": "vtt", "url": "https://example.test/en"}],
            },
        }
        self.assertEqual(youtube_host.select_caption_language(auto_only, None), ("en", "auto"))
        self.assertIsNone(youtube_host.select_caption_language(auto_only, "zh"))

    def test_safe_caption_url_and_redact(self) -> None:
        self.assertEqual(
            youtube_host.safe_caption_url("https://mirror.example", "/api/v1/captions/abc"),
            "https://mirror.example/api/v1/captions/abc",
        )
        with self.assertRaises(youtube_host.HostError):
            youtube_host.safe_caption_url("https://mirror.example", "http://169.254.169.254/latest")
        scrubbed = youtube_host.redact("failed OPENAI_API_KEY=sk-secretvalue123456 url https://x.test/a?token=abc")
        self.assertNotIn("sk-secretvalue123456", scrubbed)
        self.assertNotIn("token=abc", scrubbed)
        self.assertIn("<redacted>", scrubbed)

    def test_asr_plan_is_honest_without_deps(self) -> None:
        old = os.environ.get("OPENAI_API_KEY")
        os.environ.pop("OPENAI_API_KEY", None)
        try:
            backend, reason = youtube_host.asr_plan("openai")
        finally:
            if old is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old
        self.assertEqual(backend, "openai")
        self.assertIn("OPENAI_API_KEY", reason or "")
        self.assertNotIn("sk-", reason or "")
        backend, reason = youtube_host.asr_plan("off")
        self.assertEqual(backend, "off")
        self.assertIn("not finished", reason or "")

    def test_finalize_writes_citation_or_status_only(self) -> None:
        usable = (ROOT / "evals/fixtures/usable_en_transcript.txt").read_text(encoding="utf-8")
        empty = (ROOT / "evals/fixtures/empty_transcript.txt").read_text(encoding="utf-8")
        loop = (ROOT / "evals/fixtures/en_loop_transcript.txt").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            ok = youtube_host.finalize_job(
                text=usable,
                video_id="usable-en",
                source="settle-transcript:usable-en",
                out_dir=out,
                expected_lang="en",
                acquisition="settle-transcript",
            )
            self.assertEqual(ok["exit_code"], 0)
            note_path = out / "youtube_usable-en" / "note.md"
            transcript_path = out / "youtube_usable-en" / "transcript.txt"
            self.assertTrue(note_path.is_file())
            self.assertTrue(transcript_path.is_file())
            note = note_path.read_text(encoding="utf-8")
            self.assertIn(youtube_host.cite_path(transcript_path), note)
            status = json.loads((out / "youtube_usable-en" / "status.json").read_text(encoding="utf-8"))
            self.assertNotIn("title", status)
            self.assertNotIn("description", status)
            checked = verify_note.verify(transcript_path, note, expected_lang="en")
            self.assertTrue(checked["allowed"], checked["reasons"])

            refused = youtube_host.finalize_job(
                text=empty,
                video_id="usable-en",
                source="settle-transcript:usable-en",
                out_dir=out,
                expected_lang="en",
                acquisition="settle-transcript",
            )
            self.assertEqual(refused["exit_code"], 2)
            self.assertFalse(note_path.exists())
            self.assertFalse(transcript_path.exists())
            self.assertTrue((out / "youtube_usable-en" / "status.json").is_file())

            blocked = youtube_host.finalize_job(
                text=loop,
                video_id="zh-loop",
                source="settle-transcript:zh-loop",
                out_dir=out,
                expected_lang="zh",
                acquisition="settle-transcript",
            )
            self.assertEqual(blocked["status"], "quality_gate_failed")
            self.assertFalse((out / "youtube_zh-loop" / "note.md").exists())
            self.assertNotIn("title", blocked)


if __name__ == "__main__":
    unittest.main()
