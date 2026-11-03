# Verify rules

`verify_note.py` runs these in order. Each failure is one line, `R07 FAIL: ...`. Nothing in this list calls a language model.

A section may be one line, `本节不适用：<reason>`, plus one quote. That section skips the prose checks that do not apply. If all four sections are that form, R03 fails and `--job` deletes `note.md`, setting status `no-extractable-content`.

| Rule | Refusal |
| :--- | :--- |
| R01 | The transcript is missing or fails the quality gate, including an essay about a failed transcription. |
| R02 | Frontmatter is missing a required field, `gate_passed` is not true, `quoted_window` is not a real quote, or the note does not cite the transcript path. |
| R03 | A knowledge section is missing or out of order, `本节不适用` is malformed, or all four sections are `本节不适用`. |
| R04 | A blockquote is not a verbatim transcript span of at least 40 characters. A path or a title is not a quote. |
| R05 | A quote's `[mm:ss]` or `[hh:mm:ss]` stamp is more than 15 seconds from the cue that contains the words. Quotes with no stamp are not timed. |
| R06 | The same blockquote is used in two sections. |
| R07 | A digit or percent in the prose is not in the transcript. |
| R08 | More than two proper nouns in the prose (mid-sentence capitals, `《》`, or quoted terms) are absent from the transcript. |
| R09 | Prose stacks four or more short comma-separated fragments, or uses salad phrasing such as "uses these words" or "marking words". |
| R10 | After transcript overlap of 12 characters or more is removed, a non-N/A section has fewer than 60 characters or fewer than two sentences, or the prose is a quote stub. |
| R11 | More than 70% of a section's prose is its own quote. |
| R12 | A transcript longer than five minutes has quotes in fewer than three quartile stretches. Untimed or shorter transcripts skip this. |
| R13 | 今天立刻动手一步 does not start with a verb, runs past two sentences, or shares less than 30% of its action's words with an imperative in the transcript. An N/A section skips this. |
| R14 | More than three words from `platform_title` are absent from the transcript. |
| R15 | `status` is `failed`, `not_finished`, `quality_gate_failed`, or `no-extractable-content` while `note.md` is still being checked. |

`scripts/verify_report.py` scores `evals/adversarial/` and `evals/good/` and writes `evals/results/verify-report.md`. Intercept below 95% or a false positive above 10% fails the run.
