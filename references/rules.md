# Verify rules

`verify_note.py` runs these in order. Each failure is one line, `R07 FAIL: ...`. Nothing in this list calls a language model.

Sections 翻车或别用 and 今天立刻动手一步 may be one line, `本节不适用：<reason>`, with an optional proof quote. Sections 问题与做法 and 完整怎么做 must not be whole-section `本节不适用`. If all four sections are that form, R03 fails and `--job` deletes `note.md`, setting status `no-extractable-content`.

A note that fails verify is 未交 (not deposited).

Coverage gate C is not one of these rules and does not loosen them. It lives in `scripts/coverage_check.py`. A long note can pass R01–R17 and still fail C. The human bar is 9/10 detail depth and 9/10 summary completeness. C does not score that bar and does not call a model. Hall thresholds are unchanged.

C checks the note against the inventory the job already wrote (the rows exist, quartile spread, and at least 9/10 of those rows in the note). It does not prove that inventory was complete against the full transcript. A thin inventory can still pass. The gate stops "wrote an inventory and then ignored it," not "under-extracted at inventory time." A `C WARN` line when the row count is implausibly low versus duration or chunk count is a notice only. It does not loosen C01–C04, and the absence of that warning is not a completeness proof. Operators: `scripts/README.md`.

| Rule | Refusal |
| :--- | :--- |
| R01 | The transcript is missing or fails the quality gate, including an essay about a failed transcription. |
| R02 | Frontmatter is missing a required field, `gate_passed` is not true, `quoted_window` is not a real quote, or the note does not cite the transcript path. |
| R03 | A knowledge section is missing or out of order, `本节不适用` is malformed, a required content section is whole-section N/A, or all four sections are `本节不适用`. |
| R04 | A blockquote is not a verbatim transcript span of at least 40 characters. Adjacent cues count as one span: their texts are joined in order, and a leading `[mm:ss]` or `[hh:mm:ss]` is not part of the speech. A path or a title is not a quote. Optional N/A sections 3–4 may omit a proof quote. |
| R05 | A quote's `[mm:ss]` or `[hh:mm:ss]` stamp is more than 15 seconds from the stamp anchor. The anchor is the start of the covered cue closest to the stamp (the earlier cue when the distances tie). A span across adjacent cues uses that same anchor. Quotes with no stamp are not timed. |
| R06 | The same blockquote is used in two sections. |
| R07 | An Arabic digit, or a Chinese number claim of 10 or more or containing a magnitude unit, is unsupported by Arabic digits or English number words in the transcript. |
| R08 | More than two proper nouns in the prose (mid-sentence capitals, `《》`, or quoted terms) are absent from the transcript. |
| R09 | Prose stacks four or more short comma-separated fragments, or uses salad phrasing such as "uses these words" or "marking words". |
| R10 | Same-script: after transcript overlap of 12 characters or more is removed, a non-N/A section has fewer than 60 characters or fewer than two sentences, unless it is a short compression covered by its section quotes. Chinese prose on a Latin transcript skips the 60-char leftover gate and only requires quotes plus at least one prose sentence. Quote stubs still fail. |
| R11 | Same-script: more than 85% of a section's prose is its own quote. Chinese prose on a Latin transcript skips this lexical gate. |
| R12 | A transcript longer than five minutes has quotes in fewer than three quartile stretches. Untimed or shorter transcripts skip this. |
| R13 | The today action runs past two sentences, or (same-script) shares less than 30% of its words with a transcript imperative and is not supported by its section quote. Chinese prose on a Latin transcript requires a supporting quote. An N/A section skips this. |
| R14 | More than three words from `platform_title` are absent from the transcript. |
| R15 | `status` is `failed`, `not_finished`, `quality_gate_failed`, or `no-extractable-content` while `note.md` is still being checked. |
| R16 | A mid-sentence proper noun in the prose is absent from that section's supporting quotes (tolerance 0). No cross-lingual lexical-overlap gate. |
| R17 | Same-script prose shares fewer than three content tokens with that section's own quotes (a Latin word of at least four letters, or a consecutive CJK pair), or an Arabic digit or Chinese number claim in the prose is absent from those quotes. A quote taken from another section fails. Chinese prose on a Latin quote skips the token floor and still checks Arabic digits and Chinese number claims. |

R04 folds speech by joining cue texts in order with a single space. Whitespace is collapsed and case is folded. A leading `[mm:ss]` or `[hh:mm:ss]` on a cue is not speech. The blockquote has to be an exact substring of that string, at least 40 characters. A paraphrase, a skipped cue, or a reordering is not a quote.

R05 times a stamped quote against cue starts. Every cue whose text overlaps that verbatim span is covered. The stamp anchor is the covered start closest to the stamp. When two starts are equally close, the earlier cue is the anchor. The stamp has to fall within 15 seconds of the anchor. A quote with no stamp is not timed.

`scripts/verify_report.py` scores `evals/adversarial/` and `evals/good/` and writes `evals/results/verify-report.md`. Intercept below 95% or a false positive above 10% fails the run.

Known gap: English number words in note prose are not checked in this release. Chinese number claims in prose are checked against Arabic digits and supported English number expressions in the transcript or section quote. Single Chinese digit words below ten are not checked because they often appear with non-numeric meanings.
