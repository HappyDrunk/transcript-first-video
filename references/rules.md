# Single-note checks

Run `python3 scripts/verify_note.py --job <dir> --with-coverage`, then the independent review below. Formal delivery uses the renderer with `--require-review`. See the [delivery format](delivery-format.md) for the Markdown, receipt, selection templates, and counts.

R01 到 R17 和 Coverage C 不检查意思是否和引文一致，意思由复核步骤负责。

| Rule | What it checks |
| --- | --- |
| R01 | The current transcript exists and passes the transcription quality gate. |
| R04 | Each line under 原文依据 contains at least 40 contiguous verbatim characters. Matching folds whitespace and case and permits adjacent cues. |
| R05 | Each quote stamp is within 15 seconds of the nearest cue start covered by its verbatim span. Equidistant cue starts resolve to the earlier start. An untimed transcript is preserved and refused with「缺时间戳，请用带时间戳的转写重跑」. |
| R13 | 今天立刻动手一步 provides a short, linked action in at most two sentences. A same-language action needs a literal match or at least 30% content-token support from an instruction in its evidence. |
| R14 | An optional `platform_title` with more than three unsupported content tokens fails. |
| R15 | Failure, unfinished, and no-extractable-content statuses forbid delivery. |
| C02 | Long jobs need at least three quartiles, based on the full transcript. A known duration uses verified cue times. Character positions remain available for the no-clock diagnostic. |
| C04a | Obsidian properties, current `transcript_path`, ordered headings for the chosen type, meaningful prose, and the final 本文略去 line and evidence section. |
| C04b | Each middle claim has a time link. Each link selects all valid quotes at the exact stamp or the unique nearest quote within 15 seconds. Same-script speech pairs need three shared content tokens. Each end quote must be used, with at most one speech quote per second. |
| C04c | Numbers, calendar dates, years, months, and versions are normalized by type before comparison with the linked original words. Calendar values do not supply ordinary quantities. Claims without links use the end evidence. Only 这场在谈什么、谁 may repeat `published`, `channel`, or `title` verbatim. Markdown list numbering is formatting. Caption corrections may supply a supported spelling. |
| C04d | Term, analogy, and caption-correction blocks follow the specified forms. Terms accept aliases and hyphen spacing. A correction gives the original spelling from the transcript and the corrected spelling. Titles and prose use the corrected spelling and exclude commentary about preparing or checking the note. |
| S01 | Selection ranges cover the transcript in order. Verified quotes hit at least `max(3, ceil(0.9 × retained units))` retained units. The note's omission line lists the omitted ranges, and its links, quote spans, and identifiable verbatim excerpts stay within retained material. In slides mode, a ready, hash-matching `screen.txt` with slide markers requires one selection row per slide, using its number and start time, 留 or 略, and a reason. |

S01 warns when the omitted intervals exceed half the runtime. Verify warns when the readable Chinese body exceeds 1.2 Han characters per English word in the full English transcript. Properties, times, the omission line, end evidence, and explanation blocks are excluded from the Chinese count. A warning leaves the repair count and exit status alone.

Slide rows use `mm:ss | [幻灯片 N] optional title | 留 or 略 | reason`. These rows and the existing `[画面]` rows supplement the speech ranges without changing their hit or omission thresholds. Missing, duplicate, unknown, or mistimed slide selections fail S01. Slide markers identify groups and their first screenshots. They are separate from quotable `[画面]` lines. A ready, hash-matching slides result with `slide_count: 1` also requires a row for slide 1, using the first valid screen line's timestamp, while retaining the original ungrouped output format. Legacy files with neither markers nor a slide count, nameplate mode, and disabled screen mode keep the existing selection behavior.

The numeric checks cover Arabic digits, qualifying Chinese numerals, English number phrases, and spoken decimals. Explicit calendar dates retain their month and day together, including the year when present. Two-digit spoken years after early, mid, late, or in use the 2000s. A following quantity unit, such as “in 24 hours”, keeps the value a quantity. Existing ranges, month spellings, and version labels retain their support rules. Name detection is heuristic, especially for unmarked Chinese names. The checks establish a traceable evidence chain. Read the evidence in context to verify meaning, causal direction, and whether the most important parts of the transcript were retained.

C04d applies the note-commentary check to headings and prose outside the three marked blocks and 原文依据. It catches incomplete-transcription explanations tied to a sentence or passage, statements that the author will leave out unidentified text, uncertain recognition described as “部分识别也不确定”, and claims that a spoken name or term was miswritten by automatic captions. Technical content about 图像识别、语音识别 or identifying an object remains valid. Caption errors belong in 字幕更正, while the end evidence preserves the original transcript.

Verify and coverage share the repair limit. The status records completion after both pass on the same inputs. A successful transcript replacement resets the limit and archives previous writing. A failed acquisition preserves the previous deposit. Historical all-N/A notes are archived.

## Independent semantic review

Only after verify and coverage pass on the same inputs, give the evidence note, full transcript, and selection to a Task that did not write the note. Supply the complete passed `status.verifier.inputs` for its receipt. With screen evidence, also supply `screen.txt` and screenshots. The reviewer uses slide groups to find omitted tables and lists, opens doubtful screenshots and those supporting key numbers, and reads necessary surrounding transcript context. If a reading preview helps assess clarity or terms, generate it from the same note with `render_reading_note.render_note()`.

Report only issues with a location and evidence. Follow this checklist. Do not repeat mechanical checks or add unrelated preferences.

- Compare each claim with its evidence for negation, order, conditions, and causal direction. Check whether an analogy adds an unsupported conclusion. For 今天立刻动手一步, verify that the reader can perform the action with the stated prerequisites.
- Find repeated passages and cases where speech and screen state the same point twice. Preserve useful differences such as precision or scope.
- In interviews, verify who proposed, summarized, or opposed a point. The opening explains roles and any missing speaker labels. Mark the host's own views, extra numbers, and disagreements where they occur.
- Check retained lists for missing items. Read omitted selection units for core claims, steps, or supporting numbers. Locate useful screen-only tables or lists that appear neither in the note nor as a distinct decision in selection. A slide row alone does not prove its useful content was considered.
- List essential terms and basic words used technically without an explanation at first use. In Chinese prose, flag untranslated phrases that obstruct understanding while preserving useful original-language parentheses, proper names, and code. If a speaker's definition differs from a verifiable standard definition, check that the difference and attribution are clear.
- For screen-only numbers, inspect the actual image for units, comparison targets, and conditions. Check compatibility with the note and spoken context. Remove uses unsupported by the image or contradicted by that context.
- Find commentary in prose about preparing, checking, or selecting material, including new wording missed by C04d. Preserve legitimate source attribution, technical discussion of recognition, and marked caption corrections.

Every `review.md` must include `## 未解释的术语和基础词`. Read the reading copy or the preview generated from this note section by section. Check essential terms, abbreviations and basic words at their first technical use. Flag a bare abbreviation or expansion that lacks a plain explanation of what it means here. Write one bullet per unexplained term in `词 | 首次出现的小节 | 原句` format, using that section's heading and quoting the first-use sentence verbatim. If the list is empty after checking every section, write `已逐节查过，没有`. Include any findings from this section in the same batch of changes.

The Task writes `review.md` with the bound receipt. Give each issue one row: note section or selection interval, original words or screenshot location, problem, and minimal change. Merge issues with the same cause. Use `clear` when the initial review finds no issue and `changes` when proposing a batch. The writer may reject a suggestion, leaving it in the receipt body with a one-sentence reason. Keep the Task's first-line judgment unchanged. The reviewer checks only this batch's treatment and affected evidence or selection. The scripts enforce input binding and bounded counting, not the semantic quality or the independence of the Task.
