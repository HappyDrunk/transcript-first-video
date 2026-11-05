---
title: "youtube_LVEfFyijQ2c"
source_url: "https://www.youtube.com/watch?v=LVEfFyijQ2c"
video_id: "LVEfFyijQ2c"
acquisition: "yt-dlp"
gate_passed: true
transcript_path: "artifacts/youtube_LVEfFyijQ2c/transcript.txt"
quoted_window: |-
  After I received early access to Gemini 4 Argon,
caption_language: "en"
caption_kind: "manual"
---

# youtube_LVEfFyijQ2c

Transcript: `artifacts/youtube_LVEfFyijQ2c/transcript.txt`.

## 先记住一句话

拿到 Gemini 4 Argon 后，Chromium 大仓上能一次起很多能过测的改动，瓶颈从「人手干得动多少」换成「想改成什么样」。

## 问题与做法

Chromium 是开源仓，驱动浏览器，也用于很多电子设备；它已存在约二十年，大约有 40 million 行代码，像任何长跑开源项目一样很复杂。

> [00:08] Chromium is an open source repository that powers web browsers, and it's also used to power a lot of other electronics

> [00:24] Chromium has been around for two decades. It's got about 40 million lines of code, and like any long running open source project, it's really complex.

核心引擎本身很扎实，上面叠了大量功能（书签栏、标签条、下载栏等），由很多团队一点点加上去，结果功能之间常有意想不到的互相牵扯；看起来无关的地方，底下可能连着。

> [00:33] There's the core engine itself, and that's a very solid piece of technology. Then there's a set of features on top, think the bookmarks bar, the tab strip, the downloads bar.

> [00:43] There's hundreds of features that have been added by lots of different teams, and these features have been built up incrementally, and as a result, they often have unexpected interactions with each other.

> [01:05] Things that seem unrelated can be connected underneath.

团队目标是做成可独立开发和测试的模块化组件；这本来要花很多年，所以试过很多模型想加速，但 Chromium 仓体量特殊，AI agents 很难有效导航。

> [01:08] The goal of our team is to create modular components so that we can independently develop and test our features.

> [01:14] This is something that would have taken years of time, and therefore we've tried a lot of different models in an attempt to speed up some of this work but the Chromium repository is different because of its size, and that's really hard for AI agents to navigate effectively.

讲者拿到 Gemini 4 Argon 早期权限后，过去两周往 Chromium 合进去的改动，比平常几个月还多。

> [00:00] After I received early access to Gemini 4 Argon, I've spun out more changes into Chromium in the last two weeks than I would typically do in a matter of months.

## 完整怎么做

Gemini 4 Argon 似乎已经越过了这些限制。讲者直接说要拆开这团 spaghetti，不要 skills、不要 harness，再给一份说明如何使用现有工具的 memory file，它就能一次起 20 个改动。

> [01:36] Gemini 4 Argon seems to have surpassed these limitations. I just tell it, "Hey, we're trying to detangle this spaghetti, no skills, no harness. Here's a memory file for how to work with some of the existing tools”. And it spins up 20 changes at a time.

每个改动通常会跑 a couple hundred thousand tests，再由 two humans 审；然后在新设备和旧设备上再跑 a couple million tests。Gemini 4 能一次立住 20 个全部过测的改动，讲者把这看作模型质量的清晰信号。

> [01:51] We typically run a couple hundred thousand tests on every change. Then we have two humans that review the changes. We then run a couple million tests on both new and old devices.

> [02:04] Gemini 4 can stand up 20 of these changes at a time that pass all the tests. That's one of the clearest signs of the quality of the model itself.

平常一个工程师大概一天出一个改动；20 个改动大约等于 20 天的工作量。过去受限于能不能干完这些活，现在更多受限于自己对 Chromium 走向和用户体验的想象。

> [02:13] A typical engineer might put out one change a day. 20 changes is 20 days of work.

> [02:17] We can now think about where do we want to take the Chromium repository? Historically, we were limited by our ability to do the work. Now, we're only limited by our own imagination in terms of what we can accomplish and how we can improve the experience for our users.

## 翻车或别用

模型常跑偏，生成的代码达不到期望质量，还要很多手把手；在 Gemini 4 Argon 之前，这类限制很明显。

> [01:28] Quite often, the model would kind of go off rails. It would generate code that was not the level of quality that we were expecting. There was a lot of handholding involved.

> [01:36] Gemini 4 Argon seems to have surpassed these limitations.

## 今天立刻动手一步

写一份现有工具的 memory file，并明确说要拆开 spaghetti、不要 skills、不要 harness，再让它一次起一批改动，用仓内测试和两人审把关。

> [01:39] I just tell it, "Hey, we're trying to detangle this spaghetti, no skills, no harness. Here's a memory file for how to work with some of the existing tools”. And it spins up 20 changes at a time.

> [01:51] We typically run a couple hundred thousand tests on every change. Then we have two humans that review the changes.
