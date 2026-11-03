# Changelog

This repository is the portable gate and skill. A production host may live in another project. Versions here mark the skill and the scripts.

## 0.1.0 — 2026-11-03

First tagged release.

- YouTube and Twitter/X video only. Other platforms are not fetched.
- Captions first. `ASR_BACKEND` defaults to off. No captions and no ASR ends as `not_finished`, and no note is written from the title.
- A note is allowed only when it cites a transcript that passes the quality gate and quotes a real stretch of that file.
- `scripts/smoke.sh` is the offline check. `bash scripts/smoke.sh --live` adds one short captioned YouTube URL ("Me at the zoo", `jNQXAC9IVRw`). `requirements-asr.txt` is the optional second rung.
- Checked-in evidence uses repo-relative paths. CI regenerates it with `--skip-live` and fails if `evals/results` changes.
- A finished sample is committed at `evals/results/live/youtube_KwhgfwOSToQ/` so the artifact shape is visible without a network.
- Prompts in `evals/evals.json` are agent or human assertions. CI runs the gate tests and the offline evidence script, not those prompts.
