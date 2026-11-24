#!/usr/bin/env python3
"""Phase 6A.1 reader contracts, using only synthetic note and transcript pairs."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import render_reading_note
import verify_note
import verify_rules as rules
from verify_report import failed_ids

ROOT = Path(__file__).resolve().parents[1]
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
                prose = f"先记录 {a}，再检查 {b}。"
                middle = prose + " ⏱ 00:30"
                if explained:
                    middle += "\n\n" + _discrepancy(f"存疑｜「{a}」｜字幕另一次写作 {b}")
                _, result = self.verify(middle, BASE_QUOTE + prose)
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

        # Unrelated Other_Widget1.1 in 原文出入 must NOT suppress Widget1.1 vs Widget1.2 conflict
        prose_real = "先看 Widget1.1，再看 Widget1.2，并提到 Other_Widget1.1。"
        callout = _discrepancy("存疑｜「Other_Widget1.1」｜另一个组件")
        _, res_real = self.verify(prose_real + " ⏱ 00:30\n\n" + callout, BASE_QUOTE + prose_real)
        self.assert_soft_warning(res_real, r"版本冲突", True)

        # Backtick in backtick fence info string is NOT a fence opener
        self.assertIsNone(rules.match_fence_open("```python`"))
        self.assertIsNotNone(rules.match_fence_open("```python"))

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

    def test_three_minor_versions_partially_explained_still_warns(self) -> None:
        prose = "先看 Widget1.1，再看 Widget1.2，最后看 Widget1.3。"
        callout = _discrepancy("存疑｜「Widget1.2」｜仅核对了这一条")
        _, result = self.verify(prose + " ⏱ 00:30\n\n" + callout, BASE_QUOTE + prose)
        self.assert_soft_warning(result, r"版本冲突", True)


if __name__ == "__main__":
    unittest.main()
