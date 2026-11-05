#!/usr/bin/env python3
"""Coverage gate C on synthetic jobs. No network. No language model.

A thin note can quote a real stretch and still fail. A note that carries the
inventory across quartiles passes. Delivery under 9/10 of the local prose fails.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import coverage_check as cov

# Ten method arcs. Each excerpt is longer than 40 characters and shares no
# 40-character fold with the others. Stamps sit in all four quartiles of a
# 1200s talk (boundaries at 300, 600, and 900).
ARCS = [
    (30, "Export the overnight file before the standup meeting starts today."),
    (90, "Name the owner of that file before anyone else opens the folder."),
    (150, "Keep one backup copy on the side desk and do not mail the original."),
    (330, "Delete the duplicate tab before the email goes to the whole team."),
    (420, "Stop adding columns once the sheet already answers the question."),
    (630, "Stop the feed when the soil stayed wet for three full days."),
    (720, "Mark the pot that stayed wet so the next watering skips it."),
    (930, "Write the limit down before the next person opens the shared board."),
    (1020, "Read the limit aloud once before the group leaves the room."),
    (1140, "Close the board only after the limit is written where people look."),
]
DURATION = 1200


def _inventory_text() -> str:
    lines = []
    for stamp, excerpt in ARCS:
        minutes, seconds = divmod(stamp, 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {excerpt} | restatement of that line only")
    return "\n".join(lines) + "\n"


def _transcript() -> str:
    lines = []
    for stamp, excerpt in ARCS:
        minutes, seconds = divmod(stamp, 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {excerpt}")
    return "\n".join(lines) + "\n"


def _quote_block(stamps: list[int]) -> str:
    by_stamp = {stamp: excerpt for stamp, excerpt in ARCS}
    parts = []
    for stamp in stamps:
        minutes, seconds = divmod(stamp, 60)
        parts.append(f"> [{minutes:02d}:{seconds:02d}] {by_stamp[stamp]}")
    return "\n".join(parts)


def _note(stamps: list[int], prose: str) -> str:
    quotes = _quote_block(stamps)
    return "\n".join(
        [
            "---",
            'title: "fixture"',
            "gate_passed: true",
            "---",
            "",
            "## 先记住一句话",
            "",
            prose,
            "",
            quotes,
            "",
            "## 问题与做法",
            "",
            prose,
            "",
            quotes,
            "",
        ]
    )


def _write_job(
    root: Path,
    *,
    note: str,
    inventory: str | None = None,
    duration: int = DURATION,
    transcript: str | None = None,
) -> Path:
    job = root / "job"
    job.mkdir(parents=True)
    (job / "transcript.txt").write_text(
        _transcript() if transcript is None else transcript,
        encoding="utf-8",
    )
    (job / "status.json").write_text(
        json.dumps({"duration_seconds": duration}),
        encoding="utf-8",
    )
    (job / "note.md").write_text(note, encoding="utf-8")
    if inventory is not None:
        (job / "inventory.md").write_text(inventory, encoding="utf-8")
    return job


def _sparse_job(
    root: Path,
    *,
    duration: int,
    rows: list[tuple[int, str]],
    quoted: list[int],
    chunks: int = 0,
) -> Path:
    by_stamp = {stamp: excerpt for stamp, excerpt in rows}
    inventory_lines = []
    transcript_lines = []
    for stamp, excerpt in rows:
        minutes, seconds = divmod(stamp, 60)
        clock = f"[{minutes:02d}:{seconds:02d}]"
        inventory_lines.append(f"{clock} {excerpt} | restatement of that line only")
        transcript_lines.append(f"{clock} {excerpt}")
    quote_lines = []
    for stamp in quoted:
        minutes, seconds = divmod(stamp, 60)
        quote_lines.append(f"> [{minutes:02d}:{seconds:02d}] {by_stamp[stamp]}")
    note = "\n".join(["## 先记住一句话", "", "The note keeps each quoted line.", "", *quote_lines, ""])
    job = root / "job"
    job.mkdir(parents=True)
    (job / "transcript.txt").write_text("\n".join(transcript_lines) + "\n", encoding="utf-8")
    (job / "status.json").write_text(
        json.dumps({"duration_seconds": duration}),
        encoding="utf-8",
    )
    (job / "note.md").write_text(note, encoding="utf-8")
    (job / "inventory.md").write_text("\n".join(inventory_lines) + "\n", encoding="utf-8")
    if chunks:
        folder = job / "chunks"
        folder.mkdir()
        for index in range(1, chunks + 1):
            (folder / f"{index:02d}.txt").write_text(
                "chunk text without a stamp\n",
                encoding="utf-8",
            )
    return job


class CoverageCheckTests(unittest.TestCase):
    def test_script_reads_only_and_calls_no_model(self) -> None:
        source = Path(cov.__file__).read_text(encoding="utf-8")
        self.assertIn("from pathlib import Path", source)
        self.assertNotIn("import openai", source)
        self.assertNotIn("anthropic", source)
        self.assertNotIn('Path("C:', source)
        self.assertNotIn("Path('C:", source)
        self.assertNotIn("C:\\", source)
        self.assertNotIn("C:/", source)

    def test_hits_required_is_nine_tenths_at_least_three(self) -> None:
        self.assertEqual(cov.hits_required(10), 9)
        self.assertEqual(cov.hits_required(4), 4)
        self.assertEqual(cov.hits_required(1), 3)
        self.assertEqual(cov.DELIVERY_RATIO, 0.9)

    def test_thin_stub_fails_quartiles_and_depth(self) -> None:
        """Four grounded claims, one early stamp. Faithful on that line, not covered."""
        early = ARCS[0][1]
        prose = "Export the overnight file before the standup meeting starts today."
        note = _note([30, 30, 30, 30], prose)
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp), note=note, inventory=_inventory_text())
            transcript = (job / "transcript.txt").read_text(encoding="utf-8")
            self.assertIn(early, transcript)
            result = cov.check_job(job)
        codes = [line.split()[0] for line in result["reasons"]]
        self.assertIn("C02", codes)
        self.assertIn("C03", codes)
        self.assertFalse(result["ok"])
        self.assertEqual(result["inventory_hits"], 1)
        self.assertEqual(result["inventory_need"], 9)
        self.assertEqual(result["quartiles"], [0])

    def test_spread_without_depth_still_fails(self) -> None:
        """Three quartiles and four facts are still under the 9/10 inventory bar."""
        prose = "The talk names a file, a tab, a feed, and a limit."
        note = _note([30, 330, 630, 930], prose)
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp), note=note, inventory=_inventory_text())
            result = cov.check_job(job)
        self.assertFalse(result["ok"])
        self.assertTrue(any(line.startswith("C03 FAIL:") for line in result["reasons"]))
        self.assertFalse(any(line.startswith("C02 FAIL:") for line in result["reasons"]))
        self.assertEqual(result["inventory_hits"], 4)
        self.assertGreaterEqual(len(result["quartiles"]), 3)

    def test_full_arc_note_passes(self) -> None:
        prose = (
            "先把过夜的文件导出来，写上负责人，旁边留一份备份。"
            "重复的表删掉，列加够就停。"
            "土连续湿了三天就停浇，并把那盆标出来。"
            "限额写在大家看得到的地方，念一遍，再收板。"
        )
        note = _note([stamp for stamp, _excerpt in ARCS], prose)
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp), note=note, inventory=_inventory_text())
            result = cov.check_job(job)
        self.assertEqual(result["reasons"], [], result["reasons"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["long"])
        self.assertEqual(result["inventory_hits"], 10)
        self.assertEqual(result["quartiles"], [0, 1, 2, 3])
        self.assertEqual(result["warnings"], [])

    def test_nine_of_ten_passes_and_eight_fails(self) -> None:
        prose = "Ten arcs, one left as a single banter line still quoted."
        nine = [stamp for stamp, _excerpt in ARCS[:9]]
        eight = [stamp for stamp, _excerpt in ARCS[:8]]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            passed = cov.check_job(
                _write_job(root / "a", note=_note(nine, prose), inventory=_inventory_text())
            )
            failed = cov.check_job(
                _write_job(root / "b", note=_note(eight, prose), inventory=_inventory_text())
            )
        self.assertTrue(passed["ok"], passed["reasons"])
        self.assertEqual(passed["inventory_hits"], 9)
        self.assertEqual(passed["warnings"], [])
        self.assertFalse(failed["ok"])
        self.assertTrue(any(line.startswith("C03 FAIL:") for line in failed["reasons"]))
        self.assertEqual(failed["inventory_hits"], 8)

    def test_thin_delivery_fails_and_full_delivery_passes(self) -> None:
        prose = "测" * 100
        note = _note([stamp for stamp, _excerpt in ARCS], prose)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = _write_job(root, note=note, inventory=_inventory_text())
            thin = root / "thin.md"
            full = root / "full.md"
            yaml_trap = root / "yaml.md"
            thin.write_text("先记住这一句。\n", encoding="utf-8")
            full.write_text(note, encoding="utf-8")
            yaml_trap.write_text(
                "---\n"
                + ("title: " + ("alphabet" * 40) + "\n")
                + "---\n短\n",
                encoding="utf-8",
            )
            thin_result = cov.check_job(job, thin)
            full_result = cov.check_job(job, full)
            yaml_result = cov.check_job(job, yaml_trap)
        self.assertTrue(any(line.startswith("C04 FAIL:") for line in thin_result["reasons"]))
        self.assertFalse(thin_result["ok"])
        self.assertLess(thin_result["delivery_ratio"], 0.9)
        self.assertTrue(full_result["ok"], full_result["reasons"])
        self.assertGreaterEqual(full_result["delivery_ratio"], 0.9)
        self.assertTrue(any(line.startswith("C04 FAIL:") for line in yaml_result["reasons"]))

    def test_delivery_ratio_boundary(self) -> None:
        note = "测" * 100 + "\n> [00:10] " + ("hello " * 20)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            job.mkdir()
            (job / "transcript.txt").write_text("[00:10] hello from a short clip\n", encoding="utf-8")
            (job / "status.json").write_text(json.dumps({"duration_seconds": 20}), encoding="utf-8")
            (job / "note.md").write_text(note, encoding="utf-8")
            at = root / "at.md"
            under = root / "under.md"
            at.write_text("测" * 90, encoding="utf-8")
            under.write_text("测" * 89, encoding="utf-8")
            at_result = cov.check_job(job, at)
            under_result = cov.check_job(job, under)
        self.assertTrue(at_result["skipped"])
        self.assertTrue(at_result["ok"], at_result["reasons"])
        self.assertFalse(under_result["ok"])
        self.assertTrue(any(line.startswith("C04 FAIL:") for line in under_result["reasons"]))

    def test_missing_inventory_fails_and_inventory_file_satisfies(self) -> None:
        note = _note([stamp for stamp, _excerpt in ARCS], "covered")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bare = root / "bare"
            bare.mkdir()
            (bare / "transcript.txt").write_text(_transcript(), encoding="utf-8")
            (bare / "status.json").write_text(
                json.dumps({"duration_seconds": DURATION}),
                encoding="utf-8",
            )
            (bare / "note.md").write_text(note, encoding="utf-8")
            (bare / "chunks").mkdir()
            (bare / "chunks" / "01.txt").write_text("[00:30] early\n", encoding="utf-8")
            (bare / "chunks" / "02.txt").write_text("[15:30] late\n", encoding="utf-8")
            missing = cov.check_job(bare)
            held = root / "held"
            job = _write_job(held, note=note, inventory=_inventory_text())
            (job / "chunks").mkdir()
            (job / "chunks" / "01.txt").write_text("[00:30] early\n", encoding="utf-8")
            present = cov.check_job(job)
        self.assertTrue(any(line.startswith("C01 FAIL:") for line in missing["reasons"]))
        self.assertNotIn("C01", [line.split()[0] for line in present["reasons"]])
        self.assertTrue(present["ok"], present["reasons"])

    def test_chunk_notes_cover_a_long_job(self) -> None:
        note = _note([stamp for stamp, _excerpt in ARCS], "chunk notes stand in for inventory.md")
        first = "\n".join(_inventory_text().splitlines()[:5]) + "\n"
        second = "\n".join(_inventory_text().splitlines()[5:]) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp), note=note, inventory=None)
            chunks = job / "chunks"
            chunks.mkdir()
            (chunks / "01.txt").write_text("chunk one\n", encoding="utf-8")
            (chunks / "02.txt").write_text("chunk two\n", encoding="utf-8")
            (chunks / "01.notes.md").write_text(first, encoding="utf-8")
            (chunks / "02.notes.md").write_text(second, encoding="utf-8")
            result = cov.check_job(job)
        self.assertTrue(result["ok"], result["reasons"])
        self.assertEqual(result["inventory_lines"], 10)
        self.assertEqual(result["warnings"], [])

    def test_two_chunks_without_a_clock_count_as_long(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            chunks = job / "chunks"
            chunks.mkdir(parents=True)
            (chunks / "01.txt").write_text("no stamp here at all\n", encoding="utf-8")
            (chunks / "02.txt").write_text("still no clock in the second chunk\n", encoding="utf-8")
            (job / "note.md").write_text("a note\n", encoding="utf-8")
            result = cov.check_job(job)
        self.assertTrue(result["long"])
        self.assertTrue(any(line.startswith("C01 FAIL:") for line in result["reasons"]))

    def test_unstamped_quotes_use_segments(self) -> None:
        segments = []
        quote_lines = ["## 先记住一句话", ""]
        for index, (stamp, excerpt) in enumerate(ARCS):
            segments.append({"start": stamp, "end": stamp + 20, "text": excerpt})
            quote_lines.append(f"> {excerpt}")
        segments[-1]["end"] = DURATION
        note = "\n".join(quote_lines) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(Path(tmp), note=note, inventory=_inventory_text())
            (job / "segments.json").write_text(json.dumps(segments), encoding="utf-8")
            result = cov.check_job(job)
        self.assertTrue(result["ok"], result["reasons"])
        self.assertEqual(result["quartiles"], [0, 1, 2, 3])

    def test_short_video_still_runs_and_skips_arc_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = _write_job(
                Path(tmp),
                note="Short note with one quote.\n\n> [00:30] " + ARCS[0][1] + "\n",
                inventory=None,
                duration=120,
                transcript="[00:30] " + ARCS[0][1] + "\n",
            )
            result = cov.check_job(job)
        self.assertTrue(result["ok"], result["reasons"])
        self.assertTrue(result["skipped"])
        self.assertFalse(result["long"])
        self.assertEqual(result["warnings"], [])

    def test_thin_warning_does_not_loosen_thresholds(self) -> None:
        """A sparse inventory can still pass. The warning is not a new fail."""
        self.assertEqual(cov.HIT_RATE_NUMERATOR, 9)
        self.assertEqual(cov.HIT_RATE_DENOMINATOR, 10)
        self.assertEqual(cov.MIN_HITS, 3)
        self.assertEqual(cov.DELIVERY_RATIO, 0.9)
        self.assertEqual(cov.THIN_SECONDS_PER_LINE, 600)
        self.assertEqual(cov.hits_required(10), 9)
        self.assertEqual(cov.hits_required(3), 3)
        self.assertIsNone(cov.inventory_thin_warning(3, 1800, 0))
        self.assertIsNone(cov.inventory_thin_warning(6, 3600, 0))
        self.assertIsNone(cov.inventory_thin_warning(10, DURATION, 2))
        self.assertIsNone(cov.inventory_thin_warning(0, 3600, 8))
        duration_only = cov.inventory_thin_warning(3, 3600, 0)
        self.assertIsNotNone(duration_only)
        assert duration_only is not None
        self.assertTrue(duration_only.startswith("C WARN:"))
        self.assertNotIn("FAIL", duration_only)
        both = cov.inventory_thin_warning(3, 3600, 8)
        self.assertIsNotNone(both)
        assert both is not None
        self.assertIn("3600s", both)
        self.assertIn("8 chunks", both)

    def test_sparse_inventory_warns_and_still_passes(self) -> None:
        """Three lines on a one-hour talk clear C03 and still warn."""
        rows = [
            (120, ARCS[0][1]),
            (1500, ARCS[3][1]),
            (3000, ARCS[7][1]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            job = _sparse_job(Path(tmp), duration=3600, rows=rows, quoted=[120, 1500, 3000])
            result = cov.check_job(job)
            script = Path(cov.__file__)
            completed = subprocess.run(
                [sys.executable, str(script), "--job", str(job), "--json"],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertTrue(result["ok"], result["reasons"])
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["inventory_lines"], 3)
        self.assertEqual(result["inventory_hits"], 3)
        self.assertEqual(result["inventory_need"], 3)
        self.assertGreaterEqual(len(result["quartiles"]), 3)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("under one line per 10 minutes", result["warnings"][0])
        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["warnings"], result["warnings"])
        self.assertNotIn("FAIL", completed.stdout)

    def test_sparse_inventory_that_misses_rows_still_fails(self) -> None:
        """The warning does not clear a C03 miss, and it does not loosen 9/10."""
        rows = [
            (120, ARCS[0][1]),
            (1500, ARCS[3][1]),
            (3000, ARCS[7][1]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            job = _sparse_job(Path(tmp), duration=3600, rows=rows, quoted=[120])
            result = cov.check_job(job)
        self.assertFalse(result["ok"])
        self.assertTrue(any(line.startswith("C03 FAIL:") for line in result["reasons"]))
        self.assertEqual(result["inventory_hits"], 1)
        self.assertEqual(result["inventory_need"], 3)
        self.assertTrue(result["warnings"])
        self.assertTrue(result["warnings"][0].startswith("C WARN:"))

    def test_fewer_lines_than_chunks_warns_without_failing(self) -> None:
        rows = [
            (30, ARCS[0][1]),
            (400, ARCS[3][1]),
            (1000, ARCS[7][1]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            job = _sparse_job(
                Path(tmp),
                duration=DURATION,
                rows=rows,
                quoted=[30, 400, 1000],
                chunks=4,
            )
            result = cov.check_job(job)
            plain = subprocess.run(
                [sys.executable, str(Path(cov.__file__)), "--job", str(job)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertTrue(result["ok"], result["reasons"])
        self.assertEqual(result["reasons"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("fewer lines than chunk files", result["warnings"][0])
        self.assertNotIn("under one line per 10 minutes", result["warnings"][0])
        self.assertEqual(plain.returncode, 0)
        self.assertIn("coverage ok", plain.stdout)
        self.assertIn("C WARN:", plain.stdout)
        self.assertNotIn("FAIL", plain.stdout)

    def test_cli_exit_codes(self) -> None:
        prose = "Export the overnight file before the standup meeting starts today."
        note = _note([30], prose)
        script = Path(cov.__file__)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = _write_job(root, note=note, inventory=_inventory_text())
            failed = subprocess.run(
                [sys.executable, str(script), "--job", str(job)],
                check=False,
                capture_output=True,
                text=True,
            )
            missing = subprocess.run(
                [sys.executable, str(script), "--job", str(root / "nope")],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(failed.returncode, 1)
        self.assertIn("C02 FAIL:", failed.stdout)
        self.assertIn("C03 FAIL:", failed.stdout)
        self.assertEqual(missing.returncode, 2)


if __name__ == "__main__":
    unittest.main()
