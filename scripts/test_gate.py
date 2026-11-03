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
import x_host  # noqa: E402
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

    def test_chinese_jargon_ratio_fails_closed_until_expected_lang_omitted(self) -> None:
        # More than ZH_MIN_CJK characters, but English identifiers pull the
        # CJK ratio under 0.35. Fail-closed with --expected-lang zh. The
        # universal checks still pass when the script check is omitted.
        text = (
            "今天我们讨论如何把 RAG pipeline 接到 Transformer encoder 的 hidden state 上，"
            "再写入 FAISS index。然后用 LoRA 微调 LLM 的 attention，通过 OpenAI function calling "
            "接到 Kubernetes deployment，同时记录 batch size、learning rate、checkpoint、tokenizer "
            "和 embedding dimension。这段口播是中文，术语大多是英文标识。"
        )
        refused = quality_gate.assess(text, expected_lang="zh")
        self.assertFalse(refused.passed)
        self.assertGreaterEqual(refused.metrics["cjk"], quality_gate.ZH_MIN_CJK)
        self.assertLess(refused.metrics["cjk_ratio"], quality_gate.ZH_MIN_CJK_RATIO)
        self.assertTrue(any("expected Chinese" in reason for reason in refused.reasons))
        opened = quality_gate.assess(text)
        self.assertTrue(opened.passed, opened.reasons)


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

    def test_refuse_path_and_title_without_quote(self) -> None:
        transcript = ROOT / "evals/fixtures/usable_en_transcript.txt"
        note = (ROOT / "evals/fixtures/path_only_note.md").read_text(encoding="utf-8")
        result = verify_note.verify(transcript, note, expected_lang="en")
        self.assertFalse(result["allowed"], result["reasons"])
        self.assertTrue(result["cited"])
        self.assertFalse(result["quoted"])
        self.assertTrue(any("does not quote" in reason for reason in result["reasons"]))
        self.assertTrue(any("path or a title" in reason for reason in result["reasons"]))

    def test_quote_window_can_start_mid_transcript(self) -> None:
        transcript = ROOT / "evals/fixtures/usable_en_transcript.txt"
        compact = " ".join(transcript.read_text(encoding="utf-8").split())
        snippet = compact[17 : 17 + verify_note.QUOTE_WINDOW]
        self.assertEqual(len(snippet), verify_note.QUOTE_WINDOW)
        self.assertNotIn(compact[: verify_note.QUOTE_WINDOW], snippet)
        note = f"transcript: {transcript.as_posix()}\n\n{snippet}\n"
        result = verify_note.verify(transcript, note, expected_lang="en")
        self.assertTrue(result["allowed"], result["reasons"])
        self.assertTrue(result["quoted"])


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


class XHostTests(unittest.TestCase):
    def test_status_page_match_ignores_a_different_media_id(self) -> None:
        status_id = "2102748685792596449"
        self.assertTrue(
            x_host.status_in_page(
                {"id": "2102748623029059584", "webpage_url": f"https://x.com/i/status/{status_id}"},
                status_id,
            )
        )
        self.assertTrue(x_host.status_in_page({"id": status_id}, status_id))
        self.assertFalse(
            x_host.status_in_page(
                {"id": "111", "webpage_url": "https://x.com/i/status/999", "url": f"https://video.twimg.com/{status_id}"},
                status_id,
            )
        )

    def test_parse_status_urls(self) -> None:
        status_id = "2102748685792596449"
        canonical = f"https://x.com/i/status/{status_id}"
        samples = [
            f"https://x.com/NASA/status/{status_id}",
            f"https://twitter.com/NASA/status/{status_id}?s=20",
            f"https://mobile.twitter.com/NASA/status/{status_id}",
            f"https://x.com/i/web/status/{status_id}",
            f"https://www.x.com/i/status/{status_id}/",
            f"https://fxtwitter.com/NASA/status/{status_id}",
            status_id,
        ]
        for sample in samples:
            got_id, url = x_host.parse_x_ref(sample)
            self.assertEqual(got_id, status_id, sample)
            self.assertEqual(url, canonical, sample)
        for sample in (
            "https://www.youtube.com/watch?v=KwhgfwOSToQ",
            "https://x.com/NASA",
            "https://evil.example/status/2102748685792596449",
            "https://bilibili.com/video/BV1xx411c7mD",
        ):
            with self.assertRaises(x_host.HostError):
                x_host.parse_x_ref(sample)

    def test_public_payload_drops_post_text(self) -> None:
        payload = {
            "code": 200,
            "status": {
                "text": "TITLE SPAM the secret method is banana pancakes at dawn",
                "media": {
                    "videos": [
                        {
                            "type": "video",
                            "url": "https://video.twimg.com/ext_tw_video/1/pu/vid/1.mp4",
                            "subtitles": [
                                {
                                    "lang": "en",
                                    "url": "https://video.twimg.com/captions/1.vtt",
                                }
                            ],
                        }
                    ]
                },
            },
        }
        parsed = x_host.parse_public_status(payload)
        blob = json.dumps(parsed)
        self.assertNotIn("banana pancakes", blob)
        self.assertNotIn("TITLE SPAM", blob)
        self.assertTrue(parsed["has_video"])
        self.assertTrue(str(parsed["video_url"]).startswith("https://video.twimg.com/"))
        self.assertEqual(parsed["caption_lang"], "en")

        legacy = {
            "code": 200,
            "tweet": {
                "text": "legacy post text must not leak",
                "media": {
                    "videos": [
                        {
                            "type": "video",
                            "url": "https://video.twimg.com/ext_tw_video/2/pu/vid/2.mp4?tag=14",
                        }
                    ]
                },
            },
        }
        legacy_parsed = x_host.parse_public_status(legacy)
        self.assertNotIn("legacy post text", json.dumps(legacy_parsed))
        self.assertTrue(legacy_parsed["has_video"])
        self.assertTrue(str(legacy_parsed["video_url"]).startswith("https://video.twimg.com/"))

        silent = x_host.parse_public_status(
            {
                "code": 200,
                "status": {
                    "text": "just words",
                    "media": {"photos": [{"url": "https://pbs.twimg.com/media/a.jpg"}]},
                },
            }
        )
        self.assertFalse(silent["has_video"])
        self.assertEqual(silent["error"], "status has no video")
        self.assertNotIn("just words", json.dumps(silent))

        unsafe = x_host.parse_public_status(
            {
                "code": 200,
                "status": {
                    "media": {
                        "videos": [
                            {
                                "type": "video",
                                "url": "http://169.254.169.254/latest/meta-data",
                            }
                        ]
                    }
                },
            }
        )
        self.assertIsNone(unsafe["video_url"])
        self.assertIn("allowlisted", unsafe["error"])

        offsite = x_host.parse_public_status(
            {
                "code": 200,
                "status": {"media": {"external": {"url": "https://www.youtube.com/watch?v=KwhgfwOSToQ"}}},
            }
        )
        self.assertIn("off-site", offsite["error"])
        self.assertNotIn("youtube.com", json.dumps(offsite))

        missing = x_host.parse_public_status({"code": 404, "message": "NOT_FOUND", "tweet": {"text": "hidden"}})
        self.assertIn("404", missing["error"])
        self.assertNotIn("hidden", json.dumps(missing))

    def test_media_url_and_api_base_are_allowlisted(self) -> None:
        self.assertTrue(x_host.safe_media_url("https://video.twimg.com/ext/a.mp4").startswith("https://"))
        for sample in (
            "http://video.twimg.com/a.mp4",
            "https://evil.example/a.mp4",
            "https://video.twimg.com.evil.example/a.mp4",
            "https://user:pass@video.twimg.com/a.mp4",
        ):
            with self.assertRaises(x_host.HostError):
                x_host.safe_media_url(sample)
        old = os.environ.get("FX_TWITTER_API")
        try:
            os.environ["FX_TWITTER_API"] = "off"
            self.assertEqual(x_host.public_api_bases(), [])
            os.environ["FX_TWITTER_API"] = "https://evil.example"
            with self.assertRaises(x_host.HostError):
                x_host.public_api_bases()
            os.environ["FX_TWITTER_API"] = "http://api.fxtwitter.com"
            with self.assertRaises(x_host.HostError):
                x_host.public_api_bases()
            os.environ.pop("FX_TWITTER_API", None)
            self.assertEqual(x_host.public_api_bases(), ["https://api.fxtwitter.com"])
        finally:
            if old is None:
                os.environ.pop("FX_TWITTER_API", None)
            else:
                os.environ["FX_TWITTER_API"] = old

    def test_no_caption_reason_names_the_video_and_not_the_post(self) -> None:
        reason = x_host.not_finished_reason(
            "not finished: no usable captions and ASR is not configured. No note was written.",
            [
                {"source": "yt-dlp", "ok": False, "detail": "yt-dlp is not installed"},
                {"source": "fx-twitter", "ok": True, "detail": "video URL, no caption track"},
            ],
        )
        self.assertIn("no caption track", reason)
        self.assertIn("Post text was not used", reason)
        self.assertIn("yt-dlp is not installed", reason)
        self.assertNotIn("http", reason)

    def test_settle_quotes_and_refuses_path_only(self) -> None:
        usable = (ROOT / "evals/fixtures/usable_en_transcript.txt").read_text(encoding="utf-8")
        empty = (ROOT / "evals/fixtures/empty_transcript.txt").read_text(encoding="utf-8")
        status_id = "123456789012345678"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            ok = x_host.run_x_host(
                status_id=status_id,
                source=f"settle-transcript:{status_id}",
                out_dir=out,
                expected_lang="en",
                asr_choice="off",
                verify=True,
                settle_text=usable,
            )
            self.assertEqual(ok["exit_code"], 0, ok.get("reason"))
            job = out / f"x_{status_id}"
            note_path = job / "note.md"
            transcript_path = job / "transcript.txt"
            self.assertTrue(note_path.is_file())
            self.assertTrue(transcript_path.is_file())
            note = note_path.read_text(encoding="utf-8")
            self.assertIn(f"x_{status_id}", note)
            checked = verify_note.verify(transcript_path, note, expected_lang="en")
            self.assertTrue(checked["allowed"], checked["reasons"])
            self.assertTrue(checked["quoted"])
            path_only = f"Title: done.\n\ntranscript: {youtube_host.cite_path(transcript_path)}\n"
            refused = verify_note.verify(transcript_path, path_only, expected_lang="en")
            self.assertFalse(refused["allowed"])
            self.assertTrue(refused["cited"])
            self.assertFalse(refused["quoted"])
            status = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertNotIn("title", status)
            self.assertNotIn("text", status)

            blocked = x_host.run_x_host(
                status_id=status_id,
                source=f"settle-transcript:{status_id}",
                out_dir=out,
                expected_lang="en",
                asr_choice="off",
                verify=True,
                settle_text=empty,
            )
            self.assertEqual(blocked["exit_code"], 2)
            self.assertFalse(note_path.exists())
            self.assertFalse(transcript_path.exists())
            self.assertTrue((job / "status.json").is_file())
            self.assertNotIn("title", blocked)


class EvidencePathTests(unittest.TestCase):
    def test_recorded_command_strips_checkout_and_interpreter(self) -> None:
        import run_evidence

        command = run_evidence.recorded_command(
            [
                sys.executable,
                str(ROOT / "scripts" / "verify_note.py"),
                "--transcript",
                "evals/fixtures/usable_en_transcript.txt",
                "--note",
                "evals/fixtures/usable_en_note.md",
            ]
        )
        self.assertEqual(
            command,
            "python3 scripts/verify_note.py --transcript evals/fixtures/usable_en_transcript.txt "
            "--note evals/fixtures/usable_en_note.md",
        )
        self.assertNotIn(str(ROOT), command)
        self.assertNotIn("/workspace", command)

    def test_relativize_tree_rewrites_nested_checkout_paths(self) -> None:
        import run_evidence

        rewritten = run_evidence.relativize_tree(
            {"command": str(ROOT / "scripts" / "verify_note.py"), "nested": [str(ROOT)]}
        )
        self.assertEqual(rewritten["command"], "scripts/verify_note.py")
        self.assertEqual(rewritten["nested"], ["."])

    def test_machine_paths_are_refused(self) -> None:
        import run_evidence

        for sample in (
            "/workspace/scripts/verify_note.py",
            "/tmp/tfv-evidence/note.md",
            "/home/someone/transcript.txt",
            r"C:\Users\someone\note.md",
        ):
            with self.assertRaises(SystemExit):
                run_evidence.assert_relative_evidence(sample, "sample")

    def test_repo_relative_evidence_text_is_accepted(self) -> None:
        import run_evidence

        run_evidence.assert_relative_evidence(
            "python3 scripts/verify_note.py --transcript evals/fixtures/usable_en_transcript.txt",
            "sample",
        )


if __name__ == "__main__":
    unittest.main()
