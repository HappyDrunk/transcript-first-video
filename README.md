# transcript-first-video

[English](#english) · [中文](#中文)

# English

> AI has a bad habit with videos: it reads the title and acts like it watched. This skill is here to cure that.

You hand it a YouTube, Bilibili, X, or short-video link. It should get the words that were actually spoken, then write notes from those words. The title, the blurb, the tweet, and the cover don’t count as watching.

## Quick install

Send your agent this line.

```text
Install this skill: https://github.com/HappyDrunk/transcript-first-video
```

It reads the repo, finds `transcript-first-video`, and installs it.

If your agent can’t install from a link, clone it into your skills folder and keep the folder name.

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git ~/.agents/skills/transcript-first-video
```

The program that downloads the audio and turns speech into text lives in your own project. This repo is the rules.

Once it’s in, talk to it like this:

```text
Use transcript-first-video. Actually finish this video, then write the notes: <url>
```

## Three awkward misses

You’ve probably watched it do these.

**The title did the watching.** A link comes in. It skims the title and the blurb, writes something confident, and stops. Not one spoken sentence landed on the page. The note looks done. Nobody watched.

**The short clip gets a pass.** Twenty seconds, and speech-to-text comes back empty. It adds “not transcribed” and files the item anyway. Short still means somebody talked. Empty means it isn’t done.

**A bad transcript becomes a fake note.** The talk is in Chinese. The recognizer is set to English and loops the same nonsense. Then it writes a neat little essay about “the transcription failed,” and saves that essay as the talk. Before any note, look at the words: do they sound like a person? If they don’t, stop.

## What “finished” means

Finished means you have the words. Official subtitles, a transcript already saved for that same video, or speech turned into text that sounds like speech. The note is written from that text, and it names the file.

No words, say you didn’t finish. Leave the final note unwritten. Keep a status such as `needs-transcript` or `video-pending`, or say the text didn’t sound like a person, and name the next step: queue it, try once with a stronger speech model, or stop. A note from the title alone waits until you ask for that shortcut, and the note says it didn’t watch.

Look for words in this order: official subtitles, then a transcript already saved for that video, then speech-to-text, then an honest “I didn’t finish.” Run one speech job at a time. Long work can sit in the background. The chat stays yours.

## What’s in the repo

| Path | What it’s for |
| :--- | :--- |
| [SKILL.md](SKILL.md) | The rules: where the words come from, when to stop, how secrets stay out |
| [references/pitfalls.md](references/pitfalls.md) | Real mistakes, private details removed. Open it when a note looks done but isn’t, or Chinese comes out as English junk |
| [evals/evals.json](evals/evals.json) | Three practice cases. They catch a slide back to “I read the title” |
| [scripts/](scripts/) | Empty on purpose. The commands that queue and run jobs live in your project. See [scripts/README.md](scripts/README.md) |

## What this is not

Open it and nothing plays. The agent reads the rules. Your project still downloads the audio and turns speech into text.

Your inbox layout, note folders, timers, and another machine’s `.env` stay where they are.

Passwords stay out. A doc may name a setting, such as `BILIBILI_SESSDATA`, and never the value. Keep cookies and API keys out of the repo, the logs, and the notes.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 HappyDrunk.

# 中文

> AI「看视频」有个通病——其实只读了标题。这份 skill 想治的就是这件事。

你丢给它一个 YouTube、B 站、X，或者一条短视频。它该做的是：先把嘴里说的话落成文字，再按这些话写笔记。标题、简介、推文、封面，不能拿来充「看过」。

## 快速安装

把下面这句话发给你的 Agent。

```text
帮我安装这个skill：https://github.com/HappyDrunk/transcript-first-video
```

它会去读仓库，找到 `transcript-first-video`，装好。

Agent 不能从链接直接装的话，克隆到本机的 Skills 目录，文件夹名留着。

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git ~/.agents/skills/transcript-first-video
```

下载音频、把声音转成文字的程序在你自己的项目里。这个仓库只放规矩。

装好之后这样用：

```text
用 transcript-first-video，把这个链接真正看完再写笔记：<url>
```

## 三件尴尬事

你大概碰上过这三回。

**拿标题装看完。** 链接一到，它扫一眼标题和简介，写得头头是道，收工。嘴里说的话，一个字没落地。笔记像写完了，人没看。

**短视频被放过。** 二十来秒，转写回来是空的。它补一句「没转写」，照样归档。短，也是有人在说话。空的，就还没做完。

**烂转写写成假笔记。** 口播是中文，识别器按英语去听，同一段胡话来回转。它接着写一篇干干净净的小作文，讲「转写失败了」，把这篇作文当成视频内容存下来。动笔之前先看一眼：这段字像不像人说的话。不像，就停。

## 怎样算看完了

看完，就是手里有文稿。官方字幕、这条视频早就存好的文稿，或者一段听着像人话的转写，都算。笔记按这段文字来写，并且写明文件在哪。

没有文稿，就直说没看完。最终笔记先别写。状态留着，比如 `needs-transcript`、`video-pending`，或者说这段字不像人话，再写下一步：排队、换一个更强的语音模型再试一次，或者停。只靠标题写，得你自己点头要这条凑合的路，而且笔记里写明「没看视频」。

找字按这个顺序：先官方字幕，再这条视频已有的文稿，再语音转写，最后老实说没看完。语音一次做一条。费时间的活放后台，聊天留给你。

## 仓库里有什么

| 位置 | 干什么的 |
| :--- | :--- |
| [SKILL.md](SKILL.md) | 规矩：字从哪来，什么时候该停，密码怎么不写进来 |
| [references/pitfalls.md](references/pitfalls.md) | 真实翻过的车，私人信息已经去掉。笔记看着完成了其实没有，或者中文被听成英语胡话，先看它 |
| [evals/evals.json](evals/evals.json) | 三道练习。专门抓「又退回去读标题」 |
| [scripts/](scripts/) | 故意空着。排队、跑任务的命令在你自己的项目里。见 [scripts/README.md](scripts/README.md) |

## 它不是什么

点开它，什么也不会播。Agent 读这些规矩。下载和转写，还是你的项目干。

收件箱长什么样、笔记放哪、定时任务、另一台机器上的 `.env`，都留在原地。

密码不放这儿。文档最多写出一个名字，比如 `BILIBILI_SESSDATA`，不会写出值。cookie 和 API key 别进仓库、日志、笔记。

## 许可

MIT。见 [LICENSE](LICENSE)。Copyright (c) 2026 HappyDrunk。
