#!/usr/bin/env python3
"""RED/GREEN tests for Phase 6 Commit 2 validator and coverage upgrades."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import coverage_check as cov  # noqa: E402
import render_reading_note  # noqa: E402
import verify_note  # noqa: E402
import verify_rules as rules  # noqa: E402
from verify_report import failed_ids  # noqa: E402

FRONTMATTER = """\
---
title: Phase 6 Validator Fixture
source: https://example.invalid/videos/p6
channel: Tech Lab
published: 2026-08-01
type: {kind}
caption_kind: auto
skill_version: fixture
transcript_path: transcript.txt
tags: [video-note]
---"""


def _clock(sec: int) -> str:
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _write_job(
    root: Path,
    name: str,
    note: str,
    transcript: str,
    *,
    selection: str | None = None,
    duration: int = 300,
    screen: str | None = None,
) -> Path:
    job = root / name
    job.mkdir(parents=True, exist_ok=True)
    (job / "transcript.txt").write_text(transcript, encoding="utf-8")
    (job / "note.md").write_text(note, encoding="utf-8")
    status: dict = {"status": "transcript_ready", "expected_lang": "en", "duration_seconds": duration}
    if screen is not None:
        (job / "screen.txt").write_text(screen, encoding="utf-8")
        status["screen_ocr"] = {
            "state": "ready",
            "mode": "slides",
            "sha256": hashlib.sha256(screen.encode("utf-8")).hexdigest(),
        }
    (job / "status.json").write_text(json.dumps(status), encoding="utf-8")
    if selection is not None:
        (job / "selection.md").write_text(selection, encoding="utf-8")
    return job


def _build_note(
    middle: str,
    quotes: list[tuple[str, str]],
    *,
    kind: str = "讲座",
    include_closings: bool = True,
    omission: str | None = "本文略去｜无",
) -> str:
    parts = [
        FRONTMATTER.format(kind=kind),
        "## 先记住一句话\n\n先拆步骤，再验证结果。",
        "## 这场在谈什么、谁\n\nTech Lab 在 2026-08-01 演示工程实践。",
        middle.strip("\n"),
    ]
    if include_closings:
        parts.extend([
            "## 可复用做法\n\n本节没有补充中间部分之外的情况。",
            "## 翻车或别用\n\n本节没有补充中间部分之外的情况。",
            "## 今天立刻动手一步\n\n先运行一次基准测试并记录耗时。（改写讲者做法） ⏱ 00:30",
        ])
    if omission is not None:
        parts.append(omission)
    evidence = "\n".join(f"> [{stamp}] {text}" for stamp, text in quotes)
    parts.append("## 原文依据\n" + evidence + "\n")
    return "\n\n".join(parts)


class ClusterSlicingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.quotes = [
            ("00:30", "The first stage processes 10 modules in parallel before flushing logs to disk."),
            ("01:30", "The second stage takes 20 milliseconds after warm cache initialization completes."),
            ("02:30", "The third stage verifies 30 records across the cluster before reporting final metrics."),
        ]
        self.transcript = "\n".join(f"[{s}] {t}" for s, t in self.quotes) + "\n"

    def test_multi_slice_paragraph_isolates_c04c_per_slice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good_note = _build_note(
                "## 主线论点\n\n"
                "先看架构分工。第一阶段并行处理 10 个模块。 ⏱ 00:30 "
                "第二阶段耗时 20 毫秒完成。 ⏱ 01:30 "
                "第三阶段校验 30 条记录。 ⏱ 02:30 综上，三步串联完成。",
                self.quotes,
            )
            good_job = _write_job(Path(tmp), "good", good_note, self.transcript)
            good_res = verify_note.verify(good_job / "transcript.txt", good_note, expected_lang="en", job=True)
            self.assertTrue(good_res["allowed"], good_res["reasons"])
            self.assertEqual(good_res["c04c"], [], good_res["c04c"])

            # Swap 10 and 20 across slices in the SAME paragraph: must trigger C04c!
            swapped_note = _build_note(
                "## 主线论点\n\n"
                "第一阶段并行处理 20 个模块。 ⏱ 00:30 "
                "第二阶段耗时 10 毫秒完成。 ⏱ 01:30 "
                "第三阶段校验 30 条记录。 ⏱ 02:30",
                self.quotes,
            )
            swapped_job = _write_job(Path(tmp), "swapped", swapped_note, self.transcript)
            swapped_res = verify_note.verify(swapped_job / "transcript.txt", swapped_note, expected_lang="en", job=True)
            hit_terms = {row["term"] for row in swapped_res["c04c"]}
            self.assertIn("20", hit_terms, swapped_res["c04c"])
            self.assertIn("10", hit_terms, swapped_res["c04c"])

    def test_unlinked_tail_and_lead_exemptions_vs_new_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Short lead paragraph <= 120 chars with no new verifiable facts is exempt
            lead_ok = _build_note(
                "## 主线论点\n\n### 整体流程\n\n"
                "下面按顺序展开三个阶段的核心做法。\n\n"
                "第一阶段处理 10 个模块。 ⏱ 00:30 第二阶段耗时 20 毫秒。 ⏱ 01:30 第三阶段校验 30 条记录。 ⏱ 02:30",
                self.quotes,
            )
            job = _write_job(Path(tmp), "lead-ok", lead_ok, self.transcript)
            res = verify_note.verify(job / "transcript.txt", lead_ok, expected_lang="en", job=True)
            self.assertTrue(res["allowed"], res["reasons"])

            # Lead paragraph with a new number MUST fail C04b
            lead_fact = lead_ok.replace("下面按顺序展开三个阶段的核心做法。", "这一节先列出 99 个注意事项。")
            job2 = _write_job(Path(tmp), "lead-fact", lead_fact, self.transcript)
            res2 = verify_note.verify(job2 / "transcript.txt", lead_fact, expected_lang="en", job=True)
            self.assertIn("C04b", failed_ids(res2), res2["reasons"])

            # Tail after last ⏱ with a new fact MUST fail C04b
            tail_fact = _build_note(
                "## 主线论点\n\n"
                "第一阶段处理 10 个模块。 ⏱ 00:30 随后额外新增了 99 个节点。\n\n"
                "第二阶段耗时 20 毫秒。 ⏱ 01:30\n\n第三阶段校验 30 条记录。 ⏱ 02:30",
                self.quotes,
            )
            job3 = _write_job(Path(tmp), "tail-fact", tail_fact, self.transcript)
            res3 = verify_note.verify(job3 / "transcript.txt", tail_fact, expected_lang="en", job=True)
            self.assertIn("C04b", failed_ids(res3), res3["reasons"])


class DiscrepancyAndCodeBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.quotes = [
            ("00:30", "We run DocLing and call results dot print stats to inspect profiler timing on qwen3_5."),
            ("01:30", "Speaker Michael Tru also mentioned version 3.6 during the walk through of the benchmark."),
            ("02:30", "Finally we check the output table and save the summary file to disk for later comparison."),
        ]
        self.transcript = "\n".join(f"[{s}] {t}" for s, t in self.quotes) + "\n"

    def test_discrepancy_type1_merges_corrections_and_blocks_laundering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Valid casing fix works AND wrong spelling leak in prose fails C04d
            ok_note = _build_note(
                "## 主线论点\n\n"
                "先运行 Docling 工具查看分析结果。 ⏱ 00:30\n\n"
                "> [!warning] 原文出入\n"
                "> 字幕写作 DocLing，实为 Docling。\n\n"
                "接着核对后续基准与输出。 ⏱ 01:30 ⏱ 02:30",
                self.quotes,
            )
            job = _write_job(Path(tmp), "t1-ok", ok_note, self.transcript)
            res = verify_note.verify(job / "transcript.txt", ok_note, expected_lang="en", job=True)
            self.assertTrue(res["allowed"], res["reasons"])
            self.assertEqual(res["c04c"], [], res["c04c"])

            leaked = ok_note.replace("先运行 Docling 工具", "先运行 DocLing 工具")
            res_leak = verify_note.verify(job / "transcript.txt", leaked, expected_lang="en", job=True)
            self.assertIn("C04d", failed_ids(res_leak), res_leak["reasons"])

            # Version/number laundering (qwen3_5 -> Qwen3.6) MUST FAIL C04d (upgrade to Type 3!)
            ver_bad = _build_note(
                "## 主线论点\n\n"
                "这里测试 Qwen3.6 模型。 ⏱ 00:30\n\n"
                "> [!warning] 原文出入\n"
                "> 字幕写作 qwen3_5，实为 Qwen3.6。\n\n"
                "继续说明后续基准与输出。 ⏱ 01:30 ⏱ 02:30",
                self.quotes,
            )
            res_ver = verify_note.verify(job / "transcript.txt", ver_bad, expected_lang="en", job=True)
            self.assertIn("C04d", failed_ids(res_ver), res_ver["reasons"])

            # Proper name completion without second source (Michael Tru -> Michael Truell) MUST FAIL C04d
            name_bad = _build_note(
                "## 主线论点\n\n"
                "讲者 Michael Truell 介绍了基准测试。 ⏱ 01:30\n\n"
                "> [!warning] 原文出入\n"
                "> 字幕写作 Michael Tru，实为 Michael Truell。\n\n"
                "前后步骤照常记录。 ⏱ 00:30 ⏱ 02:30",
                self.quotes,
            )
            res_name = verify_note.verify(job / "transcript.txt", name_bad, expected_lang="en", job=True)
            self.assertIn("C04d", failed_ids(res_name), res_name["reasons"])

    def test_discrepancy_type2_grounds_lowercase_code_and_warns_on_bad_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Grounded lowercase code via Type 2 -> 0 C04c warnings
            ok_note = _build_note(
                "## 主线论点\n\n"
                "调用 `results.print_stats()` 查看耗时。 ⏱ 00:30\n\n"
                "> [!warning] 原文出入\n"
                "> 口述代码｜results dot print stats｜`results.print_stats()`\n\n"
                "随后完成基准和结果保存。 ⏱ 01:30 ⏱ 02:30",
                self.quotes,
            )
            job = _write_job(Path(tmp), "t2-ok", ok_note, self.transcript)
            res = verify_note.verify(job / "transcript.txt", ok_note, expected_lang="en", job=True)
            self.assertTrue(res["allowed"], res["reasons"])
            self.assertEqual(res["c04c"], [], res["c04c"])

            # Unbacked lowercase API in inline code -> C04c code finding!
            unbacked = _build_note(
                "## 主线论点\n\n"
                "调用 `secret_api.launch_rocket()` 启动任务。 ⏱ 00:30\n\n"
                "随后完成基准和结果保存。 ⏱ 01:30 ⏱ 02:30",
                self.quotes,
            )
            res_unbacked = verify_note.verify(job / "transcript.txt", unbacked, expected_lang="en", job=True)
            self.assertTrue(any(r["kind"] == "code" for r in res_unbacked["c04c"]), res_unbacked["c04c"])

            # Reverse read-back mismatch -> WARN (still allowed!)
            bad_readback = _build_note(
                "## 主线论点\n\n"
                "调用 `foo.bar_baz()` 查看结果。 ⏱ 00:30\n\n"
                "> [!warning] 原文出入\n"
                "> 口述代码｜results dot print stats｜`foo.bar_baz()`\n\n"
                "随后完成基准和结果保存。 ⏱ 01:30 ⏱ 02:30",
                self.quotes,
            )
            res_rb = verify_note.verify(job / "transcript.txt", bad_readback, expected_lang="en", job=True)
            self.assertTrue(res_rb["allowed"], res_rb["reasons"])
            self.assertTrue(any("口述代码" in w for w in res_rb["warnings"]), res_rb["warnings"])

    def test_discrepancy_type3_validates_anchor_length_and_does_not_exempt_c04c(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Valid Type 3 with an unsupported number 999 still gets C04c finding!
            note = _build_note(
                "## 主线论点\n\n"
                "讲者提到 3.6 版本和 999 次实验。 ⏱ 01:30\n\n"
                "> [!warning] 原文出入\n"
                "> 存疑｜「3.6 版本」｜画面显示为 3.5\n\n"
                "前后步骤照常完成。 ⏱ 00:30 ⏱ 02:30",
                self.quotes,
            )
            job = _write_job(Path(tmp), "t3", note, self.transcript)
            res = verify_note.verify(job / "transcript.txt", note, expected_lang="en", job=True)
            self.assertTrue(res["allowed"], res["reasons"])
            self.assertTrue(any(r["term"] == "999" for r in res["c04c"]), res["c04c"])

            # Explanation > 50 chars -> C04d FAIL
            long_exp = "存疑｜「3.6 版本」｜" + "这是一段超过五十个字的详细冲突说明" * 4
            res_long = verify_note.verify(
                job / "transcript.txt",
                note.replace("存疑｜「3.6 版本」｜画面显示为 3.5", long_exp),
                expected_lang="en",
                job=True,
            )
            self.assertIn("C04d", failed_ids(res_long), res_long["reasons"])

            # Bad anchor -> C04d FAIL (keeps verify PASS => render PASS contract!)
            res_bad_anchor = verify_note.verify(
                job / "transcript.txt",
                note.replace("存疑｜「3.6 版本」｜画面显示为 3.5", "存疑｜「不存在锚」｜说明"),
                expected_lang="en",
                job=True,
            )
            self.assertIn("C04d", failed_ids(res_bad_anchor), res_bad_anchor["reasons"])


class TermLimitsAndTipBanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.quotes = [
            ("00:30", "We use RAG retrieval before passing the prompt to the language model in production."),
            ("01:30", "Each request caches embeddings to reduce latency and keep throughput steady under load."),
            ("02:30", "Monitoring tracks recall and latency across all shards every minute in the dashboard."),
        ]
        self.transcript = "\n".join(f"[{s}] {t}" for s, t in self.quotes) + "\n"

    def test_term_box_hard_limits_and_tip_ban(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = _build_note(
                "## 主线论点\n\n"
                "系统使用 RAG 检索增强生成。 ⏱ 00:30\n\n"
                "{BLOCK}\n\n"
                "接着缓存向量并监控指标。 ⏱ 01:30 ⏱ 02:30",
                self.quotes,
            )
            job = _write_job(Path(tmp), "terms", base, self.transcript)

            good = base.replace("{BLOCK}", "> [!note] 术语：RAG\n> 检索增强生成，先查资料再作答。（Claude 补充，非视频内容）")
            res_ok = verify_note.verify(job / "transcript.txt", good, expected_lang="en", job=True)
            self.assertTrue(res_ok["allowed"], res_ok["reasons"])

            bad_cases = (
                ("time_in_term", "> [!note] 术语：RAG\n> 检索增强生成。 ⏱ 00:30"),
                ("three_sentences", "> [!note] 术语：RAG\n> 第一句解释。第二句补充。第三句超限。"),
                ("over_120_chars", "> [!note] 术语：RAG\n> " + "这是很长的术语解释用来测试一百二十字硬限" * 8 + "。"),
                ("banned_tip", "> [!tip] 类比（Claude 补充）\n> 像查字典。\n> 不成立的地方：会过期。"),
            )
            for name, block in bad_cases:
                with self.subTest(case=name):
                    note = base.replace("{BLOCK}", block)
                    res = verify_note.verify(job / "transcript.txt", note, expected_lang="en", job=True)
                    self.assertIn("C04d", failed_ids(res), res["reasons"])


class S01OverlapAndVirtualWindowTests(unittest.TestCase):
    def test_s01_cue_overlap_hits_all_covered_retained_units(self) -> None:
        cues = [
            (10, "Opening unit starts by introducing the seed storage method clearly."),
            (59, "The transition sentence crosses cleanly from the first minute into the second minute."),
            (62, "And continues right into the second unit with full details for labeling packets."),
            (130, "Third retained unit explains keeping damp envelopes on a dry shelf separately."),
        ]
        transcript = "\n".join(f"[{_clock(s)}] {t}" for s, t in cues) + "\n"
        # Quote 1 starts at 00:59 and spans cue 59 + cue 62 -> covers BOTH [00:00-01:00] and [01:00-02:00]!
        quotes = [
            ("00:59", f"{cues[1][1]} {cues[2][1]}"),
            ("02:10", cues[3][1]),
        ]
        selection = (
            "00:00–01:00 | 第一段 | 留 | 核心开篇\n"
            "01:00–02:00 | 第二段 | 留 | 核心方法\n"
            "02:00–03:00 | 第三段 | 留 | 实操步骤\n"
        )
        note = _build_note(
            "## 主线论点\n\n第一二段合并讲解标签方法。 ⏱ 00:59\n\n第三段说明防潮存放。 ⏱ 02:10",
            quotes,
            include_closings=False,
            omission=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp), "overlap", note, transcript, selection=selection, duration=180)
            res = cov.check_job(job)
            self.assertTrue(res["ok"], res["reasons"])

    def test_s01_virtual_subwindows_catch_sparse_long_unit(self) -> None:
        # 600s video with ONE huge 540s retained unit [00:00-09:00] + two short retained units.
        # Cues appear across all sub-windows (every 100s), so virtual windowing splits [00:00-09:00] into 3 slots.
        cues = [
            (20, "First hundred seconds introduce the main data structure layout in memory."),
            (200, "Second subwindow explains node splitting rules when leaf capacity is exceeded."),
            (400, "Third subwindow demonstrates latch crabbing under concurrent reader and writer load."),
            (550, "Fourth section summarizes benchmark throughput numbers on SSD storage."),
            (580, "Fifth section wraps up practical tuning knobs for buffer pool sizing."),
        ]
        transcript = "\n".join(f"[{_clock(s)}] {t}" for s, t in cues) + "\n"
        selection = (
            "00:00–09:00 | 超长主干 | 留 | 整段讲座主干\n"
            "09:00–09:30 | 基准 | 留 | 吞吐数据\n"
            "09:30–10:00 | 调优 | 留 | 调优建议\n"
        )
        # Only 1 quote inside [00:00-09:00] (misses 2 of 3 virtual sub-windows!) -> MUST FAIL S01!
        sparse_quotes = [("00:20", cues[0][1]), ("09:10", cues[3][1]), ("09:40", cues[4][1])]
        sparse_note = _build_note(
            "## 主线论点\n\n主干介绍。 ⏱ 00:20\n\n基准。 ⏱ 09:10\n\n调优。 ⏱ 09:40",
            sparse_quotes,
            include_closings=False,
            omission=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            job_sparse = _write_job(Path(tmp), "sparse", sparse_note, transcript, selection=selection, duration=600)
            res_sparse = cov.check_job(job_sparse)
            self.assertFalse(res_sparse["ok"])
            self.assertIn("S01", failed_ids(res_sparse), res_sparse["reasons"])

            # Covering all 3 virtual sub-windows + 2 short units -> PASS!
            full_quotes = [
                ("00:20", cues[0][1]),
                ("03:20", cues[1][1]),
                ("06:40", cues[2][1]),
                ("09:10", cues[3][1]),
                ("09:40", cues[4][1]),
            ]
            full_note = _build_note(
                "## 主线论点\n\n第一部分。 ⏱ 00:20\n\n第二部分。 ⏱ 03:20\n\n第三部分。 ⏱ 06:40\n\n"
                "基准。 ⏱ 09:10\n\n调优。 ⏱ 09:40",
                full_quotes,
                include_closings=False,
                omission=None,
            )
            job_full = _write_job(Path(tmp), "full", full_note, transcript, selection=selection, duration=600)
            res_full = cov.check_job(job_full)
            self.assertTrue(res_full["ok"], res_full["reasons"])


class OptionalClosingsAndTutorialTypeTests(unittest.TestCase):
    def test_tutorial_type_optional_closings_and_optional_empty_omission(self) -> None:
        quotes = [
            ("00:20", "First import cProfile and pstats in your Python script before running the workload."),
            ("01:00", "Wrap the target function call inside a Profile context manager to capture timing."),
            ("02:00", "Sort the collected statistics by cumulative time and print the top twenty functions."),
        ]
        transcript = "\n".join(f"[{s}] {t}" for s, t in quotes) + "\n"
        selection = (
            "00:00–00:50 | 导入模块 | 留 | 准备分析工具\n"
            "00:50–01:40 | 采集耗时 | 留 | 包裹目标函数\n"
            "01:40–02:30 | 输出排序 | 留 | 打印耗时榜单\n"
        )
        note = _build_note(
            "## 操作步骤\n\n"
            "先导入 `cProfile` 和 `pstats`。 ⏱ 00:20\n\n"
            "用 `Profile` 上下文管理器包裹目标函数。 ⏱ 01:00\n\n"
            "按累计耗时排序并输出前 20 个函数。 ⏱ 02:00",
            quotes,
            kind="教程",
            include_closings=False,
            omission=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp), "tutorial", note, transcript, selection=selection, duration=150)
            ver = verify_note.verify(job / "transcript.txt", note, expected_lang="en", job=True)
            self.assertTrue(ver["allowed"], ver["reasons"])
            covered = cov.check_job(job)
            self.assertTrue(covered["ok"], covered["reasons"])
            rendered = render_reading_note.render_note(note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")
            self.assertNotIn("没写进来的部分：", rendered)
            self.assertNotIn("⏱", rendered)

            # If selection HAS omitted units, missing 本文略去 MUST still fail S01!
            sel_omit = selection + "02:30–03:00 | 片尾寒暄 | 略 | 与实操无关\n"
            job_omit = _write_job(Path(tmp), "tutorial-omit", note, transcript, selection=sel_omit, duration=180)
            cov_omit = cov.check_job(job_omit)
            self.assertFalse(cov_omit["ok"])
            self.assertIn("S01", failed_ids(cov_omit), cov_omit["reasons"])

    def test_dead_rules_removed_and_chinese_lecture_r13_passes_without_imperatives(self) -> None:
        self.assertFalse(hasattr(rules, "r14_platform_title"))
        self.assertFalse(hasattr(rules, "_NOTE_CHECKING_PROCESS"))
        self.assertFalse(hasattr(rules, "_imperatives"))
        zh_quotes = [
            ("00:20", "大语言模型的注意力机制本质上是在计算不同位置向量之间的相关性权重分布，从而决定每个词元应当关注哪些上下文信息。"),
            ("01:00", "缩放点积能够避免维度增大时内积数值过大导致梯度过小，从而让深层网络的训练过程始终保持良好的数值稳定性和收敛速度。"),
            ("02:00", "多层堆叠之后，模型就能在长上下文中把远距离的语义依赖逐步汇聚起来，并在最终输出层形成更加准确的预测结果。"),
        ]
        zh_transcript = "\n".join(f"[{s}] {t}" for s, t in zh_quotes) + "\n"
        zh_note = _build_note(
            "## 主线论点\n\n"
            "注意力机制计算不同位置向量之间的相关性权重。 ⏱ 00:20\n\n"
            "缩放点积帮助高维训练保持数值稳定。 ⏱ 01:00\n\n"
            "多层堆叠可以汇聚长上下文中的远距离语义依赖。 ⏱ 02:00",
            zh_quotes,
            include_closings=False,
            omission=None,
        ).replace(
            "## 原文依据",
            "## 今天立刻动手一步\n\n对照一份模型结构图梳理注意力权重与缩放点积的关系。（改写讲者做法） ⏱ 00:20\n\n## 原文依据",
            1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp), "zh-lecture", zh_note, zh_transcript)
            ver = verify_note.verify(job / "transcript.txt", zh_note, expected_lang="zh", job=True)
            self.assertTrue(ver["allowed"], ver["reasons"])

    def test_locked_phase6_calibration_constants_and_term_count_warn(self) -> None:
        self.assertEqual(rules.MAX_CLUSTER_ANCHORS, 3)
        self.assertEqual(rules.MAX_SLICE_CHARS, 220)
        self.assertEqual(rules.MAX_TAIL_CHARS, 80)
        self.assertEqual(rules.MAX_LEAD_CHARS, 120)
        self.assertEqual(rules.MAX_TERM_SENTENCES, 2)
        self.assertEqual(rules.MAX_TERM_CHARS, 120)
        self.assertEqual(rules.TERM_COUNT_WARN_THRESHOLD, 12)
        self.assertEqual(rules.MAX_DOUBT_CHARS, 50)
        self.assertEqual(cov.OVERLAP_TOLERANCE, 1.5)
        self.assertEqual(cov.VIRTUAL_WINDOW_MIN_SECONDS, 240.0)
        self.assertEqual(cov.VIRTUAL_WINDOW_RATIO, 0.05)

        terms = [f"Term{i}" for i in range(13)]
        quotes = [
            ("00:20", "First our compiler pipeline parses Term0, checks Term1, optimizes Term2, schedules Term3, and validates Term4 before emitting bytecode."),
            ("01:00", "Next the runtime layer initializes Term5, allocates Term6, monitors Term7, and balances Term8 across worker pools smoothly."),
            ("02:00", "Finally observability aggregates Term9, traces Term10, audits Term11, and alerts on Term12 whenever latency exceeds budget."),
        ]
        transcript = "\n".join(f"[{s}] {t}" for s, t in quotes) + "\n"
        term_blocks = "\n\n".join(f"> [!note] 术语：{t}\n> 简短术语定义。" for t in terms)
        note = _build_note(
            f"## 主线论点\n\n系统依次介绍关键概念。 ⏱ 00:20 ⏱ 01:00 ⏱ 02:00\n\n{term_blocks}",
            quotes,
            include_closings=False,
            omission=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp), "term-warn", note, transcript)
            ver = verify_note.verify(job / "transcript.txt", note, expected_lang="en", job=True)
            self.assertTrue(ver["allowed"], ver["reasons"])
            self.assertTrue(any("术语数 WARN" in w for w in ver["warnings"]), ver["warnings"])

    def test_review_round1_validator_and_s01_regressions(self) -> None:
        quotes = [
            ("00:20", "We run load local config on version v1.10, v10, and v_10 during startup checks cleanly."),
            ("01:00", "The second stage writes metrics to local disk after validating the active schema."),
            ("02:00", "The third stage closes connections and prints a clean exit summary to stdout."),
        ]
        transcript = "\n".join(f"[{s}] {t}" for s, t in quotes) + "\n"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # BLOCKING-5 & R2-BLOCKING-4: v1.10 -> v1.1, v10 -> Ten, and v_10 -> vTen must all fail C04d
            for header, orig, corr in (
                ("> [!warning] 原文出入", "v1.10", "v1.1"),
                ("> [!warning] 字幕更正", "v1.10", "v1.1"),
                ("> [!warning] 原文出入", "v10", "Ten"),
                ("> [!warning] 原文出入", "v_10", "vTen"),
            ):
                with self.subTest(header=header, orig=orig, corr=corr):
                    bad = _build_note(
                        f"## 主线论点\n\n系统升级到 {corr} 版本。 ⏱ 00:20\n\n{header}\n> 字幕写作 {orig}，实为 {corr}。\n\n"
                        "后续落盘与退出正常完成。 ⏱ 01:00 ⏱ 02:00",
                        quotes,
                        include_closings=False,
                        omission=None,
                    )
                    job = _write_job(root, f"launder-{corr}", bad, transcript)
                    ver = verify_note.verify(job / "transcript.txt", bad, expected_lang="en", job=True)
                    self.assertIn("C04d", failed_ids(ver), ver["reasons"])

            # BLOCKING-7 & R2-BLOCKING-1: Type 2 cannot smuggle partial tokens (secret) or ground unrelated/uncited slices
            smuggle = _build_note(
                "## 主线论点\n\n"
                "先调用 `load_local_config()` 与 `load_local_secret_config()`。 ⏱ 00:20\n\n"
                "> [!warning] 原文出入\n"
                "> 口述代码｜load local config｜`load_local_config(); load_local_secret_config()`\n\n"
                "另一片无关引文又调用 `load_local_config()`。 ⏱ 01:00\n\n"
                "最后关闭连接并汇总。 ⏱ 02:00",
                quotes,
                include_closings=False,
                omission=None,
            )
            job_s = _write_job(root, "smuggle", smuggle, transcript)
            ver_s = verify_note.verify(job_s / "transcript.txt", smuggle, expected_lang="en", job=True)
            code_hits = [r["term"] for r in ver_s["c04c"] if r["kind"] == "code"]
            self.assertIn("load_local_secret_config", code_hits, ver_s["c04c"])
            self.assertIn("load_local_config", code_hits, ver_s["c04c"])  # unrelated slice 01:00!
            self.assertTrue(any("口述代码反向读回不一致" in w for w in ver_s["warnings"]), ver_s["warnings"])

            # BLOCKING-8: Unlinked short paragraph AFTER cited paragraphs MUST FAIL C04b
            trailing_para = _build_note(
                "## 主线论点\n\n"
                "启动检查。 ⏱ 00:20\n\n"
                "写指标。 ⏱ 01:00\n\n"
                "关闭连接。 ⏱ 02:00\n\n"
                "这个流程会自动删除旧配置。",
                quotes,
                include_closings=False,
                omission=None,
            )
            job_t = _write_job(root, "trailing-para", trailing_para, transcript)
            ver_t = verify_note.verify(job_t / "transcript.txt", trailing_para, expected_lang="en", job=True)
            self.assertIn("C04b", failed_ids(ver_t), ver_t["reasons"])

            # NON-BLOCKING-10 & Claude NON-BLOCKING-2: 4 repeated ⏱ triggers cluster WARN; dup term triggers dup WARN
            repeated = _build_note(
                "## 主线论点\n\n"
                "启动检查。 ⏱ 00:20 ⏱ 00:20 ⏱ 00:20 ⏱ 00:20\n\n"
                "> [!note] 术语：startup\n> 启动流程。\n\n"
                "> [!note] 术语：Startup\n> 重复定义。\n\n"
                "写指标与关闭连接。 ⏱ 01:00 ⏱ 02:00",
                quotes,
                include_closings=False,
                omission=None,
            )
            job_r = _write_job(root, "repeated", repeated, transcript)
            ver_r = verify_note.verify(job_r / "transcript.txt", repeated, expected_lang="en", job=True)
            self.assertTrue(any("单簇包含 4 个 ⏱" in w for w in ver_r["warnings"]), ver_r["warnings"])
            self.assertTrue(any("术语重复 WARN" in w for w in ver_r["warnings"]), ver_r["warnings"])

            # NON-BLOCKING-9: Symmetric ±1.5s tolerance on point cue at 240.5
            from types import SimpleNamespace
            slots = [(0.0, 240.0), (240.0, 480.0)]
            cue_left = SimpleNamespace(start=239.5, end=None, text="left boundary cue")
            cue_right = SimpleNamespace(start=240.5, end=None, text="right boundary cue")
            q_left = SimpleNamespace(
                stamp=239, text=cue_left.text, raw="", screen=False,
                match=SimpleNamespace(offset=0, cues=(cue_left,)), anchor=cue_left, timed=True,
            )
            q_right = SimpleNamespace(
                stamp=240, text=cue_right.text, raw="", screen=False,
                match=SimpleNamespace(offset=0, cues=(cue_right,)), anchor=cue_right, timed=True,
            )
            self.assertEqual(cov._quote_covered_slots(q_left, slots), set(slots))
            self.assertEqual(cov._quote_covered_slots(q_right, slots), set(slots))


if __name__ == "__main__":
    unittest.main()
