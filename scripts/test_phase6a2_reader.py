#!/usr/bin/env python3
"""Phase 6A.2 reader leap contracts (H3 recall filter, filler guard, 5-book doc rules)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_reading_note  # noqa: E402
import verify_note  # noqa: E402
import verify_rules as rules  # noqa: E402
from verify_report import failed_ids  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER = """\
---
title: Synthetic Workshop 6A2
source: https://example.invalid/workshop6a2
channel: Synthetic Workshop
published: 2026-08-01
type: 讲座
caption_kind: auto
skill_version: fixture
transcript_path: transcript.txt
tags: [video-note]
---"""

Q0110 = "这一步先检查初始缓存结构，确认索引表长度、字段命名和默认配置状态是否全部符合预期要求，便于后续逐步排查与核对。"
Q0224 = "先在测试脚本里准备基准函数，运行一遍并保存本次执行的原始耗时日志和调用次数明细，方便之后进行逐项对照检查。"
Q0740 = "接着用分析工具按函数自身耗时与累计耗时排序各个调用记录，定位真正拖慢整体运行速度的核心瓶颈与热点路径。"
Q1000 = "最后把最慢的循环改写成更紧凑的表达式，重新运行基准脚本并核对前后耗时变化，验证整体运行耗时是否明显下降。"
Q1200 = "复核优化后的输出文件与中间结果，确保计算结果与改动前完全一致，没有遗漏边界情况，并把最终核对数据写入汇报摘要。"
Q1300 = "如果输出存在任何偏差或指标异常，立刻回退改动并重新核对输入数据与脚本版本，确保本次变更不会引入任何新的问题。"


def _build_note(middle: str, evidence: list[tuple[str, str]]) -> str:
    quotes = "\n".join(f"> [{stamp}] {quote}" for stamp, quote in evidence)
    return "\n\n".join((
        FRONTMATTER,
        "## 先记住一句话\n\n程序变慢时先用计时工具找瓶颈，再针对最慢函数改写验证。",
        "## 这场在谈什么、谁\n\nSynthetic Workshop 在 2026-08-01 演示如何排查并优化脚本耗时。",
        "## 主线论点\n\n" + middle.strip("\n"),
        "本文略去｜无",
        "## 原文依据\n" + quotes,
    )) + "\n"


def _render(note: str) -> str:
    return render_reading_note.render_note(note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")


class Phase6A2Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.job = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def verify(self, middle: str, evidence: list[tuple[str, str]]) -> tuple[str, dict]:
        note = _build_note(middle, evidence)
        transcript = self.job / "transcript.txt"
        transcript.write_text(
            "".join(f"[{stamp}] {line}\n" for stamp, line in evidence),
            encoding="utf-8",
        )
        (self.job / "note.md").write_text(note, encoding="utf-8")
        (self.job / "status.json").write_text(json.dumps({
            "status": "transcript_ready", "expected_lang": "zh", "duration_seconds": 900,
        }), encoding="utf-8")
        return note, verify_note.verify(transcript, note, expected_lang="zh", job=True)


class H3TimeLabelTests(Phase6A2Fixture):
    def test_h3_label_drops_recall_keeps_true_replay_and_omits_all_recall(self) -> None:
        evidence = [
            ("01:10", Q0110),
            ("02:24", Q0224),
            ("07:40", Q0740),
            ("10:00", Q1000),
            ("12:00", Q1200),
            ("13:00", Q1300),
        ]
        middle = (
            "### 准备基准\n\n"
            "先准备基准函数并保存原始耗时日志。 ⏱ 02:24\n\n"
            "### 排序定位瓶颈\n\n"
            "沿用前述基准函数后，用分析工具排序内部耗时并改写最慢循环。 ⏱ 02:24 ⏱ 07:40 ⏱ 10:00\n\n"
            "### 复核初始配置与最终输出\n\n"
            "先核对开头的初始缓存结构，再复核优化后的输出文件并在偏差时回退。 ⏱ 01:10 ⏱ 12:00 ⏱ 13:00\n\n"
            "### 纯回引小结\n\n"
            "再次对照前述基准函数与原始耗时日志确认改动范围。 ⏱ 02:24"
        )
        note, result = self.verify(middle, evidence)
        self.assertTrue(result["allowed"], result["reasons"])
        reading = _render(note)
        self.assertIn("### 准备基准 · 02:24\n", reading)
        # Recall of 02:24 dropped from B's label, body still preserves prose; no backward inversion!
        self.assertIn("### 排序定位瓶颈 · 07:40–10:00\n", reading)
        self.assertNotIn("02:24–10:00", reading)
        # True un-cited earlier replay (01:10 < 10:00, gap > 180s) shown honestly as 2 segments!
        self.assertIn("### 复核初始配置与最终输出 · 01:10、12:00–13:00\n", reading)
        # All-recall section gets no time label
        self.assertIn("### 纯回引小结\n", reading)
        self.assertNotIn("### 纯回引小结 ·", reading)
        for line in middle.splitlines():
            if "⏱" in line:
                self.assertIn(line.split(" ⏱", 1)[0], reading)

    def test_empty_h3_does_not_claim_time_or_set_replay_boundary(self) -> None:
        note = _build_note(
            "### 空标题 ⏱ 10:00\n\n"
            "### 首段正文\n\n"
            "核对初始缓存，再改写最慢循环。 ⏱ 01:10 ⏱ 10:00",
            [("01:10", Q0110), ("10:00", Q1000)],
        )
        self.assertIn("### 首段正文 · 01:10–10:00\n", _render(note))

    def test_three_replay_segments_and_h2_reset(self) -> None:
        note = _build_note(
            "### 回放前的核对\n\n发现偏差后回退改动。 ⏱ 13:00\n\n"
            "### 三处回放\n\n依次核对缓存、输出和汇报。 ⏱ 01:10 ⏱ 12:00 ⏱ 16:00\n\n"
            "## 另一主题\n\n"
            "### 重新定位\n\n从初始缓存和基准函数重新核对。 ⏱ 01:10 ⏱ 07:40",
            [("01:10", Q0110), ("07:40", Q0740), ("12:00", Q1200), ("13:00", Q1300),
             ("16:00", "最后整理核对结果并交付汇报。")],
        )
        reading = _render(note)
        self.assertIn("### 三处回放 · 01:10、12:00、16:00\n", reading)
        self.assertIn("### 重新定位 · 01:10–07:40\n", reading)


    def test_replay_gap_boundary_and_four_segment_fallback(self) -> None:
        for stamps, expected in (
            (("01:10", "04:10"), "01:10–04:10"),
            (("01:10", "04:11"), "01:10、04:11"),
            (("01:10", "04:11", "07:40", "12:00"), "01:10–12:00"),
        ):
            with self.subTest(stamps=stamps):
                anchors = " ".join(f"⏱ {stamp}" for stamp in stamps)
                note = _build_note(
                    "### 先核对输出\n\n发现偏差后回退改动。 ⏱ 13:00\n\n"
                    f"### 回放排查过程\n\n依次核对排查步骤。 {anchors}",
                    [("13:00", Q1300), *((stamp, Q0110) for stamp in stamps)],
                )
                self.assertIn(f"### 回放排查过程 · {expected}\n", _render(note))


class ReaderFillerGuardTests(Phase6A2Fixture):
    def test_filler_fails_in_body_but_exempts_quotes_code_callout_and_evidence(self) -> None:
        evidence = [("02:24", Q0224), ("07:40", Q0740)]
        for bad_phrase in (
            "若还记得前面函数", "如果还记得基准脚本", "口播当时在读日志",
            "[若还记得](https://example.invalid)",
        ):
            with self.subTest(bad_phrase=bad_phrase):
                middle = (
                    f"### 排查流程\n\n"
                    f"{bad_phrase}，先准备基准函数并保存原始耗时日志。 ⏱ 02:24\n\n"
                    f"接着用分析工具排序内部耗时。 ⏱ 07:40"
                )
                _, result = self.verify(middle, evidence)
                self.assertFalse(result["allowed"], f"{bad_phrase} should FAIL")
                self.assertIn("C04a", failed_ids(result), result["reasons"])

        # Direct quotes, code, callouts and evidence may contain the original wording.
        filler = "若还记得、如果还记得、口播当时与[若还记得](https://example.invalid)"
        safe_evidence = [
            ("02:24", Q0224 + filler),
            ("07:40", Q0740),
        ]
        safe_middle = (
            "### 合法豁免场景\n\n"
            f"讲者原话提到「{filler}」与『{filler}』，又说「请看\n{filler}」，示例标记为 `{filler}`；"
            "画面上列出初始基准函数与原始耗时日志。 ⏱ 02:24\n\n"
            "> [!warning] 原文出入\n"
            f"> 存疑｜「原始耗时日志」｜{filler}\n\n"
            f"```python\n# {filler}\n```\n\n"
            "接着用分析工具排序内部耗时并定位瓶颈。 ⏱ 07:40"
        )
        _, safe_result = self.verify(safe_middle, safe_evidence)
        self.assertTrue(safe_result["allowed"], safe_result["reasons"])
        # Single "画面上" should NOT trigger screen narration WARN (threshold > 2)
        self.assertFalse(
            any("机器转述" in w for w in safe_result["warnings"]),
            safe_result["warnings"],
        )

    def test_three_screen_narration_phrases_include_visible_link_text(self) -> None:
        evidence = [("02:24", Q0224), ("07:40", Q0740)]
        noisy_middle = (
            "### 过多过滤词\n\n"
            "[镜头切到](https://example.invalid)基准函数，画面上列出耗时日志，图上标出运行结果。 ⏱ 02:24\n\n"
            "接着用分析工具排序内部耗时并定位瓶颈。 ⏱ 07:40"
        )
        _, noisy_result = self.verify(noisy_middle, evidence)
        self.assertTrue(noisy_result["allowed"], noisy_result["reasons"])
        self.assertTrue(
            any("机器转述" in w for w in noisy_result["warnings"]),
            noisy_result["warnings"],
        )

    def test_attributions_and_diagram_terms_do_not_trigger_narration_warning(self) -> None:
        evidence = [("02:24", Q0224), ("07:40", Q0740)]
        middle = (
            "### 排查流程\n\n"
            "讲者在口播里纠正了字幕，讲者在口播里纠正了字幕，讲者在口播里纠正了字幕。"
            "变焦时，镜头拉近会压缩背景。"
            "地图上、流程图上、追踪图上和架构图上都有标记。准备基准函数并保存原始耗时日志。 ⏱ 02:24\n\n"
            "讲者引用『画面上有标记，\n图上有日志』，随后用分析工具排序内部耗时。"
            " [参见记录](https://example.invalid/视频展示了) ⏱ 07:40"
        )
        _, result = self.verify(middle, evidence)
        self.assertTrue(result["allowed"], result["reasons"])
        self.assertFalse(any("机器转述" in w for w in result["warnings"]), result["warnings"])


class ParagraphBindingAndDocTests(Phase6A2Fixture):
    def test_paragraph_binding_preserves_c04c_and_informational_cluster_warn(self) -> None:
        self.assertEqual(rules.MAX_CLUSTER_ANCHORS, 3)
        self.assertEqual(rules.MAX_SLICE_CHARS, 220)
        evidence = [
            ("01:10", Q0110),
            ("02:24", Q0224),
            ("07:40", Q0740),
            ("10:00", Q1000),
            ("12:00", Q1200),
        ]
        long_para_body = (
            "排查性能时先检查初始缓存结构并确认索引表长度、字段命名和默认配置状态是否全部符合预期要求，以便后续逐步排查与核对；"
            "接着在测试脚本里准备基准函数，运行一遍并保存本次执行的原始耗时日志和调用次数明细方便逐项对照检查；"
            "随后用分析工具按函数自身耗时与累计耗时排序各个调用记录，从而定位真正拖慢整体运行速度的核心瓶颈与热点路径；"
            "再把最慢的循环改写成更紧凑的表达式，重新运行基准脚本并核对前后耗时变化以验证整体耗时是否明显下降；"
            "最后复核优化后的输出文件与中间结果，确保计算结果与改动前完全一致并把最终核对数据写入汇报摘要。"
        )
        self.assertGreater(len(long_para_body), 220)
        stamps = "⏱ 01:10 ⏱ 02:24 ⏱ 07:40 ⏱ 10:00 ⏱ 12:00"

        # With unbacked number "37%": C04c MUST still catch it!
        _, bad_res = self.verify(f"### 长因果段\n\n{long_para_body}优化后提速 37%。 {stamps}", evidence)
        self.assertIn("37%", {row["term"] for row in bad_res["c04c"]}, bad_res["c04c"])

        # Without unbacked number: C04b PASSES, cluster WARN is marked informational (don't split!)
        _, ok_res = self.verify(f"### 长因果段\n\n{long_para_body} {stamps}", evidence)
        self.assertTrue(ok_res["allowed"], ok_res["reasons"])
        self.assertEqual(ok_res["c04c"], [], ok_res["c04c"])
        cluster_warns = [w for w in ok_res["warnings"] if "簇分片 WARN" in w]
        self.assertCountEqual(
            cluster_warns,
            [
                "簇分片 WARN: 长因果段 单簇包含 5 个 ⏱（信息性提示，不要为此拆开因果段）",
                f"簇分片 WARN: 长因果段 单片去代码长度 {len(long_para_body)} 字"
                "（信息性提示，不要为此拆开因果段）",
            ],
        )

    def test_phase6a2_docs_budget_and_five_book_rules(self) -> None:
        writer_docs = ("SKILL.md", "references/delivery-format.md", "references/rules.md")
        review_doc = "references/review-guide.md"
        docs = {rel: (ROOT / rel).read_bytes() for rel in (*writer_docs, review_doc)}
        for rel, data in docs.items():
            with self.subTest(doc=rel):
                self.assertNotIn(b"\r", data)
        df = docs["references/delivery-format.md"].decode("utf-8")
        rg = docs[review_doc].decode("utf-8")
        writer_bytes = sum(len(docs[rel]) for rel in writer_docs)
        review_bytes = len(docs[review_doc])
        self.assertLessEqual(writer_bytes, 30720, f"WRITER_REQUIRED={writer_bytes}")
        self.assertLessEqual(review_bytes, 8192, f"review-guide={review_bytes}")
        # Ensure L35 no longer pressures writers to split causal paragraphs at 3/220
        self.assertNotIn("≤220 字", df)
        self.assertIn("不要为此拆开因果段", df)
        self.assertIn("不得补写视觉描述", df)
        self.assertIn("不强补原文未讲环节", df)
        self.assertIn("不替讲者作答", df)
        # Ensure review-guide adopts two-pass single-focus review and preserves informational cluster rule
        self.assertIn("红帽念读关", rg)
        self.assertIn("黑帽零脑补关", rg)
        self.assertIn("不要为此拆开因果段", rg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
