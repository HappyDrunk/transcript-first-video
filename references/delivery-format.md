# 交付格式：模板与合成示例

本文件规定交给读者的视频文章格式。任务目录里的 `note.md` 仍是证据底稿，保留原有 frontmatter、四节分析和 R01–R17 所需引文；交付文章不搬运引文，但每个中间论点都用 `⏱ mm:ss` 指回 `note.md` 中的一条引文。这是交付层唯一的证据链接。

交付文件按频道建文件夹，文件名为 `〈发布日期〉 〈频道〉 - 〈标题〉.md`。任务目录里的 `note.md`、`tech-elements.md` 和其他证据文件留在原位，不放进交付文章。

## 动笔前：整理技术要素

写作者先通读完整文稿，再在对应视频任务文件夹中手写 `tech-elements.md`。逐项记录讲者用来说明“东西怎么做出来、怎么运转”的技术要素，至少留意：

- 方法：采用什么办法，按什么顺序完成。
- 组件：系统、器具或流程由哪些部分组成，各部分做什么。
- 指标：用什么数值、单位、比较对象或条件衡量变化。
- 流程环节：信息或物品从哪里来，经过哪些步骤，最后到哪里。

每个要素都必须在交付稿里出现。核心技术术语第一次出现时，紧接一条 `[!note]` 术语块解释；其他技术要素第一次出现时，也用术语块或一句白话说明。解释要说清它是什么、在这里做什么，不能只换个近义词。写作后逐项对照 `tech-elements.md`，确认每项都在交付稿里有对应说明。这个清单留在任务目录，不复制进交付文章；由写作者整理，不由脚本代写。

四种类型还共用以下写法：

- 讲者列出的清单、步骤或类别必须写全；若确实略写，逐项注明略去了哪些编号或项目。
- 保留讲者提到的具体公司名、项目名和其他案例名称。案例按“之前怎样 → 讲者做了什么 → 之后怎样”写；文稿给出量化结果时，连同数字、单位、比较对象和条件一并保留。不得泛化成无名的“某公司”，不得省掉前后变化或已有结果；文稿没给出的数字或环节不补造。
- 中间论点都附 `⏱ mm:ss`，时间点必须对应本地 `note.md` 的一条引文。
- 正文解释只用下面三种标记块。类比必须说明“不成立的地方”；字幕更正不改底稿原引文。

## 共用结构

```markdown
---
title: 〈视频标题〉
source: 〈视频链接〉
channel: 〈频道〉
published: 〈YYYY-MM-DD〉
type: "〈讲座 | 访谈 | 大会 | 演示〉"
caption_kind: "〈auto | manual〉"
skill_version: 〈提交号〉
note_path: 〈对应 note.md 的相对路径〉
tags: [video-note]
---

## 先记住一句话
〈一句话概括，只写本地 note.md 已支持的内容。〉

## 这场在谈什么、谁
〈类型；视频发布日期；适合谁看。用初学者能懂的话说明主题和对象。〉

〈此处放下方对应类型的中间结构。〉

## 可复用做法
〈从本地 note.md 已支持的讲者做法中提炼。〉

## 翻车或别用
〈只写中间部分没有出现过的失败条件、边界或不适用情况；若无新增内容，写“本节没有补充中间部分之外的情况”。〉

## 今天立刻动手一步
〈写给读者，以一个可执行动词开头。若把讲者做法改写成读者行动，标明“改写讲者做法”。〉
```

### 三种解释块

术语块只解释文稿或视频里实际出现的词。解释不得伪装成讲者原话；不要在块里再塞进未解释的行话。

```markdown
> [!note] 术语：〈视频里出现的技术词〉
> 〈用白话说明它是什么、在这里起什么作用。（Claude 补充，非视频内容）〉

> [!tip] 类比（Claude 补充）
> 〈帮助理解的类比。〉
> 不成立的地方：〈指出类比不能覆盖的差异。〉

> [!warning] 字幕更正
> 字幕写作〈字幕原样〉，实为〈正确写法及必要解释〉。
```

### 初学者解释与关系表达

核心技术术语必须在正文第一次出现时用 `[!note]` 解释。写法是先写出含该词的论点，紧接术语块，再继续后续说明；不能只在标题、清单或文末词汇表中解释。其他技术要素也在第一次出现时用术语块或白话句说明。解释要告诉读者“这是什么”以及“它在这里起什么作用”；只给英文全称、直译或另一个术语不算解释。复合词要拆开说明各部分及其关系。必要时补充常见专名的类别和它在这段话里的作用；无法可靠说明且非必要的名称就删去，不编背景。

不要只留下术语、数字或步骤名称，让读者自己猜它们为何放在一起。写清谁做了什么、事情怎样变化，以及文稿明确给出的先后、对照、条件或结果。比较要说清比较对象和比较的量；效果要说明是谁报告、证据到哪一步。只有原文明确表达因果时才写因果词。文稿没有给出的比较对象、条件、结果或验证方式，不要补造。

## 四种类型模板

### 讲座、课程

按讲者自己的顺序写主线论点。讲者列出的清单、步骤或类别必须完整列出；略写时逐项注明省略编号。具名案例保留名称、之前情况、讲者做法、之后情况和原文给出的量化结果。

```markdown
## 主线论点

1. 〈论点，含技术要素首次出现时的白话解释。〉 ⏱ 00:00
> [!note] 术语：〈核心技术词〉
> 〈白话定义及其在本方法中的作用。（Claude 补充，非视频内容）〉

讲者列出的〈清单名称〉共〈数量〉项：〈按原顺序逐项列全〉。若略写，写明“本文略去第〈编号〉项〈项目〉”。 ⏱ 00:00

讲者的具名案例：〈公司/项目〉此前〈情况〉；讲者〈做法〉后，〈之后情况〉；文稿报告〈数值、单位、比较对象、条件〉。 ⏱ 00:00
```

### 访谈、对谈

按话题分段。访谈中的清单和分步说明同样必须列全，或逐项注明略去项目。保留具名案例和前后量化变化。只有原文里有人自我介绍或被点名，才写“某某说”；否则写“对话中提到”。没有意见分歧时保留小节并写“不适用”。

```markdown
## 话题

### 〈话题〉
〈按原文可确认的方式归属观点；没有明确身份时写“对话中提到”。〉 ⏱ 00:00

对话中列出的〈清单/问题/步骤〉共〈数量〉项：〈按原顺序列全〉。若略写，注明略去的编号和项目。 ⏱ 00:00

嘉宾的具名案例：〈公司/项目〉此前〈情况〉；嘉宾〈做法〉后，〈之后情况〉；文稿报告〈数值、单位、比较对象、条件〉。 ⏱ 00:00

## 意见不一致的地方
〈双方各自的理由；若无分歧，写“不适用（文稿中未出现意见分歧）”。〉
```

### 大会演讲、发布会

把台上演示、讲者给出的数据和未展示的口头主张分开。讲者列出的清单或步骤必须完整列出，或写明略去项目。保留具名案例及其前后变化、量化结果，并标清是现场演示、讲者报告还是尚未展示的说法。

```markdown
## 发布或主张了什么
〈发布内容、主张及讲者列出的完整清单；若略写，逐项标明省略编号。〉 ⏱ 00:00

## 有证据的 / 只是说法

### 演示过或给出数据
〈说明现场实际显示了什么、讲者报告了什么数据。具名案例按“之前 → 做法 → 之后”写出量和条件。〉 ⏱ 00:00

### 只是口头声称
〈明确写成讲者的说法，不写成已证实结果。〉 ⏱ 00:00
```

### 产品演示（≤10 分钟）

按实际顺序写完整操作步骤和屏幕可见结果。若讲者列出清单，全部列出或注明略去的编号。保留具名产品/项目案例、操作前状态、操作、之后变化、量化结果和适用条件。所有数字都附时间点。

```markdown
## 演示了什么

演示步骤：1.〈完整步骤〉；2.〈完整步骤〉；3.〈完整步骤〉。若略写，明确标出省略编号；每项附对应时间点。

〈具名产品/项目〉此前〈状态〉；演示者〈操作〉后，屏幕/结果变为〈之后状态〉；文稿给出的量化结果是〈数值、单位、比较对象、条件〉。 ⏱ 00:00

## 关键数字与条件
- 〈数字、单位、比较对象及出现时的条件。〉 ⏱ 00:00
```

## 合成示例一：讲座、烹饪

建议交付路径：`河谷烘焙/2026-04-12 河谷烘焙 - 面包面团怎样慢慢发起来.md`

```markdown
---
title: 面包面团怎样慢慢发起来
source: https://example.invalid/videos/cold-dough
channel: 河谷烘焙
published: 2026-04-12
type: 讲座
caption_kind: manual
skill_version: abc1234
note_path: jobs/synthetic-cold-dough/note.md
tags: [video-note]
---

## 先记住一句话
把面团放在低温环境慢慢发起，再按时间和外观检查它是否适合烘烤。

## 这场在谈什么、谁
讲座；发布日期：2026-04-12。适合第一次在家做面包、想知道怎样安排发面时间的人。

## 主线论点

1. 讲者把“低温发酵”作为主要方法：混合面团后放进约 4°C 的冰箱八小时。 ⏱ 01:10
> [!note] 术语：低温发酵（cold fermentation）
> 把面团放在较冷的环境里，让它比放在温暖处发得慢一些。（Claude 补充，非视频内容）

2. 取出面团后折叠一次，再在室温下放三十分钟。 ⏱ 03:20
3. 烤箱预热到 220°C，烘烤十八分钟。 ⏱ 05:10

讲者列出的三项检查是：表面没有干粉；面团比刚混合时大约高出一半；烤好后切面没有湿黏的生面团。 ⏱ 06:02

讲者举河岸面包房为例：之前每十个面包有六个边缘偏干；改用低温发酵并按时间检查后，最近一批只有一个偏干。 ⏱ 07:16

## 可复用做法
提前安排冷藏时间，取出后按步骤折叠和回温，再检查外观后烘烤。

## 翻车或别用
文稿没有给出适合所有面粉或所有烤箱的统一时间；这里的温度和时长是讲者这次演示采用的条件。

## 今天立刻动手一步
记下你家冰箱的温度，再按讲者给出的时间做一小份面团。（改写讲者做法）
```

合成底稿引文（不属于交付文件）：

```markdown
> [01:10] Mix the dough, then put it in a refrigerator at about four degrees Celsius for eight hours. I call this cold fermentation.
> [03:20] Take the dough out, fold it once, and leave it at room temperature for thirty minutes.
> [05:10] Preheat the oven to two hundred twenty degrees Celsius and bake for eighteen minutes.
> [06:02] My three checks are no dry flour on the surface, the dough is about one and a half times taller, and the baked center is not wet dough.
> [07:16] At Riverbank Bakery, six out of ten loaves used to have dry edges. In the latest batch, after this timing and check routine, only one was dry at the edge.
```

合成 `tech-elements.md`（任务文件内的写作清单，不随交付）：

```markdown
- 方法：低温发酵 → 交付稿在主线论点首次出现，并用术语块解释。
- 条件指标：冰箱约 4°C、冷藏八小时 → 交付稿保留数值和时间点。
- 后续流程：折叠一次、室温三十分钟、220°C 烘烤十八分钟 → 交付稿按讲者顺序列全。
- 检查方法：三项外观/成品检查 → 交付稿逐项列全。
- 案例结果：河岸面包房从十个中六个偏干到一个偏干 → 交付稿保留名称、前后数量和做法。
```

## 合成示例二：访谈、医疗流程

建议交付路径：`石桥门诊/2026-05-03 石桥门诊 - 怎样减少预约爽约.md`

```markdown
---
title: 怎样减少预约爽约
source: https://example.invalid/videos/clinic-reminders
channel: 石桥门诊
published: 2026-05-03
type: 访谈
caption_kind: auto
skill_version: abc1234
note_path: jobs/synthetic-clinic-reminders/note.md
tags: [video-note]
---

## 先记住一句话
先提醒并确认预约；有人取消时，再把空出的时间给等候的人。

## 这场在谈什么、谁
访谈；发布日期：2026-05-03。适合安排门诊预约、需要联系候补患者的工作人员。

## 话题

### 提醒和确认
对话中提到，三步是：预约前一天发短信；请患者回复确认；收到取消后联系候补名单里的下一位。 ⏱ 01:14

> [!note] 术语：候补名单（waiting list）
> 一份按顺序记录“有空位时愿意来”的人的名单。（Claude 补充，非视频内容）

### 用数量看提醒有没有帮助
对话中提到石桥门诊的记录：过去每四十个预约约有八人没来；开始提前一天发提醒、并把取消时段给候补者后，最近一月每四十个预约约有三人没来。 ⏱ 04:26

## 意见不一致的地方
不适用（文稿中未出现意见分歧）。

## 可复用做法
把提醒时间、回复确认和取消后的递补顺序写清楚。

## 翻车或别用
文稿只报告石桥门诊最近一月的记录，不能据此保证其他门诊也会有同样变化。

## 今天立刻动手一步
检查你负责的预约流程，写清提醒时间和有人取消后的联系顺序。（改写讲者做法）
```

合成底稿引文（不属于交付文件）：

```markdown
> [01:14] We use three steps: send a text the day before, ask the patient to confirm, and if someone cancels, call the next person on the waiting list.
> [04:26] At Stonebridge Clinic, we used to have about eight no-shows for every forty appointments. After the day-before reminder and filling cancelled slots from the waiting list, last month we had about three for every forty.
```

合成 `tech-elements.md`（任务文件内的写作清单，不随交付）：

```markdown
- 提醒流程：前一天发消息、收确认、取消后联系下一位 → 交付稿完整列出三步。
- 组件：候补名单 → 首次出现时用术语块解释其用途。
- 指标：每四十个预约中的未到人数 → 交付稿保留前后数量和统计范围。
- 结果边界：这是石桥门诊最近一月的数据 → 交付稿明确说明，不推广成普遍保证。
```

## 合成示例三：大会演讲、物流

建议交付路径：`沿海冷运会/2026-06-18 沿海冷运会 - 冷藏货物怎样记录温度.md`

```markdown
---
title: 冷藏货物怎样记录温度
source: https://example.invalid/videos/cold-chain
channel: 沿海冷运会
published: 2026-06-18
type: 大会
caption_kind: manual
skill_version: abc1234
note_path: jobs/synthetic-cold-chain/note.md
tags: [video-note]
---

## 先记住一句话
货物运输途中持续记温度；超过设定范围时通知司机检查。

## 这场在谈什么、谁
大会演讲；发布日期：2026-06-18。适合负责冷藏货物运输、想看清温度记录和异常处理流程的人。

## 发布或主张了什么
演讲者介绍三步流程：把记录器放进冷藏箱；运输中记录温度；超过 5°C 时通知司机检查。 ⏱ 00:48

> [!note] 术语：温度记录器（temperature logger）
> 放在货物旁边、按间隔测量并保存温度的小装置。（Claude 补充，非视频内容）

## 有证据的 / 只是说法

### 演示过或给出数据
台上演示的箱内读数是 3.8°C，屏幕显示了两次经过的地点。演示只说明这次记录器显示了这些内容。 ⏱ 02:11

演讲者报告海湾冷运的案例：过去每两百箱有十二箱超过温度范围；改用记录器并在超温时通知司机后，最近一月每两百箱有四箱超温。现场没有展示完整运输记录，因此这是讲者报告的数据。 ⏱ 03:02

### 只是口头声称
演讲者说以后会把提醒扩展到更多运输路线；现场没有展示扩展后的记录。 ⏱ 03:36

## 可复用做法
先确定温度上限，再说明超限后由谁检查并记录处理结果。

## 翻车或别用
演示读数不能说明每一箱货物都保持在同一温度；讲者也没有展示扩展路线的数据。

## 今天立刻动手一步
写下你负责的一类冷藏货物的温度上限，以及超限后谁来检查。（改写讲者做法）
```

合成底稿引文（不属于交付文件）：

```markdown
> [00:48] Our three steps are: place a temperature logger beside the goods, record the temperature during transport, and call the driver if it goes above five degrees Celsius.
> [02:11] The logger now reads three point eight degrees. This screen also shows the two stops on this trip.
> [03:02] Bayline Cold Freight used to have twelve boxes above the limit for every two hundred. After adding the logger and calling the driver on an alert, last month it was four in every two hundred. We are showing the summary, not the full route records.
> [03:36] We plan to add the alert to more routes next season.
```

合成 `tech-elements.md`（任务文件内的写作清单，不随交付）：

```markdown
- 组件：温度记录器 → 首次出现时用术语块解释是什么、做什么。
- 指标/条件：5°C 上限；演示读数 3.8°C → 交付稿保留单位和时间点。
- 流程：放置记录器、运输中记录、超限后通知司机 → 交付稿列全三步。
- 案例结果：海湾冷运从每两百箱十二箱超限到四箱 → 保留名称、比较范围、做法和数据来源边界。
```

## 合成示例四：产品演示（≤10 分钟），厨房备料

建议交付路径：`南桥厨房/2026-07-09 南桥厨房 - 怎样先用较早到货的食材.md`

```markdown
---
title: 怎样先用较早到货的食材
source: https://example.invalid/videos/kitchen-stock
channel: 南桥厨房
published: 2026-07-09
type: 演示
caption_kind: auto
skill_version: abc1234
note_path: jobs/synthetic-kitchen-stock/note.md
tags: [video-note]
---

## 先记住一句话
给每箱食材标上到货日期，再先取较早到货的那箱。

## 这场在谈什么、谁
产品演示；发布日期：2026-07-09；视频时长为 7 分 10 秒。适合管理厨房备料、希望减少食材过期浪费的人。

## 演示了什么

演示者按三步操作：1. 给到货的菜箱登记日期。 ⏱ 00:34
2. 在箱子上贴出到货日期。 ⏱ 01:20
3. 取料时先拿日期较早的箱子。 ⏱ 02:05

> [!note] 术语：先进先出（first in, first out）
> 先使用较早到货的食材，再使用后来到货的食材，避免旧食材一直留在后面。（Claude 补充，非视频内容）

讲者举南桥食堂为例：过去每周丢掉约七公斤叶菜；按日期贴标签并先用旧货后，最近四周平均每周约丢三公斤。 ⏱ 04:18

## 关键数字与条件

- 每周约七公斤降到约三公斤；这是南桥食堂最近四周的平均记录。 ⏱ 04:18
- 演示用日期标签按到货日排序；视频没有展示其他食材种类的数据。 ⏱ 05:02

## 可复用做法
把到货日期放在箱子明显处，取料时先检查日期较早的箱子。

## 翻车或别用
演示只展示叶菜的记录，不能把这组数字当成所有食材都会有的结果。

## 今天立刻动手一步
在一箱新到食材上写下到货日期，再检查货架上哪箱更早。（改写讲者做法）
```

合成底稿引文（不属于交付文件）：

```markdown
> [00:34] First, enter the arrival date for each new box of greens.
> [01:20] Next, print the date label and put it on the front of the box.
> [02:05] When taking greens, use the box with the earlier arrival date first. We call this first in, first out.
> [04:18] At South Bridge Kitchen, we used to throw away about seven kilograms of leafy greens each week. With date labels and using the older box first, the average for the last four weeks was about three kilograms per week.
> [05:02] This screen sorts boxes by arrival date. We only tracked leafy greens in this example.
```

合成 `tech-elements.md`（任务文件内的写作清单，不随交付）：

```markdown
- 方法：先进先出 → 首次出现时解释“先用早到货食材”的含义。
- 组件：到货日期登记和箱体标签 → 交付稿按演示顺序写全。
- 排序依据：按到货日期由早到晚取用 → 交付稿用白话说明。
- 指标：每周丢弃叶菜重量 → 保留南桥食堂名称、之前与之后的数据及统计范围。
```

## 规则预算说明

本包的交付要求包括固定结构、四种类型、逐点时间链接、三种解释块、Obsidian 属性、归档命名和手工技术要素清单。技术要素清单是写作者留在任务目录的过程材料，不进入交付稿，也不由脚本代写。它与 `note.md` 的 R01–R17、Coverage C、转写质量门和红测试职责不同，没有可删除或合并的旧规则。本次不改 `SKILL.md`、脚本、测试、fixture、阈值、验收标准或安装内容。
