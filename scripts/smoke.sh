#!/usr/bin/env bash
# Offline check by default. Pass --live to also try one short captioned YouTube URL.
# ASR stays off. requirements-asr.txt is not installed here.
set -euo pipefail

cd "$(dirname "$0")/.."

LIVE=0
if [[ "${1:-}" == "--live" ]]; then
  LIVE=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: bash scripts/smoke.sh [--live]" >&2
  echo "  (no flag)  venv, pip install -r requirements.txt, gate tests, fixture settle" >&2
  echo "  --live     the same, then one captioned YouTube URL if the network works" >&2
  exit 2
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --disable-pip-version-check -r requirements.txt

python scripts/test_gate.py

python scripts/youtube_host.py \
  --settle-transcript evals/fixtures/usable_en_transcript.txt \
  --video-id smoke-usable \
  --expected-lang en \
  --out artifacts/smoke \
  --json >/dev/null

python scripts/run_evidence.py --skip-live

echo "offline smoke passed (ASR left off; yt-dlp only)"

if [[ "$LIVE" -eq 0 ]]; then
  echo "captioned URL not attempted. When the network is up: bash scripts/smoke.sh --live"
  exit 0
fi

echo "live: https://www.youtube.com/watch?v=jNQXAC9IVRw (Me at the zoo)"
python scripts/youtube_host.py \
  "https://www.youtube.com/watch?v=jNQXAC9IVRw" \
  --out artifacts/smoke-live \
  --json
