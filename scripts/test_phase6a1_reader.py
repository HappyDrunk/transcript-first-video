#!/usr/bin/env python3
"""Phase 6A.1 reader contracts, using only synthetic note and transcript pairs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import render_reading_note
import verify_note
import verify_rules as rules
from verify_report import failed_ids

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FRONTMATTER = """\
---
title: Synthetic Workshop
source: https://example.invalid/workshop
channel: Synthetic Workshop
published: 2026-08-01
type: 讲座
caption_kind: auto
skill_version: fixture
transcript_path: transcript.txt
tags: [video-note]
---"""
BASE_QUOTE = (
    "先单独核对缓存，再运行脚本，最后检查输出并记录结果。"
    "保存本次运行的详细记录，方便之后逐项检查和比较输出。"
)
GUIDANCE = (
    r"(?:段落|列表项|paragraph|prose|list item).{0,30}"
    r"(?:与|和|到|及|、|and|before|之后|后|→|->).{0,30}"
    r"(?:代码块|围栏|fence|code block)"
    r"|(?:代码块|围栏|fence|code block)(?:之前|前面|前)"
)


def _build_note(middle: str, evidence: list[tuple[str, str]], *, english: bool = False) -> str:
    takeaway = "Check the cache before running the script." if english else "先核对缓存，再运行脚本。"
    intro = "Synthetic Workshop explains how to check output." if english else "这次演示如何检查输出。"
    quotes = "\n".join(f"> [{stamp}] {quote}" for stamp, quote in evidence)
    return "\n\n".join((
        FRONTMATTER,
        f"## 先记住一句话\n\n{takeaway}",
        f"## 这场在谈什么、谁\n\n{intro}",
        "## 主线论点\n\n" + middle,
        "本文略去｜无",
        "## 原文依据\n" + quotes,
    )) + "\n"


def _discrepancy(*rows: str) -> str:
    return "> [!warning] 原文出入\n" + "\n".join(f"> {row}" for row in rows)


def _render(note: str) -> str:
    return render_reading_note.render_note(note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")


class ReaderFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.job = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def verify(
        self, middle: str, quote: str = BASE_QUOTE, *,
        later: tuple[tuple[str, str], ...] = (), english: bool = False,
        transcript_lang: str | None = None,
    ) -> tuple[str, dict]:
        evidence = [("00:30", quote), *later]
        note = _build_note(middle, evidence, english=english)
        transcript = self.job / "transcript.txt"
        transcript.write_text(
            "".join(f"[{stamp}] {line}\n" for stamp, line in evidence), encoding="utf-8"
        )
        (self.job / "note.md").write_text(note, encoding="utf-8")
        lang = transcript_lang or ("en" if english else "zh")
        (self.job / "status.json").write_text(json.dumps({
            "status": "transcript_ready", "expected_lang": lang, "duration_seconds": 240,
        }), encoding="utf-8")
        return note, verify_note.verify(transcript, note, expected_lang=lang, job=True)

    def assert_clean(self, result: dict) -> None:
        self.assertTrue(result["allowed"], result["reasons"])
        self.assertEqual(result["c04c"], [])

    def assert_soft_warning(self, result: dict, label: str, expected: bool) -> None:
        self.assertTrue(result["allowed"], result["reasons"])
        matches = [warning for warning in result["warnings"]
                   if "WARN" in warning and re.search(label, warning, re.IGNORECASE)]
        self.assertEqual(bool(matches), expected, result["warnings"])


class FenceTests(ReaderFixture):
    PROSE = "先核对缓存。 ⏱ 00:30"
    FENCE = "```python\nif True:\n    print(7)\n\n```"
    QUOTE = BASE_QUOTE + "示例代码是 if True: print(7)，命令是 echo cache。"
    DOUBT = _discrepancy("存疑｜「缓存」｜未交代缓存位置")

    def test_t1_cited_paragraph_and_list_attach_verbatim(self) -> None:
        for lead, fence in ((self.PROSE, self.FENCE), ("- " + self.PROSE, "```bash\necho cache\n```")):
            with self.subTest(lead=lead):
                note, result = self.verify(f"{lead}\n\n{fence}", self.QUOTE)
                reading = _render(note)
                self.assertIn(f"{lead.removesuffix(' ⏱ 00:30')}\n\n{fence}\n", reading)
                self.assertNotIn("⏱", reading)
                self.assert_clean(result)

    def test_t2_marker_on_opening_fence_or_in_body_fails(self) -> None:
        for fence in ("```python ⏱ 00:30\nprint(7)\n```", "```python\n# ⏱ 00:30\nprint(7)\n```"):
            with self.subTest(fence=fence):
                _, result = self.verify(f"{self.PROSE}\n\n{fence}", self.QUOTE)
                self.assertIn("C04b", failed_ids(result), result["reasons"])
                self.assertFalse(result["allowed"])

    def test_t3_malformed_closing_line_or_unclosed_fence_at_eof(self) -> None:
        for case in ("trailing text", "end of file"):
            with self.subTest(case=case):
                valid, _ = self.verify(f"{self.PROSE}\n\n{self.FENCE}", self.QUOTE)
                if case == "trailing text":
                    note = valid.replace("\n```\n", "\n``` ⏱ 00:30\n")
                else:
                    note = valid[:valid.index("\n```\n")] + "\n"
                result = verify_note.verify(self.job / "transcript.txt", note, expected_lang="zh", job=True)
                with self.subTest(stage="verify"):
                    self.assertIn("C04a", failed_ids(result), result["reasons"])
                    self.assertRegex(" ".join(result["reasons"]), r"(?i)C04a[^\n]*(?:fence|围栏|代码块)")
                with self.subTest(stage="render"):
                    with self.assertRaises(render_reading_note.RenderError):
                        _render(note)

    def test_t4_fence_cannot_borrow_citation_from_other_item(self) -> None:
        for lead in ("", "下面说明流程。\n\n"):
            with self.subTest(lead=lead):
                _, result = self.verify(
                    f"### 输出\n\n{lead}{self.FENCE}\n\n{self.PROSE}", self.QUOTE
                )
                self.assertIn("C04b", failed_ids(result), result["reasons"])
        with self.subTest(lead="intervening uncited paragraph"):
            _, result = self.verify(
                f"### 输出\n\n{self.PROSE}\n\n这里是一段没有时间码的过渡句。\n\n{self.FENCE}", self.QUOTE
            )
            self.assertIn("C04b", failed_ids(result), result["reasons"])

    def test_t5_doubt_after_fence_explains_required_order(self) -> None:
        note, result = self.verify(f"{self.PROSE}\n\n{self.FENCE}\n\n{self.DOUBT}", self.QUOTE)
        with self.subTest(stage="verify"):
            self.assertIn("C04d", failed_ids(result), result["reasons"])
            message = next(reason for reason in result["reasons"] if reason.startswith("C04d FAIL"))
            self.assertIn("原文出入", message)
            self.assertRegex(message, GUIDANCE)
        with self.subTest(stage="render"):
            with self.assertRaises(render_reading_note.RenderError) as caught:
                _render(note)
            self.assertIn("原文出入", str(caught.exception))
            self.assertRegex(str(caught.exception), GUIDANCE)

    def test_t6_doubt_before_fence_inserts_in_prose(self) -> None:
        note, result = self.verify(f"{self.PROSE}\n\n{self.DOUBT}\n\n{self.FENCE}", self.QUOTE)
        reading = _render(note)
        self.assertIn(f"先核对缓存（存疑：未交代缓存位置）。\n\n{self.FENCE}\n", reading)
        self.assertNotRegex(reading, r"⏱|\[!warning\]")
        self.assert_clean(result)

    def test_t6_type_one_or_two_only_can_follow_fence(self) -> None:
        for row in ("字幕写作 CacheMode，实为 Cachemode。", "口述代码｜echo cache｜`echo cache`"):
            with self.subTest(row=row):
                note, result = self.verify(
                    f"{self.PROSE}\n\n{self.FENCE}\n\n{_discrepancy(row)}",
                    self.QUOTE + "也检查 CacheMode 设置。",
                )
                reading = _render(note)
                self.assertIn(self.FENCE, reading)
                self.assertNotRegex(reading, r"⏱|\[!warning\]")
                self.assert_clean(result)

    def test_t7_code_facts_use_last_cluster_only(self) -> None:
        fence = "```python\ncache_slot = 73\n```"
        first = BASE_QUOTE + "初始代码是 cache_slot = 73。"
        last = "接下来清理输出并保存记录，以便稍后检查。请把本次运行的详细输出单独归档，方便稍后核对结果。"
        middle = f"{self.PROSE} 随后保存记录。 ⏱ 01:30\n\n{fence}"
        _, result = self.verify(middle, first, later=[("01:30", last)])
        with self.subTest(evidence="earlier cluster only"):
            self.assertTrue(result["allowed"], result["reasons"])
            terms = {finding["term"] for finding in result["c04c"]}
            self.assertTrue({"cache_slot", "73"} <= terms, result["c04c"])
        with self.subTest(evidence="last cluster"):
            _, result = self.verify(middle, first, later=[("01:30", last + "代码是 cache_slot = 73。")])
            self.assert_clean(result)

    def test_t8_longer_fence_contains_shorter_fence(self) -> None:
        fence = "````markdown\n```python\nprint(7)\n```\n````"
        note, result = self.verify(f"{self.PROSE}\n\n{fence}", self.QUOTE)
        self.assertIn(fence, _render(note))
        self.assert_clean(result)

    def test_t9_chinese_prose_inside_text_or_markdown_fence_warns(self) -> None:
        for language in ("text", "markdown"):
            for prose, expected in (("先查看缓存记录并逐项核对输出是否符合预期。", True), ("检查输出。", False)):
                with self.subTest(language=language, expected=expected):
                    _, result = self.verify(f"{self.PROSE}\n\n```{language}\n{prose}\n```")
                    self.assert_soft_warning(result, "围栏", expected)


class GlossaryTests(ReaderFixture):
    def test_organizer_suffixes_strip_before_render_and_both_limits(self) -> None:
        tail = "。重复访问时可直接读取。"
        size = rules.MAX_TERM_CHARS - len(tail)
        phrase = "缓存保存近期结果以减少重复计算"
        definition = (phrase * (size // len(phrase) + 1))[:size] + tail
        self.assertEqual(len(definition), rules.MAX_TERM_CHARS)
        credits = ("（整理者补充，非视频内容）", "（Claude 补充，非视频内容）",
                   "（AI 补充，非视频内容）", "（整理者补充）")
        for credit in credits:
            block = f"先核对缓存。 ⏱ 00:30\n\n> [!note] 术语：缓存\n> {definition}"
            with self.subTest(credit=credit, stage="render"):
                note, _ = self.verify(block + credit)
                reading = _render(note)
                self.assertEqual(reading.count("以下为整理者补充，非讲者原话。"), 1)
                self.assertIn(f"- **缓存**：{definition}\n", reading)
                for suffix in credits:
                    self.assertNotIn(suffix, reading)
            with self.subTest(credit=credit, stage="verify"):
                _, result = self.verify(block + credit)
                self.assert_clean(result)
            short = block.removesuffix(definition) + "缓存保存结果。读取可以更快。仍需定期更新。"
            for over_limit, limit in ((block + "字", f"{rules.MAX_TERM_CHARS} characters"),
                                      (short, f"{rules.MAX_TERM_SENTENCES} sentences")):
                with self.subTest(credit=credit, limit=limit):
                    _, result = self.verify(over_limit + credit)
                    self.assertIn("C04d", failed_ids(result), result["reasons"])
                    self.assertIn(limit, " ".join(result["reasons"]))


class AsrTests(ReaderFixture):
    def verify_corrections(self, *pairs: tuple[str, str]) -> dict:
        prose = "先核对缓存、运行脚本并记录结果。讲者提到 " + "、".join(dict.fromkeys(target for _, target in pairs)) + "。 ⏱ 00:30"
        callout = _discrepancy(*(f"字幕写作 {raw}，实为 {target}。" for raw, target in pairs))
        quote = BASE_QUOTE + "字幕中提到了 " + "、".join(raw for raw, _ in pairs) + "。"
        return self.verify(f"{prose}\n\n{callout}", quote)[1]

    def test_high_certainty_phonetic_fixes_need_only_speech(self) -> None:
        for pair in (("chachbt", "ChatGPT"), ("GPD3", "GPT-3"), ("RHF", "RLHF"), ("cat data", "CAD data")):
            with self.subTest(pair=pair):
                self.assert_clean(self.verify_corrections(pair))

    def test_established_target_allows_second_variant_in_separate_callout(self) -> None:
        first = _discrepancy("字幕写作 chachbt，实为 ChatGPT。")
        second = _discrepancy("字幕写作 chache BT，实为 ChatGPT。")
        _, result = self.verify(
            f"核对缓存并记录结果，再介绍 ChatGPT。 ⏱ 00:30\n\n{first}\n\n"
            f"保存输出并检查结果，再演示 ChatGPT。 ⏱ 01:30\n\n{second}",
            BASE_QUOTE + "先介绍 chachbt。",
            later=[("01:30", "保存输出并检查结果，再演示 chache BT。请把本次运行的详细记录单独存放，方便之后逐项核对。")],
        )
        self.assert_clean(result)

    def test_strict_anti_laundering_boundary(self) -> None:
        for pair in (("chache BT", "ChatGPT"), ("v3.5", "v3.6"), ("alpha1.10", "alpha1.1"),
                     ("Alex Tr", "Alex Trumble"), ("natural laws", "scaling laws")):
            with self.subTest(pair=pair):
                result = self.verify_corrections(pair)
                self.assertIn("C04d", failed_ids(result), result["reasons"])

    def test_doubt_downgrade_warning_only_for_valid_phonetic_fix(self) -> None:
        for raw, explanation, expected in (("GPD3", "疑似指 GPT-3", True),
                                            ("v3.5", "可能指 v3.6", False)):
            with self.subTest(raw=raw):
                callout = _discrepancy(f"存疑｜「{raw}」｜{explanation}")
                _, result = self.verify(f"讲者提到 {raw}。 ⏱ 00:30\n\n{callout}",
                                        BASE_QUOTE + f"讲者提到 {raw}。")
                self.assert_soft_warning(result, "存疑可降级", expected)

    def test_doubt_density_boundary(self) -> None:
        anchors = ("缓存", "脚本", "输出", "记录")
        for count in (0, 3, 4):
            with self.subTest(count=count):
                prose = "依次查看缓存、脚本、输出和记录。 ⏱ 00:30"
                if count:
                    prose += "\n\n" + _discrepancy(
                        *(f"存疑｜「{anchor}」｜未交代保存位置" for anchor in anchors[:count])
                    )
                _, result = self.verify(prose)
                self.assert_soft_warning(result, "存疑密度", count > 3)


class ReadabilityTests(ReaderFixture):
    def test_screen_narration_threshold(self) -> None:
        sentences = ("画面把缓存放在左侧。", "画面写明输出位置。", "幻灯片写着检查方法。")
        for count in (0, 2, 3):
            with self.subTest(count=count):
                prose = "".join(sentences[:count]) or "先核对缓存。"
                _, result = self.verify(prose + " ⏱ 00:30", BASE_QUOTE + "".join(sentences))
                self.assert_soft_warning(result, r"画面|幻灯片|屏幕|屏显", count > 2)

    def test_binary_decimal_unit_mixing(self) -> None:
        for unit, other, expected in (("KB", "KiB", True), ("GB", "GiB", True), ("KB", "KB", False)):
            with self.subTest(unit=unit, other=other):
                prose = f"缓存占用 8 {unit}，输出占用 9 {other}。"
                _, result = self.verify(prose + " ⏱ 00:30", BASE_QUOTE + prose)
                self.assert_soft_warning(result, r"单位|二进制|十进制", expected)

    def test_repeated_metric_counts_distinct_h3_sections(self) -> None:
        metric = "输出规模为 142.5M。"
        for count in (2, 3):
            with self.subTest(sections=count):
                middle = "\n\n".join(f"### {label}\n\n{metric} ⏱ 00:30" for label in "甲乙丙"[:count])
                if count == 2:
                    middle += f"\n\n再次提到{metric} ⏱ 00:30"
                _, result = self.verify(middle, BASE_QUOTE + metric)
                self.assert_soft_warning(result, r"重复(?:指标|度量|数值|数字|量化)|(?:指标|度量|数值|数字|量化).*重复", count == 3)

    def test_ordinal_requires_prior_introduction_for_structural_terms(self) -> None:
        for prose, expected in (("第三个子层保存输出。", True), ("第 4 块保存输出。", False),
                                ("先看两个矩阵。\n\n第三个矩阵保存输出。", False)):
            with self.subTest(prose=prose):
                middle = " ⏱ 00:30\n\n".join(prose.split("\n\n")) + " ⏱ 00:30"
                _, result = self.verify(middle, BASE_QUOTE + prose.replace("\n\n", ""))
                self.assert_soft_warning(result, r"序数|序号|序词|未引入|未铺垫", expected)

    def test_minor_version_conflict_requires_unexplained_same_entity(self) -> None:
        for a, b, explained, expected in (("Nova3.6", "nova3_5", False, True),
                                          ("Nova3", "Nova4", False, False),
                                          ("Nova3.6", "nova3_5", True, False)):
            with self.subTest(a=a, b=b, explained=explained):
                prose = f"先记录 {a}，再检查 {b}，并保存运行记录。"
                middle = prose + " ⏱ 00:30"
                if explained:
                    middle += "\n\n" + _discrepancy(f"存疑｜「{a}」｜字幕另一次写作 {b}")
                quote = BASE_QUOTE + prose
                _, result = self.verify(middle, quote)
                self.assert_soft_warning(result, r"版本.*(?:冲突|不一致)|(?:冲突|不一致).*版本", expected)

    def test_untranslated_phrases_in_chinese_prose(self) -> None:
        for phrase in ("quite easy to explain", "5 to 10 years", "9 months"):
            with self.subTest(phrase=phrase):
                _, result = self.verify(f"讲者给出的说法是 {phrase}，随后继续讨论。 ⏱ 00:30",
                                        BASE_QUOTE + f"讲者说 {phrase}，随后讨论输出。")
                self.assert_soft_warning(result, "中英混杂", True)

    def test_chinese_prose_allows_names_code_links_and_translated_range(self) -> None:
        _, result = self.verify(
            "比较 Vector Lab 和 Code Pilot，示例句为“the quick brown fox”。执行 `npm install foo bar`，"
            "参照 [quite easy to explain](https://example.invalid/guide)。"
            "预计需要 5 到 10 年。 ⏱ 00:30\n\n"
            "```text\nquite easy to explain\n```",
            BASE_QUOTE + "提到 Vector Lab、Code Pilot、the quick brown fox、npm install foo bar，"
            "并说 quite easy to explain，预计 5 to 10 years。",
        )
        with self.subTest(contract="phrase exemptions"):
            self.assert_soft_warning(result, "中英混杂", False)
        with self.subTest(contract="grounding"):
            self.assertEqual(result["c04c"], [])

    def test_translated_range_is_grounded_in_english_speech(self) -> None:
        _, result = self.verify(
            "预计需要 5 到 10 年。 ⏱ 00:30",
            "The archive should last 5 to 10 years if the output is kept in a dry location.",
            transcript_lang="en",
        )
        self.assert_clean(result)
        self.assert_soft_warning(result, "中英混杂", False)

    def test_english_note_allows_english_phrases(self) -> None:
        prose = "The cache is quite easy to explain. The archive should last 5 to 10 years."
        _, result = self.verify(prose + " ⏱ 00:30", prose + " Check the output after running the script.",
                                english=True)
        self.assert_soft_warning(result, "中英混杂", False)


class DocumentationTests(unittest.TestCase):
    def test_skill_step_seven_gives_general_warnings_to_independent_reviewer(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        step = re.search(r"(?m)^7\.\s+(.+(?:\n[ \t]+.+)*)", skill)
        self.assertIsNotNone(step)
        self.assertRegex(step[1], r"(?i)independent|独立")
        self.assertRegex(step[1], r"(?i)verifier[`\s.]+warnings|all (?:verification )?warnings|校验(?:器)?(?:的|产生的)?(?:全部)?警告")

    def test_delivery_format_explains_speech_translation_and_fence_order(self) -> None:
        doc = (ROOT / "references/delivery-format.md").read_text(encoding="utf-8")
        checks = {
            "Type 1 speech": r"(?is)(?:行型\s*1|Type[ -]1).{0,450}(?:ASR|音近|同音|语音识别).{0,160}(?:无需|不需|无须|不依赖|without).{0,40}(?:第二来源|画面|second source)",
            "translation": r"(?is)(?:英文短语|英语短语|English phrases).{0,100}(?:译成|译为|翻译成|翻成|translated into).{0,20}(?:中文|汉语|Chinese)",
            "fence order": (
                r"(?is)(?:段落|列表项|paragraph).{0,16}(?:→|->|然后|再|then)\s*`?原文出入"
                r".{0,16}(?:→|->|然后|再|then).{0,16}(?:代码块|围栏|fenced code)"
                r"|原文出入.{0,30}(?:放在|置于|between).{0,30}"
                r"(?:段落|列表项|paragraph).{0,30}(?:代码块|围栏|fenced code)"
            ),
        }
        for contract, pattern in checks.items():
            with self.subTest(contract=contract):
                self.assertIsNotNone(re.search(pattern, doc), contract)

    def test_review_guide_checks_reader_quality(self) -> None:
        doc = (ROOT / "references/review-guide.md").read_text(encoding="utf-8")
        checks = {
            "Type 3 overuse": r"(?is)(?:Type[ -]3|行型\s*3|存疑).{0,230}(?:overus|downgrad|滥用|降级|过多).{0,160}(?:ASR|音近|错字|phonetic)|(?:ASR|音近|错字|phonetic).{0,150}(?:overus|downgrad|滥用|降级|过多).{0,100}(?:Type[ -]3|行型\s*3|存疑)",
            "translation": r"(?i)untranslated English|未翻译的?英[文语]|英文短语.*译|中英混杂",
            "screen narration": r"(?i)screen[ -]narration|画面写明|幻灯片写着|画面把",
        }
        for contract, pattern in checks.items():
            with self.subTest(contract=contract):
                self.assertIsNotNone(re.search(pattern, doc), contract)


class ReviewRound1RegressionTests(ReaderFixture):
    def test_fence_literal_callout_and_omission_marker_render_cleanly(self) -> None:
        fence = '```python\nprint("[!test")\n# 本文略去｜literal\n```'
        note, result = self.verify(
            f"先核对缓存。 ⏱ 00:30\n\n{fence}",
            BASE_QUOTE + '代码示例 print("[!test") 与 本文略去｜literal。',
        )
        note_no_omit = note.replace("\n\n本文略去｜无", "")
        result2 = verify_note.verify(self.job / "transcript.txt", note_no_omit, expected_lang="zh", job=True)
        self.assertTrue(result["allowed"], result["reasons"])
        self.assertTrue(result2["allowed"], result2["reasons"])
        reading = _render(note_no_omit)
        self.assertIn('print("[!test")', reading)

    def test_discrepancy_payload_not_stripped_by_ai_credit(self) -> None:
        callout = _discrepancy("存疑｜「缓存」｜(AI补充)")
        note, result = self.verify(f"先核对缓存。 ⏱ 00:30\n\n{callout}")
        self.assertTrue(result["allowed"], result["reasons"])
        reading = _render(note)
        self.assertIn("缓存（存疑：(AI补充)）", reading)

    def test_secondary_asr_rejects_multiword_surname_swap_and_sign_change(self) -> None:
        cases = (
            (("Anna Shaw", "Anna Shah"), ("Anna Wu", "Anna Shah")),
            (("Ali Shaw 3", "Ali Shah 3"), ("Ali Wu -3", "Ali Shah 3")),
            (("Bot 3", "Bot3"), ("Bot -3", "Bot3")),
            (("Bot 3", "Bot3"), ("Bot\u22123", "Bot3")),
            (("ABCDEFGH", "ABCDEFGHI"), ("AB CDE", "ABCDEFGHI")),
        )
        for pair1, pair2 in cases:
            with self.subTest(pair2=pair2):
                c1 = _discrepancy(f"字幕写作 {pair1[0]}，实为 {pair1[1]}。")
                c2 = _discrepancy(f"字幕写作 {pair2[0]}，实为 {pair2[1]}。")
                _, result = self.verify(
                    f"核对缓存并记录 {pair1[1]}。 ⏱ 00:30\n\n{c1}\n\n"
                    f"继续记录 {pair2[1]}。 ⏱ 01:30\n\n{c2}",
                    BASE_QUOTE + f" 提到 {pair1[0]}。",
                    later=[("01:30", f"保存本次运行的详细记录，方便之后逐项核对全部输出与日志结果，并提到 {pair2[0]}。")],
                )
                self.assertIn("C04d", failed_ids(result), result["reasons"])

    def test_unicode_digits_and_identifier_boundary_in_version_check(self) -> None:
        # Unicode full-width digits ０３ == 3 and Widget1.２ == Widget1.2 (no false conflict)
        self.assertEqual(rules._numeric_signature("０３"), rules._numeric_signature("3"))
        prose_eq = "先看 Widget1.２，再看 Widget1.2。"
        _, res_eq = self.verify(prose_eq + " ⏱ 00:30", BASE_QUOTE + prose_eq)
        self.assert_soft_warning(res_eq, r"版本冲突", False)

        # Legitimate comparison (both Widget1.1 and Widget1.2 appear in linked quote) stays soft WARN, NOT blocking FAIL!
        prose_real = "先看 Widget1.1，再看 Widget1.2，并提到 Other_Widget1.1。"
        callout = _discrepancy("存疑｜「Other_Widget1.1」｜另一个组件")
        _, res_real = self.verify(prose_real + " ⏱ 00:30\n\n" + callout, BASE_QUOTE + prose_real)
        self.assertTrue(res_real["allowed"], res_real["reasons"])
        self.assert_soft_warning(res_real, r"版本冲突", True)

        # Contradictory citation: claim says Widget1.2 while linked quote only says Widget1.1 -> blocking FAIL!
        prose_one_cited = "先看 Widget1.1，再看 Widget1.2，最后保存运行记录。"
        _, res_one = self.verify(prose_one_cited + " ⏱ 00:30", BASE_QUOTE + "先看 Widget1.1，最后保存运行记录。")
        self.assertFalse(res_one["allowed"], res_one["reasons"])
        self.assertTrue(any("版本冲突" in r for r in res_one["reasons"]), res_one["reasons"])

        # Backtick in backtick fence info string is NOT a fence opener; NBSP is NOT a valid closing fence suffix
        self.assertIsNone(rules.match_fence_open("```python`"))
        self.assertIsNotNone(rules.match_fence_open("```python"))
        self.assertFalse(rules.is_fence_close("```\u00a0", "`", 3))
        self.assertTrue(rules.is_fence_close("``` \t", "`", 3))
        # Second source cannot override sign mismatch (Bot−3 -> Bot3); fractional leading zeros stay distinct (0.05 != 0.5)
        self.assertIsNotNone(rules._discrepancy_type1_laundering_issue("Bot\u22123", "Bot3", ("Bot3",)))
        self.assertIsNotNone(rules._discrepancy_type1_laundering_issue("0.05", "0.5", ()))
        self.assertIsNotNone(rules._discrepancy_type1_laundering_issue("3.05", "3.5", ()))

    def test_fence_grounding_does_not_stitch_correction_across_separate_quotes(self) -> None:
        q0 = "开场先说明 old api 的历史背景与兼容方式，请把本次运行的详细记录单独存档以便之后逐项核对结果。"
        q1 = "先单独核对缓存并运行脚本，最后检查并保存记录以便复核全部流程，这段原话的结尾是 old"
        q2 = "api 是独立另一条引文的开头，请保存本次运行的详细记录方便之后逐项核对全部结果。"
        callout = _discrepancy("字幕写作 old api，实为 old_api。")
        fence = "```python\nold_api()\n```"
        middle = (
            "开场说明 old_api 的历史背景与兼容方式，并单独存档详细记录。 ⏱ 00:10\n\n"
            f"核对缓存、运行脚本并保存本次运行的详细记录以便逐项核对结果。 ⏱ 00:30 ⏱ 01:30\n\n{fence}\n\n{callout}"
        )
        _, result = self.verify(middle, q1, later=[("00:10", q0), ("01:30", q2)])
        self.assertTrue(result["allowed"], result["reasons"])
        terms = {finding["term"] for finding in result["c04c"]}
        self.assertIn("old_api", terms, result["c04c"])

    def test_huge_version_digits_do_not_crash_warnings(self) -> None:
        huge = "v" + ("9" * 4305) + ".2"
        _, result = self.verify(
            f"核对缓存并记录 {huge} 版本。 ⏱ 00:30",
            BASE_QUOTE + f" 记录 {huge} 版本。",
        )
        self.assertTrue(result["allowed"], result["reasons"])

    def test_three_minor_versions_partially_explained_still_warns_on_comparison(self) -> None:
        prose = "先看 Widget1.1，再看 Widget1.2，最后看 Widget1.3。"
        callout = _discrepancy("存疑｜「Widget1.2」｜仅核对了这一条")
        _, result = self.verify(prose + " ⏱ 00:30\n\n" + callout, BASE_QUOTE + prose)
        self.assertTrue(result["allowed"], result["reasons"])
        self.assert_soft_warning(result, r"版本冲突", True)

    # --- Phase 6A.1 R2 RED tests ---

    def test_term_short_gloss_inline_rendering_and_invariant7(self) -> None:
        quote = BASE_QUOTE + " 这里讲到 dot product 和 gating 机制，再配合 relu 激活函数。"
        middle = (
            "先核对缓存并运行脚本，再用点积算相似度、看门控怎么开关。 ⏱ 00:30\n\n"
            "> [!note] 术语：点积（dot product）\n"
            "> 短释：两组数对应相乘再相加\n"
            "> 衡量两个向量方向有多一致的基础运算。\n\n"
            "> [!note] 术语：门控（gating）\n"
            "> 短释：决定放行多少信号的开关\n"
            "> 按权重放大或截断中间特征通道的机制。\n\n"
            "最后核对缓存并运行脚本，再经过 `relu` 输出。 ⏱ 00:30\n\n"
            "> [!note] 术语：relu\n"
            "> 短释：把负数归零的函数\n"
            "> 神经网络里常用的非线性激活函数。"
        )
        note, result = self.verify(middle, quote)
        self.assertTrue(result["allowed"], result["reasons"])
        reading = render_reading_note.render_note(note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")
        # First gloss injects inline after alias; second gloss in same paragraph is skipped (max 1/paragraph)
        self.assertIn("点积（注：两组数对应相乘再相加）", reading)
        self.assertNotIn("门控（注：", reading)
        # Code-only alias falls back to sentence end before punctuation
        self.assertIn("最后核对缓存并运行脚本，再经过 `relu` 输出（注：把负数归零的函数）。", reading)
        # Full definitions remain in bottom glossary without leaking 短释 prefix
        self.assertIn("## 术语速查", reading)
        self.assertIn("衡量两个向量方向有多一致的基础运算。", reading)
        self.assertIn("按权重放大或截断中间特征通道的机制。", reading)
        self.assertNotIn("短释：", reading)
        # Top notice discloses inline glosses are organizer additions
        self.assertIn("说明：", reading)
        self.assertIn("（注：", reading)
        # Without any 短释 lines, rendering stays byte-identical to plain glossary mode
        no_gloss_note = "\n".join(ln for ln in note.splitlines() if not ln.startswith("> 短释：")) + "\n"
        reading_plain = render_reading_note.render_note(no_gloss_note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")
        self.assertNotIn("（注：", reading_plain)

    def test_term_short_gloss_validation_and_manual_note_forbidden(self) -> None:
        quote = BASE_QUOTE + " 这里提到 dot product 运算。"
        # >16 chars fails
        too_long = (
            "先核对缓存并运行脚本，再算点积。 ⏱ 00:30\n\n"
            "> [!note] 术语：点积（dot product）\n"
            "> 短释：这是一个超过十六个字而且非常啰嗦的短释解释\n"
            "> 基础向量运算。"
        )
        _, res_long = self.verify(too_long, quote)
        self.assertIn("C04d", failed_ids(res_long), res_long["reasons"])

        # Digits in 短释 fail
        with_digit = (
            "先核对缓存并运行脚本，再算点积。 ⏱ 00:30\n\n"
            "> [!note] 术语：点积（dot product）\n"
            "> 短释：把 2 组数相乘\n"
            "> 基础向量运算。"
        )
        _, res_digit = self.verify(with_digit, quote)
        self.assertIn("C04d", failed_ids(res_digit), res_digit["reasons"])

        # Hand-written （注： in prose fails
        manual = "先核对缓存并运行脚本，再算点积（注：手写注释）。 ⏱ 00:30"
        _, res_manual = self.verify(manual, quote)
        self.assertIn("C04d", failed_ids(res_manual), res_manual["reasons"])

        # English transcript with Chinese-only term gives alias hint
        en_quote = (
            "First inspect the local cache and run the profiling script carefully to confirm all timings "
            "using list comprehensions in the sample code."
        )
        zh_only_term = (
            "这里改用列表推导提速。 ⏱ 00:30\n\n"
            "> [!note] 术语：列表推导\n"
            "> 用方括号在一行里生成列表的写法。"
        )
        _, res_hint = self.verify(zh_only_term, en_quote)
        self.assertIn("C04d", failed_ids(res_hint), res_hint["reasons"])
        self.assertTrue(
            any("中文（English）" in r for r in res_hint["reasons"]),
            res_hint["reasons"],
        )

    def test_name_transcription_tier2_footnote_no_inline_noise(self) -> None:
        quote = BASE_QUOTE + " 讲者提到 Jordan Kay 和 Sam Lin 一起做了这套工具。"
        middle = (
            "主讲人提到 Jordan Kay 与 Sam Lin 一起搭起了最初的原型。 ⏱ 00:30\n\n"
            "> [!warning] 原文出入\n"
            "> 人名转写｜「Jordan Kay」\n"
            "> 人名转写｜「Sam Lin」"
        )
        note, result = self.verify(middle, quote)
        self.assertTrue(result["allowed"], result["reasons"])
        self.assert_soft_warning(result, r"存疑密度", False)
        reading = render_reading_note.render_note(note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")
        # Prose untouched (zero inline （存疑：） noise)
        self.assertIn("主讲人提到 Jordan Kay 与 Sam Lin 一起搭起了最初的原型。", reading)
        self.assertNotIn("（存疑：", reading)
        # Single calm notice at top
        self.assertIn("Jordan Kay", reading)
        self.assertIn("Sam Lin", reading)
        self.assertIn("自动字幕转写", reading)

        # Digits or non-Latin or extra field in 人名转写 must FAIL
        for bad_line in (
            "人名转写｜「Model3」",
            "人名转写｜「张三」",
            "人名转写｜「Jordan Kay」｜或为 Jordan Kaye",
            "人名转写｜「One Two Three Four Five」",
        ):
            bad_middle = (
                "主讲人提到 Jordan Kay、Model3、张三 和 One Two Three Four Five。 ⏱ 00:30\n\n"
                f"> [!warning] 原文出入\n> {bad_line}"
            )
            _, bad_res = self.verify(
                bad_middle,
                BASE_QUOTE + " Jordan Kay Model3 张三 One Two Three Four Five",
            )
            self.assertFalse(bad_res["allowed"], (bad_line, bad_res["reasons"]))

    def test_r2_soft_warnings_rounded_duplication_and_tutorial_duplication(self) -> None:
        # Rounded + exact percentage double-reporting in same paragraph
        q_pct = BASE_QUOTE + " 前馈层占 78%，画面显示 78.3%，注意力占 22%，画面显示 21.7%。"
        p_pct = "前馈层占 78%，更精确的比例是 78.3%。 ⏱ 00:30"
        _, res_pct = self.verify(p_pct, q_pct)
        self.assertTrue(res_pct["allowed"], res_pct["reasons"])
        self.assert_soft_warning(res_pct, r"约数并列", True)

        # Range like 20%–21% or exact-only must NOT trigger 约数并列
        p_clean = "前馈层占 78.3%，范围在 20%–21% 之间。 ⏱ 00:30"
        _, res_clean = self.verify(p_clean, q_pct + " 范围在 20% 到 21%。")
        self.assert_soft_warning(res_clean, r"约数并列", False)

        # Tutorial duplication between 操作步骤 and 可复用做法
        note_dup = (
            "---\n"
            'title: "Synthetic Tutorial"\n'
            'source: "https://www.youtube.com/watch?v=synth000001"\n'
            'channel: "Example Lab"\n'
            'published: "2026-01-01"\n'
            'type: "教程"\n'
            'caption_kind: "auto"\n'
            'skill_version: "test"\n'
            'transcript_path: "transcript.txt"\n'
            "tags: [video-note]\n"
            "---\n\n"
            "## 先记住一句话\n\n"
            "先定位慢函数再验证提速效果。 ⏱ 00:30\n\n"
            "## 这场在谈什么、谁\n\n"
            "Example Lab 于 2026-01-01 演示如何用分析工具找出瓶颈。 ⏱ 00:30\n\n"
            "## 操作步骤\n\n"
            "### 运行分析命令\n\n"
            "先跑 `run_prof main.py`，再导出 `dump_res()` 并用 `view_res out.prof` 看图。 ⏱ 00:30\n\n"
            "## 可复用做法\n\n"
            "先跑 `run_prof main.py`，再导出 `dump_res()` 并用 `view_res out.prof` 看图。 ⏱ 00:30\n\n"
            "本文略去｜无\n\n"
            "## 原文依据\n\n"
            "> [00:30] " + BASE_QUOTE + " run_prof main.py dump_res() view_res out.prof\n"
        )
        res_dup = verify_note.verify_text(
            note_dup,
            "[00:30] " + BASE_QUOTE + " run_prof main.py dump_res() view_res out.prof\n",
            source_url="https://www.youtube.com/watch?v=synth000001",
            published="2026-01-01",
            channel="Example Lab",
            title="Synthetic Tutorial",
        )
        self.assert_soft_warning(res_dup, r"做法重复", True)

        # Inline-code version variant (`Widget1_1`) vs prose (`Widget1.2`): both cited -> soft WARN;
        # contradictory quote (only Widget1_1 cited while prose adds Widget1.2) -> blocking FAIL.
        q_ver = BASE_QUOTE + " 标题是 Widget1.2，配置字段写成 Widget1_1。"
        _, res_ver = self.verify("先核对缓存并运行脚本，看 Widget1.2，配置文件里写的是 `Widget1_1`。 ⏱ 00:30", q_ver)
        self.assertTrue(res_ver["allowed"], res_ver["reasons"])
        self.assert_soft_warning(res_ver, r"版本冲突", True)
        _, res_ver_fail = self.verify(
            "先核对缓存并运行脚本，看 Widget1.2，配置文件里写的是 `Widget1_1`。 ⏱ 00:30",
            BASE_QUOTE + " 配置字段写成 Widget1_1。",
        )
        self.assertFalse(res_ver_fail["allowed"], res_ver_fail["reasons"])
        self.assertTrue(any("版本冲突" in r for r in res_ver_fail["reasons"]), res_ver_fail["reasons"])

        # Regression checks for Claude + Codex R2 review findings:
        # 1. Literal parenthetical `（存疑：缓存）` + `短释` must NOT break invariant #7
        lit_q = BASE_QUOTE + " 这里写作（存疑：缓存）。"
        lit_m = (
            "先核对缓存并运行脚本，这里写作（存疑：缓存）。 ⏱ 00:30\n\n"
            "> [!note] 术语：缓存\n"
            "> 短释：临时保存数据\n"
            "> 加速重复读取的临时存储。"
        )
        lit_note, lit_res = self.verify(lit_m, lit_q)
        self.assertTrue(lit_res["allowed"], lit_res["reasons"])
        lit_reading = render_reading_note.render_note(lit_note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")
        self.assertIn("缓存（注：临时保存数据）", lit_reading)
        self.assertIn("（存疑：缓存）", lit_reading)

        # 2. Full-width range `78%～78.3%` and opposite-sign `-78%` vs `+78.3%` must NOT trigger 约数并列 WARN
        _, res_fw = self.verify("先核对缓存并运行脚本，前馈层比例在 78%～78.3% 之间。 ⏱ 00:30", BASE_QUOTE + " 78% 78.3%")
        self.assert_soft_warning(res_fw, r"约数并列", False)
        _, res_sign = self.verify("先核对缓存并运行脚本，降幅 -78%，增幅 +78.3%。 ⏱ 00:30", BASE_QUOTE + " -78% +78.3%")
        self.assert_soft_warning(res_sign, r"约数并列", False)

        # 2b. Multiline literal `（存疑：\n缓存继续）` + `短释` must NOT break invariant #7
        ml_q = BASE_QUOTE + " 这里写作（存疑：缓存 继续）。"
        ml_m = (
            "先核对缓存并运行脚本，这里写作（存疑：\n缓存继续）。 ⏱ 00:30\n\n"
            "> [!note] 术语：缓存\n"
            "> 短释：临时保存数据\n"
            "> 加速重复读取的临时存储。"
        )
        ml_note, ml_res = self.verify(ml_m, ml_q)
        self.assertTrue(ml_res["allowed"], ml_res["reasons"])
        ml_reading = render_reading_note.render_note(ml_note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")
        self.assertIn("缓存（注：临时保存数据）", ml_reading)
        self.assertIn("（存疑：\n缓存继续）", ml_reading)
        # Unicode minus `−78%` vs `78.3%` must NOT false-warn
        _, res_uminus = self.verify("先核对缓存并运行脚本，降幅 \u221278%，增幅 78.3%。 ⏱ 00:30", BASE_QUOTE + " -78% 78.3%")
        self.assert_soft_warning(res_uminus, r"约数并列", False)

        # 3. Literal inline code `` `（注：` `` must NOT fail manual-note check
        _, res_code_note = self.verify("先核对缓存并运行脚本，不要手写 `（注：` 标记。 ⏱ 00:30", BASE_QUOTE)
        self.assertTrue(res_code_note["allowed"], res_code_note["reasons"])

        # 4. Partial surname `Jordan Kay` must NOT match `Jordan Kay-Smith`; accented `José Müller` passes
        _, res_partial = self.verify(
            "先核对缓存并运行脚本，提到 Jordan Kay-Smith。 ⏱ 00:30\n\n> [!warning] 原文出入\n> 人名转写｜「Jordan Kay」",
            BASE_QUOTE + " Jordan Kay-Smith",
        )
        self.assertFalse(res_partial["allowed"], res_partial["reasons"])
        _, res_accent = self.verify(
            "先核对缓存并运行脚本，提到 José Müller。 ⏱ 00:30\n\n> [!warning] 原文出入\n> 人名转写｜「José Müller」",
            BASE_QUOTE + " José Müller",
        )
        self.assertTrue(res_accent["allowed"], res_accent["reasons"])

        # 5. Gloss alias `relu` must NOT match inside `my_relu`; missing alias skips inline gloss cleanly
        no_hit_q = BASE_QUOTE + " 这里提到 my_relu 和 relu。"
        no_hit_m = (
            "先核对缓存并运行脚本，这里只提 my_relu。 ⏱ 00:30\n\n"
            "> [!note] 术语：relu\n"
            "> 短释：把负数归零\n"
            "> 常见激活函数。"
        )
        no_hit_note, no_hit_res = self.verify(no_hit_m, no_hit_q)
        self.assertTrue(no_hit_res["allowed"], no_hit_res["reasons"])
        no_hit_reading = render_reading_note.render_note(no_hit_note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")
        self.assertNotIn("（注：", no_hit_reading)
        self.assertIn("常见激活函数。", no_hit_reading)

        # Screen assignment `[00:30][画面] r3 = calc()` + unintroduced prose mention `R3` -> 标识符未铺垫 WARN
        ident_note = (
            note_dup.replace("## 可复用做法\n\n先跑 `run_prof main.py`，再导出 `dump_res()` 并用 `view_res out.prof` 看图。 ⏱ 00:30\n\n", "")
            .replace("先跑 `run_prof main.py`，再导出 `dump_res()` 并用 `view_res out.prof` 看图。", "先核对缓存并运行脚本，再跑 `run_prof main.py` 并去掉名为 R3 的调用。")
            .replace("dump_res() view_res out.prof", "R3")
        )
        res_ident = verify_note.verify_text(
            ident_note,
            "[00:30] " + BASE_QUOTE + " run_prof main.py R3\n",
            source_url="https://www.youtube.com/watch?v=synth000001",
            published="2026-01-01",
            channel="Example Lab",
            title="Synthetic Tutorial",
            screen_text="[00:30][画面] r3 = calc()\n",
        )
        self.assert_soft_warning(res_ident, r"标识符未铺垫", True)

    def test_c04c_numeric_boundary_and_dedup(self) -> None:
        # Missing '0' in a code fence containing 10000000, 5000, 70000 must emit at most ONE C04c for '0',
        # NOT 17 substring matches inside larger numbers!
        q = BASE_QUOTE + " 参数是 100、5000、70000 和 10000000，外加 1 和 2。"
        fence = (
            "```python\n"
            "total = 0\n"
            "for i in range(10000000):\n"
            "    total += 100 + 5000 + 70000\n"
            "```"
        )
        middle = f"先核对缓存并运行脚本，下面给出完整示例脚本，参数含 100、5000、70000、10000000。 ⏱ 00:30\n\n{fence}"
        _, result = self.verify(middle, q)
        self.assertTrue(result["allowed"], result["reasons"])
        zero_findings = [f for f in result["c04c"] if f["term"] == "0"]
        self.assertEqual(len(zero_findings), 1, result["c04c"])

    def test_unchanged_failed_submission_does_not_burn_repair_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            (job / "transcript.txt").write_text("[00:30] " + BASE_QUOTE + "\n", encoding="utf-8")
            (job / "selection.md").write_text("00:00–01:00 | 核心步骤 | 留 | 主干\n", encoding="utf-8")
            (job / "status.json").write_text(
                json.dumps(
                    {
                        "status": "transcript_ready",
                        "next_step": "write-note",
                        "source_url": "https://www.youtube.com/watch?v=synth000001",
                        "published": "2026-01-01",
                        "channel": "Example Lab",
                        "title": "Synthetic Job",
                        "screen_ocr": {"mode": "off", "state": "skipped"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (job / "note.md").write_text("bad note draft 1\n", encoding="utf-8")
            p1 = subprocess.run(
                [sys.executable, str(SCRIPTS / "verify_note.py"), "--job", str(job), "--json"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(p1.returncode, 0)
            st1 = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(st1["repair_rounds"], 1, st1)

            # Re-running verify_note.py on the EXACT same unchanged note must NOT burn repair_rounds!
            p2 = subprocess.run(
                [sys.executable, str(SCRIPTS / "verify_note.py"), "--job", str(job), "--json"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(p2.returncode, 0)
            st2 = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(st2["repair_rounds"], 1, st2)

            # Editing note.md to a new broken draft DOES increment repair_rounds to 2
            (job / "note.md").write_text("bad note draft 2\n", encoding="utf-8")
            p3 = subprocess.run(
                [sys.executable, str(SCRIPTS / "verify_note.py"), "--job", str(job), "--json"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(p3.returncode, 0)
            st3 = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(st3["repair_rounds"], 2, st3)

            # Non-canonical --note PATH submission counts once, then repeating the EXACT same --note PATH is idempotent
            alt = Path(tmp) / "alt_bad.md"
            alt.write_text("bad note via --note path\n", encoding="utf-8")
            p4 = subprocess.run(
                [sys.executable, str(SCRIPTS / "verify_note.py"), "--job", str(job), "--note", str(alt), "--json"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertNotEqual(p4.returncode, 0)
            st4 = json.loads((job / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(st4["repair_rounds"], 3, st4)

            # Alternating A -> B -> A must NEVER evade repair_rounds (fresh job)
            job2 = Path(tmp) / "job2"
            job2.mkdir()
            (job2 / "transcript.txt").write_text("[00:30] " + BASE_QUOTE + "\n", encoding="utf-8")
            (job2 / "selection.md").write_text("00:00–01:00 | 核心步骤 | 留 | 主干\n", encoding="utf-8")
            (job2 / "status.json").write_text((job / "status.json").read_text(encoding="utf-8"), encoding="utf-8")
            st_init = json.loads((job2 / "status.json").read_text(encoding="utf-8"))
            for k in ("repair_rounds", "edit_rounds", "note_digest", "verifier", "coverage", "failure_lines", "last_failed_by_gate", "issues", "reason"):
                st_init.pop(k, None)
            st_init.update(status="transcript_ready", next_step="write-note", finished=False, locked=False)
            (job2 / "status.json").write_text(json.dumps(st_init, ensure_ascii=False), encoding="utf-8")
            for idx, txt in enumerate(("bad A\n", "bad B\n", "bad A\n"), 1):
                (job2 / "note.md").write_text(txt, encoding="utf-8")
                subprocess.run(
                    [sys.executable, str(SCRIPTS / "verify_note.py"), "--job", str(job2), "--json"],
                    capture_output=True, text=True, encoding="utf-8",
                )
                st_ab = json.loads((job2 / "status.json").read_text(encoding="utf-8"))
                self.assertEqual(st_ab["repair_rounds"], idx, (idx, st_ab))

    def test_r2_doc_size_caps_and_required_rules(self) -> None:
        root = SCRIPTS.parent
        writer_bytes = sum(
            (root / rel).stat().st_size
            for rel in ("SKILL.md", "references/delivery-format.md", "references/rules.md")
        )
        review_bytes = (root / "references/review-guide.md").stat().st_size
        self.assertLessEqual(writer_bytes, 30720, f"WRITER_REQUIRED too large: {writer_bytes}")
        self.assertLessEqual(review_bytes, 8192, f"review-guide.md too large: {review_bytes}")
        df = (root / "references/delivery-format.md").read_text(encoding="utf-8")
        rg = (root / "references/review-guide.md").read_text(encoding="utf-8")
        for needle in ("短释", "人名转写", "因果", "中文（English）"):
            self.assertIn(needle, df)
        for needle in ("版本冲突", "±30", "标签"):
            self.assertIn(needle, rg)


if __name__ == "__main__":
    unittest.main()
