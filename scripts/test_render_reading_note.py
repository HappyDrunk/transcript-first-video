#!/usr/bin/env python3
"""Exercise the reading-note CLI with synthetic evidence and the real gates."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER = """\
---
title: 整理种子盒
source: https://example.invalid/videos/seed-box
channel: 合成园艺课堂
published: 2026-04-08
type: 访谈
caption_kind: auto
skill_version: fixture
transcript_path: transcript.txt
tags: [video-note]
---
"""
QUOTES = (
    ("00:20", "Write the planting month on the outside of each seed pouches envelope before putting it away."),
    ("16:10", "Open the storage drawer at 08:30 and move the damp envelopes to a dry shelf before sorting."),
    ("34:25", "Put the envelopes with faded labels on a separate tray so nobody has to guess what they contain."),
    ("01:00:07", "Leave enough room between the dividers to pull out a packet without disturbing the row behind it."),
)
TRANSCRIPT = (
    "[00:00] Thank you for helping me find the entrance to the building this morning.\n"
    + "".join(f"[{stamp}] {speech}\n" for stamp, speech in QUOTES)
    + "[01:00:25] The coffee table outside the meeting room is open to everyone after the recording.\n"
)
SELECTION = """\
00:00–00:20 | 开场问候 | 略 | 和种子保存无关
00:20–16:10 | 标注月份 | 留 | 可以按种植时间找出信封
16:10–34:25 | 处理潮气 | 留 | 先把潮信封移开再分拣
34:25–01:00:07 | 隔离褪色标签 | 留 | 分开放就不用猜信封内容
01:00:07–01:00:25 | 留出间距 | 留 | 取走一包不会碰倒后排
01:00:25–01:01:00 | 会后提醒 | 略 | 茶水位置与保存方法无关
"""
NOTE = FRONTMATTER + """
## 先记住一句话

收好种子前，先写清月份，把发潮的信封另放。

## 这场在谈什么、谁

合成园艺课堂在 2026-04-08 聊怎样收种子，适合家里已经有种子盒的人。

## 话题

### 先做标记 ⏱ 00:20

讲者会在信封外面  写下播种月份，免得打开信封才知道要找什么。
收起来以前先看标签。 ⏱ 00:25

> [!note] 术语：种子袋（seed pouch／seed envelope）
> 用来收纳种子的纸袋。
> 外面可以写播种月份。 （Claude 补充，非视频内容） ⏱ 01:00:07

> [!warning] 字幕更正
> 字幕写作 `seed pouches`，实为 `seed pouch`。
> 合成字幕的单复数需更正。

3. 08:30 打开抽屉。  ⏱ 16:15
7. 把潮信封移到**干燥搁板**，再分拣。 ⏱ 16:10

### 分开放

- 把褪色标签的信封放在单独的托盘里。 ⏱ 34:25

### 取用时留点余量

隔板之间留点空间，抽走种子袋时才不会碰到后排。 ⏱ 01:00:07

### 一个取用比方

> [!tip] 类比（Claude 补充）
> 像从书架取书，隔壁的书有空隙才好取。
> 不成立的地方：纸袋软，不能靠隔壁的袋子撑住。 （Claude 补充，非视频内容）

## 意见不一致的地方

不适用(文稿中未出现意见分歧)。

## 可复用做法

本节没有补充中间部分之外的情况

把潮信封移到干燥处，等其他信封都分好再处理。 ⏱ 16:10

## 翻车或别用

本节没有补充中间部分之外的情况。

## 今天立刻动手一步

拿出一个信封，在外面写上播种月份。（改写讲者做法） ⏱ 00:20 ⏱ 16:10

本文略去｜开场问候（00:00–00:20）、会后提醒（01:00:25–01:01:00）

## 原文依据
""" + "".join(f"> [{stamp}] {speech}\n" for stamp, speech in QUOTES)
EXPECTED_READING = """\
# 整理种子盒
合成园艺课堂 · 2026-04-08 · [原视频](https://example.invalid/videos/seed-box)
带竖线的行是 AI 补充的名词解释或比方，不是视频里说的话。
## 先记住一句话
收好种子前，先写清月份，把发潮的信封另放。
## 这场在谈什么、谁
合成园艺课堂在 2026-04-08 聊怎样收种子，适合家里已经有种子盒的人。
## 话题
### 先做标记（00:20–16:15）
讲者会在信封外面  写下播种月份，免得打开信封才知道要找什么。
收起来以前先看标签。
> **种子袋（seed pouch／seed envelope）**：用来收纳种子的纸袋。 外面可以写播种月份。
3. 08:30 打开抽屉。
7. 把潮信封移到**干燥搁板**，再分拣。
### 分开放（34:25–34:25）
- 把褪色标签的信封放在单独的托盘里。
### 取用时留点余量（01:00:07–01:00:07）
隔板之间留点空间，抽走种子袋时才不会碰到后排。
### 一个取用比方
> **打个比方**：像从书架取书，隔壁的书有空隙才好取。 不成立的地方：纸袋软，不能靠隔壁的袋子撑住。
## 可复用做法
本节没有补充中间部分之外的情况
把潮信封移到干燥处，等其他信封都分好再处理。
## 今天立刻动手一步
拿出一个信封，在外面写上播种月份。（改写讲者做法）
---
没写进来的部分：开场问候（00:00–00:20）、会后提醒（01:00:25–01:01:00）
每句话对应的视频原话和时间点，保存在这条视频的证据版里。
"""


def write_job(job: Path) -> None:
    job.mkdir()
    (job / "note.md").write_bytes(NOTE.encode("utf-8"))
    (job / "transcript.txt").write_bytes(TRANSCRIPT.encode("utf-8"))
    (job / "selection.md").write_bytes(SELECTION.encode("utf-8"))
    (job / "status.json").write_text(
        json.dumps({"status": "transcript_ready", "expected_lang": "en", "duration_seconds": 3660}),
        encoding="utf-8",
    )


class ReadingNoteTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.job = root / "synthetic task"
        self.output = root / "reading copy.md"
        write_job(self.job)

    def _status(self) -> dict:
        return json.loads((self.job / "status.json").read_text(encoding="utf-8"))

    def _run(self, output: Path, *options: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-X", "utf8", "scripts/render_reading_note.py",
             "--task-dir", str(self.job), "--output", str(output), *options],
            cwd=ROOT, capture_output=True, encoding="utf-8", timeout=30,
        )

    def _render_passes(self, *options: str) -> bytes:
        result = self._run(self.output, *options)
        self.assertEqual(result.returncode, 0, result)
        status = self._status()
        self.assertIs(status["finished"], True, status)
        self.assertIs(status["verifier"]["allowed"], True, status)
        self.assertIs(status["coverage"]["allowed"], True, status)
        inputs = status["verifier"]["inputs"]
        self.assertEqual(inputs, status["coverage"]["inputs"])
        for key, name, original in (
            ("note_file", "note.md", NOTE),
            ("transcript", "transcript.txt", TRANSCRIPT),
            ("selection", "selection.md", SELECTION),
        ):
            evidence = (self.job / name).read_bytes()
            self.assertEqual(evidence, original.encode("utf-8"), name)
            self.assertEqual(inputs[key], hashlib.sha256(evidence).hexdigest(), name)
        self.assertTrue(self.output.is_file(), result)
        return self.output.read_bytes()

    def _render_refuses(self, output: Path, gate: str, rule: str) -> dict:
        result = self._run(output)
        self.assertNotEqual(result.returncode, 0, result)
        self.assertTrue(result.stdout.strip() or result.stderr.strip(), result)
        status = self._status()
        self.assertIs(status["finished"], False, status)
        self.assertIs(status[gate]["allowed"], False, status)
        self.assertTrue(any(reason.startswith(f"{rule} FAIL:") for reason in status[gate]["reasons"]), status)
        return status

    def test_default_render_preserves_prose_and_converts_delivery_format(self) -> None:
        reading = self._render_passes().decode("utf-8")
        for marker in ("⏱", "[!", "原文依据"):
            self.assertNotIn(marker, reading)
        expected_lines = EXPECTED_READING.splitlines()
        self.assertEqual(
            [line for line in reading.splitlines() if line.strip()],
            expected_lines,
        )
        paragraphs = re.split(r"\n(?:[ \t]*\n)+", reading.replace("\r\n", "\n").rstrip("\n"))
        for paragraph in (
            *expected_lines[1:3],
            "讲者会在信封外面  写下播种月份，免得打开信封才知道要找什么。\n收起来以前先看标签。",
            "本节没有补充中间部分之外的情况",
            expected_lines[-1],
        ):
            self.assertIn(paragraph, paragraphs)

    def test_render_is_byte_deterministic_and_can_keep_exact_frontmatter(self) -> None:
        default = self._render_passes()
        self.output.unlink()
        self.assertEqual(self._render_passes(), default)

        with_frontmatter = self._render_passes("--keep-frontmatter")
        frontmatter = FRONTMATTER.encode("utf-8")
        self.assertTrue(with_frontmatter.startswith(frontmatter))
        self.assertEqual(with_frontmatter[len(frontmatter):].lstrip(b"\r\n"), default)
        self.output.unlink()
        self.assertEqual(self._render_passes("--keep-frontmatter"), with_frontmatter)

    def test_current_verify_failure_blocks_reading_with_stale_success(self) -> None:
        previous = self._render_passes()
        bad_note = NOTE.replace("字幕写作 `seed pouches`", "字幕写作 `absent caption spelling`")
        (self.job / "note.md").write_bytes(bad_note.encode("utf-8"))

        fresh_output = self.output.with_name("verify refused.md")
        self._render_refuses(fresh_output, "verifier", "C04d")
        self.assertFalse(fresh_output.exists())

        self._render_refuses(self.output, "verifier", "C04d")
        self.assertEqual(self.output.read_bytes(), previous)

    def test_current_coverage_failure_blocks_reading_with_stale_success(self) -> None:
        previous = self._render_passes()
        bad_selection = SELECTION.replace("00:20–16:10", "00:21–16:10").encode("utf-8")
        (self.job / "selection.md").write_bytes(bad_selection)

        fresh_output = self.output.with_name("coverage refused.md")
        status = self._render_refuses(fresh_output, "coverage", "S01")
        self.assertIs(status["verifier"]["allowed"], True, status)
        self.assertEqual(status["verifier"]["inputs"]["selection"], hashlib.sha256(bad_selection).hexdigest())
        self.assertFalse(fresh_output.exists())

        self._render_refuses(self.output, "coverage", "S01")
        self.assertEqual(self.output.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
