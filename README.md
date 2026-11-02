# transcript-first-video

Read a video from its spoken text. A title, description, tweet, or thumbnail is not a watch.

**字幕优先：** 官方字幕或通过质量门的 ASR 才算读过。没有可用文稿就说未完成。

## Why it exists

Agents often “watch” a YouTube, Bilibili, or X link by reading the title, description, or the tweet around it, then write a note that looks finished. The video itself was never transcribed.

Bad ASR makes a second, quieter mistake. Loops and gibberish still look like text, so an analyzer turns them into a confident essay and that essay is saved as knowledge. On expected Chinese speech, an English recognizer commonly emits Latin hallucination; the model then writes about the failure as if it were the talk.

Short clips get a false exemption. Empty ASR on a 20-second video, plus a line that says “video not transcribed,” is still unfinished. Duration does not close the task.

## Success and failure

Done means both:

1. A usable transcript exists: official captions, a cache hit for the same stable job id, or ASR that passed the quality gate.
2. The analysis is written from that text, and the note cites the transcript path.

No usable transcript means not finished. Say so. Do not deposit a final note. Leave a recoverable status (`needs-transcript`, `video-pending`, or a named quality-gate failure) and the next action (enqueue, retry once, or stop).

A metadata-only note is allowed only when the user accepts that degraded path and the note says so.

## Pipeline

```text
link
  → stable job id (platform + durable content id)
  → official captions?
       yes → transcript
       no  → cache for that job id?
            hit  → transcript
            miss → refresh media URL → audio → ASR
  → quality gate
       pass → analyze the transcript → write notes by channel
       fail → upgrade the model once into a separate file, then stop
  → no usable text → say not finished
```

Order is fixed: captions, then cache, then ASR, then an explicit “not finished.” Prefer one ASR job at a time (`--limit 1` or the host equivalent). Long work stays in a worker; chat stays free. A timer should kick that worker. It should not re-derive the transcript inside an LLM wake.

The job id is `youtube_<id>` or `bilibili_BV…`, never a signed CDN play URL. Signed audio URLs expire. Refresh media from the canonical source URL when the worker runs.

## Quality gate

Run the gate before the analyzer. Typical hard fails when the speech is expected Chinese:

- Too few CJK characters, or an absurd Latin ratio (language mismatch).
- Looping repeats, gibberish, or cross-language hallucination.
- Confidence below the floor. “Mostly Chinese characters” is not a pass.

On fail, do not save a final note. Retry once with a stronger model (for example small → medium) into a separate transcript file, then stop and say what failed. Do not keep upgrading. If the draft is mostly an essay about “ASR failed,” that is still a gate failure, not the video’s topic.

Policy detail is in [`SKILL.md`](SKILL.md). The Chinese Bilibili cases are in [`references/pitfalls.md`](references/pitfalls.md).

## Install

Clone this repository and place the folder where the agent loads skills, often `skills/transcript-first-video/` next to the host worker.

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git
```

[`SKILL.md`](SKILL.md) is the source of truth for the pipeline, the quality gate, secrets, and knowledge sinks. This README is the map.

## Contents

| Path | Role |
|------|------|
| [`SKILL.md`](SKILL.md) | Skill policy: pipeline, quality gate, secrets rules |
| [`references/pitfalls.md`](references/pitfalls.md) | Production mistakes (sanitized) |
| [`evals/evals.json`](evals/evals.json) | Starter prompts for with-skill vs without-skill evals |
| [`scripts/`](scripts/) | Placeholder for host-project worker CLIs |

## What this repo is

An Agent Skills package: policy, sanitized pitfalls, and starter evals. Enqueue and ASR workers live in the host project. If you later extract a standalone worker, put the entrypoints under [`scripts/`](scripts/) (see [`scripts/README.md`](scripts/README.md)).

This repository is not:

- A full desk clone (inbox schemas, personal vault paths, another machine’s `.env`).
- A systemd unit, cron file, or timer. The skill requires a worker; the host decides how it is scheduled.
- A place for secrets. Docs name environment variables only.

## Pitfalls

Six rules. The full list is [`references/pitfalls.md`](references/pitfalls.md).

- **Title is not a watch.** Title, description, tweet text, and thumbnails do not finish the task.
- **Short is not exempt.** Empty ASR on a short clip still needs a recoverable job.
- **A CDN URL is not a job id.** Identity is platform plus a durable content id. Refresh signed media at run time.
- **Jobs need a consumer.** `needs-transcript` rows without a scheduled worker sit until someone remembers to drain them.
- **Secrets are env names only.** Example: `BILIBILI_SESSDATA` (optional; never print the value). Do not commit cookie values or API keys, and do not write them into logs or receipts.
- **Keep sinks separate.** YouTube, X, WeChat, and official docs stay in their own channels. An unknown source fails closed or asks; it does not drop into a catch-all folder.

## Evals

[`evals/evals.json`](evals/evals.json) ships three starter cases (with-skill vs without-skill):

1. `youtube-with-captions-or-asr` — read a YouTube link from captions or ASR; otherwise say not finished.
2. `no-transcript-must-refuse-final-deposit` — empty short-video ASR must not become a final vault note.
3. `chinese-asr-hallucination-gate` — English loops on an expected-Chinese talk must not ship as a polished essay.

## 简体中文

先拿到可用文稿，再写笔记。顺序是官方字幕、同一稳定任务 id 的缓存、然后 ASR。质量门在分析之前：中文内容若出现英文循环、乱码或置信度过低，模型最多升级一次，结果写入单独文稿，然后停止。没有文稿就明确说未完成，短视频也不例外。本仓库只包含策略、坑和评测，不含 systemd、整套桌面配置或任何密钥。

## License

[MIT](LICENSE) — Copyright (c) 2026 HappyDrunk
