# Single-note checks

Run `python3 scripts/verify_note.py --job <dir> --with-coverage`, then independent review with `references/review-guide.md`.
Mechanical rules verify traceability; meaning is checked during review.

| Rule | When it fails / warns | Where to fix |
| --- | --- | --- |
| R01 | Transcript missing or quality gate fails. | [正文与检查](delivery-format.md#正文原文依据和检查) |
| R04 | Speech quote lacks 40 contiguous verbatim characters. | [正文与检查](delivery-format.md#正文原文依据和检查) |
| R05 | Quote stamp exceeds 15 seconds or clocks are unusable. | [正文与检查](delivery-format.md#正文原文依据和检查) |
| R13 | Closing action/items are unlinked or too long when present. | [精炼版](delivery-format.md#精炼版) / [共用模板](delivery-format.md#证据版共用模板) |
| R15 | Status is failed, unfinished, or no-extractable-content. | [交付](delivery-format.md#生成阅读版与交付) |
| C02 | Long job misses three transcript quartiles. | [取舍](delivery-format.md#动笔前通读和取舍) |
| C04a | Properties, headings, prose, omission, evidence, or closing malformed. | [共用模板](delivery-format.md#证据版共用模板) / [类型模板](delivery-format.md#五种类型模板) |
| C04b | Claims lack valid links, or evidence is unused/duplicated. | [正文与检查](delivery-format.md#正文原文依据和检查) |
| C04c | Normalized numbers/names/code mismatch evidence; warnings need review. | [正文与检查](delivery-format.md#正文原文依据和检查) / [告警裁定](review-guide.md#c04c-告警裁定) |
| C04d | Term limits, `[!tip]` ban, or `原文出入`/spelling conflict. | [两种标记块](delivery-format.md#两种标记块禁-tip) |
| S01 | Selection has range, threshold, omission, screen, or slide errors. | [取舍](delivery-format.md#动笔前通读和取舍) |
