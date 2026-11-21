#!/usr/bin/env python3
"""Offline regression tests for caption mirror transport and URL validation."""

import json
import os
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import ParseResult

sys.path.insert(0, str(Path(__file__).resolve().parent))
import youtube_host


VIDEO_ID = "AbCdEf12345"
PASSWORD = "topsecretpw999"
AUTH_BASE = f"https://alice:{PASSWORD}@mirror.example"
BAD_IPV6 = "https://[::1]garbage"
PUBLIC_AUTH_BASE = "https://u:p@mirror.example"
SEED = "https://yt.chocolatemoo53.com"
LISTING_PATH = f"/api/v1/captions/{VIDEO_ID}"
TRACK_PATH = f"{LISTING_PATH}?label=English"
VTT = b"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nA sample caption.\n"


def serve_slow_body(server, stop):
    try:
        with server.accept()[0] as connection, connection.makefile("rb") as request:
            connection.settimeout(0.5)
            if not request.readline():
                return
            for line in request:
                if line == b"\r\n":
                    break
            connection.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                b"Content-Length: 400\r\nConnection: close\r\n\r\n"
            )
            # Keep the red run fast even when the client waits for the entire body.
            cutoff = time.monotonic() + 0.75
            for _ in range(40):
                if stop.wait(min(0.06, max(0, cutoff - time.monotonic()))):
                    break
                if time.monotonic() >= cutoff:
                    break
                connection.sendall(b"x" * 10)
    except OSError:
        pass


class CaptionMirrorRound3Tests(unittest.TestCase):
    def setUp(self):
        # Keep real urlopen calls independent of system proxy configuration.
        opener = youtube_host.urllib.request.build_opener(
            youtube_host.urllib.request.ProxyHandler({})
        )
        use_opener = patch.object(youtube_host.urllib.request, "_opener", opener)
        use_opener.start()
        self.addCleanup(use_opener.stop)

    def test_real_http_response_stops_slow_drip_at_deadline(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        stop = threading.Event()
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            server.settimeout(0.5)
            port = server.getsockname()[1]
            worker = threading.Thread(target=serve_slow_body, args=(server, stop), daemon=True)
            worker.start()
            try:
                started = time.monotonic()
                with self.assertRaisesRegex(youtube_host.HostError, r"deadline|timed? out"):
                    youtube_host.http_get(
                        f"http://127.0.0.1:{port}/slow",
                        limit=4096, timeout=0.2, accept="text/plain",
                    )
                self.assertLess(time.monotonic() - started, 0.7)
            finally:
                stop.set()
                worker.join(timeout=0.5)
        finally:
            server.close()

    def test_http_get_wraps_invalid_url_without_exposing_password(self):
        with patch.object(socket, "create_connection",
                          side_effect=AssertionError("Unexpected network connection")):
            with self.assertRaises(youtube_host.HostError) as raised:
                youtube_host.http_get(
                    AUTH_BASE + LISTING_PATH, limit=1024, timeout=7, accept="application/json",
                )
        self.assertFalse(PASSWORD in str(raised.exception), "HostError exposed the password")

    def test_explicit_mirror_failure_does_not_expose_password(self):
        with (
            patch.dict(os.environ, {"INVIDIOUS_INSTANCE": AUTH_BASE}),
            patch.object(socket, "create_connection",
                         side_effect=AssertionError("Unexpected network connection")),
        ):
            result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")

        self.assertIsNone(result["text"])
        self.assertTrue(result["error"])
        self.assertFalse(PASSWORD in json.dumps(result), "Mirror result exposed the password")

    def test_invalid_mirror_bases_are_rejected(self):
        for base in (BAD_IPV6, PUBLIC_AUTH_BASE):
            with self.subTest(base=base):
                self.assertIsNone(youtube_host._valid_mirror_base(base, require_https=True))

        permissive_result = ParseResult("https", "[::1]garbage", "", "", "", "")
        with self.subTest(parser="permissive IPv6"), patch.object(
            youtube_host.urllib.parse, "urlparse", return_value=permissive_result,
        ):
            self.assertIsNone(youtube_host._valid_mirror_base(BAD_IPV6, require_https=True))

    def test_invalid_discovery_entries_trigger_seed_fallback(self):
        discovery = [
            ["bad6", {"api": True, "type": "https", "uri": BAD_IPV6}],
            ["auth", {"api": True, "type": "https", "uri": PUBLIC_AUTH_BASE}],
        ]
        tracks = {"captions": [{"label": "English", "languageCode": "en", "url": TRACK_PATH}]}
        responses = {
            youtube_host.INSTANCE_LIST: json.dumps(discovery).encode("utf-8"),
            SEED + LISTING_PATH: json.dumps(tracks).encode("utf-8"),
            SEED + TRACK_PATH: VTT,
        }

        def get(url, **_):
            self.assertIn(url, responses, f"Unexpected mirror request to {url!r}")
            return responses[url]

        with (
            patch.dict(os.environ, {"INVIDIOUS_INSTANCE": ""}),
            patch.object(youtube_host, "http_get", side_effect=get) as http_get,
        ):
            result = youtube_host.fetch_mirror_captions(VIDEO_ID, "en")

        self.assertEqual([call.args[0] for call in http_get.call_args_list], list(responses))
        self.assertEqual(result["text"], VTT.decode("utf-8"))
        self.assertEqual(result["mirror_host"], "yt.chocolatemoo53.com")
        self.assertEqual(result["mirror_layer"], "seed-fallback")
        self.assertEqual(
            [(attempt["layer"], attempt["ok"]) for attempt in result["mirror_attempts"]],
            [("public-list", False), ("seed-fallback", True)],
        )


if __name__ == "__main__":
    unittest.main()
