#!/usr/bin/env python3
"""Reading-level contracts for the verifier, renderer, YouTube host, and examples."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import knowledge_note
import render_reading_note
import verify_note
import verify_rules
from test_render_reading_note import FRONTMATTER, NOTE, ROOT, write_job


PLAIN_H2 = "## 今天立刻动手一步"
CONCISE_H2 = "## 可以怎么用、可以拿去讨论什么"
FIRST_H2 = "## 先记住一句话"
SOURCE = "https://example.invalid/videos/seed-box"
PLAIN_ZH = "讲解方式：通俗版——术语和背景都做了解释。"
CONCISE_ZH = "讲解方式：精炼版——默认读者有相关背景，只解释少见的词。"
INTRO = "说明：竖线行是 AI 补充解释。"
APPLICATIONS = (
    "给信封标上播种月份，方便按时间查找。 ⏱ 00:20",
    "把褪色标签的信封单独放，免得误取。 ⏱ 34:25",
    "隔板之间留多少空间才不会碰到后排？ ⏱ 01:00:07",
)


def concise_note(closing=APPLICATIONS[:1], *, bullets=True):
    before, after = NOTE.split(PLAIN_H2, 1)
    _, omission = after.split("本文略去｜", 1)
    separator = "\n" if bullets else "\n\n"
    body = separator.join(f"- {line}" if bullets else line for line in closing)
    return f"{before}{CONCISE_H2}\n\n{body}\n\n本文略去｜{omission}"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")


def header_paragraphs(reading):
    if reading.startswith(FRONTMATTER):
        reading = reading[len(FRONTMATTER):].lstrip("\n")
    return reading.split(FIRST_H2, 1)[0].strip().split("\n\n")


def cli(script, *args, cwd=ROOT, env=None, screen="off"):
    isolated = dict(os.environ, PYTHONIOENCODING="utf-8", TFV_SCREEN_MODE=screen)
    isolated.update(env or {})
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *map(str, args)],
        cwd=cwd, env=isolated, capture_output=True, encoding="utf-8", timeout=30,
    )


class JobCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.job = self.root / "job"
        write_job(self.job)
        self.output = self.root / "reading.md"

    def status(self):
        return read_json(self.job / "status.json")

    def set_status(self, **updates):
        write_json(self.job / "status.json", self.status() | updates)

    def reopen_level(self, level):
        status = self.status()
        status.update(reading_level=level, reading_level_source="request")
        status.pop("review", None)
        status.pop("review_rounds", None)
        (self.job / "review.md").unlink(missing_ok=True)
        write_json(self.job / "status.json", status)

    def write_note(self, note):
        (self.job / "note.md").write_text(note, encoding="utf-8", newline="\n")

    def render(self, *options, automatic=False, require_review=False):
        destination = ("--output-dir", self.root / "reading") if automatic else ("--output", self.output)
        review = ("--require-review",) if require_review else ()
        return cli("render_reading_note.py", "--task-dir", self.job, *destination, *review, *options)

    def bind_review(self, result="clear"):
        command = cli("verify_note.py", "--job", self.job, "--with-coverage", "--json")
        self.assertEqual(command.returncode, 0, command.stdout + command.stderr)
        status = self.status()
        verifier, coverage = status["verifier"], status["coverage"]
        self.assertIs(verifier["allowed"], True, verifier)
        self.assertIs(coverage["allowed"], True, coverage)
        self.assertEqual(verifier["inputs"], coverage["inputs"])
        receipt = {
            "inputs": verifier["inputs"],
            "c04c_sha256": verifier["c04c_sha256"],
            "result": result,
            "reviewer": "independent",
        }
        terminology_heading = (
            "精炼版也必须解释的词" if status["reading_level"] == "concise" else "未解释的术语和基础词"
        )
        (self.job / "review.md").write_text(
            f"<!-- tfv-review: {json.dumps(receipt)} -->\n\n"
            f"## {terminology_heading}\n\n已逐节查过，没有\n\n## C04c 告警裁定\n\n无\n",
            encoding="utf-8", newline="\n",
        )
        return verifier["inputs"]


INVALID_LEVELS = (
    {"reading_level": "plain"},
    {"reading_level_source": "request"},
    *({"reading_level": value, "reading_level_source": "request"}
      for value in ("", None, 1, True, {}, "beginner", "advanced", "auto")),
    *({"reading_level": "plain", "reading_level_source": value}
      for value in ("", None, 1, False, {}, "auto", "user")),
)


class ReadingLevelStateTests(JobCase):
    def test_read_reading_level_accepts_legacy_and_all_valid_pairs(self):
        self.assertIsNone(knowledge_note.read_reading_level({}))
        for level in ("plain", "concise"):
            for source in ("request", "saved", "default"):
                with self.subTest(level=level, source=source):
                    self.assertEqual(knowledge_note.read_reading_level({
                        "reading_level": level, "reading_level_source": source,
                    }), level)

    def test_read_reading_level_rejects_malformed_pairs(self):
        for fields in INVALID_LEVELS:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                knowledge_note.read_reading_level(fields)

    def test_job_inputs_bind_level_without_provenance_and_keep_legacy_shape(self):
        legacy = verify_note.job_inputs(self.job)
        self.assertNotIn("reading_level", legacy)
        for level in ("plain", "concise"):
            for source in ("request", "saved", "default"):
                with self.subTest(level=level, source=source):
                    self.set_status(reading_level=level, reading_level_source=source)
                    inputs = verify_note.job_inputs(self.job)
                    self.assertEqual(inputs.get("reading_level"), level)
                    self.assertNotIn("reading_level_source", inputs)

    def test_job_inputs_rejects_malformed_status(self):
        baseline = self.status()
        for fields in INVALID_LEVELS:
            with self.subTest(fields=fields):
                write_json(self.job / "status.json", baseline | fields)
                with self.assertRaises(ValueError):
                    verify_note.job_inputs(self.job)

    def assert_stale_review_refused(self):
        previous = self.output.read_bytes()
        refused = self.render(require_review=True)
        self.assertEqual(self.output.read_bytes(), previous)
        self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
        self.assertIn("receipt is stale", refused.stdout + refused.stderr)

    def assert_clear_receipt_refuses_level_change(self, *, update_note=False):
        self.set_status(reading_level="plain", reading_level_source="request")
        inputs = self.bind_review()
        first = self.render(require_review=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        batch = self.status()["review"]
        self.assertEqual(batch["result"], "clear")
        self.assertEqual(batch["inputs"], inputs)
        self.assertEqual(batch["final_inputs"], inputs)

        self.set_status(reading_level="concise")
        if update_note:
            self.write_note(concise_note())
        self.assert_stale_review_refused()

    def test_clear_receipt_refuses_level_change_with_same_note(self):
        self.assert_clear_receipt_refuses_level_change()

    def test_clear_receipt_refuses_level_change_with_matching_new_closing(self):
        self.assert_clear_receipt_refuses_level_change(update_note=True)

    def test_removing_receipt_header_after_stored_batch_blocks_default_render(self):
        self.set_status(reading_level="plain", reading_level_source="request")
        inputs = self.bind_review(result="clear")
        first = self.render(require_review=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        batch = self.status()["review"]
        self.assertEqual(batch["result"], "clear")
        self.assertEqual(batch["final_inputs"], inputs)
        previous = self.output.read_bytes()

        self.set_status(reading_level="concise")
        self.write_note(concise_note())
        review = self.job / "review.md"
        header, body = review.read_text(encoding="utf-8").split("\n\n", 1)
        self.assertTrue(header.startswith("<!-- tfv-review: "), header)
        review.write_text(body, encoding="utf-8", newline="\n")

        refused = self.render(require_review=False)
        with self.subTest(check="exit status"):
            self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
        with self.subTest(check="previous reading copy"):
            self.assertEqual(self.output.read_bytes(), previous)

    def test_malformed_stored_review_blocks_default_render_when_receipt_removed(self):
        self.set_status(reading_level="plain", reading_level_source="request")
        self.bind_review()
        self.set_status(review="corrupted")
        (self.job / "review.md").unlink()

        refused = self.render(require_review=False)
        with self.subTest(check="exit status"):
            self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
        with self.subTest(check="no reading copy"):
            self.assertFalse(self.output.exists())

    def test_first_review_submission_refuses_level_change(self):
        self.set_status(reading_level="plain", reading_level_source="request")
        self.bind_review()
        self.assertIsNone(self.status().get("review"))
        self.output.write_bytes(b"Existing reading output\n")

        self.set_status(reading_level="concise")
        self.assert_stale_review_refused()

    def test_accepted_changes_batch_refuses_level_change(self):
        self.set_status(reading_level="plain", reading_level_source="request")
        inputs = self.bind_review(result="changes")
        self.write_note(NOTE.replace(FIRST_H2, "## 摘要", 1))
        check = cli("verify_note.py", "--job", self.job, "--with-coverage")
        diagnostics = check.stdout + check.stderr
        self.assertNotEqual(check.returncode, 0, diagnostics)
        self.assertIn("C04a FAIL:", diagnostics)
        batch = self.status().get("review")
        self.assertIsInstance(batch, dict, diagnostics)
        self.assertEqual(batch["inputs"], inputs)
        self.assertEqual(batch["result"], "changes")
        self.assertEqual(batch["failures"], 1)
        self.assertNotIn("final_inputs", batch)

        self.output.write_bytes(b"Existing reading output\n")
        self.set_status(reading_level="concise")
        self.assert_stale_review_refused()

    def test_rechecking_both_gates_and_rebinding_allows_new_level(self):
        self.set_status(reading_level="plain", reading_level_source="request")
        self.bind_review()
        first = self.render(require_review=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.reopen_level("concise")
        self.write_note(concise_note())
        self.assertEqual(self.bind_review().get("reading_level"), "concise")
        second = self.render(require_review=True)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn(CONCISE_ZH, self.output.read_text(encoding="utf-8"))


class ClosingTests(JobCase):
    def verify_without_status(self, note):
        transcript = self.root / "transcript.txt"
        shutil.copyfile(self.job / "transcript.txt", transcript)
        note = note.replace("transcript_path: transcript.txt", f'transcript_path: "{transcript.as_posix()}"')
        return verify_note.verify(transcript, note, expected_lang="en")

    def test_standalone_checker_accepts_both_headings_and_concise_forms(self):
        plain = self.verify_without_status(NOTE)
        self.assertTrue(plain["allowed"], plain["reasons"])
        for bullets in (True, False):
            for count in (1, 2, 3):
                with self.subTest(bullets=bullets, count=count):
                    result = self.verify_without_status(concise_note(APPLICATIONS[:count], bullets=bullets))
                    self.assertTrue(result["allowed"], result["reasons"])

    def test_concise_closing_rule_failures(self):
        cases = (
            ("empty", concise_note(()), "C04a"),
            ("four items", concise_note((*APPLICATIONS, APPLICATIONS[0])), "C04a"),
            ("orphan paragraph", concise_note().replace(
                "\n\n本文略去", "\n\n褪色标签的信封要单放。 ⏱ 34:25\n\n本文略去"), "C04a"),
            ("both headings", concise_note().replace(
                "\n\n本文略去", f"\n\n{PLAIN_H2}\n\n{APPLICATIONS[0]}\n\n本文略去"), "C04a"),
            ("setext h2 after concise closing", concise_note(APPLICATIONS[:1], bullets=False).replace(
                "\n\n本文略去", "\n\n补充讨论 ⏱ 00:20\n-----\n\n本文略去"), "C04a"),
            ("bare empty h2 after concise closing", concise_note().replace(
                "\n\n本文略去", "\n\n##\n\n本文略去"), "C04a"),
            ("fenced code item", concise_note(
                ("```text\n给信封标上播种月份。 ⏱ 00:20\n```",), bullets=False), "C04a"),
            ("nested fenced code in list item", concise_note((
                "先看下面示例。\n    ```text\n    给信封标上播种月份。 ⏱ 00:20\n    ```",)), "C04a"),
            ("one missing link", concise_note((APPLICATIONS[0], "把褪色标签的信封单独放。")), "R13"),
            ("timestamp hidden in link title", concise_note((
                '[查看示例](https://example.test "⏱ 00:20")。',)), "R13"),
            ("nested bracket link hides timestamp in title", concise_note((
                '[查看 [嵌套] 示例](https://example.test "⏱ 00:20")。',)), "R13"),
            ("timestamp after closing paren in quoted link title", concise_note((
                '[查看示例](https://example.test "note) ⏱ 00:20")。',)), "R13"),
            ("punctuation-only linked item", concise_note((APPLICATIONS[0], "— ⏱ 00:20")), "R13"),
            ("hidden link destination only", concise_note((APPLICATIONS[0], "[...](https://example.com) ⏱ 00:20")), "R13"),
            ("html comment only", concise_note((APPLICATIONS[0], "<!-- hidden text --> ⏱ 00:20")), "R13"),
            ("multiline html comment only", concise_note((APPLICATIONS[0],
                "<!-- line one\n\nline two --> ⏱ 00:20")), "R13"),
            ("three sentences", concise_note((APPLICATIONS[0],
                "写上播种月份。把信封收好。查看标签。 ⏱ 00:20")), "R13"),
        )
        for case, note, rule in cases:
            with self.subTest(case=case):
                result = self.verify_without_status(note)
                self.assertIs(result["allowed"], False, result)
                self.assertTrue(any(line.startswith(f"{rule} FAIL:") for line in result["reasons"]), result)

    def test_concise_closing_allows_balanced_parentheses_in_link_destination(self):
        result = self.verify_without_status(
            concise_note(("[查看示例](https://example.test/a(b)c.d.e)。 ⏱ 00:20",))
        )
        self.assertIs(result["allowed"], True, result["reasons"])

    def test_closing_heading_pair_ignores_comments_and_fenced_code(self):
        for wrapper in ("<!-- {} -->", "<!--\n{}\n-->", "```markdown\n{}\n```"):
            with self.subTest(wrapper=wrapper, closing="present"):
                note = concise_note().replace(
                    "\n\n本文略去", f"\n\n{wrapper.format(PLAIN_H2)}\n\n本文略去", 1
                )
                verify_note.check_closing_heading_pair(note.encode("utf-8"), "concise")
            with self.subTest(wrapper=wrapper, closing="missing"):
                note = NOTE.replace(PLAIN_H2, wrapper.format(PLAIN_H2), 1)
                with self.assertRaises(ValueError):
                    verify_note.check_closing_heading_pair(note.encode("utf-8"), "plain")

    def test_unclosed_html_comment_masks_headings_to_eof(self):
        with self.subTest(case="comment only"):
            self.assertEqual(verify_rules.markdown_headings("<!--\n## hidden\n"), [])
        with self.subTest(case="heading before comment"):
            headings = verify_rules.markdown_headings(f"{CONCISE_H2}\n\n<!--\n## hidden")
            self.assertEqual(
                [(level, heading) for level, heading, _, _ in headings],
                [(2, CONCISE_H2[3:])],
            )
        with self.subTest(case="concise closing before comment"):
            note = concise_note().replace("\n\n本文略去", "\n\n<!--\n## hidden\n\n本文略去")
            verify_note.check_closing_heading_pair(note.encode("utf-8"), "concise")

    def test_inline_code_comment_opener_does_not_mask_headings(self):
        headings = f"{CONCISE_H2}\n\n## 原文依据\n"
        expected = [(2, CONCISE_H2[3:]), (2, "原文依据")]
        for opener, visible in (("`<!--`", expected), ("<!--", [])):
            with self.subTest(opener=opener):
                parsed = verify_rules.markdown_headings(f"Mention {opener} in the note.\n\n{headings}")
                self.assertEqual([(level, title) for level, title, _, _ in parsed], visible)

    def test_inline_code_comment_opener_preserves_concise_note(self):
        prose = "收好种子前，先写清月份，把发潮的信封另放。"
        prose_with_code = f"{prose} 标签示例是 `<!--`。"
        closing = "在备注里写下 `<!--`，再标上播种月份。"
        note = concise_note((f"{closing} ⏱ 00:20",)).replace(prose, prose_with_code, 1)

        with self.subTest(operation="verify"):
            result = self.verify_without_status(note)
            self.assertTrue(result["allowed"], result["reasons"])
        with self.subTest(operation="render"):
            reading = render_reading_note.render_note(
                note.encode("utf-8"), keep_frontmatter=False, reading_level="concise"
            ).decode("utf-8")
            self.assertIn(prose_with_code, reading)
            self.assertIn(CONCISE_H2, reading.splitlines())
            self.assertIn(closing, reading)
            self.assertNotIn("## 原文依据", reading.splitlines())
            self.assertNotIn("⏱", reading)

    def test_deeply_nested_link_labels_strip_to_visible_text(self):
        depth = 1500
        label = "写清播种月份。"
        nested = "[![" * (depth // 2) + label + "](https://example.invalid)" * depth
        self.assertEqual(verify_rules._strip_markdown_links(nested), label)

    def test_deeply_nested_link_labels_in_concise_closing_verify(self):
        depth = 1500
        nested = "[" * depth + "写清播种月份。" + "](https://example.invalid)" * depth
        result = self.verify_without_status(concise_note((f"{nested} ⏱ 00:20",)))
        self.assertIsInstance(result, dict)
        self.assertTrue(result["allowed"], result["reasons"])

    def test_plain_closing_rejects_timestamp_hidden_in_link_title(self):
        note = self.plain_note_with_closing('[写清播种月份。](https://example.invalid "⏱ 00:20")')
        result = self.verify_without_status(note)
        self.assertTrue(any(reason.startswith("R13 FAIL:") for reason in result["reasons"]), result)

    def test_plain_closing_ignores_link_title_sentences(self):
        note = self.plain_note_with_closing('[写清播种月份。](https://example.invalid "One. Two. Three.") ⏱ 00:20')
        result = self.verify_without_status(note)
        r13 = next(rule for rule in result["rules"] if rule["id"] == "R13")
        self.assertTrue(r13["ok"], r13)

    def plain_note_with_closing(self, closing):
        before, after = NOTE.split(PLAIN_H2, 1)
        _, omission = after.split("本文略去｜", 1)
        return f"{before}{PLAIN_H2}\n\n{closing}\n\n本文略去｜{omission}"

    def test_closing_heading_pair_rejects_multiline_setext_and_indented_code_break(self):
        cases = (
            ("multiline Setext", "额外前提\n可以怎么用、可以拿去讨论什么\n-----"),
            ("indented code before thematic break", "    可以怎么用、可以拿去讨论什么\n-----"),
            ("space-tab indented code before thematic break", " \t可以怎么用、可以拿去讨论什么\n-----"),
        )
        for case, replacement in cases:
            with self.subTest(case=case):
                note = concise_note().replace(CONCISE_H2, replacement, 1)
                with self.assertRaises(ValueError):
                    verify_note.check_closing_heading_pair(note.encode("utf-8"), "concise")
        with self.subTest(case="space-tab indentation in heading parser"):
            self.assertEqual(verify_rules.markdown_headings(" \tcode\n---"), [])

    def test_closing_heading_pair_rejects_bare_empty_h2(self):
        note = concise_note().replace("\n\n本文略去", "\n\n##\n\n本文略去")
        with self.assertRaises(ValueError):
            verify_note.check_closing_heading_pair(note.encode("utf-8"), "concise")

    def test_concise_closing_accepts_timestamp_in_link_label(self):
        note = concise_note(("[给信封标上播种月份 ⏱ 00:20](https://example.test)。",))
        result = self.verify_without_status(note)
        self.assertIs(result["allowed"], True, result["reasons"])

    def test_renderer_preserves_setext_opening_and_body_after_masked_evidence_heading(self):
        self.set_status(reading_level="concise", reading_level_source="request")
        note = concise_note().replace(FIRST_H2, "先记住一句话\n------", 1)
        note = note.replace(f"\n\n{CONCISE_H2}", f" <!-- ## 原文依据 -->\n\n{CONCISE_H2}", 1)
        self.write_note(note)

        result = self.render()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reading = self.output.read_text(encoding="utf-8")
        self.assertIn(FIRST_H2, reading.splitlines())
        self.assertIn("收好种子前，先写清月份，把发潮的信封另放。", reading)
        self.assertIn(CONCISE_H2, reading.splitlines())
        self.assertIn("给信封标上播种月份，方便按时间查找。", reading)

    def test_renderer_requires_matching_level_and_heading(self):
        baseline = self.status()
        for level in (None, "plain", "concise"):
            for closing in (PLAIN_H2, CONCISE_H2):
                with self.subTest(level=level, closing=closing):
                    status = baseline.copy()
                    if level is not None:
                        status.update(reading_level=level, reading_level_source="request")
                    write_json(self.job / "status.json", status)
                    self.output.unlink(missing_ok=True)
                    self.write_note(NOTE if closing == PLAIN_H2 else concise_note())
                    result = self.render()
                    matched = (level == "concise") == (closing == CONCISE_H2)
                    if matched:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn(closing, self.output.read_text(encoding="utf-8").splitlines())
                    else:
                        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertFalse(self.output.exists())

    def test_mismatched_closing_refuses_render_without_locking_review_batch(self):
        self.reopen_level("plain")
        self.write_note(concise_note())
        self.bind_review("clear")
        self.assertIsNone(self.status().get("review"))

        result = self.render(require_review=True)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.output.exists())
        self.assertIsNone(self.status().get("review"))

    def test_mismatched_closing_with_changes_receipt_refuses_verify_and_allows_recovery(self):
        self.reopen_level("plain")
        self.write_note(concise_note())
        self.bind_review("changes")
        self.assertIsNone(self.status().get("review"))

        result = cli("verify_note.py", "--job", self.job, "--with-coverage")
        with self.subTest(stage="verify refuses mismatched closing"):
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        with self.subTest(stage="verify preserves review batch"):
            self.assertIsNone(self.status().get("review"))

        with self.subTest(stage="render mismatched closing"):
            result = self.render(require_review=True)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(self.output.exists())
            self.assertIsNone(self.status().get("review"))

        with self.subTest(stage="render corrected closing"):
            self.write_note(NOTE)
            result = self.render(require_review=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(PLAIN_H2, self.output.read_text(encoding="utf-8").splitlines())

    def test_both_closing_headings_with_expected_last_refuses_without_consuming_changes_batch(self):
        self.reopen_level("concise")
        note = concise_note()
        self.write_note(note)
        self.bind_review("changes")
        self.assertIsNone(self.status().get("review"))
        self.write_note(note.replace(CONCISE_H2, f"{PLAIN_H2}\n\n{APPLICATIONS[0]}\n\n{CONCISE_H2}", 1))

        result = cli("verify_note.py", "--job", self.job, "--with-coverage")
        with self.subTest(stage="verify exit"):
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        with self.subTest(stage="verify review status"):
            self.assertIsNone(self.status().get("review"))

        result = self.render(require_review=True)
        with self.subTest(stage="render exit"):
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        with self.subTest(stage="render review status"):
            self.assertIsNone(self.status().get("review"))

    def test_setext_h2_after_concise_closing_refuses_without_consuming_changes_batch(self):
        note = concise_note(APPLICATIONS[:1], bullets=False)
        malformed = note.replace(
            "\n\n本文略去", "\n\n补充讨论 ⏱ 00:20\n-----\n\n本文略去", 1
        )
        commands = (
            ("verify", lambda: cli("verify_note.py", "--job", self.job, "--with-coverage")),
            ("render", lambda: self.render(require_review=True)),
        )
        for name, run in commands:
            with self.subTest(command=name):
                self.job = self.root / name
                write_job(self.job)
                self.reopen_level("concise")
                self.write_note(note)
                self.bind_review("changes")
                self.assertIsNone(self.status().get("review"))
                self.write_note(malformed)

                result = run()
                with self.subTest(check="exit"):
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                with self.subTest(check="review status"):
                    self.assertIsNone(self.status().get("review"))

    def test_scaffold_uses_matching_heading(self):
        for level, expected, other in (
            (None, PLAIN_H2, CONCISE_H2),
            ("plain", PLAIN_H2, CONCISE_H2),
            ("concise", CONCISE_H2, PLAIN_H2),
        ):
            with self.subTest(level=level):
                scaffold = knowledge_note.render_scaffold(
                    job_id="youtube_fixture", video_id="fixture", source=SOURCE,
                    acquisition="settle-transcript", transcript_cite="transcript.txt",
                    reading_level=level,
                ).splitlines()
                self.assertIn(expected, scaffold)
                self.assertNotIn(other, scaffold)


class ReadingHeaderTests(unittest.TestCase):
    def render(self, note=NOTE, **options):
        reading = render_reading_note.render_note(note.encode(), keep_frontmatter=False, **options)
        return header_paragraphs(reading.decode())

    def test_merged_intro_combinations(self):
        for self_review, screen, expected in (
            (False, False, INTRO),
            (False, True, "说明：竖线行是 AI 补充解释；标明来自画面的内容由机器识别，可能有误差。"),
            (True, False, "说明：未经独立复核；竖线行是 AI 补充解释。"),
            (True, True, "说明：未经独立复核；竖线行是 AI 补充解释；标明来自画面的内容由机器识别，可能有误差。"),
        ):
            with self.subTest(self_review=self_review, screen=screen):
                note = NOTE + "> [00:20][画面] Label the envelope\n" if screen else NOTE
                paragraphs = self.render(note, self_review=self_review)
                self.assertEqual(paragraphs[2:], [expected])

    def test_reading_level_localizes_to_prose_not_template_headings(self):
        english = FRONTMATTER + """
## 先记住一句话

Write the planting month on the outside of each envelope before putting it away.

## 这场在谈什么、谁

The speaker explains how to store seed packets so that they are easy to find.

## 今天立刻动手一步

Label one envelope with its planting month. ⏱ 00:20

本文略去｜无

## 原文依据

> [00:20] Write the planting month on the outside of each envelope before putting it away.
"""
        for note, level, expected in (
            (NOTE, "plain", PLAIN_ZH),
            (concise_note(), "concise", CONCISE_ZH),
            (english, "plain", "Reading level: Plain — terms and background are explained."),
            (english.replace(PLAIN_H2, CONCISE_H2), "concise",
             "Reading level: Concise — assumes relevant background; only uncommon terms are explained."),
        ):
            with self.subTest(level=level, paragraph=expected):
                paragraphs = self.render(note, reading_level=level)
                self.assertEqual(len(paragraphs), 4, paragraphs)
                self.assertEqual(paragraphs[3], expected)

    def test_language_inference_ignores_setext_template_headings(self):
        for level, heading, chinese, english in (
            ("plain", PLAIN_H2, PLAIN_ZH, "Reading level: Plain — terms and background are explained."),
            ("concise", CONCISE_H2, CONCISE_ZH,
             "Reading level: Concise — assumes relevant background; only uncommon terms are explained."),
        ):
            note = (
                f"{FRONTMATTER}\n{FIRST_H2[3:]}\n---\n\n"
                "Write the planting month on the outside of each envelope before putting it away.\n\n"
                "这场在谈什么、谁\n---\n\n"
                "The speaker explains how to store seed packets so that they are easy to find.\n\n"
                f"{heading[3:]}\n---\n\nLabel one envelope with its planting month. ⏱ 00:20\n\n"
                "本文略去｜无\n\n## 原文依据\n\n"
                "> [00:20] Write the planting month on the outside of each envelope before putting it away.\n"
            )
            for language, expected in ((None, english), ("中文", chinese)):
                with self.subTest(reading_level=level, delivery_language=language):
                    paragraphs = self.render(note, reading_level=level, delivery_language=language)
                    self.assertEqual(len(paragraphs), 4, paragraphs)
                    self.assertEqual(paragraphs[3], expected)

    def test_latin_majority_bilingual_prose_uses_chinese_fourth_paragraph(self):
        prose = (
            "把播种月份写在信封上。\n"
            "Write the planting month on the outside of each envelope so that you can "
            "find the right seeds without opening every packet.\n\n"
            "按月份整理。\n"
            "Arrange the envelopes in planting order so the next packet is easy to find. ⏱ 00:20"
        )
        self.assertGreater(len(re.findall(r"[A-Za-z]", prose)), len(re.findall(r"[\u4e00-\u9fff]", prose)))

        for level, heading, chinese, english in (
            ("plain", PLAIN_H2, PLAIN_ZH, "Reading level: Plain — terms and background are explained."),
            ("concise", CONCISE_H2, CONCISE_ZH,
             "Reading level: Concise — assumes relevant background; only uncommon terms are explained."),
        ):
            takeaway, application = prose.split("\n\n")
            note = (
                f"{FRONTMATTER}\n{FIRST_H2}\n\n{takeaway}\n\n{heading}\n\n{application}\n\n"
                "本文略去｜无\n\n## 原文依据\n\n> [00:20] Arrange the envelopes in planting order.\n"
            )
            for language, expected in ((None, chinese), ("英文", english), ("中英文对照", chinese), ("中文", chinese)):
                with self.subTest(reading_level=level, delivery_language=language):
                    paragraphs = self.render(note, reading_level=level, delivery_language=language)
                    self.assertEqual(len(paragraphs), 4, paragraphs)
                    self.assertEqual(paragraphs[3], expected)

    def test_legacy_header_has_three_paragraphs_and_no_system_wording(self):
        reading = render_reading_note.render_note(NOTE.encode(), keep_frontmatter=False, reading_level=None).decode()
        self.assertEqual(len(header_paragraphs(reading)), 3)
        for wording in ("旧任务", "切换", "讲解方式", "Reading level"):
            self.assertNotIn(wording, reading)

    def test_missing_metadata_preserves_second_paragraph(self):
        note = NOTE.replace("channel: 合成园艺课堂", 'channel: ""').replace("published: 2026-04-08", 'published: ""')
        paragraphs = self.render(note, reading_level="plain")
        self.assertEqual(paragraphs[1:], [f"— · — · [原视频]({SOURCE})", INTRO, PLAIN_ZH])


class ReadingOwnershipTests(JobCase):
    def test_cli_language_flag_and_low_cjk_bilingual_note(self):
        self.reopen_level("plain")
        prose = (
            f"{FIRST_H2}\n\n"
            "写清月份。\n"
            "Write the planting month on the outside of each seed envelope before putting it away.\n\n"
            "## 这场在谈什么、谁\n\n"
            "整理种子。\n"
            "The speaker explains how to organize seed envelopes in a storage drawer. "
            "The talk starts with what to write on the outside of a packet, then explains "
            "why damp envelopes go to a dry shelf before sorting and why envelopes with "
            "faded labels go on a separate tray. It ends with how to leave space between "
            "the dividers so that a packet can be removed without disturbing the row behind it.\n\n"
            "## 主线论点\n\n"
            "Write the planting month on the outside of the envelope. ⏱ 00:20\n\n"
            "Open the storage drawer at 08:30 and move the damp envelopes to a dry shelf "
            "before sorting. ⏱ 16:10\n\n"
            "Put envelopes with faded labels on a separate tray so nobody has to guess "
            "what they contain. ⏱ 34:25\n\n"
            "Leave enough room between the dividers to pull out a packet without disturbing "
            "the row behind it. ⏱ 01:00:07\n\n"
            "## 可复用做法\n\n"
            "Move damp envelopes to a dry shelf before sorting the rest. ⏱ 16:10\n\n"
            "## 翻车或别用\n\n"
            "Keep faded labels separate so nobody needs to guess what they contain. ⏱ 34:25\n\n"
            f"{PLAIN_H2}\n\n"
            "Write the planting month on the outside of a seed envelope before storing it. ⏱ 00:20"
        )
        body_text = re.sub(r"(?m)^## .*", "", prose)
        cjk = len(re.findall(r"[\u4e00-\u9fff]", body_text))
        latin = len(re.findall(r"[A-Za-z]", body_text))
        self.assertGreaterEqual(cjk, 4)
        self.assertGreater(latin, 20 * cjk)
        self.assertGreater(len(re.findall(r"[A-Za-z][A-Za-z'’-]*", body_text)), 20 * cjk)
        _, evidence = NOTE.split("本文略去｜", 1)
        frontmatter = FRONTMATTER.replace("type: 访谈", "type: 讲座")
        self.write_note(f"{frontmatter}\n{prose}\n\n本文略去｜{evidence}")

        for language, expected in (
            (None, PLAIN_ZH),
            ("中英文对照", PLAIN_ZH),
            ("英文", "Reading level: Plain — terms and background are explained."),
        ):
            with self.subTest(language=language):
                self.output.unlink(missing_ok=True)
                options = ("--language", language) if language else ()
                result = self.render(*options)
                self.assertNotIn("language", self.status())
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                paragraphs = header_paragraphs(self.output.read_text(encoding="utf-8"))
                self.assertEqual(len(paragraphs), 4, paragraphs)
                self.assertEqual(paragraphs[3], expected)

    def assert_automatic_overwrite(self, *options):
        self.set_status(reading_level="plain", reading_level_source="request")
        self.bind_review()
        first = self.render(*options, automatic=True, require_review=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        files = list((self.root / "reading").glob("*.md"))
        self.assertEqual(len(files), 1)
        path = files[0]
        plain = path.read_text(encoding="utf-8")
        self.assertEqual(plain.startswith(FRONTMATTER), bool(options))
        self.assertEqual(header_paragraphs(plain)[3:], [PLAIN_ZH])

        second = self.render(*options, automatic=True, require_review=True)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), plain)

        self.reopen_level("concise")
        self.write_note(concise_note())
        self.bind_review()
        third = self.render(*options, automatic=True, require_review=True)
        self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
        concise = path.read_text(encoding="utf-8")
        self.assertEqual(concise.startswith(FRONTMATTER), bool(options))
        self.assertEqual(header_paragraphs(concise)[3:], [CONCISE_ZH])
        self.assertEqual(list(path.parent.glob("*.md")), [path])

        unrelated = f"# Unrelated memo\n\nPrivate notes.\n\nSee [原视频]({SOURCE}) in the reference list.\n"
        path.write_text(unrelated, encoding="utf-8", newline="\n")
        rejected = self.render(*options, automatic=True, require_review=True)
        self.assertNotEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), unrelated)

    def test_overwrites_owned_four_paragraph_output(self):
        self.assert_automatic_overwrite()

    def test_overwrites_owned_four_paragraph_output_with_frontmatter(self):
        self.assert_automatic_overwrite("--keep-frontmatter")



class PreferenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / "config"
        self.env = {"APPDATA": str(self.config), "XDG_CONFIG_HOME": str(self.config)}
        self.artifacts = self.root / "artifacts"
        self.job = self.artifacts / "youtube_fixture0001"

    def prefs_path(self):
        import user_prefs

        with patch.dict(os.environ, self.env):
            path = user_prefs.prefs_path()
        self.assertTrue(path.is_relative_to(self.config), path)
        self.assertEqual(path.name, "prefs.json")
        return path

    def write_prefs(self, raw):
        path = self.prefs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8", newline="\n")
        return path

    def assert_no_prefs(self):
        self.assertEqual(list(self.config.rglob("prefs.json")), [])

    def host(self, *flags):
        transcript = ROOT / "evals/fixtures/usable_en_transcript.txt"
        return cli(
            "youtube_host.py", "--settle-transcript", transcript, "--video-id", "fixture0001",
            "--out", self.artifacts, *flags, cwd=self.root, env=self.env,
        )

    def assert_job(self, result, level, source):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        status = read_json(self.job / "status.json")
        self.assertEqual((status["reading_level"], status["reading_level_source"]), (level, source))
        forbidden = {"audience", "video_level", "explanation_density", "user_override", "decided_at"}
        self.assertFalse(forbidden.intersection(status), status)
        scaffold = (self.job / "note.scaffold.md").read_text(encoding="utf-8").splitlines()
        heading, other = (CONCISE_H2, PLAIN_H2) if level == "concise" else (PLAIN_H2, CONCISE_H2)
        self.assertIn(heading, scaffold)
        self.assertNotIn(other, scaffold)
        return status

    def test_preference_api_round_trip_and_isolated_default_path(self):
        import user_prefs

        with patch.dict(os.environ, self.env):
            default_path = self.prefs_path()
            self.assertEqual(user_prefs.load_prefs(), {})
            self.assert_no_prefs()
            self.assertEqual(user_prefs.save_prefs("中文", "concise"), default_path)
            expected = {"language": "中文", "reading_level": "concise"}
            self.assertEqual(read_json(default_path), expected)
            self.assertEqual(user_prefs.load_prefs(), expected)
            explicit = self.root / "other.json"
            self.assertEqual(user_prefs.save_prefs("英文", "plain", path=explicit), explicit)
            self.assertEqual(user_prefs.load_prefs(path=explicit), {"language": "英文", "reading_level": "plain"})
            self.assertEqual(read_json(default_path), expected)

    def test_request_without_saved_pref_does_not_persist(self):
        result = self.host("--reading-level", "concise")
        self.assert_no_prefs()
        self.assert_job(result, "concise", "request")

    def test_request_beats_saved_pref_without_overwriting_it(self):
        path = self.write_prefs('{"language": "中文", "reading_level": "plain"}\n')
        before = path.read_bytes()
        result = self.host("--reading-level", "concise")
        self.assertEqual(path.read_bytes(), before)
        self.assert_job(result, "concise", "request")

    def test_saved_pref_applies_to_new_job(self):
        self.write_prefs('{"language": "中文", "reading_level": "concise"}')
        self.assert_job(self.host(), "concise", "saved")

    def test_save_pref_writes_only_explicit_settings(self):
        result = self.host("--language", "中文", "--reading-level", "concise", "--save-pref")
        self.assert_job(result, "concise", "request")
        self.assertEqual(read_json(self.prefs_path()), {"language": "中文", "reading_level": "concise"})

    def test_save_pref_requires_both_flags(self):
        for flags in ((), ("--language", "中文"), ("--reading-level", "concise")):
            with self.subTest(flags=flags):
                result = self.host("--save-pref", *flags)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assert_no_prefs()

    def test_no_request_or_saved_pref_defaults_without_writing(self):
        result = self.host()
        self.assert_no_prefs()
        self.assert_job(result, "plain", "default")

    def test_invalid_prefs_default_without_crashing(self):
        nested = "[" * 1500 + "]" * 1500
        try:
            json.loads(nested)
        except RecursionError:
            pass
        else:
            # Some Python builds allow deeper nesting in the native decoder.
            nested = "[" * 10000 + "]" * 10000
        for raw in (
            "{broken",
            '["中文", "concise"]',
            '{"language": "中文", "reading_level": "concise", "extra": true}',
            '{"language": "中文", "reading_level": "auto"}',
            '{"language": "Klingon", "reading_level": "concise"}',
            nested,
        ):
            with self.subTest(raw="deeply nested JSON" if raw == nested else raw):
                self.write_prefs(raw)
                if self.job.exists():
                    shutil.rmtree(self.job)
                self.assert_job(self.host(), "plain", "default")

    def test_legacy_language_file_is_ignored_and_preserved(self):
        path = self.root / "language.txt"
        original = "英文\n".encode()
        path.write_bytes(original)
        result = self.host()
        self.assertEqual(path.read_bytes(), original)
        self.assert_no_prefs()
        self.assert_job(result, "plain", "default")
        show = cli("youtube_host.py", "--show-pref", cwd=self.root, env=self.env)
        self.assertEqual(show.returncode, 0, show.stdout + show.stderr)
        self.assertNotIn("英文", show.stdout)
        self.assertEqual(path.read_bytes(), original)

    def test_skill_stops_referencing_legacy_preference_in_new_workflow(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        preference = re.search(r"(?m)^## Language and reading preference\n([\s\S]*?)(?=^## |\Z)", skill)
        self.assertIsNotNone(preference, skill)
        run = skill.split("\n## Run\n", 1)[1].split("\n## ", 1)[0]
        step_one = run.split("\n1. ", 1)[1].split("\n2. ", 1)[0]
        for obsolete in ("language.txt", "x_host.py"):
            self.assertNotIn(obsolete, preference[1])
            self.assertNotIn(obsolete, step_one)

    def test_skill_scopes_reading_preferences_and_concise_closing_to_youtube(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        preference = skill.split("\n## Language and reading preference\n", 1)[1].split("\n## ", 1)[0]
        run = skill.split("\n## Run\n", 1)[1].split("\n## ", 1)[0]
        step_one = run.split("\n1. ", 1)[1].split("\n2. ", 1)[0]
        step_four = run.split("\n4. ", 1)[1].split("\n5. ", 1)[0]
        with self.subTest(section="preferences and Run step 1"):
            for obsolete in ("language.txt", "x_host.py"):
                self.assertNotIn(obsolete, preference)
                self.assertNotIn(obsolete, step_one)
            self.assertIn("YouTube", preference)
        with self.subTest(section="Run step 4"):
            self.assertIn(CONCISE_H2, step_four)
            self.assertRegex(
                step_four,
                rf"without `?reading_level`?[^.\n]*{re.escape(PLAIN_H2)}",
            )
        with self.subTest(section="README"):
            readme = (ROOT / "README.md").read_text(encoding="utf-8")
            self.assertNotIn("language.txt", readme)

    def test_show_pref_without_job_is_read_only(self):
        absent = cli("youtube_host.py", "--show-pref", cwd=self.root, env=self.env)
        self.assertEqual(absent.returncode, 0, absent.stdout + absent.stderr)
        self.assert_no_prefs()
        self.assertRegex(absent.stdout.strip().lower(), r"^(?:\{\}|null|none|)$|no (?:saved )?pref|not set|未保存|未设置|没有|暂无|无")
        path = self.write_prefs('{"language": "中文", "reading_level": "concise"}\n')
        before = path.read_bytes(), path.stat().st_mtime_ns
        saved = cli("youtube_host.py", "--show-pref", cwd=self.root, env=self.env)
        self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)
        self.assertIn("中文", saved.stdout)
        self.assertRegex(saved.stdout, r"concise|精炼版")
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertFalse(self.artifacts.exists())

    def test_delivery_language_does_not_change_caption_language(self):
        status = self.assert_job(self.host("--expected-lang", "en", "--language", "中文"), "plain", "default")
        self.assertEqual(status["expected_lang"], "en")
        self.assertEqual(status["gate_lang"], "en")

    def test_existing_job_keeps_level_until_explicitly_changed(self):
        self.assert_job(self.host("--reading-level", "concise"), "concise", "request")
        result = self.host()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(read_json(self.job / "status.json")["reading_level"], "concise")
        scaffold = (self.job / "note.scaffold.md").read_text(encoding="utf-8").splitlines()
        self.assertIn(CONCISE_H2, scaffold)
        self.assert_job(self.host("--reading-level", "plain"), "plain", "request")

    def test_explicit_level_change_archives_existing_review(self):
        first = self.host()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        status = read_json(self.job / "status.json")
        status["review"] = {"result": "clear"}
        write_json(self.job / "status.json", status)
        review = self.job / "review.md"
        contents = b"# Independent review\n"
        review.write_bytes(contents)

        status = self.assert_job(self.host("--reading-level", "concise"), "concise", "request")
        self.assertIsNone(status.get("review"))
        self.assertFalse(review.exists())
        archives = list(self.job.glob("review.prev*.md"))
        self.assertEqual(len(archives), 1, archives)
        self.assertEqual(archives[0].read_bytes(), contents)


class StderrTests(unittest.TestCase):
    def test_main_escapes_unencodable_error_under_ascii_streams(self):
        runner = """
import sys
from unittest.mock import patch
import render_reading_note

# Python normally starts stderr with backslashreplace even under ASCII.
sys.stderr.reconfigure(encoding="ascii", errors="strict")
with patch.object(render_reading_note, "render_job", side_effect=ValueError("\\ud800")):
    raise SystemExit(render_reading_note.main(["--task-dir", "fixture", "--output", "unused.md"]))
"""
        result = subprocess.run(
            [sys.executable, "-c", runner], cwd=ROOT / "scripts",
            env=dict(os.environ, PYTHONIOENCODING="ascii"),
            capture_output=True, encoding="ascii", timeout=30,
        )
        self.assertEqual(result.returncode, 1, result)
        self.assertIn(r"Reading note not written: \ud800", result.stderr)
        self.assertNotIn("UnicodeEncodeError", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


EXAMPLE = ROOT / "evals/fixtures/note-examples/whue9_YquGA"
DOCUMENTS = ROOT / "references"
TITLE = "Building an Autonomous Engineering Org"


class ExampleTests(unittest.TestCase):
    def fenced_blocks(self, document, language=r"[\w-]*"):
        return re.findall(rf"(?m)^```{language}[ \t]*\n(.*?)^```[ \t]*$", document, re.DOTALL)

    def example_block(self, language, prefix):
        document = (DOCUMENTS / "note-examples.md").read_text(encoding="utf-8")
        block = next((text for text in self.fenced_blocks(document, language) if text.startswith(prefix)), None)
        self.assertIsNotNone(block, f"Missing {language} example starting with {prefix!r}")
        return block

    def evidence_note(self):
        return self.example_block("markdown", f'---\ntitle: "{TITLE}')

    def test_examples_are_optional_reading(self):
        document = (DOCUMENTS / "note-examples.md").read_text(encoding="utf-8")
        self.assertIn("选读", document)

    def test_delivery_guidance_matches_reading_level_rules(self):
        delivery = (DOCUMENTS / "delivery-format.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        bullet = re.search(r"(?m)^- \*\*解释留用的技术要素。\*\*.*$", delivery)
        self.assertIsNotNone(bullet, "Missing technical-elements bullet")
        guidance = bullet[0]
        plain = re.search(r"通俗版(?:(?!精炼版).)*?(?:任何|所有|每个)术语", guidance)
        concise = re.search(r"精炼版((?:(?!通俗版).)*)", guidance)
        checks = {
            "Universal term callouts must be scoped to 通俗版": plain is not None,
            "精炼版 must limit required explanations to the four categories in review-guide.md": (
                concise is not None
                and re.search(r"只|仅", concise[1]) is not None
                and re.search(r"(?:陌生|不熟悉|需要解释)[^。；、，]*缩写|缩写[^。；、，]*需要解释",
                              concise[1]) is not None
                and all(term in concise[1] for term in ("视频自造", "冷门专名", "通行定义不一致"))
            ),
            "SKILL.md still advertises an outdated example count": "four synthetic examples" not in skill,
        }
        self.assertEqual([message for message, passed in checks.items() if not passed], [])

    def test_gitattributes_pins_note_example_fixtures_to_lf(self):
        fixtures = sorted(path.relative_to(ROOT).as_posix() for path in EXAMPLE.iterdir() if path.is_file())
        self.assertTrue(fixtures)
        result = subprocess.run(
            ["git", "check-attr", "-z", "text", "eol", "--", *fixtures],
            cwd=ROOT, capture_output=True, check=True,
        )
        fields = result.stdout.decode("utf-8").split("\0")[:-1]
        attributes = {(path, name): value for path, name, value in zip(
            fields[::3], fields[1::3], fields[2::3], strict=True,
        )}
        unpinned = [path for path in fixtures if attributes[path, "text"] != "unset"
                    and (attributes[path, "text"], attributes[path, "eol"]) != ("set", "lf")]
        self.assertEqual(unpinned, [], ".gitattributes must pin note-example fixtures to LF")

    def test_example_screen_checksum_matches_lf_fixture(self):
        status = read_json(EXAMPLE / "status.json")
        screen = (EXAMPLE / "screen.txt").read_bytes()
        self.assertNotIn(b"\r", screen)
        self.assertEqual(status["screen_ocr"]["sha256"], hashlib.sha256(screen).hexdigest())

    def test_full_example_passes_verify_and_coverage(self):
        note = self.evidence_note()
        selection = self.example_block("text", "00:00–00:47 | 开场与早期采用")
        with tempfile.TemporaryDirectory() as temp:
            job = Path(temp)
            for name in ("transcript.txt", "screen.txt", "segments.json", "status.json"):
                shutil.copyfile(EXAMPLE / name, job / name)
            (job / "note.md").write_bytes(note.encode("utf-8"))
            (job / "selection.md").write_bytes(selection.encode("utf-8"))
            verify = cli("verify_note.py", "--job", job, "--with-coverage", "--json", screen="slides")
            coverage = cli("coverage_check.py", "--job", job, "--json", screen="slides")
            for result in (verify, coverage):
                with self.subTest(script=result.args[3]):
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertNotIn(" FAIL:", result.stdout + result.stderr)
            self.assertIs(json.loads(verify.stdout)["allowed"], True)
            self.assertIs(json.loads(coverage.stdout)["ok"], True)
            status = read_json(job / "status.json")
            self.assertIs(status["verifier"]["allowed"], True)
            self.assertIs(status["coverage"]["allowed"], True)

    def section_bullets(self, note, heading):
        section = note.split(f"\n{heading}\n", 1)[1].split("\n## ", 1)[0]
        return [line for line in section.splitlines() if line.startswith("- ")]

    def test_full_example_formats_bullets_and_keeps_quote_wording_in_evidence(self):
        note = self.evidence_note()
        mistakes = self.section_bullets(note, "## 翻车或别用")
        self.assertTrue(mistakes)
        self.assertRegex(mistakes[-1], r"^- \*\*[^*]+。\*\* .+⏱ 16:48$")
        applications = self.section_bullets(note, CONCISE_H2)
        self.assertEqual(len(applications), 3)
        for item in applications:
            self.assertRegex(item, r"^- \*\*[^*]+。\*\* .+")
            self.assertNotIn("：**", item)
        body, evidence = note.split("\n## 原文依据\n", 1)
        self.assertIn("「止血」（stop the bleeding）", body)
        self.assertNotIn("stop the bleeding a bit", body)
        self.assertIn("stop the bleeding a bit", evidence)

    def test_delivery_format_uses_compact_concise_excerpt(self):
        delivery = (DOCUMENTS / "delivery-format.md").read_text(encoding="utf-8")
        for obsolete in ("石桥门诊", "沿海冷运会"):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, delivery)
        excerpt = next((text for text in self.fenced_blocks(delivery)
                        if TITLE in text and CONCISE_H2 in text), None)
        self.assertIsNotNone(excerpt, "Missing concise evidence excerpt")
        for marker in ("本文略去｜无", "## 原文依据"):
            self.assertIn(marker, excerpt)
        self.assertLessEqual(len(excerpt.encode("utf-8")), 5120)


class LoadPrefsTests(unittest.TestCase):
    def test_load_prefs_returns_empty_with_cleared_environment(self):
        import user_prefs

        with patch.dict(os.environ, {}, clear=True), patch.object(
            user_prefs.Path, "home", side_effect=RuntimeError("Could not determine home directory.")
        ):
            self.assertEqual(user_prefs.load_prefs(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
