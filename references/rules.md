# Single-note checks

Run `python3 scripts/verify_note.py --job <dir>`, then `python3 scripts/coverage_check.py --job <dir>`. See the [delivery format](delivery-format.md) for the Markdown and selection templates.

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
