from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_phase2e
import verify_rules


SCRIPT = Path(__file__).with_name("extract_quote.py")
FIRST = "A finding can survive review only when its source is clear."
SECOND = "Keep the exact wording and include the original numbers."


class SpeechQuoteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.job = Path(temporary.name)
        (self.job / "status.json").write_text('{"state":"locked"}', encoding="utf-8")
        (self.job / "selection.md").write_text("Do not consult selection.", encoding="utf-8")

    def write_transcript(self, text, cues=None):
        (self.job / "transcript.txt").write_text(text, encoding="utf-8")
        if cues is not None:
            data = [dict(start=start, end=end, text=cue) for start, end, cue in cues]
            (self.job / "segments.json").write_text(json.dumps(data), encoding="utf-8")

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.job.iterdir()}

    def extract(self, start="00:10", end="00:14", *, env=None):
        before = self.snapshot()
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), str(self.job), start, end],
            capture_output=True, encoding="utf-8", check=False, env=env,
        )
        self.assertEqual(self.snapshot(), before)
        return result

    def test_copies_the_cues_verbatim_and_preserves_the_precise_actual_bounds(self):
        cues = [(9.5, 10.75, FIRST), (11.25, 14.5, SECOND), (14.6, 16, "Omit this.")]
        self.write_transcript(
            f"[00:09] {FIRST}\n[00:11] {SECOND}\n[00:14] Omit this.\n", cues,
        )

        result = self.extract()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"> [00:09] {FIRST} {SECOND}\n")
        self.assertIn("00:09.5", result.stderr)
        self.assertIn("00:14.5", result.stderr)
        path = self.job / "transcript.txt"
        index = verify_rules.TranscriptIndex(verify_rules.transcript_segments(
            path.read_text(encoding="utf-8"), path.with_name("segments.json"),
        ))
        quotes, errors = verify_rules._end_quotes(result.stdout, index, None)
        self.assertEqual(errors, [])
        self.assertTrue(quotes[0].timed)
        self.assertEqual(quotes[0].anchor.start, 9.5)

    def test_timestamp_only_archive_reports_last_start_and_supports_hours(self):
        self.write_transcript(f"[01:02:05] {FIRST}\n[01:02:08] {SECOND}\n")

        result = self.extract("01:02:04", "01:02:08")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"> [01:02:05] {FIRST}\n")
        self.assertIn("last cue starts at 01:02:05", result.stderr)

    def test_reports_missing_clock_without_emitting_a_quote(self):
        self.write_transcript(FIRST)

        result = self.extract()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("transcript.txt", result.stderr)
        self.assertIn("no cue clocks", result.stderr)

    def test_reports_a_gap_or_unclocked_cue_inside_the_range(self):
        for raw, reason in (
            (f"[00:10] {FIRST}\n[00:17] {SECOND}", "00:10"),
            (f"[00:10] {FIRST}\nUntimed speech\n[00:12] {SECOND}", "cue 2"),
        ):
            with self.subTest(reason=reason):
                self.write_transcript(raw)

                result = self.extract("00:10", "00:20")

                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn("not continuous", result.stderr)
                self.assertIn(reason, result.stderr)

    def test_uses_the_gate_length_and_reports_the_selected_location(self):
        for length in (39, 40):
            with self.subTest(length=length):
                fragment = "字幕原话只在此处取用" * 4
                fragment = fragment[:length]
                self.assertEqual(len(fragment), length)
                self.write_transcript(f"[00:11] {fragment}")

                result = self.extract()

                if length == 39:
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("39", result.stderr)
                    self.assertIn("40", result.stderr)
                    self.assertIn("00:11", result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, f"> [00:11] {fragment}\n")

    def test_reports_an_empty_range_at_the_requested_location(self):
        self.write_transcript(f"[00:20] {FIRST}")

        result = self.extract()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("no timed captions", result.stderr)
        self.assertIn("00:10", result.stderr)
        self.assertIn("00:14", result.stderr)

    def test_redirected_quote_preserves_unicode_in_a_legacy_locale(self):
        text = "A public record can retain punctuation and spelling such as Café — 官方。"
        self.write_transcript(f"[00:11] {text}")

        result = self.extract(env={**os.environ, "PYTHONIOENCODING": "ascii"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"> [00:11] {text}\n")


class ScreenQuoteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.job = Path(temporary.name)
        self.screen = self.job / "screen.txt"
        self.env = os.environ.copy()
        self.env.pop("TFV_SCREEN_MODE", None)

    def write_screen(self, source, *, mode="slides", state="ready"):
        self.screen.write_text(source, encoding="utf-8")
        status = {"status": "transcript_ready", "duration_seconds": 120, "expected_lang": "en"}
        if mode is not None:
            status["screen_ocr"] = {
                "requested_mode": mode, "mode": mode, "state": state,
                "sha256": hashlib.sha256(self.screen.read_bytes()).hexdigest(),
            }
        (self.job / "status.json").write_text(json.dumps(status), encoding="utf-8")

    def snapshot(self):
        return {
            path.relative_to(self.job): None if path.is_dir() else path.read_bytes()
            for path in self.job.rglob("*")
        }

    def extract(self, start="03:12", end="03:14", *, flag_last=False, ascii_streams=False):
        positionals = [str(self.job), start, end]
        args = positionals + ["--screen"] if flag_last else ["--screen"] + positionals
        python_flags = [] if ascii_streams else ["-X", "utf8"]
        env = dict(self.env, PYTHONIOENCODING="ascii" if ascii_streams else "utf-8")
        before = self.snapshot()
        result = subprocess.run(
            [sys.executable, *python_flags, str(SCRIPT), *args],
            env=env, capture_output=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(self.snapshot(), before)
        return result

    def assert_plain_diagnostic(self, result):
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("UnicodeEncodeError", result.stderr)
        self.assertNotIn("usage:", result.stderr.lower())

    def assert_rejected(self, result):
        self.assertEqual(result.returncode, 1, result)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.strip())
        self.assert_plain_diagnostic(result)

    def test_verifier_accepts_verbatim_screen_quotes_in_both_modes(self):
        start_line = "[01:35][画面] 检查记录：  材料齐全。"
        inside_line = "[01:36][画面] 复核项目：排水孔。"
        source = "\n".join((
            "[01:34][画面] 准备材料。",
            start_line,
            inside_line,
            "[01:37][画面] 完成复核。",
            "",
        ))
        (self.job / "transcript.txt").write_text(test_phase2e.TRANSCRIPT, encoding="utf-8")
        (self.job / "selection.md").write_bytes(
            (test_phase2e.FIXTURES / "usable_selection.md").read_bytes()
        )
        note_path = self.job / "note.md"
        for mode in ("slides", "nameplate"):
            for flag_last in (False, True):
                with self.subTest(mode=mode, flag_last=flag_last):
                    self.write_screen(source, mode=mode)
                    note_path.write_text(test_phase2e.NOTE, encoding="utf-8")
                    result = self.extract("01:35", "01:37", flag_last=flag_last)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, f"> {start_line}\n> {inside_line}\n")

                    note = test_phase2e.with_screen(
                        test_phase2e.NOTE, "画面记录材料齐全，并列出排水孔作为复核项目。 ⏱ 01:35 ⏱ 01:36",
                    )
                    note_path.write_text(note + result.stdout, encoding="utf-8")
                    verified = subprocess.run(
                        [sys.executable, "-X", "utf8", str(SCRIPT.with_name("verify_note.py")),
                         "--job", str(self.job), "--json"],
                        env=dict(self.env, PYTHONIOENCODING="utf-8"),
                        capture_output=True, encoding="utf-8", timeout=30,
                    )
                    self.assertEqual(verified.returncode, 0, verified)
                    self.assertIs(json.loads(verified.stdout)["allowed"], True)

    def test_hour_timestamps_preserve_the_half_open_window(self):
        line = "[01:03:12][画面] 工序确认。"
        self.write_screen(
            f"[01:03:11][画面] 工序准备。\n{line}\n[01:03:13][画面] 工序完成。\n"
        )
        result = self.extract("01:03:12", "01:03:13")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"> {line}\n")

    def test_counts_only_in_range_uncertain_lines(self):
        trusted = "[03:12][画面] 材料登记。"
        self.write_screen(
            f"{trusted}\n[03:13][画面?] 字迹模糊。\n[03:13][画面?] 编号不清。\n"
            "[03:14][画面?] 来源待查。\n"
        )
        warning = "跳过 2 行存疑画面（不能当依据）"
        with self.subTest(trusted=True):
            result = self.extract()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, f"> {trusted}\n")
            self.assertIn(warning, result.stderr)
        with self.subTest(trusted=False):
            result = self.extract("03:13", "03:14")
            self.assert_rejected(result)
            self.assertIn(warning, result.stderr)
            diagnostic = result.stderr.replace(warning, "")
            self.assertRegex(
                diagnostic.lower(),
                r"(?:无|没有|未找到|未发现|找不到|不含).*(?:画面|可信)|no (?:trusted|usable|matching).*",
            )

    def test_preserves_column_breaks_and_omits_slide_markers(self):
        left = ("[03:12][画面] 材料登记。", "[03:12][画面] 领取工具。")
        right = ("[03:12][画面] 检查尺寸。", "[03:12][画面] 记录结果。")
        for trailing_column in (right, ("[03:12][画面?] 字迹模糊。",)):
            with self.subTest(trailing_column=trailing_column):
                self.write_screen("\n".join((
                    "[03:12][幻灯片 1] frame-000001.png", *left, "",
                    *trailing_column, "[03:14][幻灯片 2] frame-000002.png",
                    "[03:14][画面] 下一页。", "",
                )))
                result = self.extract()
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = "".join(f"> {line}\n" for line in left)
                trusted = left
                if trailing_column == right:
                    expected += "\n" + "".join(f"> {line}\n" for line in right)
                    trusted += right
                self.assertNotIn("[幻灯片", result.stdout)
                self.assertEqual(result.stdout, expected)
                quotes, errors = verify_rules._end_quotes(
                    result.stdout, verify_rules.TranscriptIndex([]),
                    verify_rules._screen_index(self.screen),
                )
                self.assertEqual(errors, [])
                self.assertEqual(len(quotes), len(trusted))
                self.assertTrue(all(quote.screen and quote.timed and quote.matches for quote in quotes))

    def test_preserves_verbatim_spacing_after_screen_tag(self):
        line = "[03:12][画面]  材料登记。"
        self.write_screen(f"{line}\n")

        result = self.extract()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"> {line}\n")
        quotes, errors = verify_rules._end_quotes(
            result.stdout, verify_rules.TranscriptIndex([]),
            verify_rules._screen_index(self.screen),
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(quotes), 1)
        self.assertTrue(quotes[0].screen and quotes[0].timed and quotes[0].matches)

    def test_rejects_ready_status_when_screen_file_is_missing(self):
        self.write_screen("[03:12][画面] 材料登记。\n")
        self.screen.unlink()

        self.assert_rejected(self.extract())

    def test_rejects_screen_content_changed_after_hashing(self):
        self.write_screen("[03:12][画面] 材料登记。\n")
        self.screen.write_text("[03:12][画面] 复核完成。\n", encoding="utf-8")
        self.assert_rejected(self.extract())

    def test_rejects_off_nonready_and_missing_screen_status(self):
        for mode, state in (("off", "skipped"), ("off", "ready"),
                            ("slides", "fallback"), (None, None)):
            with self.subTest(mode=mode, state=state):
                self.write_screen("[03:12][画面] 材料登记。\n", mode=mode, state=state)
                self.assert_rejected(self.extract())

    def test_cli_handles_cjk_under_ascii_streams(self):
        self.write_screen("[03:12][画面] 材料登记。\n[03:13][画面?] 字迹模糊。\n")
        result = self.extract(ascii_streams=True)
        self.assertEqual(result.returncode, 0, result)
        self.assertTrue(result.stdout.strip())
        self.assertTrue(result.stderr.strip())
        self.assert_plain_diagnostic(result)
        self.assertNotIn("UnicodeEncodeError", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_main_escapes_unencodable_output_and_errors_under_ascii_streams(self):
        for mock_behavior, code, stream in (
            (r'return_value=("> [03:12] \ud800", "03:12")', 0, "stdout"),
            (r'side_effect=ValueError("bad \ud800")', 1, "stderr"),
        ):
            with self.subTest(stream=stream):
                runner = f"""
import sys
from unittest.mock import patch
import extract_quote

sys.stdout.reconfigure(encoding="ascii", errors="strict")
sys.stderr.reconfigure(encoding="ascii", errors="strict")
sys.argv = ["extract_quote.py", "fixture", "03:12", "03:14"]
with patch.object(extract_quote, "extract", {mock_behavior}):
    raise SystemExit(extract_quote.main())
"""
                result = subprocess.run(
                    [sys.executable, "-c", runner], cwd=SCRIPT.resolve().parent,
                    env=dict(self.env, PYTHONIOENCODING="ascii"),
                    capture_output=True, encoding="ascii", timeout=30,
                )
                self.assertEqual(result.returncode, code, result)
                self.assertIn(r"\ud800", getattr(result, stream))
                self.assert_plain_diagnostic(result)
                self.assertNotIn("UnicodeEncodeError", result.stdout)
                self.assertNotIn("Traceback", result.stdout)


if __name__ == "__main__":
    unittest.main()
