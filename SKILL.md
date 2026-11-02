---
name: transcript-first-video
description: Read videos into usable knowledge without pretending a title counts as watched. Use whenever the user pastes a YouTube / Bilibili / X / short-video link, asks to 通读 / summarize / extract methods from a video, or asks an agent to build or run a caption→ASR→quality-gate pipeline. Also use when a prior run left needs-transcript / video-pending / ASR-quality-failed tags, or when a note claims the video was understood but no usable transcript exists.
---

# Transcript-first video reading

## What this skill does

Turn a video URL into **usable text**, then analyze that text.

Success = a usable transcript (captions or ASR that passes a quality gate) **and** analysis based on that text.

Failure that must be said out loud = no usable transcript. Do not deposit “finished” knowledge in that case.

## What this skill does not do

- Treat title, description, UP metadata, tweet text, or thumbnails as a full watch.
- Burn visual multi-turn by default (vision only when the picture itself is the information and the user asks).
- Clone an entire host desk (systemd stack, foreign inbox schemas, personal vault paths).
- Put cookies, SESSDATA, or API keys into the skill, logs, receipts, or git.

## Quickstart success check

After one link:

1. A job exists with a **stable id** (platform + durable content id, e.g. `youtube_<id>` / `bilibili_BV…`).
2. Either captions were used, or ASR wrote a transcript file.
3. Quality gate passed (or status is clearly `failed` / retry with reason).
4. Any note / knowledge write cites the transcript path (or explicitly says “not finished”).

If step 3–4 are missing, the task is not done.

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

Read `references/pitfalls.md` before shipping a production default for Bilibili Chinese ASR.

## Stable identity and media URLs

- Job id must come from a durable content id (video id / BV), never from a signed CDN playurl.  
- Signed audio URLs expire. At worker time, **refresh** from the source URL; do not replay the URL saved at enqueue.  
- Short vs long video does not change the rule: no transcript ⇒ not finished. Inline ASR failure must enqueue a recoverable job, not a warning-only deposit.

## Secrets

Environment variable **names** only in docs, for example:

- `BILIBILI_SESSDATA` (optional; improves some fetches; never print the value)  
- ASR / LLM keys as your runtime defines them  

Missing or expired cookies ⇒ say so in the status / action hint. Do not abandon public API paths solely because SESSDATA is absent.

## Knowledge sinks

Write notes only after a usable transcript (or an explicitly labeled degraded path).

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

Add platforms by implementing a fetcher; do not fork the whole pipeline.

## Bundled resources

- `references/pitfalls.md` — production mistakes distilled from real failures (sanitized). Read when debugging “looks done but isn’t” or Chinese ASR issues.  
- `evals/evals.json` — starter prompts for Anthropic-style skill evals (with-skill vs without).

## Packaging note

This folder follows the Agent Skills shape (`SKILL.md` + optional `references/` / `scripts/` / `evals/`). It is meant to be installed beside a runnable worker in the host project, not as a magic one-file drop-in that invents credentials.
