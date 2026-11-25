#!/usr/bin/env python3
"""Phase 6A.2 reader leap contracts (H3 recall filter, filler guard, 5-book doc rules)."""

from __future__ import annotations

import json
import re
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


class ReaderFillerGuardTests(Phase6A2Fixture):
    def test_filler_fails_in_body_but_exempts_quotes_code_callout_and_single_screen_note(self) -> None:
        evidence = [("02:24", Q0224), ("07:40", Q0740)]
        for bad_phrase in ("若还记得前面函数", "如果还记得基准脚本", "把镜头拉远看整体", "口播当时在读日志", "口播提到需要保存"):
            with self.subTest(bad_phrase=bad_phrase):
                middle = (
                    f"### 排查流程\n\n"
                    f"{bad_phrase}，先准备基准函数并保存原始耗时日志。 ⏱ 02:24\n\n"
                    f"接着用分析工具排序内部耗时。 ⏱ 07:40"
                )
                _, result = self.verify(middle, evidence)
                self.assertFalse(result["allowed"], f"{bad_phrase} should FAIL")
                self.assertIn("C04a", failed_ids(result), result["reasons"])

        # Exempt contexts: direct quotes 「」/“”, inline code, fenced code, callout, ## 原文依据
        safe_evidence = [
            ("02:24", Q0224 + "讲者原话说若还记得镜头拉远口播当时这几个词。"),
            ("07:40", Q0740),
        ]
        safe_middle = (
            "### 合法豁免场景\n\n"
            "讲者原话提到「若还记得」与“镜头拉远”，示例标记为 `口播提到`；画面上列出初始基准函数与原始耗时日志。 ⏱ 02:24\n\n"
            "> [!warning] 原文出入\n"
            "> 存疑｜「原始耗时日志」｜口播当时未报精确行数\n\n"
            "接着用分析工具排序内部耗时并定位瓶颈。 ⏱ 07:40"
        )
        _, safe_result = self.verify(safe_middle, safe_evidence)
        self.assertTrue(safe_result["allowed"], safe_result["reasons"])
        # Single "画面上" should NOT trigger screen narration WARN (threshold > 2)
        self.assertFalse(
            any("机器转述" in w for w in safe_result["warnings"]),
            safe_result["warnings"],
        )

        # > 2 occurrences of expanded screen narration ("画面上", "图上", "视频展示了") MUST trigger WARN
        noisy_middle = (
            "### 过多过滤词\n\n"
            "画面上给出基准函数，图上标出耗时日志，视频展示了完整运行结果。 ⏱ 02:24\n\n"
            "接着用分析工具排序内部耗时并定位瓶颈。 ⏱ 07:40"
        )
        _, noisy_result = self.verify(noisy_middle, evidence)
        self.assertTrue(noisy_result["allowed"], noisy_result["reasons"])
        self.assertTrue(
            any("机器转述" in w for w in noisy_result["warnings"]),
            noisy_result["warnings"],
        )


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
        self.assertTrue(cluster_warns, ok_res["warnings"])
        self.assertTrue(
            all("不要为此拆开因果段" in w for w in cluster_warns),
            cluster_warns,
        )

    def test_phase6a2_docs_budget_and_five_book_rules(self) -> None:
        df = (ROOT / "references/delivery-format.md").read_text(encoding="utf-8")
        rg = (ROOT / "references/review-guide.md").read_text(encoding="utf-8")
        writer_bytes = sum(
            (ROOT / rel).stat().st_size
            for rel in ("SKILL.md", "references/delivery-format.md", "references/rules.md")
        )
        review_bytes = (ROOT / "references/review-guide.md").stat().st_size
        self.assertLessEqual(writer_bytes, 30720, f"WRITER_REQUIRED={writer_bytes}")
        self.assertLessEqual(review_bytes, 8192, f"review-guide={review_bytes}")
        # Ensure L35 no longer pressures writers to split causal paragraphs at 3/220
        self.assertNotIn("≤220 字", df)
        self.assertIn("不要为此拆开因果段", df)
        self.assertIn("不得补写视觉描述", df)
        # Ensure review-guide adopts two-pass single-focus review and preserves informational cluster rule
        self.assertIn("红帽念读关", rg)
        self.assertIn("黑帽零脑补关", rg)
        self.assertIn("不要为此拆开因果段", rg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
