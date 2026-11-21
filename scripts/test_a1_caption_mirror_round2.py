#!/usr/bin/env python3
"""Offline regression tests for caption mirror deadlines and invalid responses."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import youtube_host


VIDEO_ID = "AbCdEf12345"
SEED = "https://yt.chocolatemoo53.com"
LISTING_PATH = f"/api/v1/captions/{VIDEO_ID}"
TRACK_PATH = f"{LISTING_PATH}?label=English"
TRACKS = json.dumps({
    "captions": [{"label": "English", "languageCode": "en", "url": TRACK_PATH}],
}).encode("utf-8")
VTT = b"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nA sample caption.\n"
NESTED_JSON = b"[" * 10000


class SlowResponse:
    def __init__(self, advance):
        self.advance = advance
        self.chunks_read = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        if self.chunks_read == 4:
            return b""
        self.chunks_read += 1
        self.advance(3.0)
        return b"x" * 16

    read1 = read


class CaptionMirrorRound2Tests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        environment = patch.dict(os.environ, {"INVIDIOUS_INSTANCE": ""})
        clock = patch.object(youtube_host.time, "monotonic", side_effect=lambda: self.now)
        network = patch.object(
            youtube_host.urllib.request, "urlopen",
            side_effect=AssertionError("Unexpected network request"),
        )
        for mock in (environment, clock, network):
            mock.start()
            self.addCleanup(mock.stop)

    def advance(self, seconds):
        self.now += seconds

    def test_http_get_stops_slow_drip_at_deadline(self):
        response = SlowResponse(self.advance)
        with patch.object(youtube_host.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(youtube_host.HostError, r"(?i)budget|timed?\s*out|deadline"):
                youtube_host.http_get(f"{SEED}/test", limit=1024, timeout=7, accept="text/plain")
        self.assertGreater(self.now, 7)
        self.assertLess(response.chunks_read, 4)

    def test_mirror_rejects_track_returned_after_total_deadline(self):
        os.environ["INVIDIOUS_INSTANCE"] = SEED

        def get(url, **_):
            if url == SEED + LISTING_PATH:
                self.advance(26.0)
                return TRACKS
            self.assertEqual(url, SEED + TRACK_PATH)
            self.advance(6.0)
            return VTT

        with patch.object(youtube_host, "http_get", side_effect=get) as http_get:
            result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")

        self.assertEqual([call.args[0] for call in http_get.call_args_list],
                         [SEED + LISTING_PATH, SEED + TRACK_PATH])
        self.assertIsNone(result["text"])
        self.assertTrue(any(
            attempt["ok"] is False and "budget" in attempt["detail"].casefold()
            for attempt in result["mirror_attempts"]
        ), result)

    def assert_seed_fallback(self, discovery_payload):
        responses = {
            youtube_host.INSTANCE_LIST: discovery_payload,
            SEED + LISTING_PATH: TRACKS,
            SEED + TRACK_PATH: VTT,
        }

        def get(url, **_):
            self.assertIn(url, responses, f"Unexpected request to {url!r}")
            return responses[url]

        with patch.object(youtube_host, "http_get", side_effect=get) as http_get:
            result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")

        self.assertEqual([call.args[0] for call in http_get.call_args_list], list(responses))
        self.assertEqual(result["text"], VTT.decode("utf-8"))
        self.assertEqual(result["mirror_layer"], "seed-fallback")
        self.assertEqual(result["mirror_host"], "yt.chocolatemoo53.com")
        self.assertEqual(
            [(attempt["layer"], attempt["ok"]) for attempt in result["mirror_attempts"]],
            [("public-list", False), ("seed-fallback", True)],
        )

    def test_malformed_public_mirrors_trigger_seed_fallback(self):
        discovery = json.dumps([
            ["bad", {"api": True, "type": "https", "uri": "https://bad host"}],
            ["ctrl", {"api": True, "type": "https", "uri": "https://bad\nhost.example"}],
        ]).encode("utf-8")
        self.assert_seed_fallback(discovery)

    def test_malformed_explicit_mirror_fails_without_request(self):
        os.environ["INVIDIOUS_INSTANCE"] = "https://bad host"
        with patch.object(youtube_host, "http_get", return_value=TRACKS) as http_get:
            result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")

        http_get.assert_not_called()
        self.assertIsNone(result["text"])
        self.assertTrue(result["error"])

    def test_deeply_nested_public_list_triggers_seed_fallback(self):
        self.assert_seed_fallback(NESTED_JSON)

    def test_deeply_nested_mirror_listing_allows_next_mirror(self):
        first = "https://m1.example"
        second = "https://m2.example"
        os.environ["INVIDIOUS_INSTANCE"] = f"{first},{second}"
        responses = {
            first + LISTING_PATH: NESTED_JSON,
            second + LISTING_PATH: TRACKS,
            second + TRACK_PATH: VTT,
        }

        with patch.object(youtube_host, "http_get",
                          side_effect=lambda url, **_: responses[url]) as http_get:
            result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")

        self.assertEqual([call.args[0] for call in http_get.call_args_list], list(responses))
        self.assertEqual(result["text"], VTT.decode("utf-8"))
        self.assertEqual(result["mirror_host"], "m2.example")
        failed, succeeded = result["mirror_attempts"]
        self.assertIs(failed["ok"], False)
        self.assertIn("m1.example", failed["detail"])
        self.assertIs(succeeded["ok"], True)


if __name__ == "__main__":
    unittest.main()
