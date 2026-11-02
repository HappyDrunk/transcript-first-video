# transcript-first-video

[English](#english) · [中文](#中文)

# English

> AI has a bad habit with videos: it only reads the title. This skill is here to cure that.

You hand it a YouTube, Bilibili, X, or short-video link. It finds the words that were actually spoken, then writes the notes from those words. A title, a blurb, a tweet, or a cover is not a watch.

## What you get

You paste a link. You get notes written from what was said, and the note names the transcript file.

No captions, empty speech-to-text, or text that does not sound like a person: you get the next step. Queue it, try once with a stronger speech model, or stop.

## Quick install

Send your agent this line.

```text
Install this skill: https://github.com/HappyDrunk/transcript-first-video
```

It reads the repo, finds `transcript-first-video`, and installs it.

If your agent can’t install from a link, clone it and keep the folder name.

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git ~/.agents/skills/transcript-first-video
```

## How to use

Nothing to memorize. After it is installed, say:

```text
Use transcript-first-video. Actually finish this video, then write the notes: <url>
```

Or say it straighter:

```text
No transcript, say you didn’t finish.
This one is twenty seconds and the speech-to-text came back empty. Don’t archive it. Queue it.
The talk is in Chinese and the text came back as English nonsense. Stop. Don’t write the note.
```

## What it holds to

- **Captions, then speech, then notes.** Official subtitles first, then a transcript already saved for that same video, then speech turned into text. The note comes from that text.
- **No fake finish.** No usable transcript, no final note. The status stays `needs-transcript` or `video-pending`, and it names the next step. If you ask for a title-only pass, the note says the video was not watched.
- **A short video still counts.** Twenty seconds is still somebody talking. Empty text stays unfinished.
- **Bad speech-to-text stops.** Chinese heard as looping English junk is not a note. If the words don’t sound like a person, it stops, retries once with a stronger model, or says what failed. A tidy essay about the failure stays out of the knowledge base.

## Who does the work

The rules live in this repo. The program that downloads the video and turns speech into text lives in your project. Open this folder and nothing plays.

Keep passwords out. A doc may name a setting, such as `BILIBILI_SESSDATA`, and never the value.

## What’s in the repo

```text
transcript-first-video/
├── SKILL.md
├── references/pitfalls.md
├── evals/evals.json
├── scripts/
└── LICENSE
```

| Path | What it’s for |
| :--- | :--- |
| [SKILL.md](SKILL.md) | The rules: where the words come from, and when to stop |
| [references/pitfalls.md](references/pitfalls.md) | Real mistakes, private details removed. Open it when a note looks done but isn’t, or Chinese comes out as English junk |
| [evals/evals.json](evals/evals.json) | Three practice cases. They catch a slide back to “I read the title” |
| [scripts/](scripts/) | Empty on purpose. Queue and run commands live in your project. See [scripts/README.md](scripts/README.md) |

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 HappyDrunk.

# 中文

> AI「看视频」有个通病：其实只读了标题。这份 skill 想治的就是这件事。

你丢给它一条 YouTube、B 站、X，或者短视频。它先把嘴里说的话找出来，再按这些话写笔记。标题、简介、推文、封面，都不算看过。

## 装上之后你得到什么

你丢进去一条链接。回来的是按嘴里说的话写成的笔记，笔记里写明文稿文件在哪。

没有字幕、转写是空的、或者转出来的字不像人话，你拿到的是下一步：排队、换一个更强的语音模型再试一次，或者停。

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

## 怎么用

不用背提示词。装好直接说：

```text
用 transcript-first-video，把这个视频真正看完再写笔记：<url>
```

也可以更明确一点：

```text
没拿到文稿就说没看完。
这条只有二十秒，转写是空的。别归档，去排队。
口播是中文，转出来全是英语胡话。停，别写笔记。
```

## 它认的四条

- **字幕，然后是人话，然后才是笔记。** 先官方字幕，再这条视频已经存好的文稿，再把声音转成文字。笔记从这段文字来。
- **没看完就别装看完。** 没有能用的文稿，最终笔记先不写。状态留着，比如 `needs-transcript`、`video-pending`，并写上下一步。你要是开口说就按标题写一版，笔记里得写明：没看视频。
- **短视频也算。** 二十秒也是有人在说话。转写空了，这事就还没完。
- **烂转写就停。** 中文被听成来回转的英语胡话，这段字就不算笔记。不像人说的话，就停。换一个更强的模型再试一次，或者停下来说明白。那篇讲「转写失败了」的干净小作文，别存进知识库。

## 谁来干活

规矩在这个仓库里。下载视频、把声音转成文字的程序，在你自己的项目里。点开这个文件夹，什么也不会播。

密码别往这儿放。文档最多写出一个名字，比如 `BILIBILI_SESSDATA`，不会写出值。

## 仓库里有什么

```text
transcript-first-video/
├── SKILL.md
├── references/pitfalls.md
├── evals/evals.json
├── scripts/
└── LICENSE
```

| 位置 | 干什么的 |
| :--- | :--- |
| [SKILL.md](SKILL.md) | 规矩：字从哪来，什么时候该停 |
| [references/pitfalls.md](references/pitfalls.md) | 真实翻过的车，私人信息已经去掉。笔记看着完成了其实没有，或者中文被听成英语胡话，先看它 |
| [evals/evals.json](evals/evals.json) | 三道练习，专门抓「又退回去读标题」 |
| [scripts/](scripts/) | 故意空着。排队、跑任务的命令在你自己的项目里。见 [scripts/README.md](scripts/README.md) |

## 许可

MIT。见 [LICENSE](LICENSE)。Copyright (c) 2026 HappyDrunk。
