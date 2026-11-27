#!/usr/bin/env python3
"""Exercise the screen OCR fallback notice, absence guard, and doc contract."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import verify_note
from render_reading_note import render_job, render_note
from test_phase6_render_contract import _make_note
from test_render_reading_note import ROOT, write_job
from verify_rules import SCREEN_FALLBACK_NOTICE as FALLBACK_NOTICE


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
            ("review-guide.md", ("等读者向边界说明",)),
        ):
            with self.subTest(filename=filename):
                raw = (ROOT / "references" / filename).read_bytes()
                self.assertNotIn(b"\r", raw)
                document = raw.decode("utf-8")
                for phrase in phrases:
                    self.assertIn(phrase, document)
                if filename == "review-guide.md":
                    self.assertNotIn("画面识别失败时勿断言画面没有", document)


class ScreenAbsenceGuardTests(unittest.TestCase):
    R1 = "这次没有可用的画面识别结果，下面只根据口述整理，视频未给出可完整复制的源码。"
    R2 = "视频未给出完整可运行代码，正文只保留讲者口述到的结构和名称。"
    GUARD = "画面识别失败时勿断言"

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        job = Path(folder.name) / "job"
        write_job(job)
        self.transcript = job / "transcript.txt"
        self.status_path = job / "status.json"
        self.original_status = self.status_path.read_text(encoding="utf-8")
        self.fallback_status = json.dumps({
            **json.loads(self.original_status),
            "screen_ocr": {"requested_mode": "auto", "state": "fallback"},
        })
        self.status_path.write_text(self.fallback_status, encoding="utf-8")

    def _note(self, content: str, **kwargs) -> str:
        return _make_note(f"## 话题\n\n先检查标签。 ⏱ 00:20\n\n{content}", **kwargs).replace(
            "transcript_path: transcript.txt", f"transcript_path: {self.transcript.as_posix()}",
        )

    def test_fallback_without_result_rejects_screen_absence_claims(self):
        for claim, hit in (
            (self.R1, "视频未给出"),
            (self.R2, "视频未给出"),
            ("说明：视频未给出完整可运行代码", "视频未给出"),
            (f"说明：{FALLBACK_NOTICE}；视频未给出代码", "视频未给出"),
            ("这并非重点：视频未给出代码", "视频未给出"),
            ("无法确认版本但视频没有提供代码", "视频没有提供"),
            (f"> [!warning]\n> {self.R2}", "视频未给出"),
            ("视频未给出 `main.py` 源码", "视频未给出"),
            ("画面上没有代码", "画面上没有代码"),
            ("画面没有完整代码", "画面没有完整"),
            ("屏幕中无任何命令", "屏幕中无任何"),
            ("视频中并未展示", "视频中并未展示"),
            ("视频画面中未出现", "画面中未出现"),
            ("演示中未出现源码", "演示中未出现"),
            ("**视频**没有提供代码", "视频没有提供"),
        ):
            with self.subTest(claim=claim):
                result = verify_note.verify(self.transcript, self._note(claim), job=True)
                c04b = "\n".join(reason for reason in result["reasons"] if reason.startswith("C04b FAIL:"))
                self.assertIn(f"话题: {self.GUARD}视频/画面没有某内容（「{hit}」）；改写为“口述未给出…”", c04b)

    def test_fallback_allows_quotes_code_and_transcript_boundaries(self):
        for claim in (
            f"```text\n{self.R2}\n```",
            f"> ```text\n> {self.R2}\n> ```",
            f"> [!warning]\n> ```text\n> {self.R2}\n> ```",
            f"讲者说：“{self.R2}”",
            f"说明：正文中「（注：…）」为整理者补充的极短术语解释，非视频原话；{FALLBACK_NOTICE}。",
            "视频说明了没有提供代码",
            "讲者提到没有公开源码",
            FALLBACK_NOTICE,
            f"{FALLBACK_NOTICE}代码。",
            "口述未给出",
            "视频未展开",
            "视频没有提到",
            "画面无法识别",
            "画面没能识别",
            "画面没有完整识别，本节只按口述整理。",
            "这次没有可用的画面识别结果",
            "只凭口述无法判定视频没有提供代码",
            "不代表这段视频没有给出源码",
            "接下来演示没有代码基础也能完成的流程",
            "演示未完整展开",
        ):
            with self.subTest(claim=claim):
                result = verify_note.verify(self.transcript, self._note(claim), job=True)
                self.assertNotIn(self.GUARD, "\n".join(result["reasons"]))

    def test_fallback_allows_end_evidence(self):
        note = self._note("", evidence=f"> [00:20] {self.R2}\n")
        result = verify_note.verify(self.transcript, note, job=True)
        self.assertNotIn(self.GUARD, "\n".join(result["reasons"]))

    def test_guard_is_off_without_a_failed_screen_reading_job(self):
        not_found = json.loads(self.fallback_status)
        not_found["screen_ocr"]["result"] = "not_found"
        for case, status in (
            ("not_found", json.dumps(not_found)),
            ("ok", json.dumps({**not_found, "screen_ocr": {"state": "ok"}})),
            ("no screen_ocr", self.original_status),
            ("invalid JSON", "{"),
        ):
            self.status_path.write_text(status, encoding="utf-8")
            for claim in (self.R1, self.R2):
                with self.subTest(case=case, claim=claim):
                    result = verify_note.verify(self.transcript, self._note(claim), job=True)
                    self.assertNotIn(self.GUARD, "\n".join(result["reasons"]))

        self.status_path.write_text(self.fallback_status, encoding="utf-8")
        transcript = self.transcript.read_text(encoding="utf-8")
        for claim in (self.R1, self.R2):
            with self.subTest(case="verify_text", claim=claim):
                result = verify_note.verify_text(self._note(claim), transcript)
                self.assertNotIn(self.GUARD, "\n".join(result["reasons"]))


if __name__ == "__main__":
    unittest.main()
