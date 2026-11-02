# transcript-first-video

对照阅读：每一节先写中文，紧接着写英文。流程图只出现一次。

Read in parallel: each section is Chinese first, then English. The pipeline diagram appears once.

从口播文本读视频。标题、简介、推文或封面都不算看过。

Read a video from its spoken text. A title, a description, a tweet, or a thumbnail is not a watch.

官方字幕，或通过质量门的 ASR，才算读过。没有可用文稿，就说未完成。

Official captions, or ASR that passes the quality gate, are what count as having read the video. If there is no usable transcript, say the task is not finished.

## 为什么存在 / Why it exists

代理经常“看”一条 YouTube、Bilibili 或 X 链接，其实只读了标题、简介，或链接周围的推文，然后写出一篇看起来已经完成的笔记。视频本身从未被转写。

Agents often “watch” a YouTube, Bilibili, or X link by reading the title, the description, or the tweet around it, then write a note that looks finished. The video itself was never transcribed.

糟糕的 ASR 会犯第二种、更安静的错。循环和胡话看起来仍像文本，于是分析器把它们写成一篇自信的文章，而这篇文章被存成知识。面对预期为中文的口播，英语识别器常常吐出拉丁字母幻觉；模型接着把这次失败本身写成讲稿内容。

Bad ASR makes a second, quieter mistake. Loops and gibberish still look like text, so an analyzer turns them into a confident essay and that essay is saved as knowledge. On expected Chinese speech, an English recognizer commonly emits Latin hallucination; the model then writes about the failure as if it were the talk.

短视频会得到一种虚假豁免。一段 20 秒视频上的空 ASR，再加一行“视频未转写”，仍然是未完成。时长不能把任务关掉。

Short clips get a false exemption. Empty ASR on a 20-second video, plus a line that says “video not transcribed,” is still unfinished. Duration does not close the task.

## 成功与失败 / Success and failure

完成必须同时满足下面两件事。

Done means both:

1. **可用文稿存在：** 官方字幕、同一稳定任务 id 的缓存命中，或通过质量门的 ASR。
   **A usable transcript exists:** official captions, a cache hit for the same stable job id, or ASR that passed the quality gate.
2. **分析写自这段文本，** 并且笔记引用文稿路径。
   **The analysis is written from that text,** and the note cites the transcript path.

没有可用文稿，就是未完成。要说出来。不要落一份最终笔记。留下可恢复的状态（`needs-transcript`、`video-pending`，或具名的质量门失败），以及下一步（入队、重试一次，或停止）。

No usable transcript means not finished. Say so. Do not deposit a final note. Leave a recoverable status (`needs-transcript`, `video-pending`, or a named quality-gate failure) and the next action (enqueue, retry once, or stop).

只有用户接受这条降级路径，并且笔记自己写明这一点时，才允许只基于元数据的笔记。

A metadata-only note is allowed only when the user accepts that degraded path and the note says so.

## 流程 / Pipeline

文稿获取顺序固定：官方字幕，然后同一任务的缓存，然后 ASR，然后明确说未完成。图中标识保持语言中立。

Acquisition order is fixed: official captions, then the cache for that job, then ASR, then an explicit “not finished.” Identifiers in the diagram stay language-neutral.

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

一次只跑一个 ASR 任务（`--limit 1` 或宿主等价物）。长活留在 worker 里；对话保持空闲。定时器应该去叫醒那个 worker，而不是在一次 LLM 唤醒里重新推导文稿。

Prefer one ASR job at a time (`--limit 1` or the host equivalent). Long work stays in a worker; chat stays free. A timer should kick that worker. It should not re-derive the transcript inside an LLM wake.

任务 id 是 `youtube_<id>` 或 `bilibili_BV…`，绝不是带签名的 CDN 播放地址。签名音频 URL 会过期。worker 运行时，从规范源 URL 刷新媒体。

The job id is `youtube_<id>` or `bilibili_BV…`, never a signed CDN play URL. Signed audio URLs expire. Refresh media from the canonical source URL when the worker runs.

## 质量门 / Quality gate

在分析器之前跑质量门。当口播预期为中文时，典型硬失败是：

Run the gate before the analyzer. Typical hard fails when the speech is expected Chinese:

- 汉字太少，或拉丁字母比例荒谬（语言不匹配）。
  Too few CJK characters, or an absurd Latin ratio (language mismatch).
- 循环重复、胡话，或跨语言幻觉。
  Looping repeats, gibberish, or cross-language hallucination.
- 置信度低于下限。“大部分是汉字”不算通过。
  Confidence below the floor. “Mostly Chinese characters” is not a pass.

失败时不要保存最终笔记。用更强的模型重试一次（例如 small → medium），结果写入单独的文稿文件，然后停止，并说明失败了什么。不要一直升级。如果草稿主要是一篇关于“ASR 失败”的文章，这仍然是质量门失败，不是视频的主题。

On fail, do not save a final note. Retry once with a stronger model (for example small → medium) into a separate transcript file, then stop and say what failed. Do not keep upgrading. If the draft is mostly an essay about “ASR failed,” that is still a gate failure, not the video’s topic.

策略细节在 [`SKILL.md`](SKILL.md)。中文 Bilibili 案例在 [`references/pitfalls.md`](references/pitfalls.md)。

Policy detail is in [`SKILL.md`](SKILL.md). The Chinese Bilibili cases are in [`references/pitfalls.md`](references/pitfalls.md).

## 安装 / Install

克隆本仓库，把文件夹放到代理加载技能的位置。常见做法是放在宿主 worker 旁边的 `skills/transcript-first-video/`。

Clone this repository and place the folder where the agent loads skills, often `skills/transcript-first-video/` next to the host worker.

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git
```

[`SKILL.md`](SKILL.md) 是流程、质量门、密钥规则和知识落点的依据。本 README 是地图。

[`SKILL.md`](SKILL.md) is the source of truth for the pipeline, the quality gate, secrets, and knowledge sinks. This README is the map.

## 目录 / Contents

| 路径 / Path | 作用 / Role |
| --- | --- |
| [`SKILL.md`](SKILL.md) | 技能策略：流程、质量门、密钥规则。<br>Skill policy: pipeline, quality gate, secrets rules. |
| [`references/pitfalls.md`](references/pitfalls.md) | 生产事故（已脱敏）。<br>Production mistakes (sanitized). |
| [`evals/evals.json`](evals/evals.json) | 有技能 / 无技能对照的起步提示。<br>Starter prompts for with-skill vs without-skill evals. |
| [`scripts/`](scripts/) | 宿主项目 worker CLI 的占位。<br>Placeholder for host-project worker CLIs. |

## 这个仓库是什么 / What this repo is

这是一个 Agent Skills 包：策略、脱敏后的坑，以及起步评测。入队和 ASR worker 住在宿主项目里。如果以后抽出独立 worker，把入口放在 [`scripts/`](scripts/)（见 [`scripts/README.md`](scripts/README.md)）。

An Agent Skills package: policy, sanitized pitfalls, and starter evals. Enqueue and ASR workers live in the host project. If you later extract a standalone worker, put the entrypoints under [`scripts/`](scripts/) (see [`scripts/README.md`](scripts/README.md)).

### 这个仓库不是 / What this repository is not

- 整套桌面克隆（收件箱字段、个人知识库路径、另一台机器的 `.env`）。
  A full desk clone (inbox schemas, personal vault paths, another machine’s `.env`).
- systemd unit、cron 文件或 timer。技能需要一个 worker；怎么调度由宿主决定。
  A systemd unit, a cron file, or a timer. The skill requires a worker; the host decides how it is scheduled.
- 存放密钥的地方。文档只写环境变量名。
  A place for secrets. Docs name environment variables only.

## 常见坑 / Pitfalls

六条规则。完整列表在 [`references/pitfalls.md`](references/pitfalls.md)。

Six rules. The full list is [`references/pitfalls.md`](references/pitfalls.md).

- **标题不是观看。 / Title is not a watch.** 标题、简介、推文和封面都不能完成任务。
  Title, description, tweet text, and thumbnails do not finish the task.
- **短不等于豁免。 / Short is not exempt.** 短片上的空 ASR 仍然需要一个可恢复的任务。
  Empty ASR on a short clip still needs a recoverable job.
- **CDN 地址不是任务 id。 / A CDN URL is not a job id.** 身份是平台加上持久内容 id。签名媒体在运行时刷新。
  Identity is platform plus a durable content id. Refresh signed media at run time.
- **任务需要消费者。 / Jobs need a consumer.** 没有定时 worker 的 `needs-transcript` 行会一直坐着，直到有人想起去排空它们。
  `needs-transcript` rows without a scheduled worker sit until someone remembers to drain them.
- **密钥只出现环境变量名。 / Secrets are env names only.** 例如 `BILIBILI_SESSDATA`（可选；绝不打印值）。不要提交 cookie 值或 API key，也不要把它们写进日志或回执。
  Example: `BILIBILI_SESSDATA` (optional; never print the value). Do not commit cookie values or API keys, and do not write them into logs or receipts.
- **落点保持分开。 / Keep sinks separate.** YouTube、X、微信和官方文档各自留在自己的频道。未知来源应失败关闭或先询问；不要掉进一个大杂烩文件夹。
  YouTube, X, WeChat, and official docs stay in their own channels. An unknown source fails closed or asks; it does not drop into a catch-all folder.

## 评测 / Evals

[`evals/evals.json`](evals/evals.json) 带三条起步用例（有技能对照无技能）。

[`evals/evals.json`](evals/evals.json) ships three starter cases (with-skill vs without-skill):

1. `youtube-with-captions-or-asr` — 从字幕或 ASR 读一条 YouTube 链接；否则说未完成。
   Read a YouTube link from captions or ASR; otherwise say not finished.
2. `no-transcript-must-refuse-final-deposit` — 短视频上的空 ASR 不能变成最终知识库笔记。
   Empty short-video ASR must not become a final vault note.
3. `chinese-asr-hallucination-gate` — 预期中文讲稿上的英文循环，不能当成一篇打磨好的文章发出去。
   English loops on an expected-Chinese talk must not ship as a polished essay.

## 许可 / License

以 [MIT](LICENSE) 许可发布。Copyright (c) 2026 HappyDrunk。

Released under the [MIT](LICENSE) license. Copyright (c) 2026 HappyDrunk.
