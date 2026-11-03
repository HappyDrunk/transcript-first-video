# transcript-first-video

[English](#english) · [中文](#中文)

# English

YouTube and Twitter/X video. This skill fetches those two. Other platforms are not promised. It is a transcript-first honesty gate, not a multi-platform summarizer: a note is allowed only after the spoken words are written down, the text passes a quality check, and the note quotes that transcript.

## Try it on one captioned video

Cloning this repository does not fetch a video and does not write a note. You have the rules. The smallest path that finishes is `yt-dlp`, then one command, on a short public video that already has captions.

```bash
pip install -r requirements.txt
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --out artifacts
```

That URL is "Me at the zoo" (`jNQXAC9IVRw`). It is short, public, and captioned. When the captions come back, the command writes `artifacts/youtube_jNQXAC9IVRw/transcript.txt` and a note that quotes that file. yt-dlp is the first try. If YouTube asks it to sign in, the host tries a public caption mirror and can still finish from that text.

A video with no captions stops at `not_finished`. That stop is the design. `ASR_BACKEND` is unset by default, which means off, so speech-to-text does not run. The host does not fill the gap with the title.

Speech-to-text is a second rung. Install it only when you want that rung. Local whisper also needs `ffmpeg` on the machine.

```bash
pip install -r requirements-asr.txt
ASR_BACKEND=whisper python3 scripts/youtube_host.py "<url-without-captions>" --out artifacts
```

Until `ASR_BACKEND` is set, a video with no captions stays unfinished.

No network right now? A finished job is already in the repo. Open [evals/results/live/youtube_KwhgfwOSToQ/note.md](evals/results/live/youtube_KwhgfwOSToQ/note.md). It names [the transcript](evals/results/live/youtube_KwhgfwOSToQ/transcript.txt) and quotes it. [status.json](evals/results/live/youtube_KwhgfwOSToQ/status.json) is the same job.

To check this copy without fetching:

```bash
bash scripts/smoke.sh
```

That creates `.venv` when it is missing, installs `requirements.txt` (yt-dlp only), runs the gate tests, and settles a fixture transcript. When the network is up and you also want the short captioned URL:

```bash
bash scripts/smoke.sh --live
```

`--live` still leaves ASR off. Offline is `bash scripts/smoke.sh`. Live is the same script with `--live`.

You have seen the failure this gate is for. A YouTube or X video link lands in the chat. The agent reads the title and the short blurb, sometimes the post beside the link, and writes a note that sounds like it watched. The words that were spoken never get written down. The note looks finished. Nobody heard the video.

This repository is a skill: a folder of rules the agent loads so the next note waits for those words. The title, the blurb, and the post can help it find the right video. Finding it still leaves the listening to do.

## What you get

You do not get an auto-summary button. After this is installed, a link does not immediately come back as a summary. You get a rule, and the rule is short: a note is allowed only after the spoken words have been written down.

**When it goes well.** You paste a link. It looks for official captions first. If captions exist, that text is the transcript. If they do not, it looks for a transcript already saved for this same video, not a different video with a similar title. If that file is there and it still sounds like a person talking, it uses that file. If neither is there, it downloads the audio and turns the speech into text. A note is allowed only after one of those three has actually produced words. The note has to name the transcript file and quote a real stretch of it (about 40 characters), so you can open the file and match the sentences. A pasted path under a rewritten title is not a quote. A note that reads smoothly and cannot point at its file is not finished.

```text
link
  → official captions? use them
  → else a transcript already saved for this same video? use it if it sounds like speech
  → else download the audio and turn speech into text
  → then write the note, name the transcript file, and quote it
```

**When it does not.** Three ordinary dead ends. None of them gets an essay that pretends the video was watched.

No captions, and no saved transcript either. Say it is not finished, and put the job on the queue so a later run can fetch the audio and transcribe it. The title stays a title.

Speech-to-text comes back empty. A clip of about twenty seconds does this often. Empty stays empty. The item stays open. The next step is the queue, or one retry. Filing it as archived, with a line that says "not transcribed," leaves the video unheard.

Speech-to-text comes back as nonsense. The talk is in Chinese, the recognizer was set to English, and the same scrap of Latin text loops. Or the characters are Chinese and the nouns are mush. Neither one is a transcript. Leave the note unwritten. A clean little essay whose subject is "the transcription failed" is the same failure wearing nicer clothes. It does not get saved as what the video was about. The next step is one try with a stronger speech model, written to a separate file so the bad text is still there to compare. If that try still does not sound like a person, stop, and say which step failed. That one stronger try is the retry. Then stop.

```text
no captions, and no saved transcript
  → not finished; queue it

speech-to-text came back empty
  → not finished; queue it, or retry once

speech-to-text came back nonsense
  → not finished; one stronger model, or stop
```

**Success, in one line:** the note is written from the transcript, it names the transcript file, and it quotes that file.

**Failure, in one line:** it says not finished, names the next step (queue it, try a stronger model once, or stop), and leaves no essay that pretends the video was watched.

A note from the title alone is a different request. It waits until you ask for that shortcut, and the note itself says the video was not watched. A status such as `needs-transcript` or `video-pending` can sit on the item while it waits. "Fully understood" cannot sit beside it.

## Install

Two ways. The first is one sentence you send to your agent.

```text
Install this skill: https://github.com/HappyDrunk/transcript-first-video
```

It should open this repo, find the folder named `transcript-first-video`, and install that folder as a skill. Leave the name as it is. If the folder gets renamed on the way in, a later "use transcript-first-video" may not find it.

If your agent cannot install from a link, clone it into the directory that agent loads skills from, and leave the folder name alone.

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git ~/.agents/skills/transcript-first-video
```

`~/.agents/skills/` is a common place. Yours might be `skills/transcript-first-video/` beside the project that actually downloads audio. Either works, as long as that agent reads skills from there.

When the clone finishes, nothing plays by itself. You have the rules. The command that finishes a captioned link is in [Try it on one captioned video](#try-it-on-one-captioned-video). `scripts/` has a YouTube fetcher, an X/Twitter video fetcher, and a gate you can run before a note is allowed into a vault. The queue and the shelf where notes live stay in your project. Other video sites are not fetched here.

## How to use

Once it is in, hand it a link like this.

```text
Use transcript-first-video. Actually finish this video, then write the notes: <url>
```

"Actually finish" is doing work in that sentence. Many agents treat a bare link as a reading assignment about the title. With this wording, you are asking for the rule above: words first, then the note, and an honest stop if the words never arrive.

Leftovers from an earlier run belong here too. An item tagged `needs-transcript` or `video-pending`, or a note that claims the video was understood while no transcript file exists, is unfinished. Hand it back under this skill. The same order applies.

The order is fixed: official captions, then a transcript already saved for that video, then speech-to-text, then an honest "not finished." One speech job at a time. If the command in your project takes a limit, that is `--limit 1`. A long video can run in the background. The chat stays yours. If a timer runs these, the timer wakes the program that picks up the queue. It does not ask the model in the chat to listen to the video all over again each time it wakes.

## Four traits

Four rules. Each one is a scene.

**A title does not get to do the watching.** A link comes in. The agent skims the title and the blurb, writes something confident, and stops. Not one spoken sentence is on the page. The note looks done. The title can stay at the top of the note as a title. The evidence has to be the words that were spoken.

**A short clip is still a video.** About twenty seconds, and speech-to-text returns nothing. The agent adds "not transcribed" and files the item as archived. Short means the person talked briefly. Empty means the job is open. Length is not a reason to close it. A two-hour talk and a twenty-second clip follow the same rule.

**Nonsense does not become the note.** The talk is in Chinese. The recognizer is set to English and loops the same scrap of gibberish. The agent then writes a tidy essay about "the transcription failed," and saves that essay as the video. The essay looks smarter than the transcript, which is why this one slips through. Before any note, read the text as if someone were saying it. If it does not sound like a person, stop. Chinese characters are not enough on their own: mushy nouns and low confidence are the same stop.

**A queued job needs something that runs it.** You mark three links `needs-transcript` and close the chat. Three days later they are still sitting there, because nothing picked up the queue. Closing the chat does not fetch audio. The everyday path is a timer that wakes the program, and that program takes one waiting job and tries captions, then speech-to-text. Running it by hand is how you check. The timer is how it gets done on a normal day.

## Who does the work

This repo is what the agent reads. Your project does the labor: fetch captions, download audio, turn speech into text, keep the queue, and write the note onto the shelf you already use.

This repo fetches YouTube and X video only. If your notes are already split, keep the split. Each source stays where that project already puts it. If you cannot tell where it came from, wait, or ask. A miscellaneous folder is how two sources end up in the same pile.

Your inbox fields, your note paths, your timers, and another machine's `.env` stay where they are. Copying someone else's whole desk over produces a pile of paths that do not match, the next morning. When these jobs run on a schedule, the schedule lives in your project. This repo has no cron file and no service file from another machine. Some program still has to pick up the queue. You decide when that program wakes.

The program has to store which video it is. The download address the site handed out this morning will expire, and opening it again at night often answers 403. Store the job as `youtube_<id>` or `x_<status id>`. When it runs, go back to the video page and ask for a fresh address. Replaying this morning's link produces an empty transcript of a video that did have sound.

Cookies and API keys stay out. A doc may name a setting, such as `YTDLP_COOKIES` or `OPENAI_API_KEY`, and does not print the value. The same goes for logs and notes. If the cookie is missing or expired, say that in the status. Keep using the public way to fetch the video. The cookie is optional. It helps some fetches. The skill still works without it.

## What's in the repo

| Path | What it's for |
| :--- | :--- |
| [SKILL.md](SKILL.md) | The full rules: where words may come from, when to stop, what a note has to cite, how a cookie or a key stays a name. If this page and that file disagree, follow the file. |
| [references/pitfalls.md](references/pitfalls.md) | Ten real mistakes, private details removed. Open it when a note looks done and you suspect it is not, or when a Chinese talk comes back as English junk. The stories include a queue nobody ran, a download link that expired, and a "mostly Chinese characters" transcript that was still garbage. |
| [evals/evals.json](evals/evals.json) | Three prompts for an agent or a person. CI does not run the prompts or score the assertions. CI runs `scripts/test_gate.py` and `scripts/run_evidence.py --skip-live` on the fixture files. |
| [evals/results/live/youtube_KwhgfwOSToQ/](evals/results/live/youtube_KwhgfwOSToQ/) | A finished YouTube job, already committed. The note quotes the transcript. Open it when you have no network. |
| [scripts/](scripts/) | YouTube and X/Twitter video fetchers, and a gate that refuses a note unless it quotes a real transcript. `bash scripts/smoke.sh` checks this copy offline. See [scripts/README.md](scripts/README.md). |

How to change this repo, and what shipped: [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md).

## License

MIT. You can use it, change it, and ship it with your own work. Keep the copyright notice in the copies. The full text is [LICENSE](LICENSE). Copyright (c) 2026 HappyDrunk.

# 中文

YouTube，和 Twitter/X 上的视频。这份 skill 只抓这两处。别的平台不承诺。它是一道「先有文稿才许写笔记」的门槛，不是多平台摘要器：嘴里的话先落成文字，文字过了质量检查，笔记还得引用这段文稿。

## 先跑通一条有字幕的视频

克隆这个仓库，视频不会自己开始下，笔记也不会自己出现。你拿到的是规矩。最小的一条能走完的路是：装上 `yt-dlp`，然后对一条短的、公开的、已经有字幕的视频跑一个命令。

```bash
pip install -r requirements.txt
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --out artifacts
```

这个地址是 "Me at the zoo"（`jNQXAC9IVRw`）。短，公开，有字幕。字幕回来之后，命令会写下 `artifacts/youtube_jNQXAC9IVRw/transcript.txt`，以及一篇引用了这个文件的笔记。yt-dlp 是第一次尝试。如果 YouTube 要求登录，主机会再试一个公开字幕镜像，镜像上的字仍然可以把这条做完。

没有字幕的视频会停在 `not_finished`。这是设计如此。`ASR_BACKEND` 默认不设置，就是关着的，语音转文字不会自己跑。缺文稿的空档，不会拿标题去补一篇笔记。

语音转文字是第二级，不在默认安装里。你要这一级的时候再装。本地 whisper 还要机器上有 `ffmpeg`。

```bash
pip install -r requirements-asr.txt
ASR_BACKEND=whisper python3 scripts/youtube_host.py "<没有字幕的链接>" --out artifacts
```

在你设置 `ASR_BACKEND` 之前，没有字幕的视频就停在没看完。

现在没有网络，也可以看一份已经写完的样子。打开 [evals/results/live/youtube_KwhgfwOSToQ/note.md](evals/results/live/youtube_KwhgfwOSToQ/note.md)。它点名了[文稿](evals/results/live/youtube_KwhgfwOSToQ/transcript.txt)，并引用了其中一段。同一条任务的状态在 [status.json](evals/results/live/youtube_KwhgfwOSToQ/status.json)。

不联网，先核对这一份拷贝：

```bash
bash scripts/smoke.sh
```

它会在缺少 `.venv` 时建一个，安装 `requirements.txt`（只有 yt-dlp），跑门槛测试，再用一份现成文稿走一遍 settle。网络可用、还想试那条短字幕视频时：

```bash
bash scripts/smoke.sh --live
```

`--live` 同样不会把 ASR 打开。只跑离线是 `bash scripts/smoke.sh`。要连那条短视频，是同一个脚本加上 `--live`。

你见过这个失败。一个 YouTube 或 X 视频的链接丢进聊天。它读了标题和简介，有时还读了链接旁边那条帖子，写出一篇听着像看过的笔记。嘴里说的话，一个字没落下来。笔记像写完了。视频没人听。

这个仓库是一份 skill：一个文件夹，里面写着规矩。Agent 装上之后，下次写笔记，得先拿到这些话。标题、简介、帖子，可以帮它找对那条视频。找对了，还不等于听过。

## 装上之后你得到什么

你得到的不是一颗「自动总结」按钮。装上之后，链接一到，并不会马上吐出一篇摘要。你得到的是一条规矩，规矩很短：笔记只能写在嘴里的话已经落成文字之后。

**顺的时候。** 你贴一个链接。它先找官方字幕。有字幕，这段字就是文稿。没有，就看这条视频是不是早就存过一份文稿。要同一条，标题碰巧像的另一条不算。有，而且读起来还像人在说话，就用那份。两样都没有，再去下音频，把声音转成文字。三条路里有一条真正拿出了字，才许写笔记。笔记得点名这份文稿在哪个文件里，还得从文稿里引用大约 40 个连续的字，你能打开文件，对上笔记里的句子。只贴一个路径，再配一个改写过的标题，不算引用。一篇读着很顺、却说不出文件在哪的笔记，不算写完。

```text
链接
  → 有官方字幕？用字幕
  → 没有的话，这条视频存过文稿吗？像人话就用
  → 还没有，就下音频，把声音转成文字
  → 然后写笔记，点名文稿文件，并引用其中一段
```

**不顺的时候。** 常见就这三种。哪一种都不能交一篇假装看过的作文。

没有字幕，也没有存好的文稿。这时候就直说，并把这条放进队列，等后面那一轮去下音频、做转写。标题还是标题。

语音转文字回来是空的。二十来秒的片子经常这样。空的就是空的。这条还开着。下一步是队列，或者再试一次。写上「没转写」然后归档，视频还是没人听。

转写回来是胡话。口播是中文，识别器按英语去听，同一小段拉丁字母来回转。或者字看着是中文，名词却是一锅粥。这都不算文稿。笔记先别写。一篇干干净净的小作文，题目是「转写失败了」，只是同一种失败换了身整齐的衣服。不能把它当成视频内容存下来。下一步是换一个更强的语音模型再试一次，结果写到另一个文件里，坏的那份留着给对照。这一次还不像人话，就停，说清楚是哪一步失败的。更强的模型试这一次，然后停。

```text
没有字幕，也没有存好的文稿
  → 没看完，去排队

转写回来是空的
  → 没看完，去排队，或再试一次

转写回来是胡话
  → 没看完，更强的模型试一次，或停
```

**成功就一句话：** 笔记按文稿写，写明了文稿文件，并且引用了其中一段。

**失败就一句话：** 它说没看完，写下一步（排队、更强的模型试一次、或者停），不留一篇假装看过的作文。

只靠标题写，是另一回事。得你自己开口要这条凑合的路，而且笔记里写明「没看视频」。等待的时候，状态可以是 `needs-transcript` 或 `video-pending`。「完全看懂」不能跟它放在一起。

## 怎么装

两条路。第一条是你直接发给 Agent 的一句话。

```text
帮我安装这个skill：https://github.com/HappyDrunk/transcript-first-video
```

它该做的是：打开这个仓库，找到名叫 `transcript-first-video` 的文件夹，把这个文件夹当成 skill 装上。名字留着。装的时候改了名，以后你说「用 transcript-first-video」，它可能对不上。

Agent 不能从链接装的话，你自己克隆到它加载 skill 的目录，文件夹名同样留着。

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git ~/.agents/skills/transcript-first-video
```

`~/.agents/skills/` 是常见的一个位置。你的也可能是项目旁边的 `skills/transcript-first-video/`，跟真正下载音频的那个程序放一起。只要这个 Agent 会从那儿读 skill，就行。

克隆完，什么也不会自己播。你拿到的是规矩。真正能把一条有字幕的链接做完的命令，在[先跑通一条有字幕的视频](#先跑通一条有字幕的视频)。`scripts/` 里有 YouTube 抓取、X / Twitter 视频抓取，和一道入库前的门槛。队列和笔记放哪，仍在你自己的项目里。别的视频网站，这里不抓。

## 怎么用

装好之后，把链接这样交给它。

```text
用 transcript-first-video，把这个链接真正看完再写笔记：<url>
```

「真正看完」这四个字是有用的。只有一个光链接的时候，很多 Agent 会把它当成一道读标题的题。写成这样，你要的就是上面那条规矩：先有字，再写笔记；字没来，就老实说没看完。

以前跑过、留下 `needs-transcript` 或 `video-pending` 的，也可以交回来。有的笔记写着「已经看懂了」，旁边却没有文稿文件，同样算没做完。按同一个顺序再走一遍。

找字的顺序是固定的：先官方字幕，再这条视频已经存好的文稿，再语音转文字，最后老实说没看完。语音一次做一条。你项目里的命令如果有条数限制，那就是 `--limit 1`。长的可以在后台跑，聊天留给你。如果你用定时去跑这些，定时该去叫醒那个领队列的程序，而不是每次醒来都让聊天里的模型从头把视频再听一遍。

## 四条规矩

四条规矩。每条是一个场面。

**标题不能拿来充看过。** 链接一到，它扫一眼标题和简介，写得头头是道，收工。嘴里的话，一个字没落到纸上。笔记像完成了。标题可以留在笔记顶上当标题。拿来当证据的，得是说出口的那些话。

**短视频没有豁免。** 二十来秒，转写回来是空的。它补一句「没转写」，照样归档。短，是话说得短，不是没人说话。空的，这条就还开着。时长不能当结案的理由。两小时的长谈，和二十秒的片子，走同一条规矩。

**胡话不能写成笔记。** 口播是中文，识别器按英语去听，同一小段胡话来回转。它接着写一篇整齐的小作文，讲「转写失败了」，把这篇作文当成视频内容存下来。作文看起来比文稿聪明，所以这一条特别容易漏过去。动笔之前，先把那段字当成有人在说，在心里读一遍。不像人说的，就停。字是汉字也不够：名词是糊的、把握很低，同样停。

**标了待转写，还得有东西去跑。** 你把三条标成 `needs-transcript`，关掉聊天。三天后它们还在那儿，因为没有东西去领队列。关掉聊天并不会去下音频。日常靠一个定时去叫醒那个程序，程序领起一条等待中的活，先试字幕，再试语音转文字。你亲手跑一遍，是拿来核对的。平常把它做完的，是那个定时。

## 活是谁干的

这个仓库是 Agent 读的东西。干活的是你的项目：抓字幕、下音频、把声音转成文字、守着队列，再把笔记写到你已经在用的那个架子上。

这个仓库只抓 YouTube 和 X 的视频。笔记如果本来就是分开放的，就继续分开。各回各的地方。来源对不上的，就等一等，或者问你一声。别因为省事，掉进一个杂物文件夹。

收件箱的字段、笔记的路径、定时、另一台机器上的 `.env`，都留在原地。把别人的整桌搬过来，第二天就是一堆对不上的路径。这些活如果要定时跑，时刻表在你的项目里。这个仓库里没有 cron 文件，也没有另一台机器的服务配置。队列还是得有一个程序去领。那个程序什么时候醒，你来定。

这个程序得记住视频是哪一条。今早网站发下来的下载地址会过期，晚上再打开常常是 403。任务记成 `youtube_<id>` 或 `x_<状态 id>`。真正跑的时候，回到视频页要一个新地址。拿今早的链接再播一次，转写是空的，可视频并不是没有声音。

cookie 和 API key 不放这儿。文档可以写出一个名字，比如 `YTDLP_COOKIES` 或 `OPENAI_API_KEY`，不写出值。日志和笔记也一样。cookie 缺了，或者过期了，在状态里说一声。抓视频仍然走公开的那条路。cookie 是可选的。有些抓取它能帮上忙。没有它，这份 skill 也成立。

## 仓库里有什么

| 位置 | 干什么的 |
| :--- | :--- |
| [SKILL.md](SKILL.md) | 完整的规矩：字可以从哪来，什么时候该停，笔记必须点名什么，cookie 和密钥怎么只留名字。这页和那个文件要是说得不一样，以那个文件为准。 |
| [references/pitfalls.md](references/pitfalls.md) | 十条真实翻过的车，私人信息已经去掉。笔记看着完成了、你又觉得不对，或者中文口播被听成英语胡话，先打开它。里面有没人去跑的队列、过期的下载地址，还有一份「大部分是汉字」却仍然是垃圾的文稿。 |
| [evals/evals.json](evals/evals.json) | 三道给 Agent 或人的题目。CI 不跑这些题目，也不给断言打分。CI 跑的是 `scripts/test_gate.py` 和 `scripts/run_evidence.py --skip-live`，核对的是夹具文件。 |
| [evals/results/live/youtube_KwhgfwOSToQ/](evals/results/live/youtube_KwhgfwOSToQ/) | 一条已经提交进仓库的、写完了的 YouTube 任务。笔记引用了文稿。没有网络时打开它看成品长什么样。 |
| [scripts/](scripts/) | YouTube 和 X / Twitter 视频抓取，以及一道不引用真实文稿就不许写笔记的门槛。`bash scripts/smoke.sh` 在离线时核对这一份拷贝。见 [scripts/README.md](scripts/README.md)。 |

怎么改这个仓库、发过什么： [CONTRIBUTING.md](CONTRIBUTING.md)，[CHANGELOG.md](CHANGELOG.md)。

## 许可

MIT。可以用，可以改，可以带着它一起发出去。副本里留着版权声明就行。全文见 [LICENSE](LICENSE)。Copyright (c) 2026 HappyDrunk。
