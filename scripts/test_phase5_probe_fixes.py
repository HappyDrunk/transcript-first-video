#!/usr/bin/env python3
"""RED/GREEN regression suite for long-transcript gate, C04c review state machine, and CJK numeral rules."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import c04c_review  # noqa: E402
import quality_gate  # noqa: E402
import verify_rules as rules  # noqa: E402
from test_phase2e import NOTE, TRANSCRIPT  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def _make_zipf_lecture(word_count: int = 17_000, *, seed: int = 20261122) -> str:
    """Build a synthetic natural-English Zipf-like lecture (~1,450 unique words)."""
    rng = random.Random(seed)
    onsets = (
        "b", "c", "d", "f", "g", "h", "k", "l", "m", "n", "p", "r", "s", "t", "v", "w",
        "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "sc", "sh", "sl",
        "sp", "st", "tr", "th", "ch", "wh",
    )
    vowels = ("a", "e", "i", "o", "u", "ea", "ee", "ai", "oa", "ou", "oo")
    codas = (
        "", "b", "d", "f", "g", "k", "l", "m", "n", "p", "r", "s", "t",
        "nd", "nt", "st", "rt", "rk", "ld", "lt", "mp", "nk", "ng", "sh", "ch", "th",
    )
    suffixes = ("", "", "", "s", "ed", "ing", "er", "al", "ic", "ly", "tion", "ment")
    core = [
        "the", "to", "of", "and", "in", "that", "is", "we", "you", "it",
        "for", "on", "this", "so", "have", "are", "be", "with", "as", "if",
        "can", "about", "what", "not", "at", "from", "one", "or", "but", "by",
        "they", "all", "do", "there", "an", "which", "when", "then", "now", "just",
        "like", "how", "more", "some", "here", "because", "out", "into", "up", "very",
    ]
    vocab: list[str] = list(core)
    seen = set(vocab)
    while len(vocab) < 1_450:
        syl1 = rng.choice(onsets) + rng.choice(vowels) + rng.choice(codas)
        syl2 = rng.choice(onsets) + rng.choice(vowels) + rng.choice(codas)
        word = (syl1 + (syl2 if rng.random() < 0.65 else "") + rng.choice(suffixes)).lower()
        if len(word) >= 3 and word not in seen:
            seen.add(word)
            vocab.append(word)

    # Zipf-like weights s=1.08 yield global unique_word_ratio ~0.085 at 17,000 words
    # while every 500-word window maintains healthy lexical diversity (~0.35-0.48).
    weights = [1.0 / ((rank + 1) ** 1.08) for rank in range(len(vocab))]
    words = rng.choices(vocab, weights=weights, k=word_count)
    lines: list[str] = []
    idx = 0
    while idx < len(words):
        sent_len = rng.randint(10, 18)
        chunk = words[idx : idx + sent_len]
        if chunk:
            chunk[0] = chunk[0].capitalize()
            lines.append(" ".join(chunk) + ".")
        idx += sent_len
    return "\n".join(lines)


class LongTranscriptQualityGateTests(unittest.TestCase):
    def test_long_zipf_lecture_passes_windowed_unique_word_ratio(self) -> None:
        short_keys = set(quality_gate.assess("This is a short valid English transcript sentence for schema parity.", expected_lang="en").metrics)
        lecture = _make_zipf_lecture(17_000, seed=20261122)
        result = quality_gate.assess(lecture, expected_lang="en")
        self.assertGreaterEqual(result.metrics["latin_words"], 17_000)
        self.assertLess(result.metrics["unique_word_ratio"], quality_gate.UNIQUE_WORD_FLOOR)
        self.assertEqual(set(result.metrics), short_keys, "metrics schema must remain unchanged for long transcripts")
        self.assertTrue(result.passed, f"expected healthy long lecture to pass: {result.reasons}")

    def test_long_400_word_period_repeat_rejected(self) -> None:
        block = _make_zipf_lecture(400, seed=99)
        multiline_repeat = "\n".join([block] * 42)
        singleline_repeat = " ".join(block.splitlines() * 42)
        # 3-copy punctuation-free 400-word block (~1,200 words, unique tokens per copy)
        distinct_400 = " ".join(f"tok{chr(97 + (i // 26) % 26)}{chr(97 + i % 26)}e" for i in range(400))
        three_copy_singleline = " ".join([distinct_400] * 3)
        for label, payload, min_words in (
            ("multiline", multiline_repeat, 16_000),
            ("singleline", singleline_repeat, 16_000),
            ("three_copy_singleline", three_copy_singleline, 1_200),
        ):
            with self.subTest(form=label):
                result = quality_gate.assess(payload, expected_lang="en")
                self.assertGreaterEqual(result.metrics["latin_words"], min_words)
                self.assertFalse(result.passed, f"{label} 400-word repeat must be rejected")
                self.assertTrue(
                    any("looping repeats" in reason for reason in result.reasons),
                    result.reasons,
                )

    def test_localized_asr_loop_inside_long_lecture_rejected(self) -> None:
        rng = random.Random(7)
        prefix = _make_zipf_lecture(8_000, seed=101)
        suffix = _make_zipf_lecture(8_500, seed=202)
        # 500-word localized loop with only 20 distinct words (window unique ratio = 0.04 < 0.08),
        # shuffled so no single 4-gram exceeds global NGRAM_MIN_COVERAGE.
        small_vocab = [
            "alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "sigma",
            "omega", "kappa", "vector", "matrix", "scalar", "tensor", "kernel", "signal",
            "filter", "buffer", "stream", "packet",
        ]
        loop_words = [rng.choice(small_vocab) for _ in range(500)]
        loop_lines = [" ".join(loop_words[i : i + 12]) + "." for i in range(0, 500, 12)]
        combined = "\n".join([prefix, *loop_lines, suffix])
        result = quality_gate.assess(combined, expected_lang="en")
        self.assertGreaterEqual(result.metrics["latin_words"], 17_000)
        self.assertFalse(result.passed, "localized 500-word low-diversity stretch must be rejected")
        self.assertTrue(
            any("looping repeats" in reason for reason in result.reasons),
            result.reasons,
        )

    def test_short_transcript_below_1000_words_still_uses_global_floor(self) -> None:
        rng = random.Random(13)
        # 600 words from 55 distinct words -> global unique_word_ratio ~0.092 < 0.12
        # without triggering single-word dominance or repeated-sentence/4-gram checks.
        vocab = [f"word{chr(97 + i // 26)}{chr(97 + i % 26)}e" for i in range(55)]
        words = [rng.choice(vocab) for _ in range(600)]
        text = "\n".join(" ".join(words[i : i + 15]) + "." for i in range(0, len(words), 15))
        result = quality_gate.assess(text, expected_lang="en")
        self.assertLess(result.metrics["latin_words"], 1000)
        self.assertLess(result.metrics["unique_word_ratio"], quality_gate.UNIQUE_WORD_FLOOR)
        self.assertFalse(result.passed, "short low-diversity transcript must still be rejected")
        self.assertTrue(
            any("looping repeats" in reason for reason in result.reasons),
            result.reasons,
        )

    def test_tail_window_boundary_1200_words_loop_in_tail_rejected(self) -> None:
        rng = random.Random(31)
        head = _make_zipf_lecture(700, seed=303)
        small_vocab = [
            "alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "sigma",
            "omega", "kappa", "vector", "matrix", "scalar", "tensor", "kernel", "signal",
            "filter", "buffer", "stream", "packet",
        ]
        tail_words = [rng.choice(small_vocab) for _ in range(500)]
        tail = "\n".join(" ".join(tail_words[i : i + 12]) + "." for i in range(0, 500, 12))
        combined = head + "\n" + tail
        result = quality_gate.assess(combined, expected_lang="en")
        self.assertEqual(result.metrics["latin_words"], 1200)
        self.assertFalse(result.passed, "1200-word transcript with loop in trailing 500-word window must be rejected")
        self.assertTrue(
            any("looping repeats" in reason for reason in result.reasons),
            result.reasons,
        )


CLAIM_TWO_CM = "stopping two centimeters below the rim"
BAD_NUMERIC = NOTE.replace(CLAIM_TWO_CM, "stopping 21.1 centimeters below the rim", 1)
VALUELESS_CLAIM_SRC = "loosen the soil with your fingers. ⏱ 00:00"
VALUELESS_CLAIM_NEW = "loosen the soil with your 17 fingers. ⏱ 00:00"
VALUELESS_CLAIM_ALT = "loosen the soil with your 19 fingers. ⏱ 00:00"
BROKEN_QUOTE_NOTE = NOTE.replace("> [00:30] Snip the black", "> [00:30] Preserve the black", 1)


class PostReviewC04cDeadlockTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.job = self.root / "job"
        self.job.mkdir()
        self.output = self.root / "reading.md"
        (self.job / "transcript.txt").write_text(TRANSCRIPT, encoding="utf-8")
        (self.job / "selection.md").write_bytes((ROOT / "evals/fixtures/usable_selection.md").read_bytes())
        (self.job / "status.json").write_text(
            json.dumps({
                "status": "transcript_ready",
                "expected_lang": "en",
                "duration_seconds": 120,
                "next_step": "write-note",
            }),
            encoding="utf-8",
        )
        self.note(NOTE)

    def note(self, body: str) -> None:
        (self.job / "note.md").write_bytes(body.encode("utf-8"))

    def status(self) -> dict:
        return json.loads((self.job / "status.json").read_text(encoding="utf-8"))

    def command(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *args],
            cwd=ROOT,
            env=dict(os.environ, TFV_SCREEN_MODE="off"),
            capture_output=True,
            encoding="utf-8",
            timeout=25,
        )

    def submit(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.command("verify_note.py", "--job", str(self.job), "--with-coverage", "--json", *args)

    def render(self, required: bool = True) -> subprocess.CompletedProcess[str]:
        args = ("--require-review",) if required else ()
        return self.command("render_reading_note.py", "--task-dir", str(self.job), "--output", str(self.output), *args)

    def write_receipt(self, rows: str, *, result: str = "changes", followup: str = "") -> str:
        verifier = self.status()["verifier"]
        header = {
            "inputs": verifier["inputs"],
            "result": result,
            "c04c_sha256": verifier.get("c04c_sha256"),
        }
        content = (
            f"<!-- tfv-review: {json.dumps(header, ensure_ascii=False)} -->\n\n"
            f"## C04c 告警裁定\n\n{rows}\n{followup}"
        )
        (self.job / "review.md").write_text(content, encoding="utf-8")
        return content

    def start_changes_review(self, initial_note: str = BAD_NUMERIC) -> str:
        self.note(initial_note)
        checked = self.submit()
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        return self.write_receipt(
            "- C04c-001 | 21.1 | two centimeters below the rim | 真错",
            result="changes",
        )

    def test_c04c_final_allows_valueless_number_warning_with_verbatim_linked_excerpt(self) -> None:
        # Initial review must STILL require 待补 when linked quotes have values == []
        wrong_initial = NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1)
        self.note(wrong_initial)
        first = self.submit()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.write_receipt(
            "- C04c-001 | 17 | loosen the soil with your fingers | 误报",
            result="clear",
        )
        self.assertNotEqual(self.render().returncode, 0, "initial() must still reject non-numeric excerpt")

        # Post-review final(): a newly introduced numeric warning whose linked quotes have values == []
        # must be adjudicable via - 终稿 using a verbatim linked excerpt.
        self.setUp()
        base_receipt = self.start_changes_review()
        confirmed = "- 已修 C04c-001 | stopping two centimeters below the rim\n"
        rev1 = NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1)
        self.note(rev1)
        (self.job / "review.md").write_text(base_receipt + confirmed, encoding="utf-8")
        pending = self.submit()
        self.assertNotEqual(pending.returncode, 0)
        verifier = self.status()["verifier"]
        self.assertEqual([row["term"] for row in verifier["c04c"]], ["17"])
        self.assertTrue(all(not q["values"] for q in verifier["c04c"][0]["citations"]))

        # Non-verbatim excerpt must still fail
        (self.job / "review.md").write_text(
            base_receipt + confirmed
            + f'<!-- tfv-c04c-final: {verifier["c04c_sha256"]} -->\n'
            + "- 终稿 C04c-001 | 17 | not in linked quote | 误报\n",
            encoding="utf-8",
        )
        self.assertNotEqual(self.render().returncode, 0)

        # Verbatim linked excerpt succeeds cleanly
        (self.job / "review.md").write_text(
            base_receipt + confirmed
            + f'<!-- tfv-c04c-final: {verifier["c04c_sha256"]} -->\n'
            + "- 终稿 C04c-001 | 17 | loosen the soil with your fingers | 误报\n",
            encoding="utf-8",
        )
        done = self.render()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(self.output.is_file())
        self.assertTrue(self.status()["finished"])

        # Sanity: when linked quotes DO have numeric values, - 终稿 still requires a numeric excerpt
        self.setUp()
        base_receipt = self.start_changes_review()
        rev_with_vals = NOTE.replace("three days. ⏱ 01:00", "12 days. ⏱ 01:00", 1)
        self.note(rev_with_vals)
        (self.job / "review.md").write_text(base_receipt + confirmed, encoding="utf-8")
        self.assertNotEqual(self.submit().returncode, 0)
        verifier = self.status()["verifier"]
        (self.job / "review.md").write_text(
            base_receipt + confirmed
            + f'<!-- tfv-c04c-final: {verifier["c04c_sha256"]} -->\n'
            + "- 终稿 C04c-001 | 12 | Do not water again | 误报\n",
            encoding="utf-8",
        )
        self.assertNotEqual(self.render().returncode, 0, "excerpt without number must still fail when quote has values")

    def test_post_review_uncleared_c04c_does_not_deadlock_revision2_edit(self) -> None:
        base_receipt = self.start_changes_review()
        confirmed = "- 已修 C04c-001 | stopping two centimeters below the rim\n"
        # Revision 1 introduces an uncleared C04c WARN -> passes verify+coverage, fails c04c_review.final()
        self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1))
        (self.job / "review.md").write_text(base_receipt + confirmed, encoding="utf-8")
        first = self.submit()
        self.assertNotEqual(first.returncode, 0)
        st1 = self.status()
        self.assertEqual(len(st1["review"]["revisions"]), 1)
        self.assertEqual(st1["review"]["failures"], 0)
        self.assertEqual(st1["status"], "transcript_ready")

        # Writer edits note.md to eliminate the WARN (Revision 2) -> must NOT deadlock!
        self.note(NOTE)
        second = self.submit()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        st2 = self.status()
        self.assertTrue(st2["finished"])
        self.assertEqual(st2["status"], "finished")
        self.assertEqual(len(st2["review"]["revisions"]), 2)
        self.assertEqual(st2["review"]["failures"], 1)
        rendered = self.render()
        self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
        self.assertTrue(self.output.is_file())

    def test_post_review_allowance_cap_and_stop_for_user_writes_issues_md(self) -> None:
        # Subcase A: Revision 1 (uncleared) -> Revision 2 (uncleared) -> 3rd distinct note.md edit -> stop_for_user
        with self.subTest(case="third_distinct_note_stops_cleanly"):
            base_receipt = self.start_changes_review()
            confirmed = "- 已修 C04c-001 | stopping two centimeters below the rim\n"
            (self.job / "review.md").write_text(base_receipt + confirmed, encoding="utf-8")

            self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1))
            self.assertNotEqual(self.submit().returncode, 0)

            self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_ALT, 1))
            self.assertNotEqual(self.submit().returncode, 0)
            st2 = self.status()
            self.assertEqual(len(st2["review"]["revisions"]), 2)
            self.assertEqual(st2["review"]["failures"], 1)

            # 3rd distinct note.md edit must transition cleanly to needs_user_input + issues.md
            self.note(NOTE)
            third = self.submit()
            self.assertNotEqual(third.returncode, 0)
            st3 = self.status()
            self.assertEqual(st3["status"], "needs_user_input")
            self.assertEqual(st3["next_step"], "return-draft-and-issues")
            self.assertFalse(st3["finished"])
            self.assertTrue((self.job / "issues.md").is_file())
            self.assertIn("exhausted", (self.job / "issues.md").read_text(encoding="utf-8"))

        # Subcase A2: Restoring baseline after 2 pending revisions must ALSO stop cleanly with issues.md
        with self.subTest(case="restore_baseline_after_two_revisions_stops_cleanly"):
            self.setUp()
            base_receipt = self.start_changes_review()
            confirmed = "- 已修 C04c-001 | stopping two centimeters below the rim\n"
            (self.job / "review.md").write_text(base_receipt + confirmed, encoding="utf-8")

            self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1))
            self.assertNotEqual(self.submit().returncode, 0)

            self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_ALT, 1))
            self.assertNotEqual(self.submit().returncode, 0)

            # Restore exact baseline draft (BAD_NUMERIC) -> must stop_for_user before baseline final() check
            self.note(BAD_NUMERIC)
            third = self.submit()
            self.assertNotEqual(third.returncode, 0)
            st3 = self.status()
            self.assertEqual(st3["status"], "needs_user_input")
            self.assertEqual(st3["next_step"], "return-draft-and-issues")
            self.assertFalse(st3["finished"])
            self.assertTrue((self.job / "issues.md").is_file())
            self.assertIn("exhausted", (self.job / "issues.md").read_text(encoding="utf-8"))

        # Subcase B: Revision 1 (uncleared) -> Revision 2 (ConfirmedError) -> stop_for_user
        with self.subTest(case="rev2_confirmed_error_stops_cleanly"):
            self.setUp()
            base_receipt = self.start_changes_review()
            confirmed = "- 已修 C04c-001 | stopping two centimeters below the rim\n"
            (self.job / "review.md").write_text(base_receipt + confirmed, encoding="utf-8")

            self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1))
            self.assertNotEqual(self.submit().returncode, 0)

            self.note(NOTE.replace("three days. ⏱ 01:00", "12 days. ⏱ 01:00", 1))
            self.assertNotEqual(self.submit().returncode, 0)
            verifier = self.status()["verifier"]
            (self.job / "review.md").write_text(
                base_receipt + confirmed
                + f'<!-- tfv-c04c-final: {verifier["c04c_sha256"]} -->\n'
                + "- 终稿 C04c-001 | 12 | three days | 真错\n",
                encoding="utf-8",
            )
            rejected = self.submit()
            self.assertNotEqual(rejected.returncode, 0)
            st = self.status()
            self.assertEqual(st["status"], "needs_user_input")
            self.assertEqual(st["next_step"], "return-draft-and-issues")
            self.assertTrue((self.job / "issues.md").is_file())

    def test_post_review_uncleared_review_only_update_stays_free(self) -> None:
        base_receipt = self.start_changes_review()
        confirmed = "- 已修 C04c-001 | stopping two centimeters below the rim\n"
        rev1 = NOTE.replace("three days. ⏱ 01:00", "12 days. ⏱ 01:00", 1)
        self.note(rev1)
        (self.job / "review.md").write_text(base_receipt + confirmed, encoding="utf-8")
        pending = self.submit()
        self.assertNotEqual(pending.returncode, 0)
        verifier = self.status()["verifier"]

        # Update ONLY review.md (same note.md) -> succeeds with 1 revision and 0 failures
        (self.job / "review.md").write_text(
            base_receipt + confirmed
            + f'<!-- tfv-c04c-final: {verifier["c04c_sha256"]} -->\n'
            + "- 终稿 C04c-001 | 12 | three days | 误报\n",
            encoding="utf-8",
        )
        ok = self.submit()
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        st = self.status()
        self.assertTrue(st["finished"])
        self.assertEqual(len(st["review"]["revisions"]), 1)
        self.assertEqual(st["review"]["failures"], 0)

    def test_review_state_machine_no_deadlock_invariant(self) -> None:
        """Every reachable non-finished review state must have a legal next transition or be needs_user_input + issues.md."""
        confirmed = "- 已修 C04c-001 | stopping two centimeters below the rim\n"
        observed_states: dict[tuple, str] = {}

        def state_key(st: dict) -> tuple:
            batch = st.get("review") or {}
            return (
                len(batch.get("revisions", [])),
                batch.get("failures", 0),
                batch.get("final_inputs") is not None,
                bool(batch.get("c04c_pending_inputs")),
                st.get("status"),
            )

        def setup_scenario(initial_failures: int) -> str:
            self.setUp()
            for idx in range(initial_failures):
                self.note(NOTE.replace("> [00:30] Snip the black", f"> [00:30] Bad{idx} the black", 1))
                self.assertNotEqual(self.submit().returncode, 0)
            return self.start_changes_review()

        def assert_transition(st: dict, expected_before: tuple, label: str, next_fn, expected_after: tuple) -> None:
            key = state_key(st)
            self.assertEqual(key, expected_before, f"{label} before-state mismatch: {st}")
            observed_states[key] = label
            next_rc, next_st = next_fn()
            after_key = state_key(next_st)
            self.assertEqual(after_key, expected_after, f"{label} after-state mismatch (rc={next_rc}): {next_st}")
            observed_states[after_key] = f"{label}:after"
            if expected_after[4] == "finished":
                self.assertEqual(next_rc, 0, f"{label}: expected exit 0")
                self.assertTrue(next_st.get("finished"), label)
            elif expected_after[4] == "needs_user_input":
                self.assertNotEqual(next_rc, 0, f"{label}: expected non-zero exit")
                self.assertTrue((self.job / "issues.md").is_file(), f"{label}: missing issues.md")
                self.assertEqual(next_st.get("next_step"), "return-draft-and-issues", label)

        for init_fail in (0, 2):
            # Path 1: Rev1 uncleared -> edit note (Rev2 clean) -> finished
            base = setup_scenario(init_fail)
            (self.job / "review.md").write_text(base + confirmed, encoding="utf-8")
            self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1))
            self.assertNotEqual(self.submit().returncode, 0)
            assert_transition(
                self.status(),
                (1, 0, False, True, "transcript_ready"),
                f"init{init_fail}:rev1_uncleared->rev2_edit",
                lambda: (self.note(NOTE) or self.submit().returncode, self.status()),
                (2, 1, True, False, "finished"),
            )

            # Path 2: Rev1 uncleared -> review-only update -> finished
            base = setup_scenario(init_fail)
            (self.job / "review.md").write_text(base + confirmed, encoding="utf-8")
            self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1))
            self.assertNotEqual(self.submit().returncode, 0)
            v1 = self.status()["verifier"]

            def clear_rev1():
                (self.job / "review.md").write_text(
                    base + confirmed
                    + f'<!-- tfv-c04c-final: {v1["c04c_sha256"]} -->\n'
                    + "- 终稿 C04c-001 | 17 | loosen the soil with your fingers | 误报\n",
                    encoding="utf-8",
                )
                return self.submit().returncode, self.status()

            assert_transition(
                self.status(),
                (1, 0, False, True, "transcript_ready"),
                f"init{init_fail}:rev1_uncleared->review_only",
                clear_rev1,
                (1, 0, True, False, "finished"),
            )

            # Path 3: Rev1 verify fail -> Rev2 uncleared -> review-only update -> finished
            base = setup_scenario(init_fail)
            (self.job / "review.md").write_text(base + confirmed, encoding="utf-8")
            self.note(BROKEN_QUOTE_NOTE)
            self.assertNotEqual(self.submit().returncode, 0)
            assert_transition(
                self.status(),
                (1, 1, False, False, "transcript_ready"),
                f"init{init_fail}:rev1_fail->rev2_uncleared",
                lambda: (
                    self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1)) or self.submit().returncode,
                    self.status(),
                ),
                (2, 1, False, True, "transcript_ready"),
            )
            st_r2_pend = self.status()
            v2 = st_r2_pend["verifier"]

            def clear_rev2():
                (self.job / "review.md").write_text(
                    base + confirmed
                    + f'<!-- tfv-c04c-final: {v2["c04c_sha256"]} -->\n'
                    + "- 终稿 C04c-001 | 17 | loosen the soil with your fingers | 误报\n",
                    encoding="utf-8",
                )
                return self.submit().returncode, self.status()

            assert_transition(
                st_r2_pend,
                (2, 1, False, True, "transcript_ready"),
                f"init{init_fail}:rev2_uncleared->review_only",
                clear_rev2,
                (2, 1, True, False, "finished"),
            )

            # Path 4: Rev1 uncleared -> Rev2 uncleared -> 3rd note edit -> needs_user_input + stays terminal
            base = setup_scenario(init_fail)
            (self.job / "review.md").write_text(base + confirmed, encoding="utf-8")
            self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_NEW, 1))
            self.assertNotEqual(self.submit().returncode, 0)
            self.note(NOTE.replace(VALUELESS_CLAIM_SRC, VALUELESS_CLAIM_ALT, 1))
            self.assertNotEqual(self.submit().returncode, 0)
            assert_transition(
                self.status(),
                (2, 1, False, True, "transcript_ready"),
                f"init{init_fail}:rev2_uncleared->rev3_stops",
                lambda: (self.note(NOTE) or self.submit().returncode, self.status()),
                (2, 1, False, True, "needs_user_input"),
            )
            # Real resubmission from stopped state must stay terminal (needs_user_input)
            assert_transition(
                self.status(),
                (2, 1, False, True, "needs_user_input"),
                f"init{init_fail}:stopped_resubmit_stays_terminal",
                lambda: (self.submit().returncode, self.status()),
                (2, 1, False, True, "needs_user_input"),
            )

        self.assertGreaterEqual(len(observed_states), 6)


class TraditionalNumeralsAndBaseMaskingTests(unittest.TestCase):
    def grounded(self, claim: str, quotes: list[str]) -> tuple[bool, str]:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.txt"
            transcript.write_text("\n".join(line.removeprefix("> ") for line in quotes), encoding="utf-8")
            note = f"## 主线论点\n\n{claim}\n\n## 原文依据\n" + "\n".join(quotes)
            ctx = rules.build_context(transcript, note, job=True)
            self.assertEqual(len(ctx.valid_quotes), len(quotes), ctx.evidence_errors)
            _, passed, message = rules.c04c_grounding(ctx)
            return passed, message

    def test_traditional_chinese_count_range_two_three(self) -> None:
        _, values = rules.canonical_numbers("其實它是兩三個Token才能夠組成一個中文字")
        count_ranges = [v for v in values if v.kind == "count_range"]
        self.assertEqual(len(count_ranges), 1, values)
        self.assertEqual(count_ranges[0].value, rules.NumberRange(2, 3))

        quote = ["> [01:36] 每個大型語言模型所產生的詞元切分方式並不相同 對於多數中文情境來說 其實它是兩三個Token才能夠組成一個中文字"]
        for claim in (
            "不同模型的词元不同，往往要 2 到 3 个 Token 才能组成一个中文字。 ⏱ 01:36",
            "不同模型的词元不同，往往要 2–3 个 Token 才能组成一个中文字。 ⏱ 01:36",
            "不同模型的词元不同，往往要两三个 Token 才能组成一个中文字。 ⏱ 01:36",
        ):
            with self.subTest(claim=claim):
                passed, message = self.grounded(claim, quote)
                self.assertTrue(passed, message)

    def test_traditional_chinese_six_wan_and_yi(self) -> None:
        cases = (
            ("重複了六萬多次", 60_000.0),
            ("總共有兩億筆資料", 200_000_000.0),
            ("突破一萬億個參數", 1_000_000_000_000.0),
            ("資料量有300億個文字", 30_000_000_000.0),
            ("閱讀了30萬遍", 300_000.0),
            ("一千萬筆紀錄", 10_000_000.0),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                _, values = rules.canonical_numbers(text)
                nums = [v.value for v in values if isinstance(v.value, rules.NumberRange)]
                self.assertTrue(
                    any(rng.low == expected and rng.high == expected for rng in nums),
                    f"{text!r} expected exact {expected}, got {values}",
                )

        # 數十億 / 数十亿 must parse as approximate_count(1e9, 1e10 - 1), NOT an exact 1e9 point
        for approx_text in ("寫成一個有數十億個未知參數的函式", "写成有数十亿个未知参数的函数"):
            with self.subTest(approx_text=approx_text):
                _, values = rules.canonical_numbers(approx_text)
                approx = [v for v in values if v.kind == "approximate_count"]
                self.assertEqual(len(approx), 1, values)
                self.assertEqual(approx[0].value, rules.NumberRange(1_000_000_000, 9_999_999_999))
                exact_claim = rules.NumericValue("number", rules.NumberRange(1_000_000_000, 1_000_000_000), "10 亿")
                self.assertFalse(approx[0].supports(exact_claim))

        # Idiomatic 千萬/千万 must not emit 10,000,000, while range quantities like 到千萬不等 are preserved
        for idiom in ("千萬不要關機", "千万不要关机", "千萬別忘記備份", "千萬記住備份"):
            with self.subTest(idiom=idiom):
                _, values = rules.canonical_numbers(idiom)
                self.assertEqual(values, [], f"{idiom!r} must emit 0 numeric values, got {values}")
        _, range_vals = rules.canonical_numbers("費用從百萬到千萬不等")
        range_nums = [v.value for v in range_vals if isinstance(v.value, rules.NumberRange)]
        self.assertTrue(
            any(rng.low == 10_000_000.0 and rng.high == 10_000_000.0 for rng in range_nums),
            f"到千萬不等 must preserve 10,000,000, got {range_vals}",
        )

        passed, message = self.grounded(
            "有篇文章发现一个很长的段落在网爬资料里重复了 6 万多次。 ⏱ 22:04",
            ["> [22:04] 這篇研究文章在檢查去重問題時發現 以上這一個很長的段落居然在網路爬蟲資料裡面重複了六萬多次"],
        )
        self.assertTrue(passed, message)

    def test_numeral_base_masking_emits_zero_values_and_zero_c04c_warns(self) -> None:
        base_terms = (
            "二进制", "八进制", "十进制", "十六进制",
            "2进制", "8进制", "10进制", "16进制",
            "二進制", "八進制", "十進制", "十六進制",
            "2進制", "8進制", "10進制", "16進制",
            "16 进制", "16 進制",
        )
        for term in base_terms:
            with self.subTest(term=term):
                _, values = rules.canonical_numbers(f"界面用 {term} 显示原始字节。")
                self.assertEqual(values, [], f"{term!r} should emit 0 numeric values, got {values}")

        # Preceding ASCII punctuation (not preceded by a digit) must still mask the radix label
        for punctuated in ("改用,16進制顯示", "改为.16进制表示", "(16进制)"):
            with self.subTest(punctuated=punctuated):
                _, values = rules.canonical_numbers(punctuated)
                self.assertEqual(values, [], f"{punctuated!r} should emit 0 numeric values, got {values}")

        # Ordinary quantities, decimals, grouped numbers, and non-base radices must remain intact
        _, ordinary = rules.canonical_numbers("协议头共有十六个字节，编号从 32进制扩展表 读取，版本 1.16进制测试 与 1,016进制。")
        nums = [v.value for v in ordinary if isinstance(v.value, rules.NumberRange)]
        self.assertTrue(any(rng.low == 16.0 and rng.high == 16.0 for rng in nums), ordinary)
        self.assertTrue(any(rng.low == 32.0 and rng.high == 32.0 for rng in nums), ordinary)
        self.assertTrue(any(rng.low == 1.16 and rng.high == 1.16 for rng in nums), ordinary)
        self.assertTrue(any(rng.low == 1016.0 and rng.high == 1016.0 for rng in nums), ordinary)

        # C04c grounding against an English quote containing "hex" and no digits
        passed, message = self.grounded(
            "界面用十六进制显示线上的原值，不需要换算，它就是 ground truth。 ⏱ 11:16",
            ["> [11:16] It shows this number in hex because that is what is actively on the wire, and that value is the ground truth."],
        )
        self.assertTrue(passed, message)

    def test_numeral_base_in_quote_does_not_falsely_ground_quantity(self) -> None:
        passed, message = self.grounded(
            "数据包里包含 16 个字段。 ⏱ 05:00",
            ["> [05:00] 抓包分析工具在默认视图下会直接采用十六进制编码来展示这一段网络数据包里的原始内容与字节流"],
        )
        self.assertFalse(passed, "十六进制 in quote must not falsely ground a claim of 16 fields")
        self.assertIn("16", message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
