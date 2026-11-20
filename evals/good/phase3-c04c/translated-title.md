---
# expect: PASS
title: Agents in Production: How OpenGov Built and Scaled OG Assist - Gabe De Mesa, OpenGov
source: https://www.youtube.com/watch?v=4uFVSLgD2Q4
channel: AI Engineer
published: 2026-06-26
type: 大会
caption_kind: auto
skill_version: bf1d74028b7025e13906ffde1dd5e8780044e55b
transcript_path: transcript.txt
tags: [video-note]
---

## 先记住一句话
要把智能体（能调用工具、连续完成任务的程序）送进生产环境，OpenGov 用 Effect 自建循环，再配上人工批准、隔离沙箱、滚动摘要、反馈评估，以及统一存放的工具和技能。

## 这场在谈什么、谁
AI Engineer 于 2026-06-26 发布大会演讲《Agents in Production: How OpenGov Built and Scaled OG Assist - Gabe De Mesa, OpenGov》，适合正在把智能体接到真实产品里、需要看一套生产做法的工程师。讲者 Gabe De Mesa 是 OpenGov AI agents 团队的软件工程师，参与建设了 OG Assist。

## 发布或主张了什么
OpenGov 把 OG Assist 做成全部产品导航栏上的同一个按钮，由各产品团队提供工具和技能；他们押注 Effect，自建智能体循环，并用代理间协议、评估、沙箱、长上下文处理和追踪，把这套系统跑在生产里。 ⏱ 00:10 ⏱ 02:30 ⏱ 05:54

## 主线讲了什么

### 议程与讲者
标题页写着 Agents in Production: How OpenGov Built and Scaled OG Assist。讲者预告会谈智能体、运行支架（harness）、评估、可观测性、追踪，以及工具和技能，并展示生产环境中的真实工作负载。 ⏱ 00:00 ⏱ 00:10 ⏱ 00:22

> [!warning] 字幕更正
> 字幕写作 Gabe de Mesa，实为 Gabe De Mesa。

议程幻灯片列出：认识 OG Assist、起源故事、押注 Effect、核心智能体循环、A2A、评估与沙箱、长上下文处理、监测与可观测性，以及工具、技能和开发工作流。讲者补充，OpenGov 不仅向客户提供人工智能，也在内部用它改进开发流程。 ⏱ 00:54 ⏱ 00:58 ⏱ 01:42

画面介绍讲者是 OpenGov 的 Software Engineer III。他自己说，自己在 AI agents 团队工作，参与建设了 OG Assist 和后面会看到的一些系统。 ⏱ 01:50 ⏱ 01:53

### OpenGov 与 OG Assist
OpenGov 是软件公司，使命是让政府更有效、更可问责。讲者说公司出售企业资源规划（ERP）软件，包括预算、采购、资产管理和许可，并说公司创立约 14 年。 ⏱ 02:09

> [!note] 术语：OG Assist
> OpenGov 各产品导航栏上的同一个助手入口，用户可以在当前产品里和智能体对话，并让它调用该产品的工具。（Claude 补充，非视频内容）

幻灯片写的是创立逾 14 年，并写 OpenGov 为州和地方政府提供企业资源规划、预算、资产管理和许可软件，OG Assist 现在把这些产品连在一起；幻灯片这段没有写出采购。 ⏱ 02:07

OG Assist 是所有产品顶部导航栏里的一个按钮，各产品套件和产品团队都为它做了工具和技能。演示里，讲者在公用事业计费产品中打开它，询问费率代码（rate codes）；智能体可以在聊天里调用工具，对照该套件里的数据查找信息。 ⏱ 02:30 ⏱ 02:56

这张产品画面还显示演示城市 Cloud City, USA。工作台指标里，「应缴总金额」（Total Amount Owed）写着 69 美元，时间标注为 As of June 18. 2026 2:22 am；「销售应收天数」（Days Sales Outstanding）旁写着 Target <30 days。 ⏱ 02:40

### 起源：一次立刻答应的投入
一位负责人拉起了名为 AI agents 的新团队并邀请讲者加入，讲者立刻答应。之后 OG Assist 开始成长，并接入各产品的后端和前端能力。 ⏱ 03:35

幻灯片标题依次写着 One bet on、agents, one、immediate yes.，并把这位负责人写成 principal engineer。 ⏱ 03:25

前端能力之一，是智能体可以看见屏幕上的内容，并对页面采取操作。演示里，讲者问屏幕上有什么、可以高亮哪些下一步；智能体在思考可用工具后，会高亮一个可点击的位置并作出说明。画面里，它把 View Accounts 标成实际的下一步。 ⏱ 04:04 ⏱ 04:24

### 押注 Effect，自建原生循环
智能体团队对 Effect 做了很大投入，讲者说这已经得到丰厚回报。Effect 是开源的 TypeScript 库，用来把代码写得更稳、结构更好；其中有类似 Zod 的模式，也有错误处理、日志和追踪，并帮助设计核心智能体循环。 ⏱ 04:42 ⏱ 04:55

> [!note] 术语：Effect
> 一个开源 TypeScript 库。这里用它来组织智能体循环，并带上模式校验、错误处理、日志和追踪。（Claude 补充，非视频内容）

他们原本使用 LangGraph，后来随着团队扩大、使用场景变化，改成自己的 Effect 原生智能体循环，以便完全掌控复杂功能。循环全面采用 Effect 后，追踪、结构化并发和日志可以贯穿整个循环，控制也更细。 ⏱ 05:54 ⏱ 06:25

幻灯片把这套循环称作运行支架（The Harness），并写：核心循环从 LangGraph 起步，现在以 Effect 原生的类型化控制流、结构化并发和端到端资源安全运行，也对循环有更细的控制。左侧示例从 `@effect/ai` 引入 `Chat` 和 `LanguageModel`。 ⏱ 05:49

讲者说明，他们使用 Effect AI 包里的聊天和语言模型：可以创建一次聊天，用 streamText 传入提示；再靠依赖注入，在需要时热替换成另一个语言模型。 ⏱ 06:59

### 用 A2A 协议对齐前后端
他们采用谷歌提出的开放代理间协议（A2A），让智能体彼此通信，并用来定义智能体路由。后端、模型和模式都按这套协议来建。画面上的 Agent Card 含智能体名称、描述等字段；讲者说，严格遵循这份规范，让前端和后端有共同的生产与消费契约，也推动了开发和对齐。 ⏱ 07:45 ⏱ 07:48 ⏱ 08:17

> [!note] 术语：A2A（agent-to-agent protocol）
> 一套开放的代理间协议。这里用来规定智能体如何描述自己、如何通信，并作为前后端共同遵守的接口。（Claude 补充，非视频内容）

幻灯片写：A2A 协议让 OG Assist 可以基于已有规范来做，而不必从零开始。协议还有扩展，例如可以加入元数据。 ⏱ 07:45 ⏱ 08:56

### 反馈、评估与人工批准
这节的口号是：发布是起点，不是终点。除了有人打电话、发邮件告知问题，主要信号来自点赞和点踩，用来判断一次回复好不好，并拿回去改进以后的回复。 ⏱ 09:18 ⏱ 09:37

他们还在持续集成（CI）里跑自动评估，对着真实补全检查：是否调用了某些工具、是否做了该做的事，以帮助提高准确性。自动评估加上收集到的反馈，用来改进工具、技能和运行支架。 ⏱ 09:58

幻灯片补充：结构化反馈和自动评估，用来判断一次改动在到达客户前后是否真的提高了质量。正面反馈界面还列出 Accurate、Helpful、Clear、Fast、Relevant 等标签。 ⏱ 09:15 ⏱ 09:20

他们还做了人工在环：如果某次工具调用需要人批准，循环会被确定地打断，并弹出界面，让人明确点接受或拒绝。讲者强调，尤其在智能体要做会改数据的操作时，必须始终把人留在控制位置，以建立信任并保证安全。 ⏱ 10:33

幻灯片标题分成 Humans Remain 和 In Control 两行。示例里，用户说 「请获取我当前的实体和当前上下文」（Please get my current entity and my current context），界面提示工具 getEntityDetails 需要批准，才能在智能体行动前得到明确许可。 ⏱ 10:30

### 沙箱里执行代码和生成文件
与安全相关的另一项做法是：智能体要执行代码或创建文件时，会在沙箱里进行。系统可以按需拉起这种短暂、隔离的空间，让智能体在里面写代码、跑代码、建文件，而不必担心危及生产系统；演示结束时，这些沙箱会被拆除。 ⏱ 11:25

> [!note] 术语：沙箱（sandbox）
> 一块临时隔离的运行环境。这里用来让智能体真正执行代码和生成文件，同时与生产系统和客户数据分开。（Claude 补充，非视频内容）

演示中，讲者请智能体为 AI Engineer Conference 2026 的与会者做一份可下载的 PDF。画面显示这次用了 4 个工具，生成文件大小为 68 KB。幻灯片写：代码在隔离沙箱中运行，因此智能体可以采取实际行动，又不必让生产系统或客户数据承担风险。 ⏱ 12:04 ⏱ 11:20

### 用滚动摘要处理长上下文
在 OG Assist 里，他们遇到过旧模型的标记上限，以及对话变长后上下文过载的问题。他们发现，滚动摘要比总是塞进最新消息更有效：在达到一定条数后给出一份持续摘要，并只保留最近 5 条或 10 条消息。若当前只谈一个话题，却要回头引用大约一百条之前的内容，就要靠记忆：对这份滚动摘要做回想，智能体才能接着往下做。 ⏱ 12:34 ⏱ 12:56

> [!warning] 字幕更正
> 字幕写作 Ogie Assist，实为 OG Assist。

> [!note] 术语：滚动摘要（rolling summarization）
> 对话变长时，不把全部旧消息原样塞进窗口，而是不断更新一份摘要，再搭配最近几条原文，方便以后回想。（Claude 补充，非视频内容）

幻灯片标题分成 Holding more、than the window 和 allows. 三行，并写：摘要会在对话变长时压缩历史，记忆则保住关键事实，让智能体在较长会话中保持连贯，也便于回想先前的消息和回复。 ⏱ 12:25

### 运行时生成界面
在 「即时界面」（UI on the fly） 这个例子里，讲者请智能体生成一篇长文，并先给出可选论题。智能体已注册一种表单原语，能在运行时把表单搭出来，当场列出选项，讲者把这称作生成式界面。 ⏱ 14:14

画面上的选项有：地方政府中的人工智能、城市气候韧性、公共教育的未来、社交媒体与民主。幻灯片写：如果智能体认为有必要或有益于增强对话体验，就可以按需创建界面。 ⏱ 14:10

### 可观测性：看不见就无法扩展
讲者的口号是：看不见的东西，你就无法扩展。Effect 的函数会自动打上跨度（span），并汇入追踪，从而可以逐层查看这些调用。台上这张追踪图来自 Effect 团队，讲者说自己附了链接：可以看到一次请求如何打到接口、处理函数，也可以给追踪做性能分析、找瓶颈；若出现失败，还能跨服务对照数据。这在要对接其他团队、接口和平台能力的智能体系统里尤其重要。 ⏱ 14:57 ⏱ 15:08 ⏱ 15:30

幻灯片写：每次智能体运行都会被端到端追踪，从而能在生产规模上调试、测量和调整行为。画面上这条示例追踪标有 13 spans，时间刻度为 40.48ms、80.96ms、121.45ms 和 161.93ms。 ⏱ 14:52 ⏱ 14:56

### 工具、技能与内部开发速度
他们不但押注 Effect，也押注工具和技能，并认为这两者就已足够。左侧示例工具叫 GetDadJoke，讲者说这是从 Effect 网站拉取的写法：先做成工具，再加入工具包（toolkit，一组工具的集合），然后把工具包注册给语言模型。若提示要生成关于海盗的爸爸笑话，智能体就可以调用这个工具。 ⏱ 16:22 ⏱ 16:24 ⏱ 16:46

幻灯片标题分成 One repo, every 和 tool. 两行。它还写：企业贡献模型把全部工具和技能放在同一个仓库里，任何工程师都能扩展 OG Assist 的能力。示例里用 `Tool.make` 定义 GetDadJoke，再以 `Toolkit.make` 做成工具包，并用 `LanguageModel.generateText` 注册。 ⏱ 16:24

讲者建议大家试用 Effect 的 Effect AI 包，并试着做自己的工具和技能。 ⏱ 17:28

OpenGov 不仅为客户做智能体，内部也大量使用 Claude 和 Cursor，并认为这对团队是很大的改变：面向客户的工具和技能之外，他们也用 Claude、Cursor 和 Claude agents 加快读代码、写代码、评审和发布。 ⏱ 17:41

幻灯片标题分成 Building agents 和 with agents. 两行，并写：Claude Code、Cursor 和云端智能体，加快团队在建设 OG Assist 时的编写、评审和发布，用的是与他们交付给客户同类的工具。收束画面写着：让我们建设能够进入生产环境的智能体。 ⏱ 17:37 ⏱ 18:21

## 可复用做法
先为会修改数据的工具调用设置批准开关，循环在得到接受或拒绝前先停住。 ⏱ 10:33

把代码执行和文件生成放到按需拉起、用完拆除的隔离沙箱里。 ⏱ 11:25

对话变长时，不要只堆最新消息：保留最近若干条原文，并维护一份可回想的滚动摘要。 ⏱ 12:56

用点赞点踩收集信号，并在持续集成里用真实补全做自动评估，再据此改工具、技能和运行支架。 ⏱ 09:37 ⏱ 09:58

做工具时按定义工具、放入工具包、再注册到语言模型的顺序接入；若要让更多人扩展能力，把工具和技能放进同一个仓库。 ⏱ 16:46 ⏱ 16:24

## 翻车或别用
讲者说押注 Effect 已经得到丰厚回报，但没有给出可核对的前后指标。 ⏱ 04:42

工作台上的 69 美元和 As of June 18. 2026 2:22 am 这一时间，是演示环境 Cloud City 里的界面数字，不能当成公司的业务结果。 ⏱ 02:40

追踪图是 Effect 团队的示例，画面上的 13 spans 和 40.48ms、80.96ms、121.45ms、161.93ms 这些刻度，也不等于他们自己系统在生产里的实测耗时。 ⏱ 15:30 ⏱ 14:52 ⏱ 14:56

滚动摘要里最近 5 条或 10 条、约一百条之前这些说法是讲者举例，文稿没有给出他们线上实际使用的条数门槛。 ⏱ 12:56

GetDadJoke 示例取自 Effect 网站，用来说明写法，不是他们生产工具的运行数据。 ⏱ 16:46 ⏱ 16:24

## 今天立刻动手一步
在你现有的智能体循环里，先挑一个会改数据的工具调用，改成必须由人点接受或拒绝后才能继续。（改写讲者做法） ⏱ 10:33

本文略去｜无

## 原文依据

> [00:10] today we're going to be talking about agents in production, specifically how OpenGov built and scaled OG Assist.
> [00:22] Uh we're going to talk about uh AI agents. We're going to talk about our harness. We're going to talk about um evals, observability, traces. We're going to talk about um tools and skills.
> [00:58] Okay, agenda. So just really quickly going to go through uh high-level what we're going to talk about today. Uh I'm going to tell you guys a little bit about OG Assist and what uh OpenGov is. I'm going to tell you guys the origin story of how this all kind of came to be. Uh we're going to talk about OG Assist's uh big bet on effect. Uh a little bit into our core agent loop. Uh we're going to talk about the A2A protocol, evals, and sandboxing. We're going to talk about how we manage long context.
> [01:42] how at OpenGov uh we use um AI not only externally uh that we uh serve to customers, but also internally to improve our development workflows.
> [01:53] Just a little bit about me before we go any further. My name is Gabe. I'm a software engineer here at OpenGov. I work on the AI agents team and I'm one of the folks that helped build OG Assist and some of the systems that you guys will be seeing today.
> [02:09] So, a little bit about OpenGov. OpenGov is a software company on a mission to power more effective and accountable government. So, OpenGov sells ERP software. That's things like budgeting, procurement, asset management, and permitting. And we were founded about 14 years ago
> [02:30] we have this thing called OG Assist and OG Assist is this little button on the top of all of our products in the in the navigation bar. And what's cool is all of our product suites and product teams have built tools and skills in order to power this button.
> [02:56] if I click this button and I open up OG Assist, it says, "Hey, I'm going to ask about rate codes, which is very specific to utility billing, the current product that I'm in." And you can see that inside of this kind of chat interface, I'm able to speak to an agent and the agent is able to make tool calls in order to look up information against data inside of that suite.
> [03:35] a little while back we we we saw that AI was really starting to take off and a principal uh spun up this new team called the AI agents team and asked me to join. And um instantly I said yes and OG Assist started to to grow and we started to integrate OG Assist into all our products. And uh not only our back-end capabilities, but also our front-end capabilities as well.
> [04:04] um see what's on the screen and and see and and and take action on what's on the page. So, you could see that uh I'm asking the agent here, "Hey, hey, what's on the screen? Can you maybe highlight uh some of the next steps that I could take?" So, you can see that the agent here is thinking. It's saying, "Okay, what tools do I have available to use?" And "Hey, let me go and highlight something that you could actually click on and and tell you more about it."
> [04:42] because um here on the Agents team, we made a huge bet to um to to bet on Effect. And suffice to say it's paid off in dividends.
> [04:55] Um we write Effect. So, Effect is this library for TypeScript. It's open source and it helps you write better um TypeScript code. Uh you know, it's got a lot of uh stuff baked in it like a a schema similar to like Zod, if you've ever used that. It's also got um things for error handling, uh for logging, for traces, for uh it's just got so much in there. It really helps write better code and structure your code better
> [05:54] So, originally we were on LangGraph and that was fine until the team really started to scale uh and our use cases started to evolve. So, we decided to move over to our own kind of Effect Native Agent Loop to have full regency over this uh Agent Loop such that if we have complex use cases or features that we need to build, we could kind of get in we we had full control of the of the Agent Loop.
> [06:25] now we're fully on Effect. So, all the cool things you get with Effect is now propagated throughout the entire Agent Loop, like the tracing, structured concurrency, the logging, everything is more fine-grained control, and it it really allows us to really unlock the full potential uh having our own Agent Loop from the ground up.
> [06:59] we're using this thing called the Effect AI package, and in that package, there's this thing called um there's a chat and a language model. So, with the chat, you can instantiate like an a chat, for example, and then you could stream text using um that that kind of stream text function, you could pass in a prompt. And what's cool is uh with a language model under the hood uh of since we're kind of doing dependency injection, we could pass in a different language model if we were to uh hot swap to another one, for example.
> [07:48] Another thing I wanted to mention is the agent-to-agent protocol. So, here on the agents team we've had a lot of success with this protocol. So, this protocol being the protocol that Google created. Um kind of an open protocol for agents to intercommunicate, but um we found this very useful for uh defining our agent routes. So, for example, in the back end and our model and our schema to follow this kind of agent protocol.
> [08:17] there's this thing called an agent card which you see here and it's got the name of the agent, a description, etc., right? And having this kind of rigorous protocol, this rigorous spec really helped drive our development and drive alignment because, you know, all we had to do was um align with this spec and follow this spec and we knew that this was kind of the contract that our front end and back end
> [08:56] really cool is A2A has a lot of extensions, right? So, you could extend the protocol uh add in like metadata. Uh there's also A2UI.
> [09:18] Feedback and evals. So, here the quote is, "Shipping is the start, not the finish."
> [09:37] the main way is we have this thumbs up and thumbs down mechanism and here someone is able to tell us, "Hey, this this worked really well. This was a great response." Or, "That wasn't a great response." And that signal we take and we're able to iterate on.
> [09:58] Um, we also have automated evals, so in in the in our CI we we have evals that run against real completions, so we could test the prompt against, "Hey, did it hit some tools? Did it do what it's supposed to do?" And that also helps with our accuracy. So, uh, those automated evals in conjunction with collecting feedback really help us, um, improve our uh, our our tools, our skills, um, our harness
> [10:33] Humans in the loop. So, this is a really cool feature we built where we deterministically interrupt the agent loop if there is a tool call approval required. So, if an agent tries to make a tool call that it needs human approval for, it'll show this UI and the human uh, can click accept or reject. So, explicitly rejecting or explicitly accepting, uh, the action that the agent is trying to make. And this ensures that, uh, you know, we're building trust and also ensuring that, uh, you know, we're being safe, especially when the agent's trying to do a mutating operation
> [11:25] whenever an agent tries to execute code or tries to create files, it does so in a sandbox. So, we gave our agents sandboxes such that it could spin up these sandboxes on demand and it could use those sandboxes to honestly write code, execute code, create files and it's kind of this safe ephemeral isolated space such that the agent can can can take action in there and not and we don't have to worry about uh any risk to you know our our production systems. Um and it's it's really cool cuz they also get uh tied uh tear down at the end
> [12:04] in this example I said, "Hey, create a PDF uh for the folks of the AI Engineer Conference 2026." And um allow me to download it so I could share it with them. And you could see that the agent created this really cool PDF inside of that sandbox.
> [12:34] inside of Ogie Assist, we have hit many hurdles like with especially with legacy models now like with uh token limits or just way too much just completely overloaded with context especially as conversations get longer. So we found that having some sort of um rolling summarization was more effective than you know always stuffing in the latest and most recent uh messages
> [12:56] um rolling summarization was more effective than you know always stuffing in the latest and most recent uh messages uh rather just you know give like a running summary after n number of messages and uh maybe you only want the like n minus five most recent messages or n minus 10 most recent messages, right? Um and it may be that you're only talking about a specific topic now, but you may want to refer to uh context earlier like a hundred messages above, then um it uh that's where kind of the the memory component comes in
> [14:14] UI on the fly. So, um in this example, I said to the agent, "Hey, generate me a long essay, but give me some examples about what the essay could be about." So, what's really cool is the agent had this primitive registered uh uh this form, and it was able to build out this form for me at runtime and give me some options of what I could choose from.
> [14:57] You can't scale what you can't see. So, um this uh this kind of section is about tracing uh and observability. Really, what's cool about Effect is you kind of get tracing out of the box.
> [15:08] about Effect is you kind of get tracing out of the box. Um you know, when you use these effect functions, they all get kind of tagged automatically with like these spans, and kind of the span gets picked up and feeds into these traces so that you can kind of get these kind of drill downs of these function calls.
> [15:30] here's an example of a trace from the effect team. I have it linked. You could see that like, "Hey, when you hit this API, go to this endpoint, to this handler." And you know, etc. And it takes And what what's really cool is you could profile all your traces, right? So, this takes a total of this many seconds and you can see where the bottleneck is here. If there's a failure, you can cross-reference data across services.
> [16:22] Tools and skills. So, uh not only did we make a big bet on effect, but we also made a big bet on tools and skills. So, we believe that tools and skills are really all you need.
> [16:46] you know, this is pulled from the effect website, but you could see, "Hey, this is how you make a tool." And then you add it to a tool kit, which is a collection of tools, and then you can register this this tool kit with the with the language model. So, for example, if you had a prompt that said, "Hey, generate some dad jokes about pirates." Well, guess what? The agent has a tool uh that can help get a dad joke.
> [17:28] um really recommend trying out this effect AI package from uh effect and um just trying out building out your own tools and skills.
> [17:41] Developer velocity. So, not only do we build agents for our customers, but we also use agents um here internally uh in OpenGov. So, we uh use a lot of Claude and Cursor uh and it's just really been a game-changer for our team. Um it's funny because we're building tools and skills for customer-facing uh agents and and that has been great, but we're also building them internally as well to help accelerate our development workflows. So, things like Claude, Cursor, Claude agents, they really help accelerate how we read, write, review code and and ship.
> [00:00][画面] Al Engineer Conference 2026
> [00:00][画面] Agents in Production: How OpenGov
> [00:00][画面] Built and Scaled OG Assist
> [00:54][画面] Agenda
> [00:54][画面] Meet OG Assist
> [00:54][画面] The Origin Story
> [00:54][画面] Betting on Effect
> [00:54][画面] The Core Agent Loop
> [00:54][画面] A2A, Evals & Sandboxing
> [00:54][画面] Long Context Handling
> [00:54][画面] Monitoring & Observability
> [00:54][画面] Tools, Skills & Dev Workflows
> [01:50][画面] Gabe
> [01:50][画面] De Mesa
> [01:50][画面] Software Engineer III @ OpenGov
> [02:07][画面] Founded over 14 years ago, OpenGov builds ERP, budgeting,
> [02:07][画面] asset management, and permitting software for state and local
> [02:07][画面] government and OG Assist now connects across all of it.
> [02:40][画面] Cloud City, USA
> [02:40][画面] Total Amount Owed
> [02:40][画面] $69
> [02:40][画面] As of June 18. 2026 2:22 am
> [02:40][画面] Days Sales Outstanding
> [02:40][画面] Target <30 days
> [02:56][画面] Tell me about my rate codes
> [03:25][画面] One bet on
> [03:25][画面] agents, one
> [03:25][画面] immediate yes.
> [03:25][画面] A principal engineer spun up a team focused on Al agents and
> [03:25][画面] asked me to join. OG Assist grew from there. We started to
> [03:25][画面] integrate deeply with our products through frontend and
> [03:25][画面] backend tools.
> [04:24][画面] I highlighted View Accounts as a practical next step
> [05:49][画面] The Harness
> [05:49][画面] The core loop started on LangGraph. It now runs fully
> [05:49][画面] Effect-native typed control flow, structured concurrency, and
> [05:49][画面] resource safety end to end. Also allows more granular control to
> [05:49][画面] the agent loop.
> [05:49][画面] import { Chat, LanguageModel } from "@effect/ai"
> [07:45][画面] Built Off The
> [07:45][画面] A2A Protocol
> [07:45][画面] The A2A protocol allows OG Assist to build off a supported
> [07:45][画面] spec, rather than from the ground up.
> [07:45][画面] interface AgentCard {
> [07:45][画面] name: string;
> [07:45][画面] description: string;
> [09:15][画面] Structured feedback and automated evals tell us whether a
> [09:15][画面] change actually improves quality before and after it reaches
> [09:15][画面] customers.
> [09:15][画面] Clear
> [09:20][画面] Accurate
> [09:20][画面] Helpful
> [09:20][画面] Fast
> [09:20][画面] Relevant
> [10:30][画面] Humans Remain
> [10:30][画面] In Control
> [10:30][画面] Please get my current entity and my current context
> [10:30][画面] Tool approval required
> [10:30][画面] getEntityDetails
> [10:30][画面] Tool Calls can be gated behind tool call approval Ul requiring
> [10:30][画面] manual intervention and explicit permission from a user prior to
> [10:30][画面] the agent taking action.
> [11:20][画面] Used 4 tools
> [11:20][画面] 68 KB
> [11:20][画面] Code runs in isolated sandboxes, so agents can take real action
> [11:20][画面] without putting production systems or customer data at risk.
> [12:25][画面] Holding more
> [12:25][画面] than the window
> [12:25][画面] allows.
> [12:25][画面] Summarization compresses history as conversations grow;
> [12:25][画面] memory persists the facts that matter, so the agent stays
> [12:25][画面] coherent across long sessions. Also helps with memory and
> [12:25][画面] recall of previous messages and responses.
> [14:10][画面] Al in Local Government
> [14:10][画面] Climate Resilience in Cities
> [14:10][画面] The Future of Public Education
> [14:10][画面] Social Media and Democracy
> [14:10][画面] Uls can be created on demand by the agent if deemed
> [14:10][画面] necessary or beneficial to enhancing the experience of the
> [14:10][画面] conversation.
> [14:52][画面] 13 spans
> [14:52][画面] 40.48ms
> [14:52][画面] 121.45ms
> [14:52][画面] 161.93ms
> [14:52][画面] Every agent run is traced end to end, giving us the visibility to
> [14:52][画面] debug, measure, and tune behavior at production scale.
> [14:56][画面] 80.96ms
> [16:24][画面] One repo, every
> [16:24][画面] tool.
> [16:24][画面] An enterprise contribution model keeps all tools and skills in a
> [16:24][画面] single repo so any engineer can extend what OG Assist can do.
> [16:24][画面] const GetDadJoke = Tool.make("GetDadJoke", {
> [16:24][画面] const DadJokeTools = Toolkit.make(GetDadJoke)
> [16:24][画面] const generateDadJoke = LanguageModel.generateText({
> [17:37][画面] Building agents
> [17:37][画面] with agents.
> [17:37][画面] Claude Code, Cursor, and cloud agents accelerate how the
> [17:37][画面] team writes, reviews, and ships building OG Assist with the
> [17:37][画面] same kind of tools we ship.
> [18:21][画面] Let's build agents that ship to
> [18:21][画面] production.
