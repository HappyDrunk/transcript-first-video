#!/usr/bin/env python3
"""Exercise the reading notice for screen OCR fallback and its doc contract."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from render_reading_note import render_job, render_note
from test_phase6_render_contract import _make_note
from test_render_reading_note import ROOT, write_job


FALLBACK_NOTICE = "画面文字未能识别，本文仅据语音整理，未写到的画面内容不代表视频没有"
NOTE = _make_note("## 话题\n\n先检查标签。 ⏱ 00:20").encode("utf-8")
BASELINE = """\
# 整理种子盒

合成园艺课堂 · 2026-04-08 · [原视频](https://example.invalid/videos/seed-box)

## 先记住一句话

先做标记再存放。

## 这场在谈什么、谁

合成园艺课堂讲解种子收纳。

## 话题

先检查标签。

## 今天立刻动手一步

写下播种月份。
""".encode("utf-8")


class ScreenFallbackTests(unittest.TestCase):
    def test_screen_unread_notice_is_last_in_header(self):
        for self_review, expected in (
            (False, f"说明：{FALLBACK_NOTICE}。"),
            (True, f"说明：未经独立复核；{FALLBACK_NOTICE}。"),
        ):
            with self.subTest(self_review=self_review):
                rendered = render_note(
                    NOTE, keep_frontmatter=False, self_review=self_review, screen_unread=True,
                ).decode("utf-8")
                notices = [line for line in rendered.splitlines() if line.startswith("说明：")]
                self.assertEqual(notices, [expected])

    def test_default_render_matches_pre_fallback_bytes(self):
        self.assertEqual(render_note(NOTE, keep_frontmatter=False), BASELINE)
        self.assertEqual(render_note(NOTE, keep_frontmatter=False, screen_unread=False), BASELINE)

    def test_render_job_shows_notice_only_when_screen_reading_failed(self):
        cases = (
            ("fallback", "error", True),
            ("fallback", "timeout", True),
            ("fallback", "missing_dependencies", True),
            ("fallback", "not_found", False),
            ("disabled", "disabled", False),
            ("ready", "slides_detected", False),
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for state, result, expected in cases:
                with self.subTest(state=state, result=result):
                    job = root / result
                    write_job(job)
                    status_path = job / "status.json"
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    status["screen_ocr"] = {"requested_mode": "auto", "state": state, "result": result}
                    status_path.write_text(json.dumps(status), encoding="utf-8")

                    output = render_job(job, root / f"{result}.md", keep_frontmatter=False)
                    reading = output.read_text(encoding="utf-8")
                    if expected:
                        self.assertIn(f"\n说明：{FALLBACK_NOTICE}。\n", reading)
                    else:
                        self.assertNotIn(FALLBACK_NOTICE, reading)

    def test_screen_fallback_guidance_in_lf_docs(self):
        for filename, phrases in (
            ("delivery-format.md", (
                "专名、检索术语和口述代码标识符保留原拼写",
                "严禁自行补全；画面识别失败时改写“口述未给出”",
            )),
            ("review-guide.md", ("等读者向边界说明；画面识别失败时勿断言画面没有",)),
        ):
            with self.subTest(filename=filename):
                raw = (ROOT / "references" / filename).read_bytes()
                self.assertNotIn(b"\r", raw)
                document = raw.decode("utf-8")
                for phrase in phrases:
                    self.assertIn(phrase, document)


if __name__ == "__main__":
    unittest.main()
