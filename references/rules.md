# Verify rules

`verify_note.py` runs these in order. Each failure is one line, `R07 FAIL: ...`. Nothing in this list calls a language model.

Sections 翻车或别用 and 今天立刻动手一步 may be one line, `本节不适用：<reason>`, with an optional proof quote. Sections 问题与做法 and 完整怎么做 must not be whole-section `本节不适用`. If all four sections are that form, R03 fails and `--job` deletes `note.md`, setting status `no-extractable-content`.

A note that fails verify is 未交 (not deposited).

| Rule | Refusal |
| :--- | :--- |
| R01 | The transcript is missing or fails the quality gate, including an essay about a failed transcription. |
| R02 | Frontmatter is missing a required field, `gate_passed` is not true, `quoted_window` is not a real quote, or the note does not cite the transcript path. |
| R03 | A knowledge section is missing or out of order, `本节不适用` is malformed, a required content section is whole-section N/A, or all four sections are `本节不适用`. |
| R04 | A blockquote is not a verbatim transcript span of at least 40 characters. A path or a title is not a quote. Optional N/A sections 3–4 may omit a proof quote. |
| R05 | A quote's `[mm:ss]` or `[hh:mm:ss]` stamp is more than 15 seconds from the cue that contains the words. Quotes with no stamp are not timed. |
| R06 | The same blockquote is used in two sections. |
| R07 | A digit or percent in the prose is not in the transcript. |
| R08 | More than two proper nouns in the prose (mid-sentence capitals, `《》`, or quoted terms) are absent from the transcript. |
| R09 | Prose stacks four or more short comma-separated fragments, or uses salad phrasing such as "uses these words" or "marking words". |
| R10 | Same-script: after transcript overlap of 12 characters or more is removed, a non-N/A section has fewer than 60 characters or fewer than two sentences, unless it is a short compression covered by its section quotes. Chinese prose on a Latin transcript skips the 60-char leftover gate and only requires quotes plus at least one prose sentence. Quote stubs still fail. |
| R11 | Same-script: more than 85% of a section's prose is its own quote. Chinese prose on a Latin transcript skips this lexical gate. |
| R12 | A transcript longer than five minutes has quotes in fewer than three quartile stretches. Untimed or shorter transcripts skip this. |
| R13 | 今天立刻动手一步 does not start with a verb, runs past two sentences, or (same-script) shares less than 30% of its action's words with an imperative in the transcript. Chinese prose on a Latin transcript instead requires a supporting quote. An N/A section skips this. |
| R14 | More than three words from `platform_title` are absent from the transcript. |
| R15 | `status` is `failed`, `not_finished`, `quality_gate_failed`, or `no-extractable-content` while `note.md` is still being checked. |
| R16 | A mid-sentence proper noun in the prose is absent from that section's supporting quotes (tolerance 0). No cross-lingual lexical-overlap gate. |

`scripts/verify_report.py` scores `evals/adversarial/` and `evals/good/` and writes `evals/results/verify-report.md`. Intercept below 95% or a false positive above 10% fails the run.
