#!/usr/bin/env python3
"""Offline contract tests for the A1 caption mirror fallback."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import time
import tokenize
import unittest
from unittest.mock import patch
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quality_gate
import youtube_host


VIDEO_ID = "AbCdEf12345"
SOURCE = f"https://www.youtube.com/watch?v={VIDEO_ID}"
SEED = "https://yt.chocolatemoo53.com"
CAPTIONS_PATH = f"/api/v1/captions/{VIDEO_ID}"
TRACK_PATH = f"{CAPTIONS_PATH}?label=English"
TLS_ERROR = (
    "caption request failed: [SSL: UNEXPECTED_EOF_WHILE_READING] "
    "EOF occurred in violation of protocol"
)
TRACK_LIST = json.dumps({"captions": [{
    "label": "English (auto-generated)",
    "languageCode": "en",
    "url": TRACK_PATH,
}]}).encode("utf-8")
VTT = b"""WEBVTT

00:00:00.000 --> 00:00:05.000
We carried the wooden trays outside before sunrise.

00:00:05.000 --> 00:00:10.000
Each tray held paper labels for the herbs growing beside the fence.

00:00:10.000 --> 00:00:15.000
When rain started, a neighbor brought a canvas cover to protect the ink.
"""


class CaptionMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(patch.dict(os.environ, {"TFV_SCREEN_MODE": "off"}, clear=True))
        self.now = 0.0
        self.enterContext(patch.object(time, "monotonic", side_effect=lambda: self.now))
        self.enterContext(patch.object(youtube_host, "ytdlp_base", return_value=["yt-dlp"]))
        self.enterContext(patch.object(youtube_host, "fetch_ytdlp_captions", return_value={
            "text": None,
            "error": "ERROR: HTTP Error 429: Too Many Requests",
        }))
        self.urlopen = self.enterContext(patch.object(
            urllib.request, "urlopen", side_effect=AssertionError("unexpected urlopen"),
        ))
        self.stderr = self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def run_host(self, asr_choice="auto"):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            result = youtube_host.run_host(
                video_id=VIDEO_ID, source=SOURCE, out_dir=out_dir,
                expected_lang="en", asr_choice=asr_choice, verify=False,
            )
            status_path = out_dir / youtube_host.job_id_for(VIDEO_ID) / "status.json"
            raw_status = status_path.read_text(encoding="utf-8")
        return result, json.loads(raw_status), raw_status

    def mock_http(self, routes):
        def get(url, *, limit, timeout, accept):
            self.assertIn(url, routes, f"unexpected HTTP request to {url}")
            response = routes[url]
            if isinstance(response, Exception):
                raise response
            return response

        return self.enterContext(patch.object(youtube_host, "http_get", side_effect=get))

    def assert_urls(self, http_get, expected):
        self.assertEqual([call.args[0] for call in http_get.call_args_list], expected)

    def attempt(self, attempts, *, layer, ok, source=None):
        matches = [
            entry for entry in attempts
            if entry.get("layer") == layer and entry.get("ok") is ok
            and (source is None or entry.get("source") == source)
        ]
        self.assertTrue(matches, f"missing {source=} {layer=} {ok=} in {attempts!r}")
        return matches[0]

    def assert_ready(self, result, status, *, layer, host):
        self.assertEqual(result.get("exit_code"), 0, status.get("reason"))
        self.assertEqual(result.get("status"), "transcript_ready")
        self.assertEqual(result.get("acquisition"), "caption-mirror")
        for payload in (result, status):
            self.assertEqual(payload.get("mirror_layer"), layer)
            self.assertEqual(payload.get("mirror_host"), host)
        return self.attempt(status["attempts"], layer=layer, ok=True, source="caption-mirror")

    def test_constants_and_scope(self) -> None:
        with self.subTest("seed"):
            self.assertEqual(getattr(youtube_host, "SEED_INVIDIOUS_INSTANCES", None), (SEED,))
        with self.subTest("request timeout"):
            timeout = getattr(youtube_host, "MIRROR_REQUEST_TIMEOUT", 0)
            self.assertGreaterEqual(timeout, 6)
            self.assertLessEqual(timeout, 8)
        with self.subTest("total budget"):
            budget = getattr(youtube_host, "MIRROR_TOTAL_BUDGET", 0)
            self.assertGreater(budget, 0)
            self.assertLessEqual(budget, 30)
        path = Path(youtube_host.__file__)
        source = path.read_text(encoding="utf-8").casefold()
        for banned in ("libredirect", "youtube_transcript_api", "youtube-transcript-api"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)
        with self.subTest("single-point comment"):
            with path.open("rb") as stream:
                comments = [
                    token.string.casefold() for token in tokenize.tokenize(stream.readline)
                    if token.type == tokenize.COMMENT
                ]
            self.assertTrue(any(
                "single" in comment or "\u5355\u70b9" in comment
                for comment in comments
            ))

    def test_vtt_fixture_passes_quality_gate(self) -> None:
        gate = quality_gate.assess(VTT.decode("utf-8"), expected_lang="en")
        self.assertTrue(gate.passed, gate.reasons)

    def test_tls_list_failure_is_visible_after_seed_success(self) -> None:
        http = self.mock_http({
            youtube_host.INSTANCE_LIST: youtube_host.HostError(TLS_ERROR),
            SEED + CAPTIONS_PATH: TRACK_LIST,
            SEED + TRACK_PATH: VTT,
        })
        result, status, _ = self.run_host()
        success = self.assert_ready(result, status, layer="seed-fallback", host="yt.chocolatemoo53.com")
        self.assert_urls(http, [youtube_host.INSTANCE_LIST, SEED + CAPTIONS_PATH, SEED + TRACK_PATH])
        self.attempt(status["attempts"], layer=None, ok=False, source="yt-dlp")
        failure = self.attempt(status["attempts"], layer="public-list", ok=False, source="caption-mirror")
        self.assertIn("UNEXPECTED_EOF_WHILE_READING", failure["detail"])
        self.assertIn("yt.chocolatemoo53.com", success["detail"])
        self.assertIn("seed-fallback", success["detail"])
        self.assertRegex(self.stderr.getvalue().casefold(), r"seed-fallback|fall(?:ing)?\s*back.*seed|fallback.*seed")

    def test_alternate_public_list_failures_use_seed(self) -> None:
        cases = {
            "empty list": b"[]",
            "invalid JSON": b"not-json{",
            "HTTP 503": youtube_host.HostError("HTTP 503 for caption request"),
            "timeout": TimeoutError("timed out"),
        }
        for name, response in cases.items():
            with self.subTest(name=name):
                http = self.mock_http({
                    youtube_host.INSTANCE_LIST: response,
                    SEED + CAPTIONS_PATH: TRACK_LIST,
                    SEED + TRACK_PATH: VTT,
                })
                result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")
                self.assert_seed_success(result)
                self.assert_urls(http, [youtube_host.INSTANCE_LIST, SEED + CAPTIONS_PATH, SEED + TRACK_PATH])

    def assert_seed_success(self, result):
        self.assertEqual(result.get("text"), VTT.decode("utf-8"), result.get("error"))
        self.assertEqual(result.get("mirror_layer"), "seed-fallback")
        self.assertEqual(result.get("mirror_host"), "yt.chocolatemoo53.com")
        attempts = result["mirror_attempts"]
        self.assertTrue(self.attempt(attempts, layer="public-list", ok=False).get("detail"))
        self.attempt(attempts, layer="seed-fallback", ok=True)

    def test_healthy_public_list_uses_public_mirror(self) -> None:
        public = "https://pub.example"
        listing = [["pub.example", {"api": True, "type": "https", "uri": public}]]
        http = self.mock_http({
            youtube_host.INSTANCE_LIST: json.dumps(listing).encode("utf-8"),
            public + CAPTIONS_PATH: TRACK_LIST,
            public + TRACK_PATH: VTT,
        })
        result, status, _ = self.run_host()
        self.assert_urls(http, [youtube_host.INSTANCE_LIST, public + CAPTIONS_PATH, public + TRACK_PATH])
        self.assert_ready(result, status, layer="public-list", host="pub.example")

    def test_explicit_mirror_takes_priority(self) -> None:
        custom = "https://custom.example"
        os.environ["INVIDIOUS_INSTANCE"] = custom
        http = self.mock_http({custom + CAPTIONS_PATH: TRACK_LIST, custom + TRACK_PATH: VTT})
        result, status, _ = self.run_host()
        self.assert_urls(http, [custom + CAPTIONS_PATH, custom + TRACK_PATH])
        self.assert_ready(result, status, layer="env", host="custom.example")

    def test_failed_explicit_mirror_does_not_fall_back(self) -> None:
        custom = "https://bad-custom.example"
        os.environ["INVIDIOUS_INSTANCE"] = custom
        http = self.mock_http({custom + CAPTIONS_PATH: youtube_host.HostError("HTTP 502")})
        result, status, _ = self.run_host()
        self.assert_urls(http, [custom + CAPTIONS_PATH])
        self.assertEqual(result.get("exit_code"), 2)
        self.attempt(status["attempts"], layer="env", ok=False, source="caption-mirror")

    def test_explicit_off_disables_mirror_calls(self) -> None:
        os.environ["INVIDIOUS_INSTANCE"] = "off"
        http = self.mock_http({})
        result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")
        self.assertFalse(result.get("text"))
        self.assertTrue(result.get("error"))
        with patch.object(youtube_host, "fetch_mirror_captions", wraps=youtube_host.fetch_mirror_captions) as fetch:
            result, _, _ = self.run_host()
        self.assertEqual(result.get("exit_code"), 2)
        fetch.assert_not_called()
        http.assert_not_called()
        self.urlopen.assert_not_called()

    def timed_http(self, routes):
        calls = []
        in_flight = 0

        def get(url, *, limit, timeout, accept):
            nonlocal in_flight
            in_flight += 1
            try:
                self.assertEqual(in_flight, 1, "HTTP calls overlapped")
                self.assertIn(url, routes, f"unexpected HTTP request to {url}")
                calls.append((url, timeout, self.now))
                duration, response = routes[url]
                self.now += duration
                if isinstance(response, Exception):
                    raise response
                return response
            finally:
                in_flight -= 1

        self.enterContext(patch.object(youtube_host, "http_get", side_effect=get))
        return calls

    def assert_timeouts(self, calls):
        for url, timeout, started in calls:
            with self.subTest(url=url):
                self.assertGreater(timeout, 0)
                self.assertLessEqual(timeout, 8)
                self.assertLessEqual(timeout, youtube_host.MIRROR_REQUEST_TIMEOUT)
                self.assertLessEqual(timeout, youtube_host.MIRROR_TOTAL_BUDGET - started)

    def assert_budget_exhausted(self, result):
        self.assertFalse(result.get("text"))
        self.assertTrue(any(
            entry.get("ok") is False and "budget" in entry.get("detail", "").casefold()
            for entry in result.get("mirror_attempts", [])
        ), result)

    def test_explicit_mirrors_are_sequential_and_stop_at_budget(self) -> None:
        bases = [f"https://m{index}.example" for index in range(1, 7)]
        os.environ["INVIDIOUS_INSTANCE"] = ",".join(bases)
        urls = [base + CAPTIONS_PATH for base in bases]
        calls = self.timed_http({url: (7.0, youtube_host.HostError("timed out")) for url in urls})
        result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")
        self.assert_timeouts(calls)
        with self.subTest("call order and budget cutoff"):
            self.assertEqual([url for url, _, _ in calls], urls[:5])
        with self.subTest("fifth request timeout"):
            self.assertGreaterEqual(len(calls), 5)
            self.assertLessEqual(calls[4][1], 2.0)
        self.assert_budget_exhausted(result)

    def test_public_list_and_seed_share_budget(self) -> None:
        calls = self.timed_http({
            youtube_host.INSTANCE_LIST: (7.0, youtube_host.HostError(TLS_ERROR)),
            SEED + CAPTIONS_PATH: (7.0, TRACK_LIST),
            SEED + TRACK_PATH: (7.0, VTT),
        })
        result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")
        self.assert_timeouts(calls)
        self.assert_seed_success(result)
        self.assertEqual(
            [url for url, _, _ in calls],
            [youtube_host.INSTANCE_LIST, SEED + CAPTIONS_PATH, SEED + TRACK_PATH],
        )

    def test_public_list_can_exhaust_budget_before_seed(self) -> None:
        calls = self.timed_http({
            youtube_host.INSTANCE_LIST: (30.0, youtube_host.HostError(TLS_ERROR)),
        })
        result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")
        self.assertEqual([url for url, _, _ in calls], [youtube_host.INSTANCE_LIST])
        self.assert_budget_exhausted(result)

    def test_http_get_wraps_and_redacts_transport_errors(self) -> None:
        for stage, error, detail in (
            ("open", ssl.SSLError("UNEXPECTED_EOF_WHILE_READING token=transportsecret"), "UNEXPECTED_EOF_WHILE_READING"),
            ("read", TimeoutError("timed out token=transportsecret"), "timed out"),
        ):
            with self.subTest(stage=stage):
                self.urlopen.side_effect = error if stage == "open" else None
                response = self.urlopen.return_value.__enter__.return_value
                response.read.side_effect = error if stage == "read" else None
                with self.assertRaises(youtube_host.HostError) as caught:
                    youtube_host.http_get(SEED, limit=1024, timeout=7, accept="application/json")
                self.assertIn(detail, str(caught.exception))
                self.assertNotIn("transportsecret", str(caught.exception))

    def test_mirror_error_credentials_are_redacted_in_status(self) -> None:
        custom = "https://alice:supersecretpw@priv.example"
        os.environ["INVIDIOUS_INSTANCE"] = custom
        http = self.mock_http({custom + CAPTIONS_PATH: youtube_host.HostError(
            f"failed {custom}/api?token=toksecret123 Bearer bearersecret456"
        )})
        result, status, raw_status = self.run_host(asr_choice="off")
        self.assert_urls(http, [custom + CAPTIONS_PATH])
        self.assertEqual(result.get("exit_code"), 2)
        for secret in ("supersecretpw", "toksecret123", "bearersecret456"):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, raw_status)
        if status.get("mirror_host"):
            self.assertEqual(status["mirror_host"], "priv.example")

    def test_all_caption_failures_leave_plain_language_hint(self) -> None:
        http = self.mock_http({
            youtube_host.INSTANCE_LIST: youtube_host.HostError(TLS_ERROR),
            SEED + CAPTIONS_PATH: youtube_host.HostError("HTTP 502 for caption request"),
        })
        result, status, _ = self.run_host()
        self.assertEqual(result.get("exit_code"), 2)
        self.assertEqual(result.get("status"), "not_finished")
        self.assertIs(result.get("finished"), False)
        self.assertEqual(result.get("next_step"), "configure-asr-or-retry-captions")
        for hint in ("not finished", "INVIDIOUS_INSTANCE", "ASR_BACKEND=whisper",
                     "ASR_BACKEND=openai", "No note was written."):
            with self.subTest(hint=hint):
                self.assertIn(hint, status["reason"])
        self.attempt(status["attempts"], layer=None, ok=False, source="yt-dlp")
        for layer in ("public-list", "seed-fallback"):
            with self.subTest(layer=layer):
                self.attempt(status["attempts"], layer=layer, ok=False, source="caption-mirror")
        self.assert_urls(http, [youtube_host.INSTANCE_LIST, SEED + CAPTIONS_PATH])

    def test_asr_off_plan_preserves_x_host_compatibility(self) -> None:
        backend, reason = youtube_host.asr_plan("off")
        self.assertEqual(backend, "off")
        self.assertIn("ASR is not configured", reason)


if __name__ == "__main__":
    unittest.main()
