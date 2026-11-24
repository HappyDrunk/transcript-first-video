#!/usr/bin/env python3
"""RED/GREEN contract tests for Phase 6 Commit 1 renderer & verify->render invariant."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_reading_note  # noqa: E402
import verify_report  # noqa: E402
from test_render_reading_note import FRONTMATTER, NOTE, write_job  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _make_note(
    middle: str,
    *,
    omission: str | None = "本文略去｜无",
    evidence: str = "> [00:20] Write the planting month on the outside of each seed pouches envelope before putting it away.\n",
) -> str:
    parts = [
        FRONTMATTER.rstrip("\n"),
        "## 先记住一句话\n\n先做标记再存放。",
        "## 这场在谈什么、谁\n\n合成园艺课堂讲解种子收纳。",
        middle.strip("\n"),
        "## 今天立刻动手一步\n\n写下播种月份。 ⏱ 00:20",
    ]
    if omission is not None:
        parts.append(omission)
    parts.append("## 原文依据\n" + evidence)
    return "\n\n".join(parts)


class Phase6RendererContractTests(unittest.TestCase):
    def _render(self, note: str, **kwargs) -> str:
        return render_reading_note.render_note(
            note.encode("utf-8"), keep_frontmatter=False, **kwargs
        ).decode("utf-8")

    def test_discrepancy_type1_hidden_with_clean_blank_lines(self) -> None:
        note = _make_note(
            "## 话题\n\n### 规范拼写\n\n"
            "第一段提到 Docling 工具。 ⏱ 00:20\n\n"
            "> [!warning] 原文出入\n"
            "> 字幕写作 `DocLing`，实为 `Docling`。\n"
            "> 画面写作 Azure Al，实为 Azure AI。\n\n"
            "第二段继续讲解流程。 ⏱ 00:20"
        )
        reading = self._render(note)
        self.assertNotIn("原文出入", reading)
        self.assertNotIn("DocLing", reading)
        self.assertNotIn("Azure Al", reading)
        self.assertIn("第一段提到 Docling 工具。\n\n第二段继续讲解流程。", reading)
        self.assertNotIn("\n\n\n", reading)

    def test_discrepancy_type2_spoken_code_adds_single_header_notice(self) -> None:
        note = _make_note(
            "## 话题\n\n### 口述代码\n\n"
            "调用 `results.print_stats()` 查看耗时。 ⏱ 00:20\n\n"
            "> [!warning] 原文出入\n"
            "> 口述代码｜results dot print stats｜`results.print_stats()`\n\n"
            "再执行 `total += 1` 累加计数。 ⏱ 00:20\n\n"
            "> [!warning] 原文出入\n"
            "> 口述代码｜total plus equals one｜`total += 1`"
        )
        reading = self._render(note)
        self.assertIn("说明：部分代码按讲者口述整理。", reading)
        self.assertEqual(reading.count("部分代码按讲者口述整理"), 1)
        self.assertNotIn("口述代码｜", reading)
        self.assertNotIn("results dot print stats", reading)

        self_rev = self._render(note, self_review=True)
        self.assertIn("说明：未经独立复核；部分代码按讲者口述整理。", self_rev)

    def test_discrepancy_type3_inserts_before_terminal_punctuation_and_preserves_decimals(self) -> None:
        note = _make_note(
            "## 话题\n\n### 版本冲突\n\n"
            "配置里显示模型版本为 qwen3.5，口述提到 3.6。 ⏱ 00:20\n\n"
            "> [!warning] 原文出入\n"
            "> 存疑｜「qwen3.5」｜画面配置与口述版本号不一致\n\n"
            "- 使用 v3.5 部署 ⏱ 00:20\n\n"
            "> [!warning] 原文出入\n"
            "> 存疑｜「v3.5」｜未确认具体小版本\n\n"
            "讲者提到 Michael Tru 和另一位作者 Alex。 ⏱ 00:20\n\n"
            "> [!warning] 原文出入\n"
            "> 存疑｜「Michael Tru」｜字幕仅给出名字未见姓氏\n"
            "> 存疑｜「Alex」｜未提及全名"
        )
        reading = self._render(note)
        self.assertIn("配置里显示模型版本为 qwen3.5，口述提到 3.6（存疑：画面配置与口述版本号不一致）。", reading)
        self.assertIn("- 使用 v3.5 部署（存疑：未确认具体小版本）", reading)
        self.assertIn(
            "讲者提到 Michael Tru 和另一位作者 Alex（存疑：字幕仅给出名字未见姓氏）（存疑：未提及全名）。",
            reading,
        )
        self.assertNotIn("原文出入", reading)

    def test_discrepancy_mixed_three_row_types_in_one_block(self) -> None:
        note = _make_note(
            "## 话题\n\n### 混合块\n\n"
            "运行 `run_eval()` 并核对模型 3.6 的分数。 ⏱ 00:20\n\n"
            "> [!warning] 原文出入\n"
            "> 字幕写作 run eval，实为 run_eval\n"
            "> 口述代码｜run eval｜`run_eval()`\n"
            "> 存疑｜「模型 3.6」｜画面写作 3.5"
        )
        reading = self._render(note)
        self.assertIn("说明：部分代码按讲者口述整理。", reading)
        self.assertIn("运行 `run_eval()` 并核对模型 3.6 的分数（存疑：画面写作 3.5）。", reading)

    def test_extreme_invalid_discrepancy_anchors_and_syntax_raise_render_error(self) -> None:
        cases = (
            ("missing_anchor", "普通句子。 ⏱ 00:20\n\n> [!warning] 原文出入\n> 存疑｜「不存在」｜说明"),
            ("duplicate_anchor", "重复词和重复词都在这里。 ⏱ 00:20\n\n> [!warning] 原文出入\n> 存疑｜「重复词」｜说明"),
            ("crosses_time_marker", "前半 ⏱ 00:20 后半。 ⏱ 00:20\n\n> [!warning] 原文出入\n> 存疑｜「前半 后半」｜说明"),
            ("inside_inline_code", "调用 `qwen3_5` 接口。 ⏱ 00:20\n\n> [!warning] 原文出入\n> 存疑｜「qwen3_5」｜说明"),
            (
                "inside_fenced_code",
                "```python\nval = qwen3_5\n```\n\n> [!warning] 原文出入\n> 存疑｜「qwen3_5」｜说明",
            ),
            (
                "inside_markdown_link",
                "详见 [模型文档](https://example.invalid) 说明。 ⏱ 00:20\n\n"
                "> [!warning] 原文出入\n> 存疑｜「模型文档」｜说明",
            ),
            (
                "inside_markdown_table",
                "| 模型 | 分数 |\n| --- | --- |\n| qwen3.5 | 90 |\n\n"
                "> [!warning] 原文出入\n> 存疑｜「qwen3.5」｜说明",
            ),
            ("no_preceding_block", "> [!warning] 原文出入\n> 存疑｜「章节标题」｜说明"),
            ("empty_block", "正常句子。 ⏱ 00:20\n\n> [!warning] 原文出入"),
            ("unknown_row", "正常句子。 ⏱ 00:20\n\n> [!warning] 原文出入\n> 随便写的一行说明"),
            ("closing_paren_in_explanation", "正常句子。 ⏱ 00:20\n\n> [!warning] 原文出入\n> 存疑｜「正常」｜含有）右括号"),
            ("empty_explanation", "正常句子。 ⏱ 00:20\n\n> [!warning] 原文出入\n> 存疑｜「正常」｜"),
        )
        for name, block in cases:
            with self.subTest(case=name):
                note = _make_note(f"## 话题\n\n### 章节标题\n\n{block}")
                with self.assertRaises(render_reading_note.RenderError):
                    self._render(note)

    def test_invariant7_detects_corruption_and_tolerates_literal_speaker_text(self) -> None:
        literal_note = _make_note(
            "## 话题\n\n### 字面存疑\n\n"
            "讲者说这句（存疑：原话如此）保留下来，并提到版本 3.6。 ⏱ 00:20\n\n"
            "> [!warning] 原文出入\n"
            "> 存疑｜「版本 3.6」｜画面写作 3.5"
        )
        reading = self._render(literal_note)
        self.assertIn("讲者说这句（存疑：原话如此）保留下来，并提到版本 3.6（存疑：画面写作 3.5）。", reading)

        # Simulate a corrupted Type-3 insertion that alters prose outside `（存疑：…）`
        original_insert = render_reading_note._insert_doubt_note

        def corrupt_insert(block: str, anchor: str, explanation: str) -> str:
            return original_insert(block, anchor, explanation).replace("版本 3.6", "版本 3.9", 1)

        with patch.object(render_reading_note, "_insert_doubt_note", side_effect=corrupt_insert):
            with self.assertRaises(render_reading_note.RenderError) as ctx:
                self._render(literal_note)
            self.assertIn("invariant #7", str(ctx.exception).lower())

    def test_mode_y_glossary_dedup_and_hidden_x_mode(self) -> None:
        note = _make_note(
            "## 话题\n\n### 术语测试\n\n"
            "先讲 RAG 检索。 ⏱ 00:20\n\n"
            "> [!note] 术语：RAG\n"
            "> 检索增强生成。（Claude 补充，非视频内容）\n\n"
            "再讲 KV Cache 缓存。 ⏱ 00:20\n\n"
            "> [!note] 术语：KV Cache\n"
            "> 键值缓存。\n\n"
            "再次提到 rag 重复定义。 ⏱ 00:20\n\n"
            "> [!note] 术语：rag\n"
            "> 重复条不应覆盖首次。\n\n"
            "> [!tip] 类比（Claude 补充）\n"
            "> 像查字典。\n"
            "> 不成立的地方：缓存会失效。",
            omission="本文略去｜开场（00:00–00:20）",
        )
        y_out = self._render(note)
        self.assertNotIn("> **RAG", y_out)
        self.assertNotIn("<details", y_out)
        self.assertIn("> **打个比方（注）**：像查字典。 不成立的地方：缓存会失效。", y_out)
        self.assertIn("## 术语速查\n\n以下为整理者补充，非讲者原话。", y_out)
        self.assertIn("- **RAG**：检索增强生成。", y_out)
        self.assertIn("- **KV Cache**：键值缓存。", y_out)
        self.assertNotIn("重复条不应覆盖首次", y_out)
        self.assertLess(y_out.index("- **RAG**"), y_out.index("- **KV Cache**"))
        self.assertLess(y_out.index("## 术语速查"), y_out.index("没写进来的部分：开场（00:00–00:20）"))

        x_out = self._render(note, inline_terms=True)
        self.assertNotIn("## 术语速查", x_out)
        self.assertIn("> **RAG（注）**：检索增强生成。", x_out)
        self.assertIn("> **KV Cache（注）**：键值缓存。", x_out)
        self.assertIn("> **打个比方（注）**：像查字典。 不成立的地方：缓存会失效。", x_out)

    def test_header_footer_h3_cleanup_and_misplaced_omission_guard(self) -> None:
        base_note = _make_note("## 话题\n\n### 轻格式章节\n\n正文内容。 ⏱ 00:20", omission="本文略去｜无")
        reading = self._render(base_note, reading_level="plain", delivery_language="中文")
        for removed in (
            "说明：",
            "竖线行是 AI 补充解释",
            "标明来自画面的内容由机器识别",
            "讲解方式：",
            "Reading level:",
            "每句话对应的视频原话和时间点",
            "没写进来的部分：",
            "## 术语速查",
        ):
            self.assertNotIn(removed, reading)
        self.assertIn("### 轻格式章节 · 00:20", reading)

        for empty_omission in (None, "本文略去｜无", "本文略去｜无。", "本文略去｜   "):
            with self.subTest(omission=empty_omission):
                out = self._render(_make_note("## 话题\n\n### 节\n\n内容。 ⏱ 00:20", omission=empty_omission))
                self.assertNotIn("没写进来的部分：", out)
                self.assertNotIn("\n---\n", out)

        misplaced = _make_note(
            "## 话题\n\n### 节\n\n本文略去｜错误位置（00:00–00:10）\n\n后续正文。 ⏱ 00:20",
            omission=None,
        )
        with self.assertRaises(render_reading_note.RenderError):
            self._render(misplaced)

        with self.assertRaises(render_reading_note.RenderError):
            self._render(base_note, reading_level="invalid")

    def test_cli_hidden_inline_terms_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            output = root / "reading-x.md"
            write_job(job)
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", "scripts/render_reading_note.py",
                 "--task-dir", str(job), "--output", str(output), "--inline-terms"],
                cwd=ROOT, capture_output=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            text = output.read_text(encoding="utf-8")
            self.assertIn("> **种子袋（seed pouch／seed envelope）（注）**：", text)
            self.assertNotIn("## 术语速查", text)

            help_proc = subprocess.run(
                [sys.executable, "-X", "utf8", "scripts/render_reading_note.py", "--help"],
                cwd=ROOT, capture_output=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(help_proc.returncode, 0)
            self.assertNotIn("--inline-terms", help_proc.stdout)

    def test_ci_contract_every_verified_good_note_renders_cleanly(self) -> None:
        good_paths = verify_report.samples(verify_report.GOOD)
        self.assertGreaterEqual(len(good_paths), 15)
        rendered_count = 0
        for path in good_paths:
            text = path.read_text(encoding="utf-8")
            verified, _ = verify_report.check_sample(text)
            if not verified["allowed"]:
                continue
            rendered_count += 1
            for inline_terms in (False, True):
                with self.subTest(sample=path.name, inline_terms=inline_terms):
                    first = render_reading_note.render_note(
                        text.encode("utf-8"), keep_frontmatter=False, inline_terms=inline_terms
                    )
                    second = render_reading_note.render_note(
                        text.encode("utf-8"), keep_frontmatter=False, inline_terms=inline_terms
                    )
                    self.assertEqual(first, second)
                    decoded = first.decode("utf-8")
                    self.assertNotIn("⏱", decoded)
                    self.assertNotIn("[!", decoded)
        self.assertGreaterEqual(rendered_count, 15)

        fixture_notes = sorted((ROOT / "evals/fixtures/delivery-examples").glob("*/note.md"))
        self.assertGreaterEqual(len(fixture_notes), 4)
        for path in fixture_notes:
            raw = path.read_bytes()
            for inline_terms in (False, True):
                with self.subTest(fixture=path.parent.name, inline_terms=inline_terms):
                    decoded = render_reading_note.render_note(
                        raw, keep_frontmatter=False, inline_terms=inline_terms
                    ).decode("utf-8")
                    self.assertNotIn("⏱", decoded)
                    self.assertNotIn("[!", decoded)

    def test_review_round1_render_and_verify_alignment_regressions(self) -> None:
        import coverage_check as cov
        import hashlib
        import json
        import verify_note

        # 1. Consecutive list items sharing anchor word (BLOCKING-1)
        # 2. Multiple doubts where row 1 explanation mentions row 2 anchor (BLOCKING-2)
        # 3. Anchor followed by URL containing `?` (BLOCKING-3)
        # 4. Literal speaker text containing `（存疑：旧说法。仍待确认）` (BLOCKING-4)
        quotes = (
            ("00:20", "We keep the index on disk, update the index later, and read configuration from the guide."),
            ("01:00", "Team A chose plan B during the review while keeping the fallback setting intact."),
            ("02:00", "This step runs normally even when an earlier note remains open for confirmation."),
        )
        screen_line = "[00:25][画面] config_mode=full"
        transcript = "\n".join(f"[{s}] {t}" for s, t in quotes) + "\n"
        selection = (
            "00:00–00:50 | 索引与配置 | 留 | 索引步骤与画面配置\n"
            "00:50–01:40 | 方案对比 | 留 | 甲乙方案\n"
            "01:40–02:30 | 常规执行 | 留 | 执行说明\n"
            "00:25 | [画面] config_mode=full | 留 | 画面配置键值\n"
        )
        note = (
            FRONTMATTER.replace("type: 访谈", "type: 讲座")
            + "\n## 先记住一句话\n\n先检查索引与配置再执行。\n\n"
            + "## 这场在谈什么、谁\n\n合成园艺课堂说明索引和配置流程。\n\n"
            + "## 主线论点\n\n"
            + "- 保留索引。 ⏱ 00:20\n"
            + "- 更新索引，参考 [说明](https://example.test/?mode=full) 与 `config_mode`。 ⏱ 00:20 ⏱ 00:25\n\n"
            + "> [!warning] 原文出入\n"
            + "> 存疑｜「索引」｜第二项索引位置待核实\n\n"
            + "甲采用乙方案。 ⏱ 01:00\n\n"
            + "> [!warning] 原文出入\n"
            + "> 存疑｜「甲」｜乙仍待确认\n"
            + "> 存疑｜「乙」｜出处不清\n\n"
            + "这一步（存疑：旧说法。仍待确认）照常执行。 ⏱ 02:00\n\n"
            + "> [!warning] 原文出入\n"
            + "> 存疑｜「这一步」｜新说明\n\n"
            + "## 原文依据\n"
            + "".join(f"> [{s}] {t}\n" for s, t in quotes)
            + f"> {screen_line}\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "screen-job"
            job.mkdir()
            (job / "transcript.txt").write_text(transcript, encoding="utf-8")
            (job / "selection.md").write_text(selection, encoding="utf-8")
            (job / "screen.txt").write_bytes((screen_line + "\n").encode("utf-8"))
            (job / "note.md").write_text(note, encoding="utf-8")
            (job / "status.json").write_text(
                json.dumps({
                    "status": "transcript_ready",
                    "expected_lang": "en",
                    "duration_seconds": 150,
                    "screen_ocr": {
                        "state": "ready",
                        "mode": "slides",
                        "sha256": hashlib.sha256((screen_line + "\n").encode("utf-8")).hexdigest(),
                    },
                }),
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"TFV_SCREEN_MODE": "slides"}):
                ver = verify_note.verify(job / "transcript.txt", note, expected_lang="en", job=True)
                self.assertTrue(ver["allowed"], ver["reasons"])
                covered = cov.check_job(job)
                self.assertTrue(covered["ok"], covered["reasons"])
            for inline_terms in (False, True):
                reading = render_reading_note.render_note(
                    note.encode("utf-8"), keep_frontmatter=False, inline_terms=inline_terms
                ).decode("utf-8")
                self.assertIn("- 更新索引，参考 [说明](https://example.test/?mode=full) 与 `config_mode`（存疑：第二项索引位置待核实）。", reading)
                self.assertIn("甲采用乙方案（存疑：乙仍待确认）（存疑：出处不清）。", reading)
                self.assertIn("这一步（存疑：旧说法。仍待确认）照常执行（存疑：新说明）。", reading)
                self.assertNotIn("⏱", reading)
                self.assertNotIn("[!", reading)


if __name__ == "__main__":
    unittest.main()
