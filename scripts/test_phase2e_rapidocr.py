"""Real OCR regression for the small storage figures on the 07:26 slide."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

from test_phase2e_first_acceptance import FrameCommands, TRUSTED, screen_output


FIXTURE = (
    Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "phase2e" /
    "rapidocr" / "newvideo-30q6fT_8aWc-0726.png"
)


@unittest.skipUnless(os.environ.get("TFV_TEST_REAL_OCR") == "1", "set TFV_TEST_REAL_OCR=1 for real screen OCR")
class StorageSlideTests(unittest.TestCase):
    def test_storage_units_are_citable_but_the_digit_misreads_are_not(self):
        rows, status = screen_output("slides", FrameCommands(446, image=FIXTURE))
        self.assertEqual(status["state"], "ready", status)
        trusted = [row for row in rows if row.partition("]")[2].startswith(TRUSTED)]
        timed = [row for row in trusted if row.startswith("[07:26]")]
        for token in ("10TB", "100GB"):
            with self.subTest(required=token):
                spelling = re.compile(rf"(?<!\w){re.escape(token)}(?!\w)")
                self.assertTrue(any(spelling.search(row) for row in timed),
                                f"No citable {token} at 07:26")
        for token in ("1078", "10068"):
            with self.subTest(forbidden=token):
                spelling = re.compile(rf"(?<!\w){re.escape(token)}(?!\w)")
                misreads = [row for row in trusted if spelling.search(row)]
                self.assertEqual(misreads, [], f"Citable OCR misread {token}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
