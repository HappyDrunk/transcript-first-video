# Review guide

Required for an independent Task or self-review.

## Independent semantic review

Only after verify and coverage pass on the same inputs, give the evidence note, full transcript, selection, all verifier warnings, and complete `status.verifier.inputs` to a Task that did not write the note. With screen evidence, also supply `screen.txt` and screenshots. Use slide groups to find omitted tables and lists, inspect doubtful screenshots and key numbers, and read necessary transcript context. A reading preview may be generated from the same note with `render_reading_note.render_note()`.

Report only located, evidenced issues. Do not repeat mechanical checks or add unrelated preferences.

### 红帽念读关

- 默念，以「必要／删损／承接／上口」四问删赘句、合并单句碎段，删与文头或正文重复的段落、步骤、命令及指标。英文短语、习语及时间译成自然中文。开篇和节首压缩时保留讲者限定，不把个例升格为全称，口径以正文为准。结尾收束。
- 拦过滤词和「画面写明」「画面上」「图上」等机器转述。核查删过滤词后未补写视频未讲的画面描述。簇分片 WARN 仅作参考，不要为此拆开因果段。

### 黑帽零脑补关

- 核查软告警与 C04c，核对否定、顺序、地区、版本、前置条件和因果方向。每处「讲者认为/提出」必查文稿 ±30 秒，将讲者给出的原因或机制写在同段。核对 `今天立刻动手一步` 的前提，并逐句核对译文的主语、宾语、修饰关系和主语切换。区分已核实事实与讲者判断或预测，保留归属和概率语气。
- 访谈核实归属，覆盖标题人物。检查遗漏的主张、清单、步骤、数字、可运行命令和画面独有表格或清单，及后文回指缺前因的演示主体。核对取舍及参数。
- 双向查术语。标出首次技术用法缺释，也查条目过密（建议 ≤12 条、每条 ≤60 字）、复述正文、藏入视频事实及冗余英文括号，保留专名、通用英文、检索词和代码。
- 核对 `原文出入`。行型 1 查语境是否唯一支持纠正（含纯语音高置信同音 ASR），严查数字、版本变更和擅补人名。行型 2 按口述核对代码，严查虚构参数或 API。行型 3 的 `存疑` 须有真实冲突或细节缺失，以中性锚点保留不确定性。勿滥用 `存疑`，可确认的同音 ASR 转行型 1。`版本冲突` 仅在引文明确对比不同版本时标 `误报`，同一对象的版本冲突用行型 3 向读者说明。
- 拒绝无来源代码标识符和无标签画面数字。对照画面查序数语境、单位、对比对象及条件。删核对、筛选自白，保留来源归属与「视频未展开」「视频未给出完整命令」等读者向边界说明；画面识别失败时勿断言画面没有。

Read the reading copy or preview section by section and include the section for the job's reading level in `review.md`.

- Plain and legacy use `## 未解释的术语和基础词`. Check essential terms, abbreviations, and basic words at first technical use.
- Concise uses `## 精炼版也必须解释的词`. 逐节只查四类：`视频自造`、`冷门专名`、首次出现且需要解释的`缩写`、讲者用法与`通行定义`不一致的词（`W8`）。`PR、CTO、LLM、IDE、JVM` 在常规用法下不必标出。

In either section, write one bullet per unexplained term in exact `词 | 首次出现的小节 | 原句` format, quoting the first-use sentence verbatim. If empty after checking every section, write exactly `已逐节查过，没有`. Include these findings in the same batch.

Give each issue one row: note section or selection interval, original words or screenshot location, problem, and minimal change. Merge issues with the same cause. Use `clear` when the initial review finds no issue and `changes` for one proposed batch. A rejected suggestion stays in the body with the writer's one-sentence reason. Keep the Task's first-line judgment unchanged. The reviewer rechecks only this batch's treatment and affected evidence or selection.

### 独立复核回执与计轮

The Task writes only the job's `review.md`. Its first line is `<!-- tfv-review: JSON对象 -->`; the JSON object contains `inputs` and `result`. Copy the complete `status.verifier.inputs` object into `inputs`, with no omitted fields or summary. `result` is `clear` for no issue or `changes` for one batch. Preserve this original judgment.

When clear, `review_rounds=0` and only the reviewed input may ship. When a changes batch enters handling, `review_rounds=1`; there is no second review batch. The lock binds the reviewed fingerprint to at most two review-corrected drafts: one concentrated correction and, only if its final checks fail, one mechanical repair. `note.md` and `selection.md` may change while source fingerprints stay fixed. These drafts do not add ordinary `edit_rounds`; normalization precedes fingerprinting and an identical retry consumes no draft. Stop on success; a second failed corrected draft returns the draft and issues.

If no separate Task is available, self-review by this guide and set `"reviewer":"self"`. The rendered reading copy must show `未经独立复核`.

### C04c 告警裁定

Copy `status.verifier.c04c_sha256` into the receipt's `c04c_sha256`. Add `## C04c 告警裁定` to `review.md`; write `无` for an empty list.

Give each warning exactly one bullet: `- C04c-001 | 正文命中词 | 所链引文原片段 | 真错或误报`. Use exactly `真错` or `误报` and copy the shown hit. The excerpt must occur in the linked quote and contain a number for a numeric warning. For a numeric warning without linked values, write `- 待补 C04c-001` and request correction. True errors and missing evidence make the receipt `changes`.

After correction, keep original rows and record `- 已修 C04c-001 | 修后正文片段`, or use `已删除` for a removed claim. For warnings new on the final draft, add `<!-- tfv-c04c-final: <current c04c_sha256> -->` and one `- 终稿 C04c-001 | 正文命中词 | 所链引文原片段 | 误报` row each. Use `真错` for an unsupported claim so the writer can use the one review correction. On a new draft, update or remove follow-up rows and their signature.
