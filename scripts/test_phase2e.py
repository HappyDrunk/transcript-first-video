#!/usr/bin/env python3
"""Freeze Phase 2E at the existing note, coverage, renderer and YouTube entry points."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import coverage_check
import render_reading_note
import verify_note
import verify_report
import youtube_host

from test_phase2e_media_fixture import MediaTools, OCR_VERSIONS


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"
MODE = "TFV_SCREEN_MODE"
VIDEO_ID = "gardenfilm1"
TRANSCRIPT = (FIXTURES / "usable_en_timed_transcript.txt").read_text(encoding="utf-8")
NOTE = (FIXTURES / "usable_en_note.md").read_text(encoding="utf-8").replace(
    "evals/fixtures/usable_en_timed_transcript.txt", "transcript.txt"
)
RULE_IDS = ["R01", "R04", "R05", "R13", "R14", "R15", "C04a", "C04b", "C04c", "C04d"]
HINT = "标明来自画面的内容由机器识别，可能有个别字符误差"


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def read_status(job: Path) -> dict:
    return json.loads((job / "status.json").read_text(encoding="utf-8"))


def entry(main, argv: list[str], mode: str | None) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.dict(os.environ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        if mode is None:
            os.environ.pop(MODE, None)
        else:
            os.environ[MODE] = mode
        try:
            code = main(argv)
        except SystemExit as exc:
            code = exc.code
    out, err = stdout.getvalue(), stderr.getvalue()
    print(json.dumps({"entry": main.__module__, "argv": argv, MODE: mode, "exit": code},
                     ensure_ascii=False))
    print("stdout:")
    sys.stdout.write(out)
    if out and not out.endswith("\n"):
        print()
    print("stderr:")
    sys.stdout.write(err)
    if err and not err.endswith("\n"):
        print()
    return code, out, err


def fingerprint(value: tuple[int, str, str], job: Path) -> str:
    code, stdout, stderr = value
    # A random directory is the only input that differs across checkouts.
    stdout = stdout.replace(job.as_posix(), "<job>")
    stderr = stderr.replace(job.as_posix(), "<job>")
    encoded = json.dumps([code, json.loads(stdout), stderr], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def with_screen(note: str, claim: str, *quotes: str) -> str:
    note = note.replace("## 翻车或别用\n", f"{claim}\n\n## 翻车或别用\n", 1)
    return note + "".join(f"> {line}\n" for line in quotes)


class Phase2ETests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)

    def job(self, name: str, note: str = NOTE, screen: str | None = None,
            transcript: str = TRANSCRIPT) -> Path:
        job = self.temp / name
        job.mkdir()
        write(job / "note.md", note)
        write(job / "transcript.txt", transcript)
        shutil.copyfile(FIXTURES / "usable_selection.md", job / "selection.md")
        write(job / "status.json", json.dumps({
            "status": "transcript_ready", "duration_seconds": 120, "expected_lang": "en",
        }))
        if screen is not None:
            write(job / "screen.txt", screen)
        return job

    def verify(self, job: Path, mode: str | None = "slides") -> tuple[int, dict]:
        code, stdout, _ = entry(verify_note.main, ["--job", str(job), "--json"], mode)
        return code, json.loads(stdout)

    def assert_rule(self, result: dict, rule_id: str, ok: bool) -> dict:
        rule = next((rule for rule in result["rules"] if rule["id"] == rule_id), None)
        self.assertIsNotNone(rule, result)
        self.assertEqual(rule["ok"], ok, rule["message"])
        return rule

    def assert_allowed(self, checked: tuple[int, dict]) -> None:
        code, result = checked
        self.assertEqual(code, 0, result["reasons"])
        self.assertTrue(result["allowed"], result)
        self.assertEqual([rule["id"] for rule in result["rules"]], RULE_IDS)

    def test_screen_quote_must_be_a_full_line(self) -> None:
        full = "Fresh potting mix drains best when coarse bark leaves room for air."
        excerpt = "potting mix drains best when coarse bark leaves room for air"
        self.assertGreaterEqual(len(excerpt), 40)
        source = f"[01:35][画面] {full}\n"
        for label, quote, ok in [("substring", excerpt, False), ("complete", full, True)]:
            with self.subTest(quote=label):
                note = with_screen(NOTE, "画面显示粗树皮让盆土透气。 ⏱ 01:35", f"[01:35][画面] {quote}")
                code, result = self.verify(self.job(label, note, source))
                self.assert_rule(result, "R04", ok)
                if ok:
                    self.assert_allowed((code, result))
                else:
                    self.assertEqual(code, 2, result)
                    self.assertFalse(result["allowed"], result)

    def test_short_screen_quote(self) -> None:
        line = "[01:35][画面] Drainage"
        note = with_screen(NOTE, "画面显示排水方式。 ⏱ 01:35", line)
        code, result = self.verify(self.job("short", note, line + "\n"))
        self.assert_rule(result, "R04", True)
        self.assert_allowed((code, result))

    def test_screen_only_number_supports_prose(self) -> None:
        line = "[01:35][画面] Drainage $48.27"
        note = with_screen(NOTE, "幻灯片上写着排水材料花费 $48.27。 ⏱ 01:35", line)
        # Keep the speech link valid in both runs so C04c evaluates the claim.
        note = note.replace("花费 $48.27。 ⏱ 01:35", "花费 $48.27。 ⏱ 00:30 ⏱ 01:35")
        self.assertNotIn("48.27", TRANSCRIPT)
        code, result = self.verify(self.job("trusted-number", note, line + "\n"))
        self.assert_rule(result, "C04c", True)
        self.assert_allowed((code, result))

    def test_uncertain_screen_quote_is_refused(self) -> None:
        for tag, ok in [("画面?", False), ("画面", True)]:
            with self.subTest(tag=tag):
                line = f"[01:35][{tag}] Drainage 72%"
                note = with_screen(NOTE, "画面显示排水率为 72%。 ⏱ 01:35", line)
                code, result = self.verify(self.job(tag.replace("?", "_"), note, line + "\n"))
                self.assert_rule(result, "R04", ok)
                if ok:
                    self.assert_allowed((code, result))
                else:
                    self.assertEqual(code, 2, result)
                    self.assertFalse(result["allowed"], result)

    def test_uncertain_source_cannot_be_relabelled_as_trusted(self) -> None:
        source = "[01:35][画面?] Drainage 72%\n"
        note = with_screen(NOTE, "画面显示排水率为 72%。 ⏱ 01:35", "[01:35][画面] Drainage 72%")
        code, result = self.verify(self.job("relabelled", note, source))
        self.assert_rule(result, "R04", False)
        self.assertEqual(code, 2, result)

    def test_uncited_uncertain_number_fails_the_number_rule(self) -> None:
        line = "[01:35][画面?] Drainage 72%"
        note = NOTE.replace("## 翻车或别用\n", "画面显示排水率为 72%。 ⏱ 00:30\n\n## 翻车或别用\n")
        code, result = self.verify(self.job("uncertain-number", note, line + "\n"))
        self.assert_rule(result, "R04", True)
        rule = self.assert_rule(result, "C04c", False)
        self.assertIn("72%", rule["message"])
        self.assertEqual([item["id"] for item in result["rules"] if not item["ok"]], ["C04c"])
        self.assertEqual(code, 2, result)

    def test_screen_only_name_supports_prose(self) -> None:
        line = "[01:35][画面] Vellora"
        note = with_screen(NOTE, "画面显示工具名为 Vellora。 ⏱ 00:30 ⏱ 01:35", line)
        self.assertNotIn("Vellora", TRANSCRIPT)
        code, result = self.verify(self.job("screen-name", note, line + "\n"))
        self.assert_rule(result, "C04c", True)
        self.assert_allowed((code, result))

    def test_screen_supports_corrected_spelling(self) -> None:
        transcript = TRANSCRIPT.replace("firm white ones", "firm vermica roots")
        note = NOTE.replace("firm white ones", "firm vermica roots")
        claim = (
            "画面显示名称拼作 Vellora。 ⏱ 00:30 ⏱ 01:35\n\n"
            "> [!warning] 字幕更正\n"
            "> 字幕写作 `vermica`，实为 `Vellora`。"
        )
        line = "[01:35][画面] Vellora"
        self.assert_allowed(self.verify(self.job(
            "caption-correction", with_screen(note, claim, line), line + "\n", transcript,
        )))

    def test_one_exact_body_time_links_multiple_screen_quotes(self) -> None:
        lines = ("[01:35][画面] Bark $48.27", "[01:35][画面] Tray $14.63")
        note = with_screen(NOTE, "画面显示树皮花费 $48.27，托盘花费 $14.63。 ⏱ 01:35", *lines)
        self.assertEqual(note.count("⏱ 01:35"), 1)
        job = self.job("same-screen-time", note, "\n".join(lines) + "\n")
        code, result = self.verify(job)
        self.assert_rule(result, "C04b", True)
        self.assert_rule(result, "C04c", True)
        self.assert_allowed((code, result))
        code, stdout, _ = entry(coverage_check.main, ["--job", str(job), "--json"], "slides")
        self.assertEqual(code, 0, stdout)
        self.assertTrue(json.loads(stdout)["finished"], stdout)

    def test_duplicate_speech_timestamp_still_fails(self) -> None:
        quote = next(line for line in NOTE.splitlines() if line.startswith("> [00:30]"))
        screen = "[01:35][画面] Drainage"
        note = with_screen(NOTE, "画面显示排水方式。 ⏱ 01:35", screen)
        for label, body, ok in [("single", note, True), ("duplicate", note + quote + "\n", False)]:
            with self.subTest(speech=label):
                code, result = self.verify(self.job(label, body, screen + "\n"))
                rule = self.assert_rule(result, "C04b", ok)
                if ok:
                    self.assert_allowed((code, result))
                else:
                    self.assertEqual(code, 2, result)
                    self.assertRegex(rule["message"], r"(?i)duplicat[^;]*00:30")

    def test_duplicate_speech_timestamp_without_screen_still_fails(self) -> None:
        quote = next(line for line in NOTE.splitlines() if line.startswith("> [00:30]"))
        code, result = self.verify(self.job("speech-duplicate", NOTE + quote + "\n"), None)
        self.assertEqual(code, 2, result)
        self.assertRegex(self.assert_rule(result, "C04b", False)["message"],
                         r"(?i)duplicat[^;]*00:30")

    def test_screen_timestamp_at_fifteen_seconds(self) -> None:
        source = "[01:35][画面] Drainage\n"
        note = with_screen(NOTE, "画面显示排水方式。 ⏱ 01:20", "[01:20][画面] Drainage")
        code, result = self.verify(self.job("at-boundary", note, source))
        self.assert_rule(result, "R04", True)
        self.assert_rule(result, "R05", True)
        self.assert_allowed((code, result))

    def test_screen_timestamp_at_sixteen_seconds(self) -> None:
        source = "[01:35][画面] Drainage\n"
        note = with_screen(NOTE, "画面显示排水方式。 ⏱ 01:19", "[01:19][画面] Drainage")
        code, result = self.verify(self.job("outside-boundary", note, source))
        self.assertEqual(code, 2, result)
        with self.subTest(rule="R05"):
            self.assert_rule(result, "R05", False)
        with self.subTest(rule="R04"):
            self.assert_rule(result, "R04", True)

    def test_speech_window_stays_at_forty_characters(self) -> None:
        for length in (39, 40):
            with self.subTest(length=length):
                quote = next(line for line in NOTE.splitlines() if line.startswith("> [00:00]"))
                prefix = "> [00:00] "
                note = NOTE.replace(quote, quote[:len(prefix) + length])
                _, result = self.verify(self.job(f"speech-{length}", note, "[01:35][画面] Drainage\n"))
                self.assert_rule(result, "R04", length == 40)

    def test_quality_gate_only_uses_transcript(self) -> None:
        screen = "".join(line.replace("] ", "][画面] ", 1) + "\n" for line in TRANSCRIPT.splitlines())
        for label, text in [("usable", TRANSCRIPT), ("bad", "Today.\n")]:
            with self.subTest(transcript=label):
                job = self.job(label, screen=screen, transcript=text)
                before = (job / "transcript.txt").read_bytes()
                _, off = self.verify(job, "off")
                _, on = self.verify(job, "slides")
                self.assertEqual(on["gate"], off["gate"])
                self.assertEqual(self.assert_rule(on, "R01", label == "usable"),
                                 self.assert_rule(off, "R01", label == "usable"))
                self.assertEqual((job / "transcript.txt").read_bytes(), before)

    def corpus_checks(self, mode: str | None, *, stale_screen: bool = True) -> dict:
        results = {}
        paths = verify_report.samples(verify_report.ADVERSARIAL) + verify_report.samples(verify_report.GOOD)
        for index, path in enumerate(paths):
            with self.subTest(sample=path.name):
                note = path.read_text(encoding="utf-8")
                fixture = dict(re.findall(r"^# fixture_([a-z]+): (.+)$", note, re.MULTILINE))
                job = self.temp / f"corpus-{index}"
                job.mkdir()
                self.addCleanup(shutil.rmtree, job)
                shutil.copyfile(ROOT / fixture["transcript"], job / "transcript.txt")
                write(job / "note.md", note)
                write(job / "status.json", json.dumps({
                    "status": fixture.get("status", "transcript_ready"),
                    "duration_seconds": int(fixture["duration"]),
                    "expected_lang": fixture["lang"],
                }))
                if "selection" in fixture:
                    shutil.copyfile(ROOT / fixture["selection"], job / "selection.md")
                if stale_screen:
                    # Leftover screen data must have no influence on speech-only checks.
                    lines = (job / "transcript.txt").read_text(encoding="utf-8").splitlines()
                    screen = "\n".join(re.sub(r"^(\[[\d:]+\]) ", r"\1[画面] ", line) for line in lines)
                    write(job / "screen.txt", "[00:00][画面] Drainage $48.27\n" + screen + "\n")
                args = ["--job", str(job), "--json"]
                key = path.relative_to(ROOT).as_posix()
                print(f"sample {key}")
                results[key] = [fingerprint(entry(main, args, mode), job)
                                for main in (verify_note.main, coverage_check.main)]
        return results

    def assert_corpus_unchanged(self, mode: str | None) -> None:
        before = json.loads((FIXTURES / "phase2e" / "baseline-corpus.json").read_text(encoding="utf-8"))
        actual = self.corpus_checks(mode)
        self.assertEqual(set(actual), set(before))
        for path, checks in actual.items():
            with self.subTest(path=path):
                self.assertEqual(checks[0], before[path][0], "verify JSON, stderr or exit changed")
                self.assertEqual(checks[1], before[path][1], "coverage JSON, stderr or exit changed")

    def test_corpus_unchanged_with_default_switch(self) -> None:
        self.assert_corpus_unchanged(None)

    def test_corpus_unchanged_with_explicit_off(self) -> None:
        self.assert_corpus_unchanged("off")

    def test_explicit_off_ignores_screen_evidence(self) -> None:
        line = "[01:35][画面] Drainage"
        note = with_screen(NOTE, "画面显示排水方式。 ⏱ 01:35", line)
        old_code, old = self.verify(self.job("without-file", note), None)
        old.pop("transcript")
        for name, mode in [("default", None), ("off", "off")]:
            with self.subTest(mode=mode):
                code, result = self.verify(self.job(name, note, line + "\n"), mode)
                result.pop("transcript")
                self.assertEqual((code, result), (old_code, old))
                self.assert_rule(result, "R04", False)

    def test_reading_copy_marks_machine_recognition(self) -> None:
        line = "[01:35][画面] Drainage"
        note = with_screen(NOTE, "画面显示排水方式。 ⏱ 01:35", line)
        old_job = self.job("reading-speech")
        old = self.temp / "reading-speech.md"
        code, stdout, stderr = entry(
            render_reading_note.main, ["--task-dir", str(old_job), "--output", str(old)], None,
        )
        self.assertEqual(code, 0, stdout + stderr)
        self.assertNotIn(HINT, old.read_text(encoding="utf-8"))

        with self.subTest(entry="render_note"):
            with patch.dict(os.environ, {MODE: "slides"}):
                reading = render_reading_note.render_note(note.encode("utf-8"), keep_frontmatter=False)
            intro, _, _ = reading.decode("utf-8").partition("## 先记住一句话")
            self.assertIn(HINT, intro)

        job = self.job("reading-screen", note, line + "\n")
        output = self.temp / "reading-screen.md"
        code, stdout, stderr = entry(
            render_reading_note.main, ["--task-dir", str(job), "--output", str(output)], "slides",
        )
        self.assertEqual(code, 0, stdout + stderr)
        reading = output.read_text(encoding="utf-8")
        print(reading, end="")
        intro, _, _ = reading.partition("## 先记住一句话")
        self.assertIn(HINT, intro)
        self.assertEqual(reading.count(HINT), 1)

    def host(self, name: str, mode: str | None, *, missing: str | None = None,
             timeout: bool = False, watermark: bool = False) -> tuple[Path, dict, MediaTools]:
        output = self.temp / name
        tools = MediaTools(VIDEO_ID, TRANSCRIPT, missing=missing, timeout=timeout,
                           mode=mode, watermark=watermark)
        argv = [VIDEO_ID, "--out", str(output), "--expected-lang", "en", "--asr", "off", "--json"]
        with (patch.dict(os.environ, {"YTDLP_COOKIES": "", "YTDLP_EXTRACTOR_ARGS": "",
                                      "INVIDIOUS_INSTANCE": "off"}),
              tools.ocr_packages.installed(), patch("time.monotonic", tools.monotonic),
              patch("shutil.which", tools.which), patch("subprocess.run", tools.run),
              patch("socket.socket.connect", side_effect=AssertionError("unexpected network access"))):
            code, stdout, stderr = entry(youtube_host.main, argv, mode)
        job = output / f"youtube_{VIDEO_ID}"
        status = read_status(job)
        print(json.dumps({"tool_events": tools.events, "status.json": status}, ensure_ascii=False))
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(status["status"], "transcript_ready", status)
        self.assertEqual(status["next_step"], "write-note", status)
        self.assertTrue(status["gate"]["passed"], status["gate"])
        self.assertEqual(status["repair_rounds"], 0, status)
        self.assertFalse(status["locked"], status)
        return job, status, tools

    def test_host_default_and_explicit_off_do_not_probe_screen_tools(self) -> None:
        for name, mode in [("default", None), ("off", "off")]:
            with self.subTest(mode=mode):
                job, _, tools = self.host(name, mode)
                self.assertFalse((job / "screen.txt").exists())
                self.assertFalse(any(event[1] in {"ffmpeg", "tesseract", *OCR_VERSIONS} for event in tools.events),
                                 tools.events)
                self.assertFalse(tools.videos, tools.videos)

    def assert_host_fallback(self, *, missing: str | None = None,
                             timeout: bool = False) -> None:
        baseline, before, _ = self.host("speech-only", None)
        job, status, tools = self.host("candidate", "slides", missing=missing, timeout=timeout)
        self.assertEqual((job / "transcript.txt").read_bytes(), (baseline / "transcript.txt").read_bytes())
        for key in ("gate", "repair_rounds", "edit_rounds"):
            self.assertEqual(status[key], before[key])
        self.assertFalse((job / "screen.txt").exists())
        serialized = json.dumps(status, ensure_ascii=False).casefold()
        with self.subTest(evidence="status.json"):
            if missing:
                self.assertIn(missing, serialized, f"status.json has no diagnostic for missing {missing}")
                self.assertRegex(serialized, r"missing|not[\s_-]*(?:found|installed|available)|缺[少失]|未安装")
            else:
                self.assertRegex(serialized, r"timed?[\s_-]*out|timeout|超时")
        with self.subTest(evidence="tool calls"):
            event = ("missing", missing) if missing else ("timeout", "rapidocr")
            self.assertIn(event, tools.events)
        write(job / "note.md", NOTE)
        self.assert_allowed(self.verify(job))
        self.assertEqual(read_status(job)["repair_rounds"], before["repair_rounds"])

    def test_missing_ffmpeg_falls_back_to_captions(self) -> None:
        self.assert_host_fallback(missing="ffmpeg")

    def test_missing_ocr_packages_fall_back_to_captions(self) -> None:
        for package in OCR_VERSIONS:
            with self.subTest(package=package):
                self.assert_host_fallback(missing=package)

    def test_screen_timeout_falls_back_to_captions(self) -> None:
        self.assert_host_fallback(timeout=True)

    def test_two_ocr_passes_publish_usable_and_uncertain_lines(self) -> None:
        speech, old_status, _ = self.host("speech-only", None)
        job, status, tools = self.host("ocr", "slides")
        self.assertEqual((job / "transcript.txt").read_bytes(), (speech / "transcript.txt").read_bytes())
        self.assertEqual(status["gate"], old_status["gate"])
        self.assertEqual(status["repair_rounds"], old_status["repair_rounds"])
        with self.subTest(evidence="OCR inputs"):
            self.assertCountEqual(tools.ocr_images, tools.ocr_text.keys())
        with self.subTest(evidence="downloaded video"):
            self.assertTrue(tools.videos, "yt-dlp did not download the video")
            self.assertTrue(all(not path.exists() for path in tools.videos), tools.videos)
        with self.subTest(evidence="tool versions"):
            serialized = json.dumps(status, ensure_ascii=False)
            for version in (*tools.versions.values(), sys.version.split()[0]):
                self.assertIn(version, serialized)
        screen_path = job / "screen.txt"
        self.assertTrue(screen_path.is_file(), "screen.txt was never published")
        screen = screen_path.read_text(encoding="utf-8")
        print(f"screen.txt:\n{screen}", end="")
        agreed = re.search(r"(?m)^(\[(\d\d:\d\d)\]\[画面\] Drainage \$48\.27)$", screen)
        self.assertIsNotNone(agreed, screen)
        self.assertRegex(screen, r"(?m)^\[\d\d:\d\d\]\[画面\] Coarse bark$")
        self.assertRegex(screen, r"(?m)^\[\d\d:\d\d\]\[画面\?\] Moisture 72%$")
        self.assertNotRegex(screen, r"(?m)^\[\d\d:\d\d\]\[画面\].*(?:Moisture|Calibration)")
        self.assertRegex(screen, r"(?m)^\[\d\d:\d\d\]\[画面\?\] Calibration .*")
        self.assertEqual(agreed[2], "01:35")
        screenshots = [path for path in job.rglob("*") if path.suffix.lower() in tools.image_suffixes]
        self.assertEqual(len(screenshots), 1, screenshots)

        note = with_screen(NOTE, f"画面显示排水材料花费 $48.27。 ⏱ {agreed[2]}", agreed[1])
        write(job / "note.md", note)
        self.assert_allowed(self.verify(job))

        note = note.replace("## 翻车或别用\n", "画面显示含水率为 72%。 ⏱ 00:30\n\n## 翻车或别用\n")
        write(job / "note.md", note)
        code, result = self.verify(job)
        self.assertEqual(code, 2, result)
        self.assertIn("72%", self.assert_rule(result, "C04c", False)["message"])

    def test_nameplate_mode_scans_the_first_three_minutes(self) -> None:
        job, _, tools = self.host("nameplate", "nameplate")
        self.assertTrue(tools.scan_limits, "FFmpeg did not scan the video")
        self.assertEqual(set(tools.scan_limits), {180.0}, tools.events)
        self.assertRegex((job / "screen.txt").read_text(encoding="utf-8"),
                         r"(?m)^\[02:40\]\[画面\] Mira Vellora, Horticulturist$")

    def test_fixed_position_watermark_is_filtered(self) -> None:
        job, _, _ = self.host("watermark", "slides", watermark=True)
        screen_path = job / "screen.txt"
        self.assertTrue(screen_path.is_file(), "screen.txt was never published")
        screen = screen_path.read_text(encoding="utf-8")
        print(f"screen.txt:\n{screen}", end="")
        self.assertNotIn("Garden Channel", screen)
        self.assertEqual(len(re.findall(r"(?m)^\[\d\d:\d\d\]\[画面\] Seasonal$", screen)), 1)
        for line in ("Topsoil", "Fine bark", "Stones", "Mulch", "Compost"):
            self.assertRegex(screen, rf"(?m)^\[\d\d:\d\d\]\[画面\] {line}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
