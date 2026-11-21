"""Outside installation, self-review marking and automatic reading paths."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from test_render_reading_note import ROOT, write_job


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.job = self.root / "youtube_source"
        write_job(self.job)
        self.output = self.root / "reading"

    def run_cli(self, script, *args):
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *args],
            cwd=ROOT, env=dict(os.environ, TFV_SCREEN_MODE="off"), capture_output=True, encoding="utf-8",
            timeout=25,
        )

    def receipt(self, reviewer):
        result = self.run_cli("verify_note.py", "--job", str(self.job), "--with-coverage")
        self.assertEqual(result.returncode, 0, result.stderr)
        verified = json.loads((self.job / "status.json").read_text(encoding="utf-8"))["verifier"]
        header = {"inputs": verified["inputs"], "result": "clear", "reviewer": reviewer,
                  "c04c_sha256": verified["c04c_sha256"]}
        (self.job / "review.md").write_text(
            f"<!-- tfv-review: {json.dumps(header)} -->\n\n## C04c 告警裁定\n无\n", encoding="utf-8",
        )

    def render(self, *extra_args):
        return self.run_cli("render_reading_note.py", "--task-dir", str(self.job),
                            "--require-review", "--output-dir", str(self.output), *extra_args)

    def test_generates_filename_and_marks_self_review(self):
        self.receipt("self")
        finished = self.render()
        self.assertEqual(finished.returncode, 0, finished.stderr)
        path = self.output / "2026-04-08 合成园艺课堂 - 整理种子盒.md"
        self.assertTrue(path.is_file(), finished.stdout)
        self.assertIn("未经独立复核", path.read_text(encoding="utf-8"))
        self.assertIn(str(path), finished.stdout)

    def test_independent_review_and_missing_metadata(self):
        note = self.job / "note.md"
        text = note.read_text(encoding="utf-8")
        text = text.replace("published: 2026-04-08\n", "published:\n").replace("channel: 合成园艺课堂\n", "channel:\n")
        text = text.replace("合成园艺课堂在 2026-04-08 聊怎样收种子", "这里聊怎样收种子")
        note.write_text(text.replace("title: 整理种子盒", "title: \"整理: 种子?盒\""), encoding="utf-8")
        self.receipt("independent")
        finished = self.render()
        self.assertEqual(finished.returncode, 0, finished.stderr)
        files = list(self.output.glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertNotRegex(files[0].name, r'[<>:"/\\|?*—]')
        self.assertNotIn("未经独立复核", files[0].read_text(encoding="utf-8"))

    def assert_automatic_overwrite_refused(self, original):
        self.receipt("self")
        path = self.output / "2026-04-08 合成园艺课堂 - 整理种子盒.md"
        path.parent.mkdir(parents=True)
        path.write_bytes(original)

        result = self.render()

        self.assertEqual(path.read_bytes(), original)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("--output", result.stderr)

    def test_refuses_source_link_only_in_body(self):
        self.assert_automatic_overwrite_refused((
            "# 整理种子盒\n\n"
            "合成园艺课堂 · 2026-04-08\n\n"
            "参考资料：[原视频](https://example.invalid/videos/seed-box)\n"
        ).encode("utf-8"))

    def test_refuses_unrelated_note_with_closed_frontmatter(self):
        self.assert_automatic_overwrite_refused((
            "---\n"
            "title: 园艺备忘\n"
            "---\n\n"
            "# 园艺备忘\n\n"
            "待整理的资料\n\n"
            "参考资料：[原视频](https://example.invalid/videos/seed-box)\n"
        ).encode("utf-8"))

    def test_refuses_unclosed_frontmatter(self):
        self.assert_automatic_overwrite_refused((
            "---\n"
            "title: 整理种子盒\n\n"
            "# 整理种子盒\n\n"
            "合成园艺课堂 · 2026-04-08 · [原视频](https://example.invalid/videos/seed-box)\n"
        ).encode("utf-8"))

    def test_refuses_vertical_tab_line_boundaries(self):
        self.assert_automatic_overwrite_refused((
            "---\ntitle: memo\v---\v# Memo\v"
            "[原视频](https://example.invalid/videos/seed-box)\n"
        ).encode("utf-8"))

    def test_refuses_unicode_line_separator_boundaries(self):
        self.assert_automatic_overwrite_refused((
            "---\ntitle: memo\u2028---\u2028# Memo\u2028"
            "[原视频](https://example.invalid/videos/seed-box)\n"
        ).encode("utf-8"))

    def test_refuses_bare_cr_line_boundaries(self):
        self.assert_automatic_overwrite_refused((
            "---\rtitle: memo\r---\r# Memo\r"
            "[原视频](https://example.invalid/videos/seed-box)\r"
        ).encode("utf-8"))

    def test_refuses_non_utf8_file(self):
        self.assert_automatic_overwrite_refused(b"\xff\xfe\x80\x81")

    def test_refuses_directory_at_generated_path(self):
        self.receipt("self")
        path = self.output / "2026-04-08 合成园艺课堂 - 整理种子盒.md"
        path.mkdir(parents=True)

        result = self.render()

        self.assertTrue(path.is_dir())
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("--output", result.stderr)

    def assert_generated_note_can_be_overwritten(self, first_args, second_args):
        self.receipt("self")
        result = self.render(*first_args)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.output / "2026-04-08 合成园艺课堂 - 整理种子盒.md"
        self.assertTrue(path.is_file(), result.stdout)
        original = path.read_text(encoding="utf-8")
        if first_args:
            lines = original.splitlines()
            self.assertEqual(lines[0], "---")
            self.assertIn("---", lines[1:])
        else:
            self.assertTrue(original.startswith("# "), original)

        result = self.render(*second_args)
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = path.read_text(encoding="utf-8")
        self.assertNotEqual(updated, original)
        if second_args:
            lines = updated.splitlines()
            self.assertEqual(lines[0], "---")
            self.assertIn("---", lines[1:])
        else:
            self.assertTrue(updated.startswith("# "), updated)

    def test_overwrites_generated_note_without_frontmatter(self):
        self.assert_generated_note_can_be_overwritten((), ("--keep-frontmatter",))

    def test_overwrites_generated_note_with_closed_frontmatter(self):
        self.assert_generated_note_can_be_overwritten(("--keep-frontmatter",), ())

    def test_overwrites_crlf_note_with_closed_frontmatter(self):
        path = self.output / "2026-04-08 合成园艺课堂 - 整理种子盒.md"
        path.parent.mkdir(parents=True)
        path.write_bytes((
            "---\r\n"
            "title: 整理种子盒\r\n"
            "---\r\n\r\n"
            "# 整理种子盒\r\n\r\n"
            "合成园艺课堂 · 2026-04-08 · [原视频](https://example.invalid/videos/seed-box)\r\n\r\n"
            "旧内容\r\n"
        ).encode("utf-8"))

        self.receipt("self")
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("旧内容", path.read_text(encoding="utf-8"))

    def test_require_review_help_describes_review_marker(self):
        result = self.run_cli("render_reading_note.py", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        help_text = " ".join(result.stdout.split())
        self.assertNotIn("independent Task", help_text)
        self.assertIn("未经独立复核", help_text)

    def test_dependency_groups_keep_ocr_optional(self):
        groups = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["dependency-groups"]
        self.assertEqual(len(groups["base"]), 1)
        self.assertTrue(groups["base"][0].startswith("yt-dlp"))
        self.assertIn({"include-group": "base"}, groups["screen"])
        self.assertIn("rapidocr", groups["screen"])
        self.assertIn("onnxruntime", groups["screen"])


if __name__ == "__main__":
    unittest.main()
