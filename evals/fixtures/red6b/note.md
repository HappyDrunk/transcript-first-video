---
title: Chromium 的模块化演示
source: https://www.youtube.com/watch?v=LVEfFyijQ2c
channel: ""
published: ""
type: 演示
caption_kind: manual
skill_version: fixture
transcript_path: transcript.txt
tags: [video-note]
---

## 先记住一句话

团队想把浏览器仓库拆成能各自开发、测试的组件。

## 这场在谈什么、谁

讲者介绍团队试做模块化的经验。

## 演示了什么

Chromium 是浏览器使用的开源仓库，也用于其他电子设备。 ⏱ 00:08

团队要做可独立开发和测试的组件。 ⏱ 01:08

讲者给模型一份现有工具的使用说明，再请它拆开相互牵连的代码。 ⏱ 01:39

## 关键数字与条件

他们通常为每次改动跑大量测试，再请两个人审查，之后在新旧设备上跑更多测试。 ⏱ 01:51

## 可复用做法

写一份说明，告诉模型怎样用现有工具。 ⏱ 01:39

## 翻车或别用

此前试过的模型常跑偏，生成的代码达不到团队的质量要求，仍要有人手把手带。 ⏱ 01:28

## 今天立刻动手一步

写一份现有工具的使用说明，再把它交给模型。（改写讲者做法） ⏱ 01:39

补充：片子里还强调，这些模块化拆分本来会拖很多年；模型只有在真能导航超大仓、并在测试与人工审里站住时，才算把瓶颈从「人手」挪到「想象力」。

本文略去｜无

## 原文依据
> [00:08] Chromium is an open source repository that powers web browsers, and it's also used to power a lot of other electronics
> [01:08] The goal of our team is to create modular components so that we can independently develop and test our features.
> [01:28] Quite often, the model would kind of go off rails. It would generate code that was not the level of quality that we were expecting. There was a lot of handholding involved.
> [01:39] I just tell it, "Hey, we're trying to detangle this spaghetti, no skills, no harness. Here's a memory file for how to work with some of the existing tools”.
> [01:51] We typically run a couple hundred thousand tests on every change. Then we have two humans that review the changes. We then run a couple million tests on both new and old devices.
