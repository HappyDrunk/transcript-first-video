# Note examples

选读，不计入写作者必读 30 KB 预算。

[交付格式中的合成示例](delivery-format.md#合成示例一讲座烹饪)展示通俗模板。下面是完整的精炼证据版及选段。

## Building an Autonomous Engineering Org

### 证据版

```markdown
---
title: "Building an Autonomous Engineering Org - Angie Jones, Agentic AI Foundation"
source: "https://www.youtube.com/watch?v=whue9_YquGA"
channel: "AI Engineer"
published: "2026-06-28"
type: "大会"
caption_kind: "auto"
skill_version: "fda8101ef8223e3e9e3f3fa12bdd8c5f94d316bb"
transcript_path: "transcript.txt"
tags: [video-note]
---

## 先记住一句话

先让一小群工程师把团队规矩和背景写进代码仓库，好让 AI 照规矩干活；再打通平时接需求的入口，让同事直接把任务交给它。 ⏱ 07:12 ⏱ 09:07 ⏱ 10:20

## 这场在谈什么、谁

这场大会演讲于 2026-06-28 在 AI Engineer 频道发布，Agentic AI Foundation 副总裁 Angie Jones 回顾了如何用两年把 Block 约 3500 人的工程组织带向自治，适合关注工程效率和 AI 落地的研发人员与管理者。 ⏱ 00:00 ⏱ 00:02

## 发布或主张了什么

讲者指出，多数工程师已在用 AI 写代码，写代码已不再是交付的瓶颈，功能却没有更快交到客户手里。她让约 1% 的 AI Champions 先改造关键仓库，再打通工程师已有的工作入口。她给出的数据是：试点启动三个月后，AI 写的代码增加 69%，工程师自报省下的时间增加 37%，自动 PR 增至原来的 21 倍，并宣称团队达到第 5 级。随后她展示了一则 CNN Business 报道，称 Block 因 AI 裁掉近半员工，追问这番努力到底是为了什么。 ⏱ 00:47 ⏱ 00:48 ⏱ 01:24 ⏱ 04:55 ⏱ 07:12 ⏱ 10:20 ⏱ 12:35 ⏱ 12:32 ⏱ 16:14 ⏱ 16:48 ⏱ 17:21

## 主线讲了什么

### 用量上来了，交付却没有

Block 在 LLM 支持工具调用前就开始自研编码智能体 Goose，后来成为 Anthropic 首发 MCP 的设计伙伴，Goose 成为 MCP 客户端的参考实现。 ⏱ 00:22

> [!note] 术语：Goose
> Block 自研的编码智能体，可以读取仓库、执行委派并提交改动。（Claude 补充，非视频内容）

> [!note] 术语：MCP
> 模型上下文协议（Model Context Protocol），让智能体通过统一接口访问工具和资源。（Claude 补充，非视频内容）

几个月后，约 90% 的工程师已定期用 Goose、Claude Code 等工具写代码。因为交付没有提速，CEO 认为工程部门根本没用 AI。讲者手里有使用指标和 token 账单，但也承认客户确实没有更早用上新功能。 ⏱ 00:47

她把 AI 赋能分为实验、采用、产生影响三个阶段。幻灯片分别定义：「实验」是先试起来、养成习惯；「采用」是有组织地铺开；「产生影响」则是拿到可衡量的成果和提效。当时团队已到采用阶段，多数用法仍是 IDE 内提问或写样板代码。 ⏱ 01:24 ⏱ 01:28

2025 年上半年，她为全公司约 12000 人做 AI 赋能，覆盖市场、设计、财务和法务，随后受 CTO 委托建设智能体驱动的工程组织。 ⏱ 01:55

### 定义智能体工程组织与成熟度

她把这类组织定义为主要通过智能体取得工程结果的团队。工程师默认负责指挥，拆解问题、委派工作、审查并验证结果。 ⏱ 02:32

她在上一年第三季度已有模型雏形，Steve Yegge 的 Gas Town 文章启发她重整模型。 ⏱ 03:22 ⏱ 03:12

- 第 0 级，未使用（Unengaged），工作流程里完全不用 AI 工具。 ⏱ 03:32 ⏱ 03:36
- 第 1 级，辅助（Assisted），用 AI 自动补全，可能还没用过智能体模式。 ⏱ 03:32 ⏱ 03:36
- 第 2 级，对话（Conversational），和智能体聊天，还没用它产出 PR。 ⏱ 03:32 ⏱ 03:44
- 第 3 级，指挥（Directed），委派任务并审查产出。 ⏱ 03:32 ⏱ 03:52
- 第 4 级，并行（Parallel），同时运行多个智能体。 ⏱ 03:32 ⏱ 04:00
- 第 5 级，自治（Autonomous），委派完整任务，无需持续人工引导就能拿到可上线结果。 ⏱ 03:32 ⏱ 04:00

到上半年结束时，多数工程师还在第 1 到第 2 级，她的目标是第 5 级。 ⏱ 03:32

> [!warning] 字幕更正
> 字幕写作 Gastown，实为 Gas Town。 ⏱ 03:22 ⏱ 03:12

### 让 AI Champions 从关键仓库做起

缺少现成手册，工具变化太快，团队出现 AI 疲劳（AI fatigue），管理层又施加不用 AI 就会掉队的压力，讲者发现让所有人自己摸索很难。 ⏱ 04:21 ⏱ 04:55

她借用数字社区的 1/9/90 规则。约 1% 创造内容，9% 参与互动，90% 被动消费。幻灯片分别标作深度用户（Power Users）、爱动手调整的人（Tinkerers）和消费者（Consumers）。她据此聚焦关键团队里愿意钻研的少数人。 ⏱ 04:55 ⏱ 04:52

试点不是自愿报名。她花一周与技术负责人和经理沟通，挑出约 50 名工程师代表关键仓库，要求至少拿出 30% 的时间，也能接受智能体第一次跑不通。幻灯片标出这批人实际约占 1.43%。 ⏱ 05:52 ⏱ 06:00

> [!warning] 字幕更正
> 字幕写作 the 1990 rule，实为 1/9/90 Rule。 ⏱ 04:55 ⏱ 04:52

> [!warning] 字幕更正
> 字幕写作 a genetic engineering，实为 agentic engineering。 ⏱ 05:52 ⏱ 01:55

### 先在代码仓库里立好规矩

2025 年 6 月左右，她要把 AI Champions 带到第 3 级。当时模型已能写功能，代码却常偏离团队规范。她让试点成员先把上下文和规则写进共享仓库，让整个团队受益。 ⏱ 06:36 ⏱ 07:12

试点涵盖 Square、Cash App、Afterpay、Tidal，横跨前端、后端、移动、数据和基础设施，包括大型遗留单体仓库、小型服务和移动应用。JVM 团队借鉴继承的思路，在根目录放共享上下文和规则，再在服务目录叠加细则。Web 与移动端的做法有差异，Android 和 iOS 有时也要分别处理。各团队先按仓库调整，形态相近的仓库逐步收敛到相同做法。 ⏱ 07:44 ⏱ 08:17

1. 用 `agents.md` 或 `claude.md` 提供仓库上下文。 ⏱ 09:07
2. 用规则文件明确智能体必须遵守的约束。 ⏱ 09:07
3. 用斜杠命令和智能体技能（skills）固化常做的流程。 ⏱ 09:07
4. 启用 AI 代码审查并说明审查重点。 ⏱ 09:07
5. 在 PR 上标明 AI 的参与。 ⏱ 09:07

### 从已有入口委派任务

试点之外很少有人委派，试点成员也还得盯着过程。于是团队把委派接入 Jira 或 Linear 工单、GitHub 议题和 Slack。 ⏱ 09:42 ⏱ 10:20

一次 Slack 讨论中，一名工程师报告缺陷，第二名回说自己没遇到过，第三名呼叫 Goose 查证。Goose 读仓库确认缺陷，贴出三种方案，再按选定的第一种修改并发回 PR。从讨论、诊断、建单、达成一致到修复，整个过程都在 Slack 里完成，约花了 5 分钟。 ⏱ 10:38

工单也可以直接交给智能体端到端实现。首次试跑时，团队不仅做完本轮工单，还两次提前把下一轮的活接了过来。试点铺好仓库基础后，其他工程师沿用平时的工作入口就能委派。试点三个月后，AI 写的代码增加 69%，工程师自报省下的时间增加 37%，自动 PR 增至原来的 21 倍，讲者据此决定迈向第 4 级。 ⏱ 11:42 ⏱ 12:35 ⏱ 12:32

### 并行后，审查和机器先吃紧

第 4 级的 PR 产量达到原来的 3–4 倍，许多 PR 卡在等待审查。这个问题还没彻底解决，只是先「止血」（stop the bleeding）。 ⏱ 12:56

早期 AI 审查质量差，团队将其设为可选。仓库改造和模型升级后，团队在所有仓库启用 Codex 审查，让另一个智能体自动修复发现的问题并提交到同一个 PR。到人工审查时，常见的毛病已经先修过一轮。 ⏱ 13:32

并行智能体会互相干扰，笔记本也出现内存和 CPU 瓶颈。团队投入专用云工作区，让每个智能体在隔离环境里运行，随时随地都能发起并行任务。 ⏱ 14:20

### 公司世界模型、第 5 级与裁员追问

工程师当时通常同时运行 4–5 个智能体，一小群工程师开始自研编排器 Builder Bot，其中有多位 AI Champions。 ⏱ 14:49

> [!note] 术语：Builder Bot
> Block 用来协调多个智能体的编排器，可以把各路探索结果汇成跨仓库的工作计划。（Claude 补充，非视频内容）

团队以全部 25000 个仓库为基础，建立机器可读的公司世界模型，记录服务位置和依赖关系。多个智能体按需取用上下文、并行探索，再由编排器汇总成跨代码库计划，尤其适合涉及多个产品的工作。 ⏱ 15:15

讲者对第 5 级的判断是，完整任务可以交给智能体，产出可上线的结果，无需人一路引导。公司任何人都能在 Slack 呼叫 Builder Bot 修缺陷或做功能，无需会用 GitHub。 ⏱ 16:14

紧接着，画面切到 CNN Business 一篇更新于 2026 年 2 月 26 日的报道，标题写着 Block 因 AI 裁掉近半数员工，并引述 CEO 称多数公司也会这么做。 ⏱ 16:48

「这算我的错吗？」她回想，就在前一天，她还为建成自治组织、跑通团队的新工作方式而深感自豪。最后，她把问题留给听众：「但到底是为了什么？我们在做什么，又在走向哪里？」 ⏱ 16:49 ⏱ 17:09 ⏱ 17:21

> [!warning] 字幕更正
> 画面写作 CNNBusiness，实为 CNN Business。
> 画面写作 Al，实为 AI。

> [!warning] 字幕更正
> 字幕写作 company world modeled，实为 company world model。 ⏱ 15:15

> [!warning] 字幕更正
> 字幕写作 act Build-A-Bot，实为呼叫 Builder Bot。 ⏱ 16:14 ⏱ 14:49

## 可复用做法

- **按仓库选人。** 按关键仓库的覆盖面和可投入工时选试点成员。 ⏱ 05:52
- **分层放规则。** 把共享上下文和规则放到仓库根目录，让各服务维护自己的细则。 ⏱ 08:17
- **沿用工作入口。** 在团队已有的工单和讨论入口接入委派，把方案和 PR 留在原来的工作流里。 ⏱ 10:20 ⏱ 10:38 ⏱ 11:42
- **并行前检查容量。** 先看审查积压和执行环境负载。 ⏱ 12:56 ⏱ 14:20

## 翻车或别用

- **试点数据有限。** 三个月的数据缺少比较基数和统计范围。 ⏱ 12:35
- **第 5 级由讲者判定。** 演讲未给出线上缺陷率或回滚数据。 ⏱ 16:14
- **审查仍会积压。** 自动审查和修复缓解了积压，审查瓶颈仍未完全解决。 ⏱ 12:56 ⏱ 13:32
- **裁员未给内部数据。** 相关细节仅来自现场展示的 CNN Business 报道，讲者未补充公司内部口径。 ⏱ 16:48

## 可以怎么用、可以拿去讨论什么

- **试点前提。** 先请工程负责人批下约 30% 工时，再按约 1% 比例选关键仓库代表试点；若要多智能体并行，还需配套隔离云工作区。 ⏱ 05:52 ⏱ 14:20 ⏱ 04:52
- **排查交付瓶颈。** 拿近期任务对照 0–5 级并看 PR 审查等待时间，判断该先解代码产出、审查积压还是跨仓依赖。 ⏱ 03:32 ⏱ 12:56 ⏱ 15:15
- **与管理层对齐角色变化。** 交付提速后省下的时间投向哪里，哪些职责转向拆任务与验收，人事决策还缺哪些数据？ ⏱ 02:32 ⏱ 17:21

本文略去｜无

## 原文依据

> [00:00][画面] ANGIE JONES, VP OF AGENTIC AI FOUNDATION
> [00:02] So, I've spent the last couple of years transforming Block's 3,500-person engineering org into an autonomous one.
> [00:22] early. We were building Goose, our internal coding agent, even before the LLM supported tool calling. We worked with Anthropic as design partners for the initial release of MCP, and Goose became the reference implementation for the MCP client. So, internally, our most
> [00:47] After a couple of months, about 90% of our engineers were now using tools like Goose and Claude Code regularly to generate code. So, on paper, it looked like we were all in on AI. But our CEO was convinced that engineering wasn't using AI at all. Like, they couldn't be, right? As far as he was concerned, because we weren't shipping any faster. Well, I had the numbers, both the metrics and the token bills. So, I knew that engineering was, in fact, using AI, but he was right. Features certainly weren't making it to our customers any faster. So, I began to dig into this a
> [00:48][画面] Code is not the
> [00:48][画面] bottleneck.
> [01:24] I think of AI enablements in three phases: experimentation, adoption, and impact. I'd say that we surpassed the experimentation phase as 90% of our engineering org was using AI, but they still were kind of using it inside of their IDE, you know, asking questions or writing boilerplate code. And I knew that if we really wanted to see impactful outcomes, then we needed a way to integrate AI into how we built and ship.
> [01:28][画面] Experimentation
> [01:28][画面] Adoption
> [01:28][画面] Impact
> [01:28][画面] explore and normalize Al
> [01:28][画面] scale usage through
> [01:28][画面] drive measurable outcomes
> [01:28][画面] usage
> [01:28][画面] structure and consistency
> [01:28][画面] and productivity gains
> [01:28][画面] HERE
> [01:55] I spent the first half of 2025 leading AI enablement for our entire company. So, 12,000 employees across every function, marketing, design, finance, legal. Now, our CTO tasked me with building an agentic engineering org.
> [02:32] of terms, I defined an agentic engineering org as one where engineers leverage AI agents as their primary means of producing engineering outcomes. So, that meant that our engineers needed to treat agents as core members of their engineering workflow. Not just using AI to help them write code here and there, but actually working with agents. Decomposing problems, delegating work, reviewing and verifying what was done. And we wanted them directing the work as their default way of operating. But, of
> [03:12][画面] Stage 3
> [03:12][画面] Stage 0
> [03:12][画面] Stage 1
> [03:12][画面] Stage 2
> [03:12][画面] adapted from Steve Yegge's Gas Town article
> [03:12][画面] Stage 4
> [03:12][画面] Stage 5
> [03:22] And while I had some form of this model in Q3 of last year, Steve Yegge's Gastown article helped me reorganize it into a better model.
> [03:32] So, stage zero is where the engineer doesn't use AI tools in their workflow at all. Stage one, they use AI to auto complete, but they've never used it in agent mode, maybe. Uh stage two is where engineers are chatting with agents, but not using it to produce any PRs. Stage three, engineers are delegating tasks to agents and reviewing the output. Those at stage four are running multiple agents in parallel. And then stage five is that final boss where engineers are delegating complete tasks to agents and the agent is able to produce shippable results without the human necessarily needing to guide it. So, I'd say by the end of the first half, the bulk of our engineers were between stages one and two. And I needed to get them to stage five.
> [03:36][画面] Unengaged
> [03:36][画面] Assisted
> [03:44][画面] Conversational
> [03:52][画面] Directed
> [04:00][画面] Parallel
> [04:00][画面] Autonomous
> [04:21] Now, I wasn't quite sure how to get 3,500 engineers to that level, especially when one, this is all highly experimental, right? There's no playbook, again, for any of this. Um two, things were moving so fast that what might be a best practice this week could be outdated when a new tool or a new model drops next week. And honestly, this was leading to AI fatigue. And then three, people were already feeling turned off by the top-down pressure from leadership to essentially AI or die.
> [04:52][画面] 1/9/90 Rule
> [04:52][画面] 1%
> [04:52][画面] Power Users
> [04:52][画面] 9%
> [04:52][画面] Tinkerers
> [04:52][画面] Consumers
> [04:52][画面] 90%
> [04:55] So, I thought about the 1990 rule where in digital communities about 1% create, 9% interact, and 90% passively consume. And this maps almost perfectly to how engineers adopt AI. So, you'll have a small percentage that'll deep dive and start creating agentic patterns and discovering useful techniques for working with agents. You'll have some that might tweak the agent's MD file here or there. But most people aren't going to spend the extra cycles to figure this stuff out. So, I realized that if my AI strategy depends on every individual leveling themselves up, I'm never going to see that broad impact. So, I leaned into this model. And I used it to my advantage. Instead of focusing on all 3,500 engineers, I decided to focus on forming the 1%, the power users, from our most critical teams.
> [05:52] So, I started an AI champions program where I handpicked about 50 engineers across the company who could pioneer what a genetic engineering looks like for their team. Now, this was not a call for volunteers, all right? I needed to be strategic about the selection. I needed engineers who were willing to dedicate at least 30% of their time to investing in AI enablement. I needed those who wouldn't be discouraged by the non-deterministic nature of AI and give up on it all when it didn't work out of the box, which it often did not, right? So, I spent the week talking to tech leads and managers to find the 50 engineers who could represent our most critical repositories.
> [06:00][画面] actually ~1.43%
> [06:36] Now, remember at this point, most of our engineers were between stages one and two where they're chatting with AI but not really using it to produce PRs. So, I wanted to get the AI champions to stage three. This was about June 2025. So, the models were decent enough to write a feature for you, right? But chances were pretty high that the code wouldn't conform to your team's conventions and standards. So, developers didn't trust the agents enough to delegate work to it yet. So, the first area that we focused on was making our repos AI ready.
> [07:12] My theory here was if I can get engineers to embed AI directly into their repos, then not only would the agents perform better but the entire team would benefit, not just the 1%. And the repos are a central point of reference for every engineer that's contributing code. So, to make their repos AI friendly, they added assets like contacts and rules files so that agents could reliably understand and navigate the code base as well as contribute to it.
> [07:44] Now, when building the AI champions, I made sure that we have folks from every corner of Block engineering: Square, Cash App, Afterpay, Tidal, across front end, back end, mobile, data, infra, right? Um we covered repos of all shapes and sizes, the nasty big legacy massive mono repos, the smaller services, mobile apps, right? And that mix let us pressure test patterns across very different engineering realities so that we could quickly see what actually scales.
> [08:17] As expected, mono repos came with their own challenges. But my JVM devs were already strong in inheritance patterns, so we set shared contexts and rules at the root, then layered more specific ones at the service levels. We also learned fast that what worked for web didn't necessarily work for mobile. So Android and iOS even needed different approaches at times. So instead of forcing a one-size-fits-all solution, each champion figured out what worked for their repo, and then teams with similar shapes and sizes naturally converged on the same tools and patterns. And honestly, engineers loved this, right? We let them choose what made sense for their repo instead of pushing a top-down mandate on them.
> [09:07] So we ended up with a standard set of components that would make a repo AI friendly, but again, customized for each team's needs. Some context files like agents.md or claude.md to provide the agent with repo guidance, rules files to provide the agent with some guardrails, repeatable workflows like slash commands and later agent skills, um an enabled AI code reviewer, preferably with some instructions on what matters and what it should review. And then AI attribution on PRs.
> [09:42] So at this point, we've done a lot of great work and technically, we do have the agents writing PRs, but I had a couple of concerns, right? Not many outside of the AI champions had gotten to this level where they were delegating work to agents. And the idea is to have the work of the 1% lift everyone up. So, we weren't there yet. And then even with the champions, they were delegating, but they were still kind of babysitting the process. So, I wanted to explore if we could delegate work to the agents in a more hands-off approach and make it easier for others outside of the champions program to do so as well.
> [10:20] So, there's three common places where engineers receive requirements for work. Issue trackers like Jira or Linear, GitHub issues, and informally in Slack. I wanted to be able to delegate work to the agents from any of these places. And the champions implemented all three.
> [10:38] So, true story. We were in Slack one day, an engineer saw a bug with the product and wrote, you know, like, "Hey, I saw this bug. Anybody else seen it?" So, engineer two responds to that and goes, "Mhm, no, I hadn't seen that one." Engineer three @goose right there in Slack and says, "Hey goose, have you seen this bug before? Like, can you can you go and check if this is a bug?" So, goose goes to the repo, it like pulls the files down, and says, "Yeah, this is a bug. Here it is right here. But, here's also three options of how you might implement a solution, right?" Right there in Slack, code snippets. And so, engineer one goes, "I like option one." Engineer two goes, "Yeah, yeah, me too." So, engineer three says, "Hey goose, go implement option one." Goose does so, returns with a link to the PR, right? So, the entire cycle from discussion, diagnosis, issue creation, alignment, and the fix took like 5 minutes all right there in Slack. Very
> [11:42] Um engineers were also able to assign linear and Jira tickets, as well as GitHub issues to an agent, and have the agent implement the work end to end. So, now the agents have become a part of the sprint. This blew everyone's minds. The first time we did this, the team ran out of work and had to pull in more tickets like twice, right? So, of course, engineering managers, product teams, they love this flow. And the beauty about these flows is that all engineers didn't necessarily have to learn a new skill. The champions had already laid the foundation so that agents were able to work well within these repos, and they worked well all of this worked well because it made delegation feel native to how people already work.
> [12:32][画面] ↑37%
> [12:32][画面] ↑69%
> [12:32][画面] Reported time savings
> [12:32][画面] Al-authored code
> [12:32][画面] ↑21x
> [12:32][画面] Automated PRs
> [12:35] At this point, it had been 3 months since launching the champions program, and we were seeing great results. AI-authored code was up by 69% reported time savings increased 37%, and automated PRs increased 21 times. We were ready to pursue stage four, multi-agent parallelism.
> [12:56] And with our setup, honestly, moving to stage four was almost free. We were pretty good at delegating work to the agents now. But, this stage introduced several new challenges that we needed to solve. Engineers are now tripling, quadrupling the number of PRs that they're producing, but the PRs are stuck waiting for code reviews, right? So, people struggled to stay on top of code reviews even before we added AI to the mix, so you know that it's bad now. And I'll be honest, this isn't a totally solved problem, but I'll share how we did stop the bleeding a bit.
> [13:32] We absolutely had to get the bots to help us review PRs. So, earlier in the process, this was optional. Mostly because the AI code reviewers sucked so badly, and we were just pissing the engineers off by having them use them. But now, with the repo readiness work that the champions had done, coupled with better models and tools, shout out to Codex, uh we were getting much better results here. So, we enabled Codex on all the repos, and we also created an auto-fix loop where if Codex identified issues, another agent will automatically fix those issues and commit them to the PR. So, now, at least people would no longer complain about not wanting to review sloppy PRs from bots, right? By time they got to them, they were in pretty good shape.
> [14:20] Another issue, specifically when running multiple agents in parallel, was that the agents were bumping into each other as they were trying to work. And more importantly, our machines couldn't handle the load anymore. Like, engineers' laptops were running out of memory. CPU was choking, you know? So, we invested in dedicated cloud workspaces where each agent ran in its own isolated environment. And this allowed us to easily run them in parallel and from anywhere.
> [14:49] So, at this point, the engineers are cooking. They got four or five agents running at any given time, and that number is growing. So, a small group of engineers, including many of the AI champions, started building our own orchestrator to coordinate all of these agents, Builder Bot. And we needed Builder Bot to get us to an autonomous engineering org.
> [15:15] We realized that if we're trying to build anything close to an autonomous engineering org, the agents need to understand where everything lives and what depends on what. So, we built a company world modeled based on the entirety of our 25,000 repo code base, right? And this was a machine-readable view of every single service and how they all connect. And this allowed orchestrators and the agents that they delegated to to pull context in as needed and understand the landscape as they implement. And this enabled multiple agents to explore different parts of the system in parallel, each building their own understanding and then come back together and have the orchestrator put all of this together, right? Put in a plan that spans across multiple code bases, which was especially useful for us as we were building offerings that spanned multiple products.
> [16:14] Now, with this, we had successfully reached stage five, where engineers are delegating complete tasks to agents. The agents are able to produce shippable results without human hand-holding. In fact, this wasn't even limited to engineers anymore. Anyone at the company could act Build-A-Bot in Slack and have it fix a bug or implement a new feature. They didn't even need GitHub.
> [16:48][画面] CNNBusiness
> [16:48][画面] Block lays off nearly half its staff because of Al.
> [16:48][画面] Its CEO said most companies will do the same
> [16:48][画面] UPDATED FEB 26, 2026
> [16:49] You know, of course, all layoffs are tough, but this one felt different. I had so many questions. Was this my fault?
> [17:09] Just the day before I had felt so proud. I was in awe of the way we were working, feeling quite accomplished that I successfully built an autonomous
> [17:21] But to what end? I guess I'll leave you all with a few questions. What are we doing? Where are we heading?
```

### selection.md

```text
00:00–00:47 | 开场与早期采用 | 留 | 交代组织规模、自治目标和自研编码智能体的起点
00:00 | [幻灯片 1] 演讲标题 | 留 | 标题页给出主题和讲者职务
00:00 | [画面] ANGIE JONES, VP OF AGENTIC AI FOUNDATION | 留 | 姓名和职务见标题页人名条
00:00 | [画面] angiejones.tech | 略 | 网站水印不承载演讲内容
00:24 | [幻灯片 2] 早期使用编码智能体 | 留 | 交代团队的早期采用
00:47–02:32 | 交付瓶颈与新任务 | 留 | 高使用率没有加快交付，讲者区分赋能阶段并接到新任务
00:48 | [幻灯片 3] 交付瓶颈 | 留 | 提炼代码产量与交付速度的差别
00:48 | [画面] Code is not the | 留 | 提炼代码产量与交付速度的差别
00:48 | [画面] bottleneck. | 留 | 提炼代码产量与交付速度的差别
01:28 | [幻灯片 4] AI 赋能阶段 | 留 | 给出各阶段说明和当前位置
01:28 | [画面] Experimentation | 留 | 图示补充阶段名称、定义和当前位置
01:28 | [画面] Adoption | 留 | 图示补充阶段名称、定义和当前位置
01:28 | [画面] Impact | 留 | 图示补充阶段名称、定义和当前位置
01:28 | [画面] explore and normalize Al | 留 | 图示补充阶段名称、定义和当前位置
01:28 | [画面] scale usage through | 留 | 图示补充阶段名称、定义和当前位置
01:28 | [画面] drive measurable outcomes | 留 | 图示补充阶段名称、定义和当前位置
01:28 | [画面] usage | 留 | 图示补充阶段名称、定义和当前位置
01:28 | [画面] structure and consistency | 留 | 图示补充阶段名称、定义和当前位置
01:28 | [画面] and productivity gains | 留 | 图示补充阶段名称、定义和当前位置
01:28 | [画面] HERE | 留 | 图示补充阶段名称、定义和当前位置
01:52 | [幻灯片 5] 智能体工程师 | 留 | 提出工程师工作方式的转变
02:32–04:21 | 组织定义与成熟度 | 留 | 给出工程师与智能体协作方式和各级标准
02:48 | [幻灯片 6] 核心协作者 | 留 | 说明智能体在工程流程中的角色
03:12 | [幻灯片 7] 成熟度模型 | 留 | 给出级别简称和改编来源
03:12 | [画面] Stage 3 | 留 | 图示补充级别编号和改编来源
03:12 | [画面] Stage 0 | 留 | 图示补充级别编号和改编来源
03:12 | [画面] Stage 1 | 留 | 图示补充级别编号和改编来源
03:12 | [画面] Stage 2 | 留 | 图示补充级别编号和改编来源
03:12 | [画面] adapted from Steve Yegge's Gas Town article | 留 | 图示补充级别编号和改编来源
03:12 | [画面] Stage 4 | 留 | 图示补充级别编号和改编来源
03:12 | [画面] Stage 5 | 留 | 图示补充级别编号和改编来源
03:36 | [画面] Unengaged | 留 | 图示给出级别简称
03:36 | [画面] Assisted | 留 | 图示给出级别简称
03:44 | [画面] Conversational | 留 | 图示给出级别简称
03:52 | [画面] Directed | 留 | 图示给出级别简称
04:00 | [画面] Parallel | 留 | 图示给出级别简称
04:00 | [画面] Autonomous | 留 | 图示给出级别简称
04:21–06:36 | 推广阻力与试点选择 | 留 | 按参与分布挑选能代表关键仓库并投入工时的人
04:24 | [幻灯片 8] 如何提升成熟度 | 留 | 从目标转入推广难题
04:52 | [幻灯片 9] 参与分布 | 留 | 显示参与比例及对应人群
04:52 | [画面] 1/9/90 Rule | 留 | 图示给出规则名称、比例或人群名称
04:52 | [画面] 1% | 留 | 图示给出规则名称、比例或人群名称
04:52 | [画面] Power Users | 留 | 图示给出规则名称、比例或人群名称
04:52 | [画面] 9% | 留 | 图示给出规则名称、比例或人群名称
04:52 | [画面] Tinkerers | 留 | 图示给出规则名称、比例或人群名称
04:52 | [画面] Consumers | 留 | 图示给出规则名称、比例或人群名称
04:52 | [画面] 90% | 留 | 图示给出规则名称、比例或人群名称
05:52 | [幻灯片 10] AI Champions | 留 | 显示试点成员占比
06:00 | [画面] actually ~1.43% | 留 | 画面给出试点实际占比
06:36–09:42 | 仓库改造 | 留 | 解释团队规范问题、仓库差异和可按需调整的组件
06:40 | [幻灯片 11] 第 1 到第 2 级 | 留 | 标明试点启动前的位置
07:12 | [幻灯片 12] AI 友好仓库 | 留 | 说明仓库改造方向
07:44 | [幻灯片 13] 代码库差异 | 留 | 提示按仓库形态调整
09:04 | [幻灯片 14] 组件图标预告 | 略 | 后续页给出组件名称
09:20 | [幻灯片 15] 仓库上下文与规则 | 留 | 列出智能体需要的上下文与规则
09:20 | [画面] 25 | 略 | 卡片数字没有单位或指标定义
09:28 | [幻灯片 16] 可重复工作流 | 留 | 补充工作流组件
09:28 | [画面] 25 | 略 | 卡片数字没有单位或指标定义
09:36 | [幻灯片 17] 代码审查 | 留 | 补充代码审查组件
09:36 | [画面] 25 | 略 | 卡片数字没有单位或指标定义
09:42–12:56 | 委派入口与结果 | 留 | 通过现有入口委派完整任务并报告试点结果
09:44 | [幻灯片 18] 第 3 级 | 留 | 标示已有任务委派和审查能力
10:24 | [幻灯片 19] 从现有入口委派 | 留 | 呈现多入口委派目标
11:28 | [画面] anglejones.tech | 略 | 网站水印不承载演讲内容
12:32 | [幻灯片 20] 试点结果 | 留 | 列出三项指标和变化幅度
12:32 | [画面] ↑37% | 留 | 画面显示指标名称或变化幅度
12:32 | [画面] ↑69% | 留 | 画面显示指标名称或变化幅度
12:32 | [画面] Reported time savings | 留 | 画面显示指标名称或变化幅度
12:32 | [画面] Al-authored code | 留 | 画面显示指标名称或变化幅度
12:32 | [画面] ↑21x | 留 | 画面显示指标名称或变化幅度
12:32 | [画面] Automated PRs | 留 | 画面显示指标名称或变化幅度
12:56–14:49 | 并行的瓶颈 | 留 | 介绍审查积压、自动修复和隔离云工作区
12:56 | [幻灯片 21] 并行带来的问题 | 留 | 引出并行执行后的瓶颈
13:12 | [幻灯片 22] 审查积压 | 留 | 点出 PR 产量上涨后的审查负荷
13:36 | [幻灯片 23] 自动审查和修复 | 留 | 展示缓解积压的做法
14:24 | [幻灯片 24] 本地机器吃紧 | 留 | 对应并发负载下的资源瓶颈
14:48 | [幻灯片 25] 第 4 级 | 留 | 标示并行能力
14:49–16:49 | 跨仓库编排与自治 | 留 | 说明世界模型、编排器和第 5 级主张
15:12 | [幻灯片 26] 世界模型过渡页 | 略 | 第 27 张给出完整标题
15:20 | [幻灯片 27] 世界模型 | 留 | 点明跨仓库协作所需的上下文
16:16 | [幻灯片 28] 第 5 级 | 留 | 标示讲者报告的自治水平
16:48 | [幻灯片 29] CNN Business 报道 | 留 | 给出报道标题、媒体和更新日期
16:48 | [画面] CNNBusiness | 留 | 现场报道显示媒体、标题或更新日期
16:48 | [画面] Block lays off nearly half its staff because of Al. | 留 | 现场报道显示媒体、标题或更新日期
16:48 | [画面] Its CEO said most companies will do the same | 留 | 现场报道显示媒体、标题或更新日期
16:48 | [画面] UPDATED FEB 26, 2026 | 留 | 现场报道显示媒体、标题或更新日期
16:49–17:33 | 结尾反思 | 留 | 保留讲者对裁员的反思、前一天的心情和结束提问
17:12 | [幻灯片 30] 讲者特写 | 略 | 没有新增幻灯片正文
17:20 | [幻灯片 31] 讲者特写 | 略 | 没有新增幻灯片正文
17:28 | [幻灯片 32] 讲者特写 | 略 | 没有新增幻灯片正文
```
