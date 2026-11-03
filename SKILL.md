---
name: transcript-first-video
description: Read YouTube and Twitter/X videos into usable knowledge without pretending a title or a post counts as watched. Use when the user pastes a YouTube or X/Twitter video link, asks to 通读 / summarize / extract methods from one of those videos, or asks an agent to build or run a caption→ASR→quality-gate pipeline. Other platforms are not promised. Also use when a prior run left needs-transcript / video-pending / ASR-quality-failed tags, or when a note claims the video was understood but no usable transcript exists.
---

# Transcript-first video reading

## What this skill does

Turn a **YouTube** or **Twitter/X video** URL into usable text, then analyze that text.

Those two are the primary platforms. This skill does not promise Bilibili, Douyin, Xiaohongshu, or any other site, and it is not a multi-platform summarizer.

Success takes both bars. (A) A usable transcript: captions or ASR that passes the quality gate. (B) A note that analyzes that transcript into reusable knowledge. The finished note has four sections, 问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步, and each section quotes a real stretch of the transcript.

Failure that must be said out loud = no usable transcript. Do not deposit “finished” knowledge in that case. A path, a status, or a quote with no analysis is the same kind of failure: the note is not finished.

## What this skill does not do

- Fetch Bilibili, Douyin, Xiaohongshu, or other platforms. A link from those sites is not a promise.
- Treat title, description, post text, or thumbnails as a full watch.
- Burn visual multi-turn by default (vision only when the picture itself is the information and the user asks).
- Clone an entire host desk (systemd stack, foreign inbox schemas, personal vault paths).
- Put cookies or API keys into the skill, logs, receipts, or git.

## Quickstart success check

After one link:

1. A job exists with a **stable id** (platform + durable content id, e.g. `youtube_<id>` / `x_<status id>`).
2. Either captions were used, or ASR wrote a transcript file.
3. Quality gate passed (or status is clearly `failed` / retry with reason).
4. Any finished note is Obsidian Markdown. YAML frontmatter: `title`, `source_url`, `video_id`, `acquisition`, `gate_passed`, `transcript_path`, `quoted_window`. `title` is the job id. The platform title is not the note. The body has at least 问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步. Each section quotes a contiguous ~40-character window of the transcript and says what to reuse. A pasted path, a status, or a quote with no analysis is not finished. On a stop, leave `status.json` and do not write `note.md`.

If step 3–4 are missing, the task is not done.

Hard gate before a vault write. Exit 0 is allowed. Any other exit means do not deposit the note.

```bash
python3 scripts/verify_note.py --transcript <transcript.txt> --note <note.md>
```

YouTube, captions first (optional ASR only when configured; otherwise it says not finished). A finished run writes `note.md` for Obsidian:

```bash
python3 scripts/youtube_host.py "<youtube url>"
```

Twitter/X video, same gate and the same Markdown note. Captions if a track exists, otherwise optional ASR. Post text is not a transcript:

```bash
python3 scripts/x_host.py "<x or twitter status url>"
```

Commands and env var names: `scripts/README.md`.

## Pipeline (portable)

```text
link
  → normalize source + stable job id
  → captions / official subtitles?
       yes → transcript
       no  → refresh media URL → audio → ASR
  → quality gate
       pass → analyze from transcript → write notes by channel
       fail → upgrade model once (e.g. small→medium) OR fuse / fail clearly
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
- Model confidence floor not met  

Gate fail ⇒ do **not** save as final knowledge. Retry with a stronger model into a **separate** transcript file, or stop and say what failed.

The gate reads the transcript text. It does not play the audio. A fluent wrong caption can still pass. CI checks the gate, the citation, the quotes inside the four sections, and that the analysis is not an empty stub. CI does not grade whether that analysis is the best reading of the talk. That reading is `evals/results/spotcheck.md`, and CI does not score it.

Read `references/pitfalls.md` before treating a Chinese ASR default as production-ready.

## CJK ratio and English jargon

`--expected-lang zh` fails closed unless the transcript has at least 8 CJK characters and a CJK ratio of at least 0.35 among CJK plus Latin letters. The constants are `ZH_MIN_CJK` and `ZH_MIN_CJK_RATIO` in `scripts/quality_gate.py`. They are not command-line flags.

A Chinese talk dense with English technical terms (model names, API identifiers, product names) can fall under 0.35 and be refused even when the universal checks would pass. That false reject is intentional. The same ratio check is what stops an English hallucination loop from being filed as a Chinese talk. Holding a jargon-heavy talk back is the tradeoff; a wrong note is worse.

Tune by omitting `--expected-lang` when you know the talk mixes Chinese with English identifiers and you accept losing the script check. Loop, gibberish, length, and confidence checks still run. Do not omit it just to push a bad transcript through. There is no per-job flag to lower 0.35. The same idea applies to `--expected-lang en`, `ja`, or `ko`: pass it when you know the language, omit it when you do not.

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

Write notes only after a usable transcript (or an explicitly labeled degraded path).

The bundled hosts write one Obsidian-friendly Markdown file, `note.md`, in the job directory. Frontmatter: `title` (the job id, not the platform title), `source_url`, `video_id`, `acquisition`, `gate_passed`, `transcript_path`, `quoted_window`. Body sections, in order: 问题与做法, 完整怎么做, 翻车或别用, 今天立刻动手一步. Each section quotes the transcript and states a reusable claim: the problem and the move, the steps, where not to use them, and one action for today. A blockquote alone is not that claim. `status.json` is the machine stub. A stop writes that stub only. No `note.md`.

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

- `scripts/knowledge_note.py` — the finished-note shape, and the check that each section quotes the transcript and is not a stub.  
- `scripts/verify_note.py` — fail-closed check: allow a note only when it cites a transcript that passes the quality gate, quotes that transcript in each knowledge section, and the analysis is not empty boilerplate.  
- `scripts/youtube_host.py` — YouTube. Captions first, optional ASR, otherwise not finished. A pass writes the knowledge note. It does not write a note from the title.  
- `scripts/x_host.py` — Twitter/X video. Same gate and the same knowledge note. Captions if present, otherwise optional ASR. Post text is not a transcript.  
- `scripts/README.md` — how to run both hosts, the note shape, the CJK false-reject tradeoff, and the env var names.  
- `scripts/smoke.sh` — offline check: venv, yt-dlp, gate tests, fixture settle. `--live` adds one captioned YouTube URL. It does not turn ASR on.  
- `requirements-asr.txt` — optional whisper install. Not the default. `ASR_BACKEND` stays off until set.  
- `references/pitfalls.md` — production mistakes distilled from real failures (sanitized). Read when debugging “looks done but isn’t” or Chinese ASR issues.  
- `evals/evals.json` — prompts for an agent or a person. CI does not run these prompts. CI runs `scripts/test_gate.py` and `scripts/run_evidence.py --skip-live`.  
- `evals/results/gate-evidence.md` — layer ①, the fixture table CI checks.  
- `evals/results/live/` — layer ②, committed public-URL receipts (captioned YouTube, no-caption stop, captioned X).  
- `evals/results/spotcheck.md` — layer ③, an agent reading that the notes contain reusable knowledge and that the quotes are in the transcript. CI does not score it. It is not an audio check.  
- `evals/results/` — paths in the evidence files are repo-relative.

## Packaging note

This folder follows the Agent Skills shape (`SKILL.md` + optional `references/` / `scripts/` / `evals/`). `scripts/` is a YouTube host, an X video host, and a verifier, not a queue or a desk. It does not invent credentials.
