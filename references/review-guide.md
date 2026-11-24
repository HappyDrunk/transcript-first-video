# Review guide

Reviewer-required guidance for an independent Task or the self-review fallback.

## Independent semantic review

Only after verify and coverage pass on the same inputs, give the evidence note, full transcript, selection, and complete `status.verifier.inputs` to a Task that did not write the note. With screen evidence, also supply `screen.txt` and screenshots. Use slide groups to find omitted tables and lists, inspect doubtful screenshots and key numbers, and read necessary transcript context. A reading preview may be generated from the same note with `render_reading_note.render_note()`.

Report only located, evidenced issues. Do not repeat mechanical checks or add unrelated preferences.

- Compare every claim with evidence for negation, order, conditions, and causal direction (especially across merged multi-sentence paragraphs). For `今天立刻动手一步` (when present), ensure the reader can act with the stated prerequisites.
- Find repeated passages and cases where speech and screen duplicate a point; preserve useful differences in precision or scope. Verify scope/region/version prerequisites appear upfront rather than buried at the end.
- In interviews, verify who proposed, summarized, or opposed each point. Check that every person named in the video title is accounted for in the body, with no silent "default to guest" attribution when speaker labels are absent.
- Check retained lists and tutorial/hands-on code blocks for missing items or omitted runnable commands (without inventing missing parameters—state when the video omits them). Read omitted units for core claims, steps, or supporting numbers. Locate useful screen-only tables or lists absent from both the note and a distinct selection decision.
- **Bidirectional terminology & readability review**:
  1. Flag essential terms missing explanation at first technical use (see reading-level section below).
  2. **Also flag excess/noise**: too many `术语` entries (target ≤12 entries, ≤60 chars each), glossary entries that merely parrot the prose, video facts (numbers/names/causality) smuggled into `术语` blocks instead of prose, and noisy English parentheses (such as `50%（50%）`, common words, or broken ASR fragments). Keep only essential proper names, search terms, and code.
- **Review `原文出入` direction and neutrality**:
  1. Type 1 (`字幕/画面写作 A，实为 B`): confirm it is a genuine typo/casing fix, not silently washing over a version/number conflict or unverified name completion.
  2. Type 2 (`口述代码`): verify the reconstructed code matches spoken words without inventing parameters or APIs.
  3. Type 3 (`存疑`): confirm each entry reflects a real source conflict or missing detail, stays neutral without picking sides, and is not used as an escape hatch for unverified claims.
- For screen-only numbers, inspect the image for units, comparison targets, and conditions; remove unsupported or contradicted uses.
- Find prose commentary about how the writer prepared, checked, or selected material. Preserve reader-facing scope/uncertainty notes (such as `存疑`, "视频未展开", "视频未给出完整命令") and source attribution.

Read the reading copy or preview section by section and include the section for the job's reading level in `review.md`.

- Plain and legacy use `## 未解释的术语和基础词`. Check essential terms, abbreviations, and basic words at first technical use (without pushing redundant entries beyond the glossary budget).
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
