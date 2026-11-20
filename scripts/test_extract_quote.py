from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
