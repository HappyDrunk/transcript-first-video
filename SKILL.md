---
name: transcript-first-video
description: Read YouTube and Twitter/X videos into usable knowledge without pretending a title or a post counts as watched. Use when the user pastes a YouTube or X/Twitter video link, asks to 通读 / summarize / extract methods from one of those videos, or asks an agent to build or run a caption→ASR→quality-gate pipeline. Other platforms are not promised. Also use when a prior run left needs-transcript / video-pending / ASR-quality-failed tags, or when a note claims the video was understood but no usable transcript exists.
---

# Transcript-first video reading

## What this skill does

Turn a **YouTube** or **Twitter/X video** URL into a transcript, then write the knowledge note yourself. The scripts fetch, chunk, and check. They do not write the analysis.

Those two are the primary platforms. This skill does not promise Bilibili, Douyin, Xiaohongshu, or any other site, and it is not a multi-platform summarizer.

Success takes both bars. (A) A usable transcript: captions or ASR that passes the quality gate. (B) A `note.md` you wrote from that transcript. The note has four sections, 问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步. Each section quotes a real stretch of the transcript, or says `本节不适用：` with a reason and one quote.

Failure that must be said out loud = no usable transcript, or nothing in the transcript worth extracting. Do not deposit a finished note in either case.

## What this skill does not do

- Fetch Bilibili, Douyin, Xiaohongshu, or other platforms. A link from those sites is not a promise.
- Treat title, description, post text, or thumbnails as a full watch.
- Let a script synthesize the analysis. `note.scaffold.md` is a blank form.
- Burn visual multi-turn by default (vision only when the picture itself is the information and the user asks).
- Clone an entire host desk (systemd stack, foreign inbox schemas, personal vault paths).
- Put cookies or API keys into the skill, logs, receipts, or git.

## Run

```text
1. python3 scripts/youtube_host.py "<youtube url>"
   or python3 scripts/x_host.py "<x or twitter status url>"
   Job directory:
     transcript.txt     lines are [mm:ss] text, or [hh:mm:ss] text after one hour
     segments.json      [{start, end, text}] in seconds; null when the source had no clock
     chunks/NN.txt      about 8 minutes or about 6000 characters, timestamps kept
     status.json
     note.scaffold.md   frontmatter, four empty headings, fill instructions
2. If status is not transcript_ready
     Tell the user no usable transcript was acquired, and the reason. Stop.
     Do not write note.md.
3. Read every file in chunks/.
     If duration_seconds is 1800 or more, first write chunks/NN.notes.md
     (3–5 lines of points per chunk), then write the note from those points.
4. Write note.md from the scaffold. You write the analysis. The script does not.
5. If every section is 本节不适用
     python3 scripts/verify_note.py --job <dir>
     That sets status to no-extractable-content, deletes note.md, and leaves the transcript.
     Tell the user there was nothing to extract. Stop.
6. python3 scripts/verify_note.py --job <dir>
     If it refuses, edit note.md from the reasons. At most 2 repair rounds.
7. If round 2 still refuses
     Tell the user which reason failed. Do not deposit the note.
```

`transcript_ready` means the transcript passed the gate. `finished` stays false until you have a note that verify allows. `not_finished` and `quality_gate_failed` are stops. `no-extractable-content` is the all-N/A stop.

Commands and env var names: `scripts/README.md`.

## Sections

Keep these four, in this order:

1. 问题与做法
2. 完整怎么做
3. 翻车或别用
4. 今天立刻动手一步

Any section may be a single line `本节不适用：<one sentence reason>` plus one quote that shows the transcript really does not contain that part. Do not invent a step to fill a section.

If all four sections are `本节不适用`, that is not a note. Delete `note.md` by running `verify_note.py --job`. Do not deposit it.

## How to write

`verify_note.py` enforces R01–R15. The list is `references/rules.md`. A failure line looks like `R07 FAIL: ...`. Fix the note from that line. These are the same checks:

- After each claim, quote the transcript: `> [mm:ss] words copied verbatim`. Use `[hh:mm:ss]` when the stamp in the transcript has hours. The quote is 40–200 characters and is a contiguous stretch of that line's words.
- Prose is your own sentences. Do not only rephrase the quote.
- For a video longer than 5 minutes, take quotes from at least 3 different quartile stretches of the transcript.
- 今天立刻动手一步 starts with a verb, is at most 2 sentences, and matches a suggestion that is actually in the transcript.
- Do not write a number, a person's name, or a product name that is not in the transcript.
- A platform title, if you record one, goes only in frontmatter `platform_title`. It does not enter the body. The hosts do not copy the platform title into the scaffold.

`caption_kind` is `auto` or `manual` when the host knows. `caption_trust: low` means the captions were automatic and their language was not the expected language. Treat that transcript as less reliable: stay close to the words, and say so if a claim is thin.

## Pipeline (portable)

```text
link
  → normalize source + stable job id
  → captions / official subtitles?
       yes → timestamped transcript, segments.json, chunks/
       no  → refresh media URL → audio → ASR
  → quality gate
       pass → note.scaffold.md; the agent reads chunks and writes note.md
       fail → upgrade model once (e.g. small→medium) OR stop with a reason
  → verify_note.py --job, at most 2 repairs
  → all sections 本节不适用 → no-extractable-content, delete note.md
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

The gate reads the transcript text. It does not play the audio. A fluent wrong caption can still pass. CI checks the gate, the citation, the quotes inside the four sections, and that the analysis is not an empty stub. CI does not grade whether that analysis is the best reading of the talk. That reading is `evals/results/spotcheck.md`, and CI does not score it.

Read `references/pitfalls.md` before treating a Chinese ASR default as production-ready. `references/note-examples.md` is the shape of a good note and three bad ones. The bodies are placeholders until the author fills them. Do not invent a video to fill them.

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

Write `note.md` only after a usable transcript, and only by reading the chunks. The host writes `note.scaffold.md`: frontmatter (`title` is the job id, not the platform title), empty headings, and fill instructions. `caption_kind` and, when set, `caption_trust` are in that frontmatter and in `status.json`.

`verify_note.py` still refuses a quote stub and refuses a note whose four sections are all `本节不适用`. A stop before `transcript_ready` writes `status.json` only.

Feishu is not required. This skill does not call Feishu and does not read a Feishu token. A Feishu wiki, a Notion database, or another sink can live in the user's own project and consume this Markdown. A folder of `.md` files is a complete sink.

Keep sinks channel-separated when the user maintains partitions (e.g. YouTube vs X vs WeChat vs official docs). Do not dump every medium into one catch-all folder.

This skill does not hardcode personal wiki tokens. Pass parent / sink config from the host project.

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

- `scripts/knowledge_note.py` — the finished-note shape check, `本节不适用` handling, and `render_scaffold`. It does not write the analysis.
- `scripts/verify_note.py` — R01–R15. `--job <dir>` reads the host directory. All-N/A sets `no-extractable-content` and deletes `note.md`.
- `references/rules.md` — what each rule refuses.
- `scripts/youtube_host.py` — YouTube. Captions first, optional ASR, otherwise not finished. A pass writes the timestamped transcript, `segments.json`, `chunks/`, and `note.scaffold.md`.
- `scripts/x_host.py` — Twitter/X video. Same gate and the same deposit. Captions if present, otherwise optional ASR. Post text is not a transcript.
- `scripts/README.md` — how to run both hosts, the note shape, the CJK false-reject tradeoff, and the env var names.
- `scripts/smoke.sh` — offline check: venv, yt-dlp, gate tests, fixture settle. `--live` adds one captioned YouTube URL. It does not turn ASR on.
- `requirements-asr.txt` — optional whisper install. Not the default. `ASR_BACKEND` stays off until set.
- `references/pitfalls.md` — production mistakes distilled from real failures (sanitized). Read when debugging “looks done but isn’t” or Chinese ASR issues.
- `references/note-examples.md` — skeletons for two good notes and three bad notes. The author fills the bodies. Do not invent a video for them.
- `evals/evals.json` — prompts for an agent or a person. CI does not run these prompts. CI runs `scripts/test_gate.py`, `scripts/test_no_overfit.py`, `scripts/run_evidence.py --skip-live`, and `scripts/verify_report.py`.
- `evals/results/gate-evidence.md` — layer ①, the fixture table CI checks.
- `evals/results/live/` — layer ②, committed public-URL receipts (captioned YouTube, no-caption stop, captioned X). The template notes were withdrawn.
- `evals/results/spotcheck.md` — layer ③. It records that withdrawal and still reads the fixture refusals. CI does not score it. It is not an audio check.
- `evals/results/` — paths in the evidence files are repo-relative.

## Packaging note

This folder follows the Agent Skills shape (`SKILL.md` + optional `references/` / `scripts/` / `evals/`). `scripts/` is a YouTube host, an X video host, and a verifier, not a queue or a desk. It does not invent credentials.
