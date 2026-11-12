# 视频笔记交付格式

任务目录里的 `note.md` 就是给读者看的成稿。检查通过后，把这份文件原样拷贝到对应频道文件夹，文件名用 `〈发布日期〉 〈频道〉 - 〈标题〉.md`。拷贝保留 Obsidian 属性、正文和文末引文。任务目录留存 `note.md`、`selection.md`、文稿和状态。已有历史文件按归档约定保全。

## 动笔前通读和取舍

写作者通读文稿，按原顺序切成意思完整的单元。相邻段落有不同用途时分成不同单元。手写 `selection.md`，每个单元一行，格式为 `时间范围 | 类别 | 留或略 | 一句理由`。理由说明这段对理解主张或照着做有什么作用。`selection.md` 取代 `tech-elements.md`，并承接原 inventory 的覆盖职责，只留在任务目录。长短视频均用这份记录，`inventory.md` 和分块 `chunks/NN.notes.md` 退出写作流程。写作者负责取舍、写正文和挑原话。

- **必须留**核心主张，步骤和实际顺序，讲者列出的清单，支撑主张的数字，具名案例，以及理解主张必需的方法、组件、指标和流程环节。
- **应当略**寒暄、广告和口播、已说过的重复内容、与主题无关的闲聊。一段重复里新增了条件、例外或结果时，单独划出并留下新增信息。
- **正文来自标「留」的单元。** 保留讲者清单的项目和顺序。遇到确实独立的、可按取舍规则略去的列举单元，写清原编号和项目，并在「本文略去」列出时间范围。核心清单、关键步骤和前置条件按「必须留」处理。
- **具名案例保留可核对的细节。** 交代谁或哪个项目、之前怎样、采取了什么做法、之后怎样。文稿有量化结果时连同比较对象、单位、时间范围和适用条件一并保留。只写文稿给出的信息。
- **解释留用的技术要素。** 核心术语第一次以相关词义出现时紧接术语块。其他技术要素第一次出现时可用术语块或一句白话交代它是什么、在这里做什么。专名恰好也能作术语时，按文稿该处词义找首次用作术语的位置。

S01 要求各时间范围按原顺序连续覆盖全文。区间左闭右开，从文稿开头排到可核对的终点，相邻区间首尾相接，每条字幕都能归属一个单元。缺文件、范围有空缺或重叠、覆盖不达标均报 FAIL。标「留」的单元至少九成且不少于三个须命中文末证据，即 `max(3, ceil(0.9 × 标留单元数))`。只有真实时间锚落在相应区间的有效引文才计入。同一个单元只计一次，少于三个留用单元无法通过。长视频还须通过 C02，按完整文稿检查至少三个四分位。

标「略」的区间合计时长严格超过全片一半时只报 WARN，正好一半不触发。照实划分单元和记录理由。Phase 3 的复核者会对照文稿查看略项是否漏掉核心主张、步骤或支撑数字。

## 正文、原文依据和检查

- **中间论点 → 引文。** 每段或每个列表项写清一个论点，附至少一个 `⏱ mm:ss`。多个证据可以分别附时间点。正文的每个 `⏱` 先配同一文件「原文依据」里的相同时间，没有才取 15 秒内唯一最近的一条。找不到或最近候选等距都报 FAIL，改用可唯一定位的准确时间。同文字体系仍检查至少三个共有内容词元。访谈文稿没有分歧时用固定的不适用说明。没有事实陈述的格式说明无需时间点。
- **引文 → 文稿。** 「原文依据」紧接「本文略去」，是全文最后一个二级标题。每行写一条 `> [mm:ss] 文稿原话`，小时级可用 `hh:mm:ss`。每条引文从原文连续取至少 40 字符，可跨相邻字幕。核对时折叠空白和大小写，字幕行首时间不算原话。时间戳距引文覆盖的最近一条字幕起点最多 15 秒，等距时取较早起点。原话保留字幕原拼写。
- **引文 → 正文。** 文末每一条引文都须被正文至少一个 `⏱` 实际用到。同一引文可以支持多处正文，只在文末列一次。文末每个秒数只能登记一条引文。同一秒起始的两段原话须取能覆盖两段的连续原文，合成一条，保留中间原话及原顺序。
- **数字和专名 → 引文。** 三种解释块之外，正文里的事实性数字和专名须有文末原话支持。只有「这场在谈什么、谁」可以原样使用 frontmatter 的 `published`、`channel`、`title`。其他小节复用这些值时也要有文末引文。带 `⏱` 的论点从它实际指到的引文核对，其他事实性表述也要能从文末核对。例中保留原话里的专名拼写，中文译名可随写，方便对照。保留 1B 数字归一化和 2B 的口述小数支持。列表项开头的 Markdown 序号按格式处理。`⏱` 和略去时间范围属于各自的字段。
- **取舍 → 正文。** 正文用了标「略」的单元，判 FAIL。写稿后回看每段所用引文，核对实际文稿位置落在留用单元内。15 秒容差用于时间链，不能跨入略去区间或替邻近单元凑覆盖。时间和逐字核对能查到可定位的素材，写作者还须通读确认正文没有转述略去内容。「本文略去」这行只列话题和时间范围。
- **无可靠时间戳。** 保全输入并报「缺时间戳，请用带时间戳的转写重跑」。秒数须来自真实字幕或转写时钟，这类文稿暂不能交付。C02 的字符位置兜底仍保留，用于四分位诊断。
- **长度提示。** 英文文稿的中文正文汉字数超过全文英文词数的 1.2 倍时只报 WARN。按 Unicode 汉字计正文可读文字，排除 YAML、时间点、「本文略去」、「原文依据」和三个补充块。分母用完整英文文稿的英文词数，去掉字幕时间戳，英文词按常规词边界计，词内撇号或连字符保留。等于 1.2 不触发，倍数由 Phase 5 按作者阅读感受校准。两项 WARN 都不计失败和修订轮次。检查输出区分 FAIL、WARN 和未检查。

## 共用模板

```markdown
---
title: 〈视频标题〉
source: 〈视频链接〉
channel: 〈频道〉
published: 〈YYYY-MM-DD〉
type: 〈讲座、访谈、大会、演示四选一〉
caption_kind: 〈auto 或 manual〉
skill_version: 〈提交号〉
transcript_path: 〈相对任务目录的文稿路径〉
tags: [video-note]
---

## 先记住一句话
〈一句话概括留用内容中读者最该记住的事。〉

## 这场在谈什么、谁
〈类型、视频发布日期和适合谁看。这里可原样使用 published、channel、title。〉

〈按类型填入中间部分。〉

## 可复用做法
〈把有原文依据的做法写成读者可以复用的步骤或判断。〉

## 翻车或别用
〈写中间部分没说过的失败条件或适用边界。若没有新增边界，写“本节没有补充中间部分之外的情况”。〉

## 今天立刻动手一步
〈写给读者的一项可执行行动，最多两句，附支持它的时间点。改写讲者做法时写明“改写讲者做法”。〉

本文略去｜〈话题（起止时间）、话题（起止时间）〉

## 原文依据
> [mm:ss] 〈从文稿逐字摘录的连续原话〉
```

「本文略去」独占一行，放在行动段之后、原文依据之前。没有略去单元时写 `本文略去｜无`。任务目录和频道目录使用同一份 YAML。`transcript_path` 从任务目录解析，拷贝后仍表示原任务里的文稿位置。单稿属性中移除 `note_path`。任务入口仍须核对当前文稿来源及质量门。

### 三种标记块

```markdown
> [!note] 术语：〈字幕中的词或可追溯的写法〉
> 〈用白话说明它是什么、在这里起什么作用。（Claude 补充，非视频内容）〉

> [!tip] 类比（Claude 补充）
> 〈帮助读者理解的类比。〉
> 不成立的地方：〈具体说明哪一点不能类推。〉

> [!warning] 字幕更正
> 字幕写作〈文稿原样 X〉，实为〈正确写法 Y〉。
```

术语词条按斜杠和括号拆别名，连字符和空格等同，至少一种写法须在文稿出现。字幕更正的 X 要能在文稿核对，合规的 Y 可用于正文和术语块，文末引文仍逐字保留 X。类比块须写具体的「不成立的地方」。区分讲者明确说出的因果与作者的解释，写清数值、比较、操作顺序和适用条件。

## 四种类型模板

四种中间小节下可用 `###` 划分论点或话题，子标题下有正文可满足该节非空要求。

### 讲座、课程

按讲者原有顺序和编号写主线。保留的清单、步骤和条件要能照着做。具名案例写前后变化及原文给出的结果。

```markdown
## 主线论点

1. 〈按原顺序解释方法或主张。〉 ⏱ 00:00
2. 〈写关键步骤和条件。〉 ⏱ 00:00

〈完整列出留用清单。若有独立略项，在“本文略去”写清原编号、项目和时段。〉 ⏱ 00:00

〈具名案例的做法、前后变化和量化结果。〉 ⏱ 00:00
```

### 访谈、对谈

按话题分段。只有原文里自我介绍或被点名时才用「某某说」，其余写「对话中提到」。有分歧时分别写明立场和理由。

```markdown
## 话题

### 〈话题〉
〈观点或做法，按文稿可确认的方式归属。〉 ⏱ 00:00

## 意见不一致的地方
〈分别写双方的说法和理由，每项附 ⏱ 00:00。文稿无分歧时写“不适用（文稿中未出现意见分歧）”。〉
```

### 大会演讲、发布会

分开写现场实际演示、讲者报告的数据和只在台上提出的说法。保留讲者给出的数据范围，明确是谁报告的。

```markdown
## 发布或主张了什么
〈核心发布或主张及其步骤。〉 ⏱ 00:00

## 有证据的 / 只是说法

### 演示过或给出数据
〈文稿所述的演示结果，或具名案例和讲者报告的数据。〉 ⏱ 00:00

### 只是口头声称
〈讲者声称、预计或计划的内容，保留其说法的程度。〉 ⏱ 00:00
```

### 产品演示（≤10 分钟）

按实际操作顺序写出留用步骤和文稿明确说出的屏幕结果。关键数字附时间点，保留单位、比较对象和条件。

```markdown
## 演示了什么

1. 〈演示者的第一步和可核对结果。〉 ⏱ 00:00
2. 〈接着做什么。〉 ⏱ 00:00

## 关键数字与条件

- 〈案例前后量化结果和适用条件。〉 ⏱ 00:00
```

## 合成示例一：讲座、烹饪

频道拷贝路径为 `河谷烘焙/2026-04-12 河谷烘焙 - 面包面团怎样慢慢发起来.md`。

```markdown
---
title: 面包面团怎样慢慢发起来
source: https://example.invalid/videos/cold-dough
channel: 河谷烘焙
published: 2026-04-12
type: 讲座
caption_kind: manual
skill_version: abc1234
transcript_path: transcript.txt
tags: [video-note]
---

## 先记住一句话
先让面团在冰箱里慢慢发起，取出回温，再检查面团和成品。

## 这场在谈什么、谁
河谷烘焙的讲座《面包面团怎样慢慢发起来》发布于 2026-04-12，适合想安排在家发面时间的初学者。

## 主线论点

1. 混合面团后，放进约 4°C 的冰箱冷藏八小时。讲者把这种做法叫低温发酵。 ⏱ 01:10

> [!note] 术语：低温发酵（cold fermentation）
> 让面团在较冷的环境里慢慢发起，便于安排发面时间。（Claude 补充，非视频内容）

2. 取出面团，折叠一次，再在室温放三十分钟。 ⏱ 03:20
3. 把烤箱预热到 220°C，烤十八分钟。 ⏱ 05:10

讲者的三项检查是表面没有干粉、面团比刚混合时高出约一半、烤好的切面没有湿黏的生面团。 ⏱ 06:02

河岸面包房（Riverbank Bakery）过去每十个面包有六个边缘偏干。按这套时间和检查方法做后，最新一批只有一个面包边缘偏干。 ⏱ 07:16

## 可复用做法
做之前先安排冷藏和回温时间。 ⏱ 01:10 ⏱ 03:20

## 翻车或别用
案例没有交代最新一批的总数，无法用这组数字算出偏干率下降了多少。 ⏱ 07:16

## 今天立刻动手一步
把冷藏和回温的开始时间写到你今天的备料单上。（改写讲者做法） ⏱ 01:10 ⏱ 03:20

本文略去｜开场问候（00:00–01:10）

## 原文依据
> [01:10] Mix the dough, then put it in a refrigerator at about four degrees Celsius for eight hours. I call this cold fermentation.
> [03:20] Take the dough out, fold it once, and leave it at room temperature for thirty minutes.
> [05:10] Preheat the oven to two hundred twenty degrees Celsius and bake for eighteen minutes.
> [06:02] My three checks are no dry flour on the surface, the dough is about one and a half times taller, and the baked center is not wet dough.
> [07:16] At Riverbank Bakery, six out of ten loaves used to have dry edges. In the latest batch, after this timing and check routine, only one was dry at the edge.
```

任务内 `selection.md` 示意。时间范围左闭右开，连续覆盖 00:00–07:45。

```text
00:00–01:10 | 寒暄 | 略 | 问候与面团做法无关
01:10–03:20 | 核心方法和条件 | 留 | 要先知道冷藏温度与时间
03:20–05:10 | 流程 | 留 | 折叠与回温有固定顺序
05:10–06:02 | 流程和条件 | 留 | 交代预热和烘烤时间
06:02–07:16 | 清单 | 留 | 讲者给出三项检查
07:16–07:45 | 具名案例 | 留 | 有之前的数量与最新一批的变化
```

为展示「略」而在合成文稿新增一行 `[00:00] Good evening, everyone. Thank you for coming.`。文末五条引文沿用原合成文稿。五个留用单元全部命中，按完整的 07:45 计算覆盖四个四分位。

## 合成示例二：访谈、医疗流程

频道拷贝路径为 `石桥门诊/2026-05-03 石桥门诊 - 怎样减少预约爽约.md`。

```markdown
---
title: 怎样减少预约爽约
source: https://example.invalid/videos/clinic-reminders
channel: 石桥门诊
published: 2026-05-03
type: 访谈
caption_kind: auto
skill_version: abc1234
transcript_path: transcript.txt
tags: [video-note]
---

## 先记住一句话
预约前先提醒并请患者确认，有人取消时就按候补顺序补上空位。

## 这场在谈什么、谁
石桥门诊的访谈发布于 2026-05-03，适合负责门诊预约和候补联络的工作人员。

## 话题

### 提醒和确认
对话中提到三步。预约前一天发短信，请患者回复确认。收到取消后，再联系候补名单里的下一位。 ⏱ 01:14

> [!note] 术语：候补名单（waiting list）
> 记录愿意在有空位时来就诊的人，用来决定接下来联系谁。（Claude 补充，非视频内容）

### 记录确认回复
对话中提到，收到确认回复后就把预约标为已确认，方便工作人员看到哪些患者已经回复。 ⏱ 02:20

### 用未到人数看变化
对话中提到石桥门诊（Stonebridge Clinic）过去每四十个预约约有八人没来。开始提前一天提醒并把取消的时段给候补者后，最近一个月每四十个预约约有三人没来。 ⏱ 04:26

## 意见不一致的地方
不适用（文稿中未出现意见分歧）。

## 可复用做法
把提醒、确认和空位递补安排到同一份预约流程里。 ⏱ 01:14

## 翻车或别用
案例只报告了石桥门诊（Stonebridge Clinic）的数据，无法据此预估其他门诊的变化。 ⏱ 04:26

## 今天立刻动手一步
在现有的预约流程上标出谁发提醒、谁联系候补者。（改写讲者做法） ⏱ 01:14

本文略去｜关于抵达会场的闲聊（00:00–01:14）

## 原文依据
> [01:14] We use three steps: send a text the day before, ask the patient to confirm, and if someone cancels, call the next person on the waiting list.
> [02:20] When a confirmation comes in, mark the appointment as confirmed on the schedule so staff can see which patients have replied.
> [04:26] At Stonebridge Clinic, we used to have about eight no-shows for every forty appointments. After the day-before reminder and filling cancelled slots from the waiting list, last month we had about three for every forty.
```

任务内 `selection.md` 示意。时间范围连续覆盖 00:00–04:50。

```text
00:00–01:14 | 闲聊 | 略 | 抵达会场的经历与预约流程无关
01:14–02:20 | 清单和技术要素 | 留 | 短信确认与候补递补的顺序决定怎样操作
02:20–04:26 | 流程和技术要素 | 留 | 在预约表上记录确认，让工作人员知道谁已回复
04:26–04:50 | 具名案例和数字 | 留 | 给出改动前后及最近一个月的比较范围
```

本例的原合成文稿引文为 `01:14` 和 `04:26`，逐字保留。合成文稿另补两行，用于演示略去闲聊和三个留用单元的覆盖下限。

- **新增略去行** `[00:00] It was hard to find the entrance to this building this morning.`
- **新增留用行** `[02:20] When a confirmation comes in, mark the appointment as confirmed on the schedule so staff can see which patients have replied.`。正文和文末证据都用到这条新增原话，三个留用单元全部命中。

## 合成示例三：大会演讲、物流

频道拷贝路径为 `沿海冷运会/2026-06-18 沿海冷运会 - 冷藏货物怎样记录温度.md`。

```markdown
---
title: 冷藏货物怎样记录温度
source: https://example.invalid/videos/cold-chain
channel: 沿海冷运会
published: 2026-06-18
type: 大会
caption_kind: manual
skill_version: abc1234
transcript_path: transcript.txt
tags: [video-note]
---

## 先记住一句话
运输中记录货物周围的温度，超过上限就通知司机。

## 这场在谈什么、谁
沿海冷运会的大会演讲发布于 2026-06-18，适合负责冷藏运输和处理超温情况的人。

## 发布或主张了什么
演讲者介绍三步。把温度记录器放在货物旁边，运输中记录温度，超过 5°C 就通知司机。 ⏱ 00:48

> [!note] 术语：温度记录器（temperature logger）
> 放在货物旁测量并保存温度的小装置，让人能回查运输过程中的读数。（Claude 补充，非视频内容）

## 有证据的 / 只是说法

### 演示过或给出数据
台上的记录器显示 3.8 度，屏幕还显示了这趟行程的两处停靠点。 ⏱ 02:11

演讲者报告，海湾冷运（Bayline Cold Freight）过去每两百箱有十二箱超温。加装记录器并在报警时通知司机后，最近一个月每两百箱有四箱超温。 ⏱ 03:02

### 只是口头声称
演讲者计划下一季把提醒扩展到更多路线。 ⏱ 03:36

## 可复用做法
先明确温度上限，再约定超温后通知谁。 ⏱ 00:48

## 翻车或别用
台上只展示了案例的汇总数据。要核对个别路线的情况，还需要看对应的运输记录。 ⏱ 03:02

## 今天立刻动手一步
在你负责的一类货物的检查单上写明温度上限和超温联系人。（改写讲者做法） ⏱ 00:48

本文略去｜赞助口播（00:00–00:48）

## 原文依据
> [00:48] Our three steps are: place a temperature logger beside the goods, record the temperature during transport, and call the driver if it goes above five degrees Celsius.
> [02:11] The logger now reads three point eight degrees. This screen also shows the two stops on this trip.
> [03:02] Bayline Cold Freight used to have twelve boxes above the limit for every two hundred. After adding the logger and calling the driver on an alert, last month it was four in every two hundred. We are showing the summary, not the full route records.
> [03:36] We plan to add the alert to more routes next season.
```

任务内 `selection.md` 示意。时间范围连续覆盖 00:00–03:50。

```text
00:00–00:48 | 赞助口播 | 略 | 赞助致谢与运输流程无关
00:48–02:11 | 清单和技术要素 | 留 | 给出记录器、检查顺序与超温门槛
02:11–03:02 | 演示 | 留 | 有当次读数与停靠点显示
03:02–03:36 | 具名案例和数字 | 留 | 有改动前后数据及证据范围
03:36–03:50 | 口头主张 | 留 | 扩展路线是讲者给出的计划
```

为展示「略」而在合成文稿新增一行 `[00:00] Thanks to our sponsor for supporting today's event.`。文末四条引文沿用原合成文稿，四个留用单元全部命中。

## 合成示例四：产品演示（≤10 分钟），厨房备料

频道拷贝路径为 `南桥厨房/2026-07-09 南桥厨房 - 怎样先用较早到货的食材.md`。

```markdown
---
title: 怎样先用较早到货的食材
source: https://example.invalid/videos/kitchen-stock
channel: 南桥厨房
published: 2026-07-09
type: 演示
caption_kind: auto
skill_version: abc1234
transcript_path: transcript.txt
tags: [video-note]
---

## 先记住一句话
给食材标上到货日期，取用时先拿早到的那一箱。

## 这场在谈什么、谁
南桥厨房的产品演示发布于 2026-07-09，适合管理厨房备料、希望减少叶菜浪费的人。

## 演示了什么

1. 给新到的每箱叶菜登记到货日期。 ⏱ 00:34
2. 打印日期标签，贴到箱子正面。 ⏱ 01:20
3. 取叶菜时先拿日期较早的箱子。演示者把这种做法叫先进先出。 ⏱ 02:05

> [!note] 术语：先进先出（first in, first out）
> 先使用早到的食材，让它们及时被用掉。（Claude 补充，非视频内容）

## 关键数字与条件

- 南桥食堂（South Bridge Kitchen）过去每周丢掉约七公斤叶菜。贴日期标签并先用早到的叶菜后，最近四周平均每周丢掉约三公斤。 ⏱ 04:18
- 演示里的屏幕按到货日期排列菜箱。这次只跟踪了叶菜。 ⏱ 05:02

## 可复用做法
把日期标签贴在箱子正面，取菜时按日期找最早的那箱。 ⏱ 01:20 ⏱ 02:05

## 翻车或别用
本节没有补充中间部分之外的情况。

## 今天立刻动手一步
挑一箱刚到的叶菜，把到货日期贴到箱子正面。（改写讲者做法） ⏱ 00:34 ⏱ 01:20

本文略去｜录制开场问候（00:00–00:34）、频道关注口播（05:36–07:10）

## 原文依据
> [00:34] First, enter the arrival date for each new box of greens.
> [01:20] Next, print the date label and put it on the front of the box.
> [02:05] When taking greens, use the box with the earlier arrival date first. We call this first in, first out.
> [04:18] At South Bridge Kitchen, we used to throw away about seven kilograms of leafy greens each week. With date labels and using the older box first, the average for the last four weeks was about three kilograms per week.
> [05:02] This screen sorts boxes by arrival date. We only tracked leafy greens in this example.
```

任务内 `selection.md` 示意。时间范围连续覆盖 00:00–07:10。

```text
00:00–00:34 | 寒暄 | 略 | 问候与备料操作无关
00:34–01:20 | 流程 | 留 | 登记日期是贴标签前的步骤
01:20–02:05 | 流程 | 留 | 标签位置影响取料时能否看见日期
02:05–04:18 | 技术要素和流程 | 留 | 按到货先后取料是演示的核心
04:18–05:02 | 具名案例和数字 | 留 | 有每周浪费量的前后比较
05:02–05:36 | 演示和边界 | 留 | 说明屏幕排序和统计范围
05:36–07:10 | 频道口播 | 略 | 关注频道与备料步骤无关
```

为展示「略」而在合成文稿新增两行 `[00:00] Hello, everyone. Thanks for joining us in the kitchen.` 和 `[05:36] Follow the channel to see our next video.`。文末五条引文沿用原合成文稿。五个留用单元全部命中，按完整的 07:10 计算覆盖三个四分位。
