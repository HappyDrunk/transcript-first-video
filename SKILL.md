---
name: transcript-first-video
description: Read YouTube and Twitter/X videos into usable knowledge without pretending a title or a post counts as watched. Use when the user pastes a YouTube or X/Twitter video link, asks to 通读 / summarize / extract methods from one of those videos, or asks an agent to build or run a caption→ASR→quality-gate pipeline. Other platforms are not promised. Also use when a prior run left needs-transcript / video-pending / ASR-quality-failed tags, or when a note claims the video was understood but no usable transcript exists.
---

# Transcript-first video reading

## What this skill does

Turn a **YouTube** or **Twitter/X video** URL into a transcript, then write the knowledge note yourself. The scripts fetch, chunk, and check. They do not write the analysis.

Those two are the primary platforms. This skill does not promise Bilibili, Douyin, Xiaohongshu, or any other site, and it is not a multi-platform summarizer.


A deliverable needs a usable transcript with reliable timestamps and one evidence note (`note.md`). Read the full transcript and write `selection.md` before drafting. The renderer runs both checks before generating the reading copy in its channel folder. If the transcript is missing, unusable, untimed, or has nothing worth extracting, report the reason and keep the inputs.

## Language preference

Ask once, on install or the first run with no saved choice. This is the first user-facing step. It comes before fetch, before note writing, and before any other preference. The choices are `中文`, `英文`, and `中英文对照`.

Persist the answer in `language.txt` beside this `SKILL.md` in the installed skill folder, when that folder is writable. One line, exactly one of those three. Do not commit the file. If you cannot write there, keep the same line in the host project and read it before the next delivery. If nothing is saved, or the saved line is not one of the three, ask. Do not assume `中英文对照`. Do not fetch, and do not deliver, until the user has chosen.


- `中文` — Write beginner-clear Chinese prose. Keep proper names where the evidence supports them.
- `英文` — Write English prose.
- `中英文对照` — Present the explanation in both languages in the same note.

In every mode, the evidence note preserves Obsidian properties and the original-language evidence under `## 原文依据`. Explain what a method does, how it works, and when to use it in plain words.

## What this skill does not do

- Fetch Bilibili, Douyin, Xiaohongshu, or other platforms. A link from those sites is not a promise.
- Treat title, description, post text, or thumbnails as a full watch.
- Let a script synthesize the analysis. `note.scaffold.md` is a blank form.
- Burn visual multi-turn by default (vision only when the picture itself is the information and the user asks).
- Clone an entire host desk (systemd stack, foreign inbox schemas, personal vault paths).
- Put cookies or API keys into the skill, logs, receipts, or git.
- Ship a thin claim-passing stub as the final 通读 when method-bearing arcs are still uncovered.


## Run

1. Confirm `language.txt`. Run `python3 scripts/youtube_host.py "<YouTube URL>"` or `python3 scripts/x_host.py "<X status URL>"`. Optional YouTube screen text uses [the same mode throughout the job](README.md#optional-youtube-screen-text).
2. When the transcript is ready, read it in full. If it has no reliable clock, keep it and report「缺时间戳，请用带时间戳的转写重跑」.
3. Write `selection.md` in transcript order, one line per unit, with time range, category, 留 or 略, and a one-sentence reason. Cover the full transcript with adjacent ranges. Keep the main claims, steps and their order, the speaker's lists, supporting numbers, named cases, and essential technical elements. Mark greetings, ads, repetition, and off-topic conversation 略.
4. Write `note.md` from the retained units. Follow [references/delivery-format.md](references/delivery-format.md) for the Obsidian properties, fixed headings, middle sections by video type, and marked explanations. Start with `## 先记住一句话`. Complete the retained lists and cases, and explain essential terms at first use. Write one grounded action for the reader in at most two sentences.
5. Link each middle claim and the action with `⏱ mm:ss`. Write `本文略去` and finish with `## 原文依据`. Copy speech quotes of at least 40 contiguous characters with their timestamps and original spelling. For `screen.txt`, follow the [screen evidence format](references/delivery-format.md#画面引文). Keep steps, conditions, and claims within the cited evidence. Mark terms, analogies, and caption corrections.
6. Run `python3 scripts/render_reading_note.py --task-dir "<dir>" --output "<channel folder>/〈发布日期〉 〈频道〉 - 〈标题〉.md"`. It runs verify on the note and evidence, then coverage (S01 on every job and C02 on long jobs). It writes the reading copy after both checks pass on the same inputs and set `finished: true`. Resolve FAIL lines within the shared repair limit and rerun the command after edits.
7. Deliver the generated reading copy from the channel folder. Keep `note.md`, `selection.md`, the transcript, and the status in the job directory.

The status is 未交 on a gate failure or lock. A historical all-`本节不适用` draft is archived by verify as `no-extractable-content`. Leave the transcript available for later work. See [references/rules.md](references/rules.md) for the rules and [scripts/README.md](scripts/README.md) for the commands. Read the linked evidence against the transcript to check meaning, especially conditions, ordering, and whether the selected units cover the methods a reader needs.

## Pipeline (portable)

```text
link
  → normalize source + stable job id
  → captions / official subtitles?
       yes → timestamped transcript, segments.json, chunks/
       no  → refresh media URL → audio → ASR
  → quality gate
       pass → note.scaffold.md; the agent reads the transcript and writes selection.md, then note.md
       fail → upgrade model once (e.g. small→medium) OR stop with a reason
  → render_reading_note.py --task-dir --output
       verify, then coverage → reading copy when finished
  → verify and coverage share at most 2 repair rounds
  → historical all-N/A → no-extractable-content, archive note.md
  → no usable text → say not finished; do not pretend
```

Prefer `--limit 1` (or equivalent) concurrency for ASR. Long work is background; chat stays free. Scheduling (cron / timer / routine) should **kick the worker**, not re-derive transcripts inside an LLM wake.

## Content acquisition order

1. Platform / official captions
2. Existing transcript cache for the same stable job id
3. Local or async ASR with quality gate (+ one model upgrade)
4. Explicit “not finished” (metadata-only only if the user accepts a degraded path **and** the note labels that boundary)

## Quality gate (why it exists)

Bad ASR still looks like “text”. Models will happily structure garbage into a confident wrong note.

Gate before analysis. Typical hard fails for expected Chinese speech:

- Too few CJK characters / absurd Latin ratio
- Looping repeats, gibberish, or cross-language hallucination

Gate fail ⇒ do **not** save as final knowledge. Retry with a stronger model into a **separate** transcript file, or stop and say what failed.

The gate reads the transcript text. It does not play the audio. A fluent wrong caption can still pass. CI checks transcript quality, the single-note structure, evidence links, and coverage. CI does not grade whether that analysis is the best reading of the talk. That reading is `evals/results/spotcheck.md`, and CI does not score it.

Read `references/pitfalls.md` before treating a Chinese ASR default as production-ready. `references/delivery-format.md` has templates and four synthetic examples.

## CJK ratio and English jargon

`--expected-lang zh` fails closed unless the transcript has at least 8 CJK characters and a CJK ratio of at least 0.35 among CJK plus Latin letters. The constants are `ZH_MIN_CJK` and `ZH_MIN_CJK_RATIO` in `scripts/quality_gate.py`. They are not command-line flags.

A Chinese talk dense with English technical terms (model names, API identifiers, product names) can fall under 0.35 and be refused even when the universal checks would pass. That false reject is intentional. The same ratio check is what stops an English hallucination loop from being filed as a Chinese talk. Holding a jargon-heavy talk back is the tradeoff; a wrong note is worse.

Tune by omitting `--expected-lang` when you know the talk mixes Chinese with English identifiers and you accept losing the script check. Loop, gibberish, and length checks still run. A confidence number is checked only when the caller passes one. The whisper CLI path does not supply a score, so there is no confidence floor on that path. Do not omit `--expected-lang` just to push a bad transcript through. There is no per-job flag to lower 0.35. The same idea applies to `--expected-lang en`, `ja`, or `ko`: pass it when you know the language, omit it when you do not.

## Stable identity and media URLs

- Job id must come from a durable content id (YouTube video id or X status id), never from a signed CDN playurl.
- Signed audio URLs expire. At worker time, **refresh** from the source URL; do not replay the URL saved at enqueue.
- Short vs long video does not change the rule: no transcript ⇒ not finished. Inline ASR failure must enqueue a recoverable job, not a warning-only deposit.

## Secrets

Environment variable **names** only in docs, for example:

- `YTDLP_COOKIES` (optional path to a cookies file for YouTube or X; never commit the file)
- `YTDLP_EXTRACTOR_ARGS` (optional yt-dlp extractor args)
- `INVIDIOUS_INSTANCE` (optional YouTube caption mirror, or `off`)
- `FX_TWITTER_API` (public X status API origin, default `https://api.fxtwitter.com`, or `off`; no key)
- `ASR_BACKEND`, `OPENAI_API_KEY`, `WHISPER_MODEL`, `WHISPER_UPGRADE_MODEL`, `WHISPER_LANGUAGE` (optional ASR)
- `OPENAI_TRANSCRIBE_MODEL`, `OPENAI_BASE_URL` (optional OpenAI ASR)

Missing or expired cookies ⇒ say so in the status. Keep the public fetch path. The bundled hosts do not read a Bilibili session cookie.


## Knowledge sinks

A channel folder of Markdown files is a complete sink. Keep the checked note's properties, prose, and evidence together. Optional host integration notes are in [references/host-delivery.md](references/host-delivery.md).

## Extending (slots)

| Slot | Responsibility |
|------|----------------|
| Fetchers | `url → {captions? , source_url, stable_id}` |
| ASR backends | audio → transcript + confidence signals |
| Quality gate | pass / upgrade / fuse |
| Sinks | transcript → note / table / inbox fields |
| Triggers | chat enqueue, cron drain, CI kick |

Bundled fetchers are YouTube (`youtube_host.py`) and Twitter/X video (`x_host.py`). They share the gate. Other platforms are a host-project choice, not a promise of this repo. Do not fork the pipeline to add one.

## Bundled resources


- `scripts/knowledge_note.py` — blank scaffold and historical all-N/A handling.
- `scripts/verify_note.py` — transcript quality, structure, evidence, and action checks.
- `scripts/coverage_check.py` — S01 selection and C02 quartiles. Run after verify.
- `scripts/render_reading_note.py` — run both checks and generate the reading copy.
- `references/rules.md` — the 12 required checks and two warnings.
- `references/delivery-format.md` — the single-note format, selection rules, and examples.

- `scripts/youtube_host.py` — YouTube. Captions first, optional ASR, otherwise not finished. A pass writes the timestamped transcript, `segments.json`, `chunks/`, and `note.scaffold.md`.
- `scripts/x_host.py` — Twitter/X video. Same gate and the same deposit. Captions if present, otherwise optional ASR. Post text is not a transcript.
- `scripts/README.md` — how to run both hosts, the note shape, the CJK false-reject tradeoff, and the env var names.
- `scripts/smoke.sh` — offline check: venv, yt-dlp, gate tests, fixture settle. `--live` adds one captioned YouTube URL. It does not turn ASR on.
- `requirements-asr.txt` — optional whisper install. Not the default. `ASR_BACKEND` stays off until set.
- `references/pitfalls.md` — production mistakes distilled from real failures (sanitized). Read when debugging “looks done but isn’t” or Chinese ASR issues.
- `references/host-delivery.md` — optional host notes for a sink outside this repo. The skill does not call that sink.
- `evals/evals.json` — prompts for an agent or a person. CI does not run these prompts. CI runs `scripts/test_gate.py`, `scripts/test_no_overfit.py`, `scripts/test_claim_ground_check.py` (counts API on synthetic notes, not a note judge), `scripts/test_coverage_check.py` (synthetic jobs for gate C, not a 9/10 grader), `scripts/run_evidence.py --skip-live`, and `scripts/verify_report.py`. `scripts/claim_ground_check.py` is not a CI gate. Coverage C is deterministic and is on that CI path. Spotcheck stays human.
- `evals/results/gate-evidence.md` — layer ①, the fixture table CI checks.
- `evals/results/live/` — layer ②, committed public-URL receipts (captioned YouTube, no-caption stop, captioned X). The template notes were withdrawn.
- `evals/results/spotcheck.md` — layer ③. It records that withdrawal and still reads the fixture refusals. CI does not score it. It is not an audio check.
- `evals/results/hall_j_retest_receipt.md` — receipt for the in-distribution 1.0.0 Hall J run. Not a held-out 9. CI does not score it. Do not copy it into a note.
- `evals/results/held_out_mechanical_receipt.md` — mechanical verify and Coverage C on 10 videos (10/10 and 10/10). Draft gold was not user-signed. `held_out_nine_claimed` is false. A signed-gold held-out is still required before any 9 claim. CI does not score this file.
- `evals/results/` — paths in the evidence files are repo-relative.

## Packaging note

This folder follows the Agent Skills shape (`SKILL.md` + optional `references/` / `scripts/` / `evals/`). `scripts/` is a YouTube host, an X video host, and a verifier, not a queue or a desk. It does not invent credentials.
