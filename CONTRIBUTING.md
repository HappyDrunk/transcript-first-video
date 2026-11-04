# Contributing

This repository is the portable gate and the skill. A production host that drains a queue on a schedule may live in another project. Change the rule here. Leave that host's cron, inbox, and `.env` where they are.

Platforms here are YouTube and Twitter/X video. Do not add Bilibili, Douyin, or Xiaohongshu to this repo.

`ASR_BACKEND` defaults to off. A video with no captions finishes as `not_finished`. Do not turn ASR on by default, and do not weaken `quality_gate.py` or `verify_note.py` so a fluent note can pass without a real quote. Do not weaken the knowledge check so a quote stub can pass. Do not claim the gate hears the audio. Do not add a CI job that scores LLM summaries.

## Check

Offline, from the repo root:

```bash
bash scripts/smoke.sh
```

That creates `.venv` when it is missing, installs `requirements.txt` (yt-dlp only), runs `scripts/test_gate.py` and `scripts/test_no_overfit.py`, settles a fixture, regenerates fixture evidence, and runs `scripts/verify_report.py`.

`bash scripts/smoke.sh --live` also tries `https://www.youtube.com/watch?v=jNQXAC9IVRw` ("Me at the zoo"). ASR stays off on that run.

Whisper is optional and separate:

```bash
pip install -r requirements-asr.txt
```

## Evidence

`python3 scripts/run_evidence.py --skip-live` rewrites `evals/results/gate-evidence.json` and `gate-evidence.md` with repo-relative paths. It keeps the checked-in live sample. CI runs that command and fails if `evals/results` changes. CI also runs `scripts/test_no_overfit.py` and `scripts/verify_report.py`. The verify report must stay at or above 95% intercept and at or below 10% false positives.

A path like `/workspace/...`, `/tmp/...`, or `C:\Users\...` in those files is a bug. Record `scripts/...` and `evals/...`. A Windows checkout prefix is stripped the same way as a POSIX prefix, and the recorded command uses `/`.

Three layers, and they stay separate. The fixture table is what CI scores: gate, citation, quotes inside the four knowledge sections, and a refusal of empty or boilerplate analysis. That table is not an audio check and not a model grade. Directories under `evals/results/live/` are public-URL receipts. The template notes that used to sit there were withdrawn. `evals/results/spotcheck.md` records that withdrawal and still reads the fixture refusals. CI does not score that file. Say so if you add another reading. A new mechanical check belongs in `scripts/test_gate.py`, `scripts/test_no_overfit.py`, or `scripts/run_evidence.py`.

`python3 scripts/run_evidence.py` without `--skip-live` refetches `youtube_KwhgfwOSToQ` only. Leave the other live directories in place. Do not invent a private corpus, and do not commit a gibberish transcript you wrote yourself.

Hosts write a timestamped `transcript.txt`, `segments.json`, `chunks/`, and `note.scaffold.md` on a passing transcript. They do not write a finished `note.md`. A section may be `本节不适用：<reason>` plus one quote. All four sections in that form are `no-extractable-content`: `verify_note.py --job` deletes `note.md`. Keep `verify_note.py` able to reject a quote stub. A stop still writes `status.json` and deletes any previous transcript, chunks, note, and scaffold. The agent flow is `SKILL.md`. `references/note-examples.md` stays a skeleton until the author fills it.

## Release

Versions are annotated tags on `main` after the change is merged. Notes live in `CHANGELOG.md`. From a checkout of the merged commit:

```bash
git tag -a v0.1.0 -m "v0.1.0 — portable YouTube and X transcript gate"
git push origin v0.1.0
gh release create v0.1.0 --title "v0.1.0" --notes-file CHANGELOG.md
```

Use the next number when `v0.1.0` already exists.
