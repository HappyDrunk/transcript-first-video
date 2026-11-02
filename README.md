# transcript-first-video

[English](#english) · [中文](#中文)

# English

You have seen this. A YouTube, Bilibili, X, or short-video link lands in the chat. The agent reads the title and the short blurb, sometimes the tweet beside the link, and writes a note that sounds like it watched. The words that were spoken never get written down. The note looks finished. Nobody heard the video.

This repository is a skill: a folder of rules the agent loads so the next note waits for those words. The title, the blurb, the tweet, and the cover can help it find the right video. Finding it still leaves the listening to do.

## What you get

You do not get an auto-summary button. After this is installed, a link does not immediately come back as a summary. You get a rule, and the rule is short: a note is allowed only after the spoken words have been written down.

**When it goes well.** You paste a link. It looks for official captions first. If captions exist, that text is the transcript. If they do not, it looks for a transcript already saved for this same video, not a different video with a similar title. If that file is there and it still sounds like a person talking, it uses that file. If neither is there, it downloads the audio and turns the speech into text. A note is allowed only after one of those three has actually produced words. The note has to name the transcript file, so you can open the file and match the sentences. A note that reads smoothly and cannot point at its file is not finished.

```text
link
  → official captions? use them
  → else a transcript already saved for this same video? use it if it sounds like speech
  → else download the audio and turn speech into text
  → then write the note, and name the transcript file
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

**Success, in one line:** the note is written from the transcript, and it names the transcript file.

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

When the clone finishes, nothing plays by itself. You have the rules. `scripts/` also has a small YouTube fetcher and a gate you can run before a note is allowed into a vault. The queue, other platforms, and the shelf where notes live stay in your project.

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

If your notes are already split, keep the split. A YouTube talk, an X clip, a WeChat video, and a doc page each stay where that project already puts them. If you cannot tell where it came from, wait, or ask. A miscellaneous folder is how a YouTube note and a WeChat note end up in the same pile.

Your inbox fields, your note paths, your timers, and another machine's `.env` stay where they are. Copying someone else's whole desk over produces a pile of paths that do not match, the next morning. When these jobs run on a schedule, the schedule lives in your project. This repo has no cron file and no service file from another machine. Some program still has to pick up the queue. You decide when that program wakes.

The program has to store which video it is. The download address the site handed out this morning will expire. A Bilibili audio link does this: opened again at night, it answers 403. Store the job as `bilibili_BV…` or `youtube_<id>`. When it runs, go back to the video page and ask for a fresh address. Replaying this morning's link produces an empty transcript of a video that did have sound.

Cookies and API keys stay out. A doc may name a setting, such as `BILIBILI_SESSDATA`, and does not print the value. The same goes for logs and notes. If the cookie is missing or expired, say that in the status. Keep using the public way to fetch the video. The cookie is optional. It helps some fetches. The skill still works without it.

## What's in the repo

| Path | What it's for |
| :--- | :--- |
| [SKILL.md](SKILL.md) | The full rules: where words may come from, when to stop, what a note has to cite, how a cookie or a key stays a name. If this page and that file disagree, follow the file. |
| [references/pitfalls.md](references/pitfalls.md) | Ten real mistakes, private details removed. Open it when a note looks done and you suspect it is not, or when a Chinese talk comes back as English junk. The stories include a queue nobody ran, a download link that expired, and a "mostly Chinese characters" transcript that was still garbage. |
| [evals/evals.json](evals/evals.json) | Three practice cases. One YouTube link has to be read from captions or speech-to-text. One empty short clip has to stay unfinished. One Chinese talk heard as English loops must not ship the tidy failure essay as the video. They catch a slide back to "I read the title." |
| [scripts/](scripts/) | A YouTube caption fetcher and a gate that refuses a note unless it names a real transcript. Queues and other platforms stay in your project. See [scripts/README.md](scripts/README.md). |

## License

MIT. You can use it, change it, and ship it with your own work. Keep the copyright notice in the copies. The full text is [LICENSE](LICENSE). Copyright (c) 2026 HappyDrunk.

# 中文

你见过这个场面。一个 YouTube、B 站、X，或者短视频的链接丢进聊天。它读了标题和简介，有时还读了链接旁边那条推文，写出一篇听着像看过的笔记。嘴里说的话，一个字没落下来。笔记像写完了。视频没人听。

这个仓库是一份 skill：一个文件夹，里面写着规矩。Agent 装上之后，下次写笔记，得先拿到这些话。标题、简介、推文、封面，可以帮它找对那条视频。找对了，还不等于听过。

## 装上之后你得到什么

你得到的不是一颗「自动总结」按钮。装上之后，链接一到，并不会马上吐出一篇摘要。你得到的是一条规矩，规矩很短：笔记只能写在嘴里的话已经落成文字之后。

**顺的时候。** 你贴一个链接。它先找官方字幕。有字幕，这段字就是文稿。没有，就看这条视频是不是早就存过一份文稿。要同一条，标题碰巧像的另一条不算。有，而且读起来还像人在说话，就用那份。两样都没有，再去下音频，把声音转成文字。三条路里有一条真正拿出了字，才许写笔记。笔记得点名这份文稿在哪个文件里，你能打开文件，对上笔记里的句子。一篇读着很顺、却说不出文件在哪的笔记，不算写完。

```text
链接
  → 有官方字幕？用字幕
  → 没有的话，这条视频存过文稿吗？像人话就用
  → 还没有，就下音频，把声音转成文字
  → 然后写笔记，笔记点名文稿文件
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

**成功就一句话：** 笔记按文稿写，并且写明了文稿文件。

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

克隆完，什么也不会自己播。你拿到的是规矩。`scripts/` 里还有一个很小的 YouTube 抓取，和一道入库前的门槛。队列、别的平台、笔记放哪，仍在你自己的项目里。

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

笔记如果本来就是分开放的，就继续分开。YouTube 的长谈、X 上的片子、微信里的视频、一篇文档，各回各的地方。来源对不上的，就等一等，或者问你一声。别因为省事，掉进一个杂物文件夹。

收件箱的字段、笔记的路径、定时、另一台机器上的 `.env`，都留在原地。把别人的整桌搬过来，第二天就是一堆对不上的路径。这些活如果要定时跑，时刻表在你的项目里。这个仓库里没有 cron 文件，也没有另一台机器的服务配置。队列还是得有一个程序去领。那个程序什么时候醒，你来定。

这个程序得记住视频是哪一条。今早网站发下来的下载地址会过期。B 站的音频链接就是这样，晚上再打开，回来的是 403。任务记成 `bilibili_BV…` 或 `youtube_<id>`。真正跑的时候，回到视频页要一个新地址。拿今早的链接再播一次，转写是空的，可视频并不是没有声音。

cookie 和 API key 不放这儿。文档可以写出一个名字，比如 `BILIBILI_SESSDATA`，不写出值。日志和笔记也一样。cookie 缺了，或者过期了，在状态里说一声。抓视频仍然走公开的那条路。cookie 是可选的。有些抓取它能帮上忙。没有它，这份 skill 也成立。

## 仓库里有什么

| 位置 | 干什么的 |
| :--- | :--- |
| [SKILL.md](SKILL.md) | 完整的规矩：字可以从哪来，什么时候该停，笔记必须点名什么，cookie 和密钥怎么只留名字。这页和那个文件要是说得不一样，以那个文件为准。 |
| [references/pitfalls.md](references/pitfalls.md) | 十条真实翻过的车，私人信息已经去掉。笔记看着完成了、你又觉得不对，或者中文口播被听成英语胡话，先打开它。里面有没人去跑的队列、过期的下载地址，还有一份「大部分是汉字」却仍然是垃圾的文稿。 |
| [evals/evals.json](evals/evals.json) | 三道练习。一条 YouTube 得从字幕或语音转文字来读。一条空的短视频得保持未完成。一条中文被听成英语打转的，不能把那篇整齐的失败作文当成视频发出去。它们用来抓住「又退回去读标题」。 |
| [scripts/](scripts/) | 一个 YouTube 字幕抓取，和一道没有真实文稿就不许写笔记的门槛。队列和别的平台仍在你的项目里。见 [scripts/README.md](scripts/README.md)。 |

## 许可

MIT。可以用，可以改，可以带着它一起发出去。副本里留着版权声明就行。全文见 [LICENSE](LICENSE)。Copyright (c) 2026 HappyDrunk。
