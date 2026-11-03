# Note examples

Skeletons only. The author fills each body later with a real transcript and a real note.

Do not invent a video to stand in for one. Do not use a private held-out video. The sample and the held-out set must not be the same video.

`verify_note.py` checks shape (citation, a real quote, not a quote stub, `本节不适用：` allowed, all four sections in that form refused). It does not yet score the writing rules named below. Those rules are in `SKILL.md`.

## Good — four sections filled

- Source: (author)
- What it shows: 问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步 are each a claim plus one verbatim quote.
- Note: (author)

## Good — one section 本节不适用

- Source: (author)
- What it shows: one section is a single line `本节不适用：<reason>` plus one quote that shows the transcript does not contain that part. The other three sections are filled. The note is still a deposit.
- Note: (author)

## Bad — keyword salad

- Source: (author)
- What it shows: prose that stacks transcript words with commas instead of stating a claim. The pending check is R09. An existing specimen, not a held-out video, is `evals/adversarial/keyword_salad_en.md`.
- Note: (author)

## Bad — invented number

- Source: (author)
- What it shows: a number in the prose that never appears in the transcript.
- Note: (author)

## Bad — quote only

- Source: (author)
- What it shows: a section that pastes the quote and does not add a claim. A quote stub is refused today.
- Note: (author)
