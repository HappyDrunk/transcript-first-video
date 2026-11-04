#!/usr/bin/env python3
"""Unit tests for the quality gate, verifier, and host deposit rules."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import knowledge_note  # noqa: E402
import quality_gate  # noqa: E402
import verify_note  # noqa: E402
import verify_rules  # noqa: E402
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
        segments = quality_gate.prepare_segments(ROLLING_VTT)
        self.assertTrue(segments)
        self.assertTrue(all(segment.start is not None for segment in segments))
        stamped = quality_gate.format_transcript(segments)
        self.assertRegex(stamped.splitlines()[0], r"^\[\d{2}:\d{2}\] ")
        self.assertNotIn("[", result.text)
        restamped = quality_gate.assess(stamped, expected_lang="en")
        self.assertTrue(restamped.passed, restamped.reasons)

    def test_vtt_keeps_start_stamps_and_chunks_on_the_clock(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:04.000\n"
            "Name the buyer outcome before a public number is chosen.\n\n"
            "00:01:05.000 --> 00:01:09.000\n"
            "Do not copy another page and call that research today.\n\n"
            "01:00:05.000 --> 01:00:09.000\n"
            "After an hour, write the one step that was actually spoken.\n"
        )
        segments = quality_gate.prepare_segments(raw)
        self.assertEqual([segment.start for segment in segments], [1.0, 65.0, 3605.0])
        lines = quality_gate.format_transcript(segments).splitlines()
        self.assertTrue(lines[0].startswith("[00:01] "))
        self.assertTrue(lines[1].startswith("[01:05] "))
        self.assertTrue(lines[2].startswith("[01:00:05] "))
        self.assertEqual(
            quality_gate.prepare_transcript(raw),
            "\n".join(segment.text for segment in segments),
        )
        chunks = quality_gate.chunk_segments(
            [
                quality_gate.Segment(0, 10, "early"),
                quality_gate.Segment(400, 410, "still inside eight minutes"),
                quality_gate.Segment(500, 510, "past eight minutes"),
            ]
        )
        self.assertEqual([[item.text for item in group] for group in chunks], [
            ["early", "still inside eight minutes"],
            ["past eight minutes"],
        ])
        long_line = "Pricing talks should name the buyer outcome before a number is published."
        plain = "\n".join([long_line] * 120)
        self.assertGreater(len(plain), quality_gate.CHUNK_MAX_CHARS)
        plain_chunks = quality_gate.chunk_segments(quality_gate.prepare_segments(plain))
        self.assertGreaterEqual(len(plain_chunks), 2)
        self.assertIsNone(plain_chunks[0][0].start)
        with tempfile.TemporaryDirectory() as tmp:
            deposited = youtube_host.finalize_job(
                text=raw,
                video_id="timed-vtt",
                source="settle-transcript:timed-vtt",
                out_dir=Path(tmp),
                expected_lang="en",
                acquisition="yt-dlp",
                caption_language="en",
                caption_kind="manual",
            )
            self.assertEqual(deposited["exit_code"], 0, deposited.get("reason"))
            self.assertIsNone(deposited["caption_trust"])
            self.assertEqual(deposited["duration_seconds"], 3609.0)
            job = Path(tmp) / "youtube_timed-vtt"
            stored = (job / "transcript.txt").read_text(encoding="utf-8")
            self.assertTrue(stored.startswith("[00:01] "))
            self.assertIn("[01:00:05] ", stored)
            saved = json.loads((job / "segments.json").read_text(encoding="utf-8"))
            self.assertEqual(saved[0]["start"], 1.0)
            self.assertEqual(saved[0]["end"], 4.0)
            self.assertTrue((job / "chunks" / "01.txt").is_file())
            self.assertIn('caption_kind: "manual"', (job / "note.scaffold.md").read_text(encoding="utf-8"))

    def test_caption_trust_is_low_only_for_auto_mismatch(self) -> None:
        self.assertEqual(quality_gate.caption_trust("auto", "zh", "en"), "low")
        self.assertIsNone(quality_gate.caption_trust("auto", "en", "en"))
        self.assertIsNone(quality_gate.caption_trust("auto", "zh", None))
        self.assertIsNone(quality_gate.caption_trust("manual", "zh", "en"))
        self.assertIsNone(quality_gate.caption_trust("api", "zh", "en"))

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
        self.assertTrue(verify_note.quotes_transcript(snippet, compact))
        # A mid-transcript snippet is a real quote, and it is still not a note.
        bare = f"transcript: {transcript.as_posix()}\n\n{snippet}\n"
        refused = verify_note.verify(transcript, bare, expected_lang="en")
        self.assertFalse(refused["allowed"])
        self.assertTrue(refused["quoted"])
        self.assertTrue(any("knowledge section" in reason for reason in refused["reasons"]))

    def test_refuse_quote_stub_and_boilerplate_analysis(self) -> None:
        transcript = ROOT / "evals/fixtures/usable_en_transcript.txt"
        stub = (ROOT / "evals/fixtures/quote_stub_note.md").read_text(encoding="utf-8")
        refused = verify_note.verify(transcript, stub, expected_lang="en")
        self.assertFalse(refused["allowed"], refused["reasons"])
        self.assertTrue(refused["quoted"])
        self.assertTrue(any("knowledge section" in reason for reason in refused["reasons"]))
        boilerplate = (ROOT / "evals/fixtures/boilerplate_note.md").read_text(encoding="utf-8")
        canned = verify_note.verify(transcript, boilerplate, expected_lang="en")
        self.assertFalse(canned["allowed"], canned["reasons"])
        self.assertTrue(any("boilerplate" in reason for reason in canned["reasons"]))

    def test_scaffold_is_not_a_finished_note(self) -> None:
        self.assertFalse(hasattr(knowledge_note, "compose"))
        self.assertFalse(hasattr(knowledge_note, "render_note"))
        text = (
            "The warehouse team loses an hour every morning reconciling two spreadsheets. "
            "Export the overnight file before standup. "
            "Paste it into the shared workbook and delete the duplicate tab. "
            "Do not email the raw export to the whole company. "
            "Ask the shift lead to confirm the row count today."
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.txt"
            path.write_text(text + "\n", encoding="utf-8")
            note = knowledge_note.render_scaffold(
                job_id="job_generic",
                video_id="generic",
                source="settle-transcript:generic",
                acquisition="settle-transcript",
                transcript_cite=path.as_posix(),
            )
            self.assertTrue(note.startswith("---\n"))
            self.assertIn("Scaffold only. This file is not a finished knowledge note.", note)
            self.assertNotIn(text[:40], note)
            bodies = dict(knowledge_note._section_bodies(note))
            for heading in knowledge_note.SECTIONS:
                self.assertIn(heading, bodies)
                self.assertEqual(bodies[heading].strip(), "")
            result = verify_note.verify(path, note, expected_lang="en")
            self.assertFalse(result["allowed"], result["reasons"])
            self.assertTrue(
                any("does not analyze" in reason or "quoted_window" in reason for reason in result["reasons"])
            )

    def _speech_quote(self, transcript: Path, size: int = 80) -> str:
        speech = " ".join(transcript.read_text(encoding="utf-8").split())
        return speech[:size]

    def test_one_inapplicable_section_still_passes_shape(self) -> None:
        transcript = ROOT / "evals/fixtures/usable_en_transcript.txt"
        quote = self._speech_quote(transcript)
        note = (ROOT / "evals/fixtures/usable_en_note.md").read_text(encoding="utf-8")
        heading = "## 今天立刻动手一步"
        note = note[: note.index(heading)] + (
            f"{heading}\n\n本节不适用：原文没有可以今天就做的一步。\n\n> {quote}\n"
        )
        result = verify_note.verify(transcript, note, expected_lang="en")
        self.assertTrue(result["allowed"], result["reasons"])

    def test_all_inapplicable_sections_are_not_a_deposit(self) -> None:
        transcript = ROOT / "evals/fixtures/usable_en_transcript.txt"
        quote = self._speech_quote(transcript)
        original = (ROOT / "evals/fixtures/usable_en_note.md").read_text(encoding="utf-8")
        front = original[: original.index("\n---\n", 4) + len("\n---\n")]
        reasons = (
            "原文没有单独的问题陈述。",
            "原文没有分步骤的做法。",
            "原文没有写出不能用的情形。",
            "原文没有可以今天就做的一步。",
        )
        body = ["# fixture", ""]
        for heading, reason in zip(knowledge_note.SECTIONS, reasons):
            body.extend([f"## {heading}", "", f"本节不适用：{reason}", "", f"> {quote}", ""])
        note = front + "\n" + "\n".join(body)
        refused = verify_note.verify(transcript, note, expected_lang="en")
        self.assertFalse(refused["allowed"], refused["reasons"])
        self.assertTrue(
            any(knowledge_note.ALL_INAPPLICABLE_REASON in reason for reason in refused["reasons"])
        )
        self.assertTrue(any(reason.startswith("R03 FAIL:") for reason in refused["reasons"]))

        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            transcript_path = job / "transcript.txt"
            transcript_path.write_text(transcript.read_text(encoding="utf-8"), encoding="utf-8")
            (job / "note.md").write_text(note, encoding="utf-8")
            (job / "note.scaffold.md").write_text("scaffold\n", encoding="utf-8")
            (job / "status.json").write_text(
                json.dumps({"status": "transcript_ready", "finished": False, "note": "note.md", "gate_lang": "en"})
                + "\n",
                encoding="utf-8",
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                code = verify_note.main(["--job", str(job), "--json"])
            self.assertEqual(code, 2)
            payload = json.loads(buf.getvalue())
            self.assertFalse(payload["allowed"])
            self.assertEqual(payload["status"], "no-extractable-content")
            self.assertTrue(payload["note_deleted"])
            self.assertFalse((job / "note.md").exists())
            self.assertTrue((job / "note.scaffold.md").is_file())
            self.assertTrue(transcript_path.is_file())
            status = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "no-extractable-content")
            self.assertFalse(status["finished"])
            self.assertIsNone(status["note"])
            self.assertEqual(status["gate_lang"], "en")

    def test_keyword_salad_fails_r09(self) -> None:
        note_path = ROOT / "evals/adversarial/keyword_salad_en.md"
        transcript = ROOT / "evals/adversarial/saas_pricing_transcript.txt"
        text = note_path.read_text(encoding="utf-8")
        self.assertIn("expect: FAIL R09", text)
        self.assertNotIn("expected-fail-pending", text)
        self.assertIn("Today, do only the first spoken move: Most, founders, set, price, too, low.", text)
        result = verify_note.verify(transcript, text, expected_lang="en")
        self.assertFalse(result["allowed"], result["reasons"])
        self.assertTrue(any(reason.startswith("R09 FAIL:") for reason in result["reasons"]))

    def test_r04_r05_cross_cue_verbatim_span(self) -> None:
        """A ≥40-character quote may cross adjacent cues. Clocks are not speech.

        R05's stamp anchor is the covered cue start closest to the stamp
        (the earlier cue when the distances tie). The ±15s window stays.
        """
        first = "Alpha starts the thought about drainage"
        second = "and beta finishes the thought"
        span = f"{first} {second}"
        bark = "Put a handful of bark in the new pot so water can drain slowly"
        leave = "Do not feed the plant this week after repotting it outside"
        cues = ((0, first), (40, second), (70, bark), (120, leave))
        self.assertLess(len(first), verify_note.QUOTE_WINDOW)
        self.assertLess(len(second), verify_note.QUOTE_WINDOW)
        self.assertGreaterEqual(len(span), verify_note.QUOTE_WINDOW)
        self.assertGreaterEqual(len(bark), verify_note.QUOTE_WINDOW)
        self.assertNotIn(span, first)
        self.assertNotIn(span, second)

        plain = ROOT / "evals/fixtures/usable_en_transcript.txt"
        plain_ctx = verify_rules.build_context(plain, "plain", expected_lang="en")
        self.assertEqual(
            verify_rules._verbatim_haystack(plain_ctx.segments, plain_ctx.gate.text),
            verify_rules._fold(plain_ctx.gate.text),
        )

        def note(path: Path, quote: str, stamp: int | None) -> str:
            cite = path.as_posix()
            quoted = f"> {quality_gate.format_stamp(stamp)} {quote}" if stamp is not None else f"> {quote}"
            return (
                "---\n"
                'title: "cross-cue"\n'
                'source_url: "fixture"\n'
                'video_id: "cross-cue"\n'
                'acquisition: "fixture"\n'
                "gate_passed: true\n"
                f'transcript_path: "{cite}"\n'
                "quoted_window: |-\n"
                f"  {bark}\n"
                "---\n"
                "# note\n\n"
                "## 问题与做法\n\n"
                "Drainage is one continuous instruction across the two spoken cues.\n\n"
                f"{quoted}\n\n"
                "## 完整怎么做\n\n"
                "Set bark in the pot before the plant goes in. That order is the method.\n\n"
                f"> {bark}\n\n"
                "## 翻车或别用\n\n"
                "本节不适用：原文没有写出不能用的情形。\n\n"
                "## 今天立刻动手一步\n\n"
                "本节不适用：原文没有可以今天就做的一步。\n"
            )

        def write(tmp: Path, kind: str) -> Path:
            path = tmp / f"{kind}.txt"
            if kind == "stamped":
                body = quality_gate.format_transcript(
                    [quality_gate.Segment(float(start), float(start) + 3, text) for start, text in cues]
                )
            elif kind == "vtt":
                blocks = ["WEBVTT", ""]
                for start, text in cues:
                    blocks.append(f"00:{start // 60:02d}:{start % 60:02d}.000 --> 00:{(start + 3) // 60:02d}:{(start + 3) % 60:02d}.000")
                    blocks.append(text)
                    blocks.append("")
                body = "\n".join(blocks)
            else:
                blocks = []
                for index, (start, text) in enumerate(cues, start=1):
                    blocks.append(str(index))
                    blocks.append(
                        f"00:{start // 60:02d}:{start % 60:02d},000 --> 00:{(start + 3) // 60:02d}:{(start + 3) % 60:02d},000"
                    )
                    blocks.append(text)
                    blocks.append("")
                body = "\n".join(blocks)
            path.write_text(body, encoding="utf-8")
            return path

        def rules(path: Path, quote: str, stamp: int | None):
            ctx = verify_rules.build_context(path, note(path, quote, stamp), expected_lang="en")
            self.assertIsNotNone(ctx.gate)
            self.assertTrue(ctx.gate.passed, ctx.gate.reasons)
            return ctx, verify_rules.r04_quotes_verbatim(ctx), verify_rules.r05_timestamps(ctx)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kind in ("stamped", "vtt", "srt"):
                path = write(root, kind)
                ctx, r04, r05 = rules(path, span, 40)
                self.assertTrue(r04[1], f"{kind}: {r04[2]}")
                self.assertTrue(r05[1], f"{kind}: {r05[2]}")
                _ctx, r04_start, r05_start = rules(path, span, 0)
                self.assertTrue(r04_start[1], r04_start[2])
                self.assertTrue(r05_start[1], r05_start[2])
                _ctx, _r04_edge, r05_edge = rules(path, span, 25)
                self.assertTrue(r05_edge[1], f"{kind}: {r05_edge[2]}")
                _ctx, _r04_far, r05_far = rules(path, span, 24)
                self.assertFalse(r05_far[1], kind)
                self.assertIn("16s", r05_far[2])
                self.assertIn("[00:40]", r05_far[2])
                _ctx, _r04_tie, r05_tie = rules(path, span, 20)
                self.assertFalse(r05_tie[1], kind)
                self.assertIn("20s from the cue at [00:00]", r05_tie[2])
                _ctx, r04_skip, _r05_skip = rules(path, f"{first} {bark}", 0)
                self.assertFalse(r04_skip[1], kind)
                self.assertIn("not verbatim", r04_skip[2])
                _ctx, r04_para, _r05_para = rules(path, "Alpha begins a remark about drainage and beta ends it", 0)
                self.assertFalse(r04_para[1], kind)
                self.assertIn("not verbatim", r04_para[2])
                _ctx, _r04_late, r05_late = rules(path, bark, 86)
                self.assertFalse(r05_late[1], kind)
                self.assertIn("16s", r05_late[2])
                self.assertIn("[01:10]", r05_late[2])
                _ctx, _r04_near, r05_near = rules(path, bark, 85)
                self.assertTrue(r05_near[1], f"{kind}: {r05_near[2]}")

            stamped = write(root, "stamped")
            held = verify_rules.build_context(stamped, note(stamped, span, 40), expected_lang="en")
            for rule in (
                verify_rules.r02_frontmatter,
                verify_rules.r08_proper_nouns,
                verify_rules.r13_today_step,
                verify_rules.r16_quote_anchored_nouns,
            ):
                result = rule(held)
                self.assertTrue(result[1], result)


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

    def test_excerpt_keeps_short_transcript_lines(self) -> None:
        text = (
            "Alpha line about repotting the plant today.\n"
            "Beta line about the fresh mix and the water."
        )
        collapsed, lines = youtube_host.transcript_excerpt(text, limit=48)
        self.assertEqual(lines, ["Alpha line about repotting the plant today."])
        self.assertEqual(collapsed, "Alpha line about repotting the plant today.")
        whole, all_lines = youtube_host.transcript_excerpt(text, limit=360)
        self.assertEqual(all_lines, text.splitlines())
        self.assertEqual(whole, " ".join(all_lines))

    def test_scaffold_exit_code_stays_zero(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = youtube_host._emit(
                {"status": "transcript_ready", "finished": False, "exit_code": 0},
                as_json=True,
            )
        self.assertEqual(code, 0)

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
            self.assertEqual(ok["status"], "transcript_ready")
            self.assertFalse(ok["finished"])
            self.assertIsNone(ok["note"])
            self.assertIsNone(ok["verifier"])
            note_path = out / "youtube_usable-en" / "note.md"
            scaffold_path = out / "youtube_usable-en" / "note.scaffold.md"
            transcript_path = out / "youtube_usable-en" / "transcript.txt"
            self.assertFalse(note_path.exists())
            self.assertTrue(scaffold_path.is_file())
            self.assertTrue(transcript_path.is_file())
            segments_path = out / "youtube_usable-en" / "segments.json"
            chunk_path = out / "youtube_usable-en" / "chunks" / "01.txt"
            self.assertTrue(segments_path.is_file())
            self.assertTrue(chunk_path.is_file())
            self.assertEqual(ok["chunk_count"], 1)
            self.assertIsNone(ok["caption_trust"])
            self.assertIsNone(ok["duration_seconds"])
            self.assertFalse(transcript_path.read_text(encoding="utf-8").lstrip().startswith("["))
            note = scaffold_path.read_text(encoding="utf-8")
            cite = youtube_host.cite_path(transcript_path)
            self.assertEqual(ok["scaffold"], youtube_host.cite_path(scaffold_path))
            self.assertIn(cite, note)
            self.assertTrue(note.startswith("---\n"))
            self.assertIn('title: "youtube_usable-en"', note)
            self.assertIn('source_url: "settle-transcript:usable-en"', note)
            self.assertIn('video_id: "usable-en"', note)
            self.assertIn('acquisition: "settle-transcript"', note)
            self.assertIn("gate_passed: true", note)
            self.assertIn(f'transcript_path: "{cite}"', note)
            self.assertIn("quoted_window: |-", note)
            self.assertIn("not a finished knowledge note", note)
            for heading in ("问题与做法", "完整怎么做", "翻车或别用", "今天立刻动手一步"):
                self.assertIn(f"## {heading}", note)
            self.assertNotIn("## Quoted window", note)
            self.assertNotIn("The quoted window is copied", note)
            self.assertNotIn("root-bound", note)
            status = json.loads((out / "youtube_usable-en" / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "transcript_ready")
            self.assertFalse(status["finished"])
            self.assertIsNone(status["note"])
            self.assertNotIn("title", status)
            self.assertNotIn("description", status)
            checked = verify_note.verify(transcript_path, note, expected_lang="en")
            self.assertFalse(checked["allowed"], checked["reasons"])

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
            self.assertFalse(scaffold_path.exists())
            self.assertFalse(transcript_path.exists())
            self.assertFalse(segments_path.exists())
            self.assertFalse(chunk_path.exists())
            self.assertTrue((out / "youtube_usable-en" / "status.json").is_file())

            blocked = youtube_host.finalize_job(
                text=loop,
                video_id="zh-loop",
                source="settle-transcript:zh-loop",
                out_dir=out,
                expected_lang="zh",
                acquisition="settle-transcript",
            )
            trusted = youtube_host.finalize_job(
                text=usable,
                video_id="auto-mismatch",
                source="settle-transcript:auto-mismatch",
                out_dir=out,
                expected_lang="en",
                acquisition="yt-dlp",
                caption_language="zh",
                caption_kind="auto",
            )
            self.assertEqual(trusted["caption_trust"], "low")
            self.assertEqual(trusted["exit_code"], 0)
            mismatch_note = (out / "youtube_auto-mismatch" / "note.scaffold.md").read_text(encoding="utf-8")
            self.assertIn('caption_kind: "auto"', mismatch_note)
            self.assertIn('caption_trust: "low"', mismatch_note)
            self.assertIn('caption_language: "zh"', mismatch_note)

            self.assertEqual(blocked["status"], "quality_gate_failed")
            self.assertFalse((out / "youtube_zh-loop" / "note.md").exists())
            self.assertFalse((out / "youtube_zh-loop" / "note.scaffold.md").exists())
            self.assertFalse((out / "youtube_zh-loop" / "segments.json").exists())
            self.assertFalse((out / "youtube_zh-loop" / "chunks").exists())
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
            self.assertEqual(ok["status"], "transcript_ready")
            self.assertFalse(ok["finished"])
            self.assertIsNone(ok["note"])
            job = out / f"x_{status_id}"
            note_path = job / "note.md"
            scaffold_path = job / "note.scaffold.md"
            transcript_path = job / "transcript.txt"
            self.assertFalse(note_path.exists())
            self.assertTrue(scaffold_path.is_file())
            self.assertTrue(transcript_path.is_file())
            note = scaffold_path.read_text(encoding="utf-8")
            self.assertIn(f"x_{status_id}", note)
            self.assertIn("gate_passed: true", note)
            self.assertIn(f'video_id: "{status_id}"', note)
            self.assertIn("not a finished knowledge note", note)
            for heading in ("问题与做法", "完整怎么做", "翻车或别用", "今天立刻动手一步"):
                self.assertIn(f"## {heading}", note)
            self.assertNotIn("## Quoted window", note)
            checked = verify_note.verify(transcript_path, note, expected_lang="en")
            self.assertFalse(checked["allowed"], checked["reasons"])
            path_only = f"Title: done.\n\ntranscript: {youtube_host.cite_path(transcript_path)}\n"
            refused = verify_note.verify(transcript_path, path_only, expected_lang="en")
            self.assertFalse(refused["allowed"])
            self.assertTrue(refused["cited"])
            self.assertFalse(refused["quoted"])
            status = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertIsNone(status["note"])
            self.assertFalse(status["finished"])
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
            self.assertFalse(scaffold_path.exists())
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
