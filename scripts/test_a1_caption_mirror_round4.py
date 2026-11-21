#!/usr/bin/env python3
"""Offline regression tests for caption mirror HTTP framing and port parsing."""

import socket
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import youtube_host


@contextmanager
def loopback_response(response, *, slow_trailers=False):
    stop = threading.Event()

    def serve():
        with server.accept()[0] as connection, connection.makefile("rb") as request:
            connection.settimeout(0.5)
            for line in request:
                if line == b"\r\n":
                    break
            connection.sendall(response)
            if slow_trailers:
                cutoff = time.monotonic() + 0.8
                try:
                    for index in range(16):
                        remaining = max(0, cutoff - time.monotonic())
                        if stop.wait(min(0.05, remaining)):
                            return
                        if time.monotonic() >= cutoff:
                            break
                        connection.sendall(f"X-Trailer-{index}: v\r\n".encode("ascii"))
                    connection.sendall(b"\r\n")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    # A client enforcing its deadline can close during a send.
                    pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(0.5)
        with ThreadPoolExecutor(max_workers=1) as executor:
            worker = executor.submit(serve)
            try:
                yield server.getsockname()[1]
            finally:
                stop.set()
                worker.result()


class CaptionMirrorRound4Tests(unittest.TestCase):
    def setUp(self):
        opener = youtube_host.urllib.request.build_opener(
            youtube_host.urllib.request.ProxyHandler({})
        )
        use_opener = patch.object(youtube_host.urllib.request, "_opener", opener)
        use_opener.start()
        self.addCleanup(use_opener.stop)

    def test_real_chunked_trailers_stop_at_deadline(self):
        response = (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
            b"Connection: close\r\n\r\n1\r\na\r\n0\r\n"
        )
        with loopback_response(response, slow_trailers=True) as port:
            started = time.monotonic()
            with self.assertRaises(youtube_host.HostError):
                youtube_host.http_get(
                    f"http://127.0.0.1:{port}/chunked",
                    limit=4096, timeout=0.18, accept="text/plain",
                )
            self.assertLess(time.monotonic() - started, 0.55)

    def test_real_truncated_content_length_raises_host_error(self):
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/vtt\r\n"
            b"Content-Length: 400\r\nConnection: close\r\n\r\n"
            b"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nPartial line.\n"
        )
        with loopback_response(response) as port:
            with self.assertRaisesRegex(youtube_host.HostError, r"(?i)truncat|incomplete|content-length"):
                youtube_host.http_get(
                    f"http://127.0.0.1:{port}/truncated",
                    limit=4096, timeout=2.0, accept="text/vtt",
                )

    def test_zero_padded_port_and_malformed_ipv6(self):
        self.assertIsNone(youtube_host._valid_mirror_base("https://[::1]garbage", require_https=False))
        self.assertEqual(
            youtube_host._valid_mirror_base("https://mirror.example:00443", require_https=False),
            "mirror.example:443",
        )


if __name__ == "__main__":
    unittest.main()
