# Contributing

This repository is the portable gate and the skill. A production host that drains a queue on a schedule may live in another project. Change the rule here. Leave that host's cron, inbox, and `.env` where they are.

Platforms here are YouTube and Twitter/X video. Do not add Bilibili, Douyin, or Xiaohongshu to this repo.

`ASR_BACKEND` defaults to off. A video with no captions finishes as `not_finished`. Do not turn ASR on by default, and do not weaken `quality_gate.py` or `verify_note.py` so a fluent note can pass without a real quote.

## Check

Offline, from the repo root:

```bash
bash scripts/smoke.sh
```

That creates `.venv` when it is missing, installs `requirements.txt` (yt-dlp only), runs `scripts/test_gate.py`, settles a fixture, and regenerates fixture evidence.

`bash scripts/smoke.sh --live` also tries `https://www.youtube.com/watch?v=jNQXAC9IVRw` ("Me at the zoo"). ASR stays off on that run.

Whisper is optional and separate:

```bash
pip install -r requirements-asr.txt
```

## Evidence

`python3 scripts/run_evidence.py --skip-live` rewrites `evals/results/gate-evidence.json` and `gate-evidence.md` with repo-relative paths. It keeps the checked-in live sample. CI runs that command and fails if `evals/results` changes.

A path like `/workspace/...` or `/tmp/...` in those files is a bug. Record `scripts/...` and `evals/...`.

Three layers, and they stay separate. The fixture table is what CI scores. Directories under `evals/results/live/` are public-URL receipts. `evals/results/spotcheck.md` is an agent or human reading. CI does not score that file. Say so if you add another reading. A new mechanical check belongs in `scripts/test_gate.py` or `scripts/run_evidence.py`.

`python3 scripts/run_evidence.py` without `--skip-live` refetches `youtube_KwhgfwOSToQ` only. Leave the other live directories in place. Do not invent a private corpus, and do not commit a gibberish transcript you wrote yourself.

Finished notes from the hosts are Obsidian Markdown. Keep that shape if you change `render_note`. A stop still writes `status.json` and no `note.md`.

## Release

Versions are annotated tags on `main` after the change is merged. Notes live in `CHANGELOG.md`. From a checkout of the merged commit:

```bash
git tag -a v0.1.0 -m "v0.1.0 — portable YouTube and X transcript gate"
git push origin v0.1.0
gh release create v0.1.0 --title "v0.1.0" --notes-file CHANGELOG.md
```

Use the next number when `v0.1.0` already exists.
