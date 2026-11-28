#!/usr/bin/env python3
"""Exercise v1.2.0 installation and fast delivery without network access."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install_check
import render_reading_note
import setup as skill_setup
import youtube_host
from test_phase2e import NOTE, TRANSCRIPT

ROOT = Path(__file__).resolve().parents[1]
WARNING_NOTE = NOTE.replace("stopping two centimeters", "stopping 21.1 centimeters", 1)
FAST_NOTICE = "快读模式（已过机械核验，未做独立复核）"
FIXES = {
    "win32": "winget install --id Gyan.FFmpeg -e",
    "darwin": "brew install ffmpeg",
}
FFMPEG_FIX = FIXES.get(sys.platform, "sudo apt install -y ffmpeg")


def run_python(*args: str | Path, cwd: Path = ROOT, env: dict | None = None):
    return subprocess.run([sys.executable, "-X", "utf8", *map(str, args)], cwd=cwd, env=env,
                          capture_output=True, timeout=60)


class FastReadingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.job = self.root / "job"
        self.job.mkdir()
        self.output = self.root / "reading.md"
        self.note = self.job / "note.md"
        self.review = self.job / "review.md"
        self.status = self.job / "status.json"
        (self.job / "transcript.txt").write_text(TRANSCRIPT, encoding="utf-8")
        shutil.copyfile(ROOT / "evals/fixtures/usable_selection.md", self.job / "selection.md")
        self.status.write_text(json.dumps({
            "status": "transcript_ready", "expected_lang": "en", "duration_seconds": 120,
        }), encoding="utf-8")
        self.note.write_bytes(NOTE.encode("utf-8"))
        self.env = dict(os.environ, TFV_SCREEN_MODE="off")

    def status_data(self):
        return json.loads(self.status.read_bytes())

    def review_status_bytes(self):
        raw = self.status.read_bytes()
        review = raw.split(b'"review": ', 1)[1].decode("utf-8")
        _, end = json.JSONDecoder().raw_decode(review)
        return review[:end].encode("utf-8")

    def render(self, *args, output=None):
        return run_python(ROOT / "scripts/render_reading_note.py", "--task-dir", self.job,
                          "--output", output or self.output, *args, env=self.env)

    def write_receipt(self, decisions):
        verifier = self.status_data()["verifier"]
        header = {
            "inputs": verifier["inputs"], "result": "clear",
            "c04c_sha256": verifier["c04c_sha256"], "reviewer": "independent",
        }
        self.review.write_text(f"<!-- tfv-review: {json.dumps(header, ensure_ascii=False)} -->\n\n"
                               f"## C04c 告警裁定\n\n{decisions}\n", encoding="utf-8")

    def test_fast_ignores_stale_independent_review_and_preserves_it(self):
        verified = run_python(ROOT / "scripts/verify_note.py", "--job", self.job,
                              "--with-coverage", "--json", env=self.env)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.write_receipt("无")
        old = self.render("--require-review")
        self.assertEqual(old.returncode, 0, old.stderr)
        old_review = self.review.read_bytes()
        old_status_review = self.review_status_bytes()

        self.note.write_bytes(WARNING_NOTE.encode("utf-8"))
        rendered = self.render("--fast")
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn(b"fast: 1 C04c warnings not reviewed", rendered.stderr)
        blocks = self.output.read_text(encoding="utf-8").split("\n\n")
        self.assertEqual(blocks[2], f"说明：{FAST_NOTICE}。")
        self.assertNotIn("未经独立复核", "\n".join(blocks))
        self.assertNotIn("independent", "\n".join(blocks))
        self.assertEqual(self.review.read_bytes(), old_review)
        self.assertEqual(self.review_status_bytes(), old_status_review)
        delivered = self.status_data()
        self.assertEqual(delivered["delivery_mode"], "fast")
        self.assertEqual(delivered["next_step"], "deliver")
        self.assertIs(delivered["finished"], True)
        self.assertIs(delivered["verifier"]["allowed"], True)
        self.assertIs(delivered["coverage"]["allowed"], True)

        broken = WARNING_NOTE.replace("> [00:30] Snip the black", "> [00:30] Invent the black", 1)
        self.note.write_bytes(broken.encode("utf-8"))
        rejected = self.root / "rejected.md"
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaisesRegex(render_reading_note.RenderError, "verify or coverage failed"):
                render_reading_note.render_job(self.job, rejected, keep_frontmatter=False, fast=True)
        self.assertIn("R04 FAIL", errors.getvalue())
        self.assertFalse(rejected.exists())
        self.assertEqual(self.review.read_bytes(), old_review)
        self.assertEqual(self.review_status_bytes(), old_status_review)

    def test_fast_cannot_bypass_coverage_or_c04b(self):
        selection = self.job / "selection.md"
        prior_selection = selection.read_bytes()
        selection.unlink()
        coverage = self.render("--fast")
        self.assertEqual(coverage.returncode, 1, coverage.stderr)
        self.assertIn(b"S01 FAIL: selection.md is missing", coverage.stderr)
        self.assertFalse(self.output.exists())

        selection.write_bytes(prior_selection)
        note = NOTE.replace("## 主线论点\n\n", "## 主线论点\n\n这一节先列出 99 个注意事项。\n\n")
        self.note.write_bytes(note.encode("utf-8"))
        c04b = self.render("--fast")
        self.assertEqual(c04b.returncode, 1, c04b.stderr)
        self.assertIn(b"C04b FAIL:", c04b.stderr)
        self.assertFalse(self.output.exists())

    def test_fast_and_require_review_are_mutually_exclusive(self):
        result = self.render("--fast", "--require-review")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(b"not allowed with argument", result.stderr)
        with self.assertRaisesRegex(render_reading_note.RenderError, "mutually exclusive"):
            render_reading_note.render_job(self.job, self.output, keep_frontmatter=False,
                                           fast=True, require_review=True)
        self.assertFalse(self.output.exists())

    def test_fast_notice_precedes_other_notices(self):
        content = render_reading_note.render_note(self.note.read_bytes(), keep_frontmatter=False,
                                                  self_review=True, screen_unread=True, fast=True)
        notice = content.decode("utf-8").split("\n\n")[2]
        self.assertTrue(notice.startswith(f"说明：{FAST_NOTICE}；"), notice)
        self.assertNotIn("未经独立复核", notice)

    def test_ordinary_review_clears_fast_delivery_mode(self):
        self.note.write_bytes(WARNING_NOTE.encode("utf-8"))
        rendered = self.render("--fast")
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertEqual(self.status_data()["delivery_mode"], "fast")
        self.assertNotIn("review", self.status_data())
        self.assertFalse(self.review.exists())
        self.write_receipt("- C04c-001 | 21.1 | two centimeters below the rim | 误报")
        reviewed = self.render("--require-review")
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        status = self.status_data()
        self.assertNotIn("delivery_mode", status)
        self.assertEqual(status["review"]["reviewer"], "independent")
        self.assertEqual(status["review"]["final_inputs"], status["verifier"]["inputs"])
        self.assertNotIn(FAST_NOTICE, self.output.read_text(encoding="utf-8"))


class InstallationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        for relative in (*install_check.FALLBACK_FILES, "SKILL.md", "VERSION"):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.env = dict(os.environ, PATH=str(self.root))
        self.env.pop("PYTHONPATH", None)
        self.env.pop("PYTHONHOME", None)

    def run_script(self, script, *args):
        return run_python(self.root / "scripts" / script, *args, cwd=self.root, env=self.env)

    def test_legacy_file_check_output_is_exact_without_dependencies(self):
        result = self.run_script("install_check.py")
        version = (self.root / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout, os.linesep.join((
            f"skill_version: {version}", "Installation check passed.", "",
        )).encode("ascii"))

        (self.root / "scripts/setup.py").unlink()
        partial = self.run_script("install_check.py")
        self.assertEqual(partial.returncode, 1)
        self.assertEqual(partial.stdout, f"skill_version: {version}{os.linesep}".encode("ascii"))
        self.assertEqual(partial.stderr, os.linesep.join((
            "Missing required installation files:", "  - scripts/setup.py", "",
        )).encode("ascii"))

    def test_doctor_probes_empty_venv_and_reports_copyable_ffmpeg_fix(self):
        venv_dir = self.root / ".venv"
        created = run_python("-m", "venv", "--without-pip", venv_dir)
        self.assertEqual(created.returncode, 0, created.stderr)
        result = self.run_script("install_check.py", "--doctor", "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, b"")
        report = json.loads(result.stdout)
        self.assertIs(report["ok"], False)
        checks = {check["name"]: check for check in report["checks"]}
        for name, level in (("files", "OK"), (".venv", "OK"), ("yt-dlp", "FAIL"),
                            ("rapidocr", "WARN"), ("onnxruntime", "WARN"), ("ffmpeg", "WARN")):
            self.assertEqual(checks[name]["level"], level, name)
        self.assertIn(".".join(map(str, sys.version_info[:3])), checks["Python"]["detail"])
        self.assertEqual(checks["yt-dlp"]["fix"], "python scripts/setup.py --base-only")
        self.assertEqual(checks["ffmpeg"]["fix"], FFMPEG_FIX)
        plain = self.run_script("install_check.py", "--doctor")
        self.assertEqual(plain.returncode, 1, plain.stderr)
        self.assertIn("[OK] .venv:", plain.stdout.decode("ascii"))
        self.assertIn("[FAIL] yt-dlp:", plain.stdout.decode("ascii"))
        self.assertIn(f" | Fix: {FFMPEG_FIX}", plain.stdout.decode("ascii"))

    def test_setup_dry_run_selects_groups_without_creating_venv(self):
        custom = self.root / "path with spaces"
        cases = [
            ((), self.root / ".venv", ["base", "screen"], ["yt-dlp>=2025.1.1", "rapidocr", "onnxruntime"]),
            (("--base-only", "--venv", custom), custom, ["base"], ["yt-dlp>=2025.1.1"]),
        ]
        for args, venv_dir, groups, packages in cases:
            with self.subTest(groups=groups):
                result = self.run_script("setup.py", "--dry-run", "--json", *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertIs(report["ok"], True)
                self.assertEqual(Path(report["venv"]), venv_dir)
                self.assertEqual(report["groups"], groups)
                self.assertEqual(report["packages"], packages)
                executable = Path(report["python"])
                suffix = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
                self.assertEqual(executable, venv_dir / suffix)
                self.assertEqual(report["commands"], [
                    [sys.executable, "-m", "venv", str(venv_dir)],
                    [str(executable), "-m", "pip", "install", *packages],
                ])
                self.assertNotIn("--group", json.dumps(report["commands"]))
                self.assertIn(str(executable), report["next"])
                self.assertIn("--doctor", report["next"])
                self.assertEqual(report["ffmpeg"], {"found": False, "fix": FFMPEG_FIX})
                self.assertIn(FFMPEG_FIX.encode("ascii"), result.stderr)
                self.assertFalse(venv_dir.exists())

    def test_python310_toml_fallback_and_nested_group_expansion(self):
        config = self.root / "pyproject.toml"
        config.write_text(
            "[project]\nname = 'fixture'\n"
            "[ dependency-groups ] # only this table is parsed\n"
            "base = ['pkg>=1', \"pkg[extra]>=2; python_version < \\\"3.12\\\"\"]\n"
            "common = [{ include-group = 'base' }, 'shared']\n"
            "\"screen\" = [ # multiline array\n"
            "  { include-group = \"common\" },\n"
            "  { include-group = \"base\" }, \"shared\", \"other\", # duplicates\n]\n"
            "[[tool.fixture]]\nignored = 1\n",
            encoding="utf-8",
        )
        with patch.object(skill_setup, "tomllib", None):
            groups = skill_setup.load_dependency_groups(config)
            actual = skill_setup.load_dependency_groups(ROOT / "pyproject.toml")
        if skill_setup.tomllib is not None:
            self.assertEqual(groups, skill_setup.load_dependency_groups(config))
        self.assertEqual(skill_setup.expand_groups(groups, ["base", "screen"]),
                         ["pkg>=1", 'pkg[extra]>=2; python_version < "3.12"', "shared", "other"])
        self.assertEqual(skill_setup.expand_groups(actual, ["base", "screen"]),
                         ["yt-dlp>=2025.1.1", "rapidocr", "onnxruntime"])
        for invalid in ('base = ["one" "two"]', 'base = [{ include-group = "base" }', 'base = [1]'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                skill_setup.parse_dependency_groups_fallback(f"[dependency-groups]\n{invalid}\n")

        config.write_text("[dependency-groups]\nbase = [{include-group = 'screen'}]\n"
                          "screen = [{include-group = 'base'}]\n", encoding="utf-8")
        cycled = self.run_script("setup.py", "--dry-run", "--json")
        self.assertEqual(cycled.returncode, 2, cycled.stderr)
        self.assertIn(b"base -> screen -> base", cycled.stderr)
        self.assertIs(json.loads(cycled.stdout)["ok"], False)

    def test_writer_files_fit_budget_and_use_lf(self):
        files = ("SKILL.md", "references/delivery-format.md", "references/review-guide.md")
        contents = [(ROOT / path).read_bytes() for path in files]
        self.assertLessEqual(sum(map(len, contents)), 30_720)
        for content in contents:
            self.assertNotIn(b"\r", content)
        self.assertIn("scripts/setup.py", install_check.FALLBACK_FILES)


class NoCaptionsTests(unittest.TestCase):
    def test_whisper_hint_is_stderr_only_and_keeps_stop_reason(self):
        errors = io.StringIO()
        with (tempfile.TemporaryDirectory() as tmp,
              patch.dict(os.environ, INVIDIOUS_INSTANCE="off", ASR_BACKEND="off"),
              patch.object(youtube_host, "ytdlp_base", return_value=["yt-dlp"]),
              patch.object(youtube_host, "fetch_ytdlp_captions", return_value={"error": "no captions"}),
              contextlib.redirect_stderr(errors)):
            out = Path(tmp)
            payload = youtube_host.run_host(video_id="fakecaption", source="https://example.invalid/watch",
                                            out_dir=out, expected_lang="en", asr_choice="auto", verify=False)
            job = out / payload["job_id"]
            status = json.loads((job / "status.json").read_bytes())
            self.assertFalse((job / "note.md").exists())

        self.assertEqual(payload["exit_code"], 2)
        self.assertEqual(status["next_step"], "configure-asr-or-retry-captions")
        stop = ("The YouTube job is not finished because no usable captions were found and ASR is not configured. "
                "Retry with a working caption mirror in INVIDIOUS_INSTANCE, or set ASR_BACKEND=whisper "
                "for local transcription or ASR_BACKEND=openai with OPENAI_API_KEY. No note was written."
                " Caption attempts: yt-dlp: no captions")
        self.assertEqual(status["reason"], stop)
        self.assertEqual(payload["reason"], stop)
        self.assertEqual(errors.getvalue().splitlines()[-2], stop)
        hint = errors.getvalue().splitlines()[-1]
        for part in ("新手提示", "-m pip install openai-whisper", "export ASR_BACKEND=whisper",
                     '$env:ASR_BACKEND="whisper"', "--asr auto", "ffmpeg"):
            self.assertIn(part, hint)


if __name__ == "__main__":
    unittest.main()
