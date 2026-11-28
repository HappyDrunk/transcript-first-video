---
name: transcript-first-video
description: Read YouTube videos into usable knowledge without pretending a title or description counts as watched. Use when the user pastes a YouTube URL, asks to 通读 / summarize / extract methods from a video, asks an agent to build or run a caption-to-ASR quality-gate pipeline, or returns to a job tagged needs-transcript, video-pending, or ASR-quality-failed. Also use when a note claims a video was understood but no usable transcript exists.
---

# Transcript-first video reading

## What this skill does

A YouTube URL becomes a transcript; the agent writes `selection.md` and `note.md`. Scripts fetch, check, and render; an independent Task reviews meaning. Failures keep inputs and report why.

Send one progress line per stage: 字幕与画面抓取完成 → 初稿过机械校验 → 独立复核定稿 (fast: 快读成稿).

## Language and reading preference

For YouTube, each field follows request, saved preference, then default `plain`. Languages are `中文`, `英文`, `中英文对照`; levels are `plain`, `concise`. Plain explains unfamiliar terms in a compact end glossary; Concise assumes relevant background. Keep `原文依据` in the original language.

If language is unknown, ask once: “Which language, and Plain (terms & background explained) or Concise (assumes background)?” / “笔记用什么语言写？讲解要通俗（术语和背景都解释），还是精炼（默认你有相关背景，直奔要点）？” Keep choices already given. If language is known but level missing, use `plain` and mention Concise in delivery chat. Unsure means `plain`.

Inspect with `--show-pref`. Pass `--language` and `--reading-level`; add `--save-pref` with both only for that combined answer. Read failure means no saved preference. Automation passes both explicitly. Do not create a separate preference text file.

## What this skill does not do

No other platform is promised. Titles/descriptions are not a watch; scripts do not write analysis; never promote failed ASR. Never store cookies/API keys in skill, logs, receipts, or git, or ship thin stubs with method-bearing arcs uncovered.

<!-- tfv-writer-required: SKILL.md, references/delivery-format.md, references/rules.md -->
<!-- tfv-reviewer-required: references/review-guide.md -->

## Run

1. Fastest: run `python scripts/setup.py` (stdlib, makes `.venv`, works on old pip), then `python scripts/install_check.py --doctor`; below, `python3` means the `.venv` Python (`.venv\Scripts\python.exe` on Windows, `.venv/bin/python` elsewhere), else `python`/`python3`. Or from the repo root install with `python3 -m pip install --group base --group screen` (on PEP 668 / externally-managed Python, use a venv first); auto screen mode needs `--group screen` for RapidOCR/ONNX Runtime. Run `python3 scripts/youtube_host.py --show-pref`, resolve preferences above, then `python3 scripts/youtube_host.py "<YouTube URL>" --language "<language>" --reading-level "<level>"`. Add `--save-pref` only as ruled above; caption language uses `--expected-lang`. Keep the persisted screen mode.
2. Wait for `status.json.next_step: write-note`. Read the full timed transcript and ready `screen.txt`. On fetch failure or missing timestamps, keep inputs and report why (`缺时间戳，请用带时间戳的转写重跑` if untimed).
3. Before drafting read this `SKILL.md`, `references/delivery-format.md`, and `references/rules.md`. Write ordered `selection.md` with continuous full-transcript coverage, screen-only items, and per-slide decisions.
4. Draft `note.md` from `note.scaffold.md` and the type template in `references/delivery-format.md`, starting with `## 先记住一句话`. Write coherent topical paragraphs (100% speaker content in body), state scope/prerequisites upfront, complete retained lists and cases, and explain essential terms at first use via compact `术语` blocks (rendered to end `## 术语速查`). Closing sections are optional; when included, `concise` closes with 1–3 linked items under `## 可以怎么用、可以拿去讨论什么` and `plain` (or jobs without `reading_level`) closes with `## 今天立刻动手一步`.
5. Link claims with `⏱ mm:ss` clusters, write `本文略去` when anything is omitted, and end with `## 原文依据`. Extract contiguous verbatim speech quotes with `python3 scripts/extract_quote.py` and trusted `[画面]` lines with `extract_quote.py --screen "<dir>" START END`. Keep steps, conditions, and claims within the cited evidence. Use only `> [!note] 术语：…` and `> [!warning] 原文出入` (spelling fix, spoken code, or `存疑`); do not use `[!tip]`.
6. Run `python3 scripts/verify_note.py --job "<dir>" --structure-only` (read-only), then `python3 scripts/verify_note.py --job "<dir>" --with-coverage`. C04c warnings do not block passing; once allowed, go to step 7 and leave WARNs to review (every note edit counts toward the 3-draft cap). If the initial draft plus two ordinary repairs fail, stop and return `note.md` and `issues.md`; pass `--resume` only when the user chooses to continue.
7. Give the passed note, full transcript, selection, `status.verifier.inputs`, verifier warnings (including C04c) plus `c04c_sha256`, and available screen evidence to an independent Task that did not write it. It reads `references/review-guide.md` and writes only bound `review.md`. Otherwise self-review by that guide, set `"reviewer":"self"`; the copy shows「未经独立复核」.
8. Handle one review batch together. Keep the Task's judgment and record a one-sentence reason for rejected suggestions in `review.md`. If the first corrected draft fails final checks, allow one mechanical repair; on second failure return draft and `issues.md`.
9. Run `python3 scripts/render_reading_note.py --require-review --task-dir "<dir>" --output-dir "<channel folder>" --language "<language>"`. It rechecks both gates, level, bound receipt, and C04c decisions; the combined gate sets `finished`. Only if the user explicitly asks for 快读/fast: skip steps 7–8 and run step 9 with `--fast` instead of `--require-review`; all mechanical gates still run and the copy is marked 快读模式.
10. Deliver the channel-folder copy path; preserve inputs, `selection.md`, `note.md`, `review.md`, and `status.json` in the job directory.

Optional: example `references/note-examples.md`; issues `references/pitfalls.md`; CLI `scripts/README.md`.
