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

    def render(self):
        return self.run_cli("render_reading_note.py", "--task-dir", str(self.job),
                            "--require-review", "--output-dir", str(self.output))

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
        text = text.replace("published: 2026-04-08\n", "").replace("channel: 合成园艺课堂\n", "")
        text = text.replace("合成园艺课堂在 2026-04-08 聊怎样收种子", "这里聊怎样收种子")
        note.write_text(text.replace("title: 整理种子盒", "title: \"整理: 种子?盒\""), encoding="utf-8")
        self.receipt("independent")
        finished = self.render()
        self.assertEqual(finished.returncode, 0, finished.stderr)
        files = list(self.output.glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertNotRegex(files[0].name, r'[<>:"/\\|?*—]')
        self.assertNotIn("未经独立复核", files[0].read_text(encoding="utf-8"))

    def test_dependency_groups_keep_ocr_optional(self):
        groups = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["dependency-groups"]
        self.assertEqual(len(groups["base"]), 1)
        self.assertTrue(groups["base"][0].startswith("yt-dlp"))
        self.assertIn({"include-group": "base"}, groups["screen"])
        self.assertTrue({"rapidocr", "onnxruntime"}.issubset(groups["screen"]))


if __name__ == "__main__":
    unittest.main()
