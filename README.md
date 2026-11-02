# transcript-first-video

[English](#english) · [中文](#中文)

# English

## What this is

This folder teaches an AI agent to read a video from the words that were spoken, and to write notes only from those words.

In other words: a title, a description, a tweet, or a cover image is not a watch.

## Who it’s for

Use it when you paste a YouTube, Bilibili, X, or short-video link and want notes about what was actually said.

You do not need to know “Agent Skills” already. An Agent Skill is a folder of written rules the agent loads so it behaves the same way each time. This repository is that folder.

## The problem it fixes

**The agent pretends it watched.** You send a link. It reads the title and the short description, writes a confident summary, and stops. The video was never turned into text. The note looks finished. The watching never happened.

**A short video gets skipped.** Speech-to-text on a 20-second clip comes back empty. The agent adds “video not transcribed” and files the item as done. A short video still has to be heard. Empty text means the job is still open.

**Bad speech-to-text becomes a fake note.** The talk is in Chinese. The recognizer is set to English and prints the same English nonsense again and again. ASR means automatic speech recognition: software that turns audio into text. The agent then writes a tidy essay about “the transcription failed” and saves that essay as the talk. A quality gate is the check that stops this. It asks whether the transcript (the written speech) is real speech, not garbage, before any note is saved.

## How to use it

1. **Clone the folder.**

   ```bash
   git clone https://github.com/HappyDrunk/transcript-first-video.git
   ```

2. **Put it where your agent loads skills.** A common place is `skills/transcript-first-video/`, next to the program that downloads audio and runs speech-to-text. That program lives in your own project, not in this repo.

3. **Give the agent a video link.** Ask it to read or summarize the video from the spoken words, and to say it is not finished when it cannot get a real transcript.

4. **Done looks like this.** Usable text exists: official subtitles, a saved transcript for that same video, or speech-to-text that passed the quality gate. The note is written from that text, and it names the transcript file.

5. **When it says “not finished,” that answer is correct.** Keep the final note unwritten until real speech text exists. Leave a status such as `needs-transcript`, `video-pending`, or a named quality-gate failure, plus a next step: queue the job, retry once with a stronger speech model, or stop. A note from the title and description is allowed only after you accept that weaker path and the note says so.

The agent tries sources in this order: official subtitles, then a saved transcript for that video, then speech-to-text, then an honest “not finished.” Run one speech job at a time. Long work belongs in a background worker (a small program that keeps processing jobs). The chat stays free for you.

## What’s inside

| Path | What it is |
| --- | --- |
| [SKILL.md](SKILL.md) | The detailed rulebook: the steps, the quality gate, and how secrets are handled. |
| [references/pitfalls.md](references/pitfalls.md) | Lessons from real mistakes, with private details removed. Read it when a note looks done but is not, or when Chinese speech comes out as English garbage. |
| [evals/evals.json](evals/evals.json) | Three practice quizzes. Each one checks that the agent follows this skill instead of slipping back into fake watching. |
| [scripts/](scripts/) | An empty slot. The commands that queue and run jobs live in your project. See [scripts/README.md](scripts/README.md). |

## What this repo is not

- **A magic app.** Cloning it does not watch videos by itself. The agent loads the skill. Your project downloads the audio and runs speech-to-text.
- **A full desktop clone.** It does not copy someone else’s inbox layout, personal note folders, timers, or another machine’s `.env`.
- **A place for passwords.** Docs may name an environment variable, such as `BILIBILI_SESSDATA`. They never include the value. Keep cookies and API keys out of the repo, logs, and notes.

## You’re doing it right if…

- The note names a transcript file, or it clearly says the task is not finished.
- The title, description, tweet, and cover were left out of the “I watched it” claim.
- A short video with empty text is still open, not marked done.
- Looping or nonsense speech-to-text was stopped before it became an article.
- No cookie or API key appears in the repo, a log, or a note.

## License

Released under the [MIT](LICENSE) license. Copyright (c) 2026 HappyDrunk.

# 中文

## 这是什么

这个文件夹教 AI 代理一件事：先读视频里真正说出口的话，再根据这些话写笔记。

换句话说，标题、简介、推文、封面，都不算看过。

## 适合谁

你会把 YouTube、Bilibili、X 或短视频链接发给代理，并且希望笔记写的是视频里说了什么。这份说明就是给你的。

不必事先懂「Agent Skill」。它就是一个文件夹，里面写着代理每次都要遵守的规则。本仓库就是那个文件夹。

## 它解决的问题

**代理用标题假装看过。** 你发来一个链接。它读了标题和简介，写出一篇很有把握的摘要就停了。视频没有被转成文字。笔记看起来写完了，观看并没有发生。

**短视频被跳过。** 一段大约 20 秒的视频，语音识别返回空白。代理补上一句「视频未转写」，仍把它收成已完成。视频短，也得听见里面的话。文字是空的，这件事就还没做完。

**糟糕的识别结果变成假笔记。** 口播是中文，识别器却按英语来听，把同一段英语胡话重复了很多遍。ASR 就是自动语音识别，也就是把声音转成文字的程序。代理接着写了一篇整齐的文章，主题是「转写失败了」，并把这篇文章当成讲稿存下来。质量门就是拦住这件事的检查：写笔记之前，先确认文稿（说出来的话写成的文字）是真人说话，不是一堆垃圾。

## 怎么用

1. **克隆这个文件夹。**

   ```bash
   git clone https://github.com/HappyDrunk/transcript-first-video.git
   ```

2. **放到代理加载技能的地方。** 常见位置是 `skills/transcript-first-video/`，跟负责下载音频、跑语音识别的程序放在一起。那个程序在你自己的项目里，不在本仓库里。

3. **把视频链接交给代理。** 请它根据口播来读或总结。拿不到真实文稿时，让它直接说没做完。

4. **做完是这样的。** 已经有能用的文字：官方字幕、这条视频保存过的文稿，或者通过质量门的语音识别。笔记根据这段文字写成，并且写明文稿文件在哪里。

5. **它说「没做完」时，这个回答是对的。** 在拿到真实口播文字之前，最终笔记先别写。留下状态，例如 `needs-transcript`、`video-pending`，或写明哪一项质量门没过，再写下一步：把任务放进队列、换一个更强的语音模型重试一次，或者停止。只有你接受这条较弱的路，并且笔记自己写明「只根据标题和简介」，才可以那样写。

代理按这个顺序尝试：先官方字幕，再这条视频已有的文稿，再语音识别，最后老实说没做完。语音任务一次做一个。费时间的活交给后台 worker（一个在旁边持续处理任务的小程序）。聊天窗口留给你。

## 仓库里有什么

| 路径 | 是什么 |
| --- | --- |
| [SKILL.md](SKILL.md) | 详细的规则手册：步骤、质量门，以及密钥怎么处理。 |
| [references/pitfalls.md](references/pitfalls.md) | 从真实失误里整理的教训，私人信息已经去掉。笔记看起来完成了其实没有，或者中文口播被听成英语胡话时，先读它。 |
| [evals/evals.json](evals/evals.json) | 三道练习题。用来检查代理是在遵守这套规则，还是又退回去假装看过。 |
| [scripts/](scripts/) | 一个空位。真正排队、跑任务的命令在你自己的项目里。见 [scripts/README.md](scripts/README.md)。 |

## 这个仓库不是什么

- **不是一个点开就能用的应用。** 克隆下来不会自己看视频。代理加载这份技能，你的项目负责下载和语音识别。
- **不是整台电脑的拷贝。** 它不带走别人的收件箱格式、个人笔记目录、定时任务，或另一台机器上的 `.env`。
- **不是放密码的地方。** 文档最多写出环境变量的名字，例如 `BILIBILI_SESSDATA`，不会写出值。cookie 和 API key 不要放进仓库、日志或笔记。

## 怎样算用对了

- 笔记标明了文稿文件，或者明确说任务没做完。
- 「我看过了」这句话里，没有用标题、简介、推文或封面来充数。
- 文字是空的短视频仍然开着，没有被标成完成。
- 循环或胡话的识别结果在变成文章之前就被拦住了。
- 仓库、日志和笔记里都没有 cookie 或 API key。

## 许可

以 [MIT](LICENSE) 许可发布。Copyright (c) 2026 HappyDrunk。
