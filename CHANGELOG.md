# Changelog

This repository is the portable gate and skill. A production host may live in another project. Versions here mark the skill and the scripts.

## Unreleased

- Feishu, wiki, and C04 host-delivery steps moved out of `SKILL.md` into `references/host-delivery.md`. `SKILL.md` stays skill-generic: language preference, the note shape (`## 先记住一句话` plus the four sections), R01–R17, Coverage C, and beginner-clear Chinese. The delivery body follows `language.txt`; do not add a fact the local note does not ground; strip machine YAML if the host needs that. The skill does not call Feishu. A past opening of `课前` / `课前先记住一句话` is recorded only in the host notes. R01–R17 and Coverage C are unchanged.
- On install or the first run with no saved choice, ask language first, then fetch. The choices stay `中文`, `英文`, or `中英文对照`, saved in `language.txt`. Do not assume `中英文对照`. Chinese delivery prose defaults to 小白能懂 (plain words: 为什么, 是什么, 好处; a Latin proper noun may stay; no jargon stacked in headings or body). There is no style prompt and no `style.txt`. Read-feel knobs (语气, 密度, 比喻, 类比, 专名) are README-only. They are not an install question and they do not loosen R01–R17 or Coverage C.
- Language preference, asked once on install or before the first delivered note: `中文`, `英文`, or `中英文对照`. Save it in `language.txt` beside the installed `SKILL.md`. If it is unset, ask. Do not assume `中英文对照`. `中文` delivers Chinese prose only; English transcript quotes stay in the local `note.md` for verify. `英文` delivers English prose only. `中英文对照` delivers the analysis plus contiguous original-language transcript quotes under the sections. A Feishu or chat upload strips YAML frontmatter. Hard gates A and B and R01–R17 are unchanged.
- The note opens with `## 先记住一句话`. `课前先记住一句话` and the prefix `课前` are forbidden. A long 通读 has to cover the video's main method-bearing transcript arcs. A stub that only passes claim/verify on a few facts is not done when those arcs are missing. Chit-chat, a sponsor read, and banter can be one line. If the analyzer times out, retry or hand-write from the full transcript. Do not invent an arc. R01–R17 and hard gates A and B are unchanged.
- Coverage gate C (`scripts/coverage_check.py`) always runs after verify and before finished or delivery. It is not opt-in. The human bar is 9/10 detail depth and 9/10 summary completeness. Both count. The script does not score 9/10 and does not call a model. On a video longer than 5 minutes it refuses a missing inventory (C01), quotes in fewer than 3 quartiles (C02), or fewer than 9/10 of the inventory lines (C03, at least 3). `--delivery` refuses a Feishu or chat body under 0.9× the local prose letter count (C04). A thin grounded stub fails. A full-arc note passes. At or under 5 minutes, C01–C03 are skipped and the command still runs. `scripts/test_coverage_check.py` is on the offline smoke path and in CI. R01–R17 and Hall thresholds are unchanged. Spotcheck stays human.
- `SKILL.md` hard gates no longer name eval-set people, works, mechanisms, or ordinal frames, and no longer paste the Hall J scoreboard. The receipt stays in `evals/results/hall_j_retest_receipt.md`. `test_no_overfit.py` scans `SKILL.md` and `references/note-examples.md` as well as `scripts/`. The 1.0.0 Hall J run used in-distribution eval notes. A held-out set is still required before a 9 claim. That run is not a completed 冲9. R01–R17 and coverage C are unchanged.
- R17 requires same-section overlap. Same-script prose must share at least three content tokens with that section's quotes, and a number in the prose must be in those quotes. A swapped quote fails. `evals/good/good_en_*` and `good_zh_*` (and the long English notes) were rewritten so each claim sits on its own quote, without the repeated boilerplate sentence. `references/note-examples.md` has two synthetic good notes and three bad ones (quote swap, invented vehicle, title-as-watch). R01–R16 were not loosened. Coverage C is unchanged. This is not a 9 score.

## 1.0.0 — 2026-11-05

Skill and scripts, with a measured Hall J pass. R01–R16 are unchanged. The annotated tag `v1.0.0` belongs on the squash-merge commit on `main` after this section lands. Do not force-push `main`.

- Hard gates in `SKILL.md`, after Pass 2 and before Pipeline. A concrete vehicle in prose (tool, list, template, metaphor, or an object the note says you write, make, or open) has to be the same kind of thing in that section's quotes. An ASR proper noun keeps its recognized Latin form (`Claude`, `OpenAI`); a vague paraphrase that drops the name is refused unless the quote itself is only vague. On a talk longer than 5 minutes, Pass 1 prefers blocks that cover a core mechanism, a named person or work, and the speaker's ask-why / ask-how beats, and Pass 2 turns those blocks into prose in 问题与做法 or 完整怎么做. Before deposit, each prose sentence points at its same-section quote stamp; a failed vehicle or a dropped ASR name is deleted or rewritten. Do not number the talk as `第一层` / `第二层` / `第三层` / `第四层` / `最上层` (or `Layer 1/2/3`) unless that ordinal framing is in the supporting quotes. Do not write `所以` / `因此推出` / `这说明他不要X` unless the quote carries that causal step.
- Hall J retest `overall_pass` true. Measured 2026-11-05T02:53:29+08:00 Asia/Shanghai. `skill_hallucinations_per_note` 0.0 (≤0.2 and < baseline×0.5; baseline_hall 1.0). `skill_core_recall` 0.913 (21/23; ≥0.7 and ≥ baseline−0.1; baseline_recall 1.0). `should_reject` 1.0. `gold_sha256` `0eaa5f806d7e6ddc175dc62abfa7851f56b9805748b5b0a8d66268e7afa54dd1` (unchanged). Public receipt: `evals/results/hall_j_retest_receipt.md`. Gold note bodies stay outside this repository. In-distribution only. Not a held-out 9, and not a completed 冲9. `v1.0.0` marks the run.
- Mechanical `sample_v2` verify stays 10/10 against the rules (pull request #10, `548a96a`). That 10/10 is the rule check, and it is the same count already disclosed. The Hall J numbers above are the measured pass.
- Grounded two-pass writing. `SKILL.md` requires Pass 1 (extract verbatim blocks only) before Pass 2 (analyse only from those same-section quotes). Outside facts, numbers, names, and causal links the quote does not state are banned. A sentence with no supporting stamp in that section is retracted. The scaffold fill text says claims come only after Pass-1 quotes. R01–R16 are unchanged.
- Optional local helper `scripts/claim_ground_check.py`. It counts sentences whose numbers, proper nouns, or long phrases are missing from that section's quotes. Paths use `pathlib`. It does not write to a drive root. It calls no language model. It is not a public CI gate and not an LLM judge. `scripts/test_claim_ground_check.py` checks that counts API on synthetic fixture notes. It does not score gold notes.
- Evidence paths on Windows strip this checkout the same way POSIX paths do. The prefix is removed whether it is written with `\` or `/`. Remaining backslashes are written as `/`, so a recorded command stays `python3 scripts/verify_note.py ...` and a nested script path stays `scripts/verify_note.py`. A leftover checkout path, including `C:\...`, still fails the evidence check.
- Eval disclosure. Lane A is Claude Desktop with this skill loaded. The comparison set is `model-consensus-gold-v2`. Those gold note bodies are not in this repository. After #10 (`548a96a`), `sample_v2` mechanical verify is 10/10 against the rules. Hall J `overall_pass` is true at the numbers in the Hall J bullet above.
- R04 accepts a blockquote that is a contiguous verbatim span of at least 40 characters across adjacent cues. Cue clocks are left out of the speech fold. The match stays exact: a paraphrase or a skipped cue still fails.
- R05 stamp anchor for a quote that covers more than one cue is the start of the covered cue closest to the stamp (the earlier cue when the distances tie). The stamp still has to fall within 15 seconds of that anchor.
- Claude v2 grounded-prose pass (eval step1): delete “Prose is your own sentences / Do not only rephrase”; allow compress/merge of in-section quotes with facts grounded in those quotes.
- Inventory-first threshold lowered from 1800s to >5 minutes (`chunks/NN.notes.md` with timestamp + excerpt + one-line restatement).
- Sections 3–4 may be `本节不适用` without a proof quote; sections 1–2 must not be whole-section N/A (R03/R04).
- R10/R11 softened for Chinese notes on Latin transcripts so lexical “own words” pressure cannot force unsupported prose; same-script still blocks paste and empty analysis.
- R13 cross-lingual path: ZH action steps need a supporting quote instead of 30% English-imperative token overlap.
- Optional R16: mid-sentence proper nouns in prose must appear in that section's quotes (tol=0).
- Eval intake: failing `verify_note.py` means 未交, not a scored deposit.


- `verify_note.py` is a deterministic rule engine. Each failure is `Rxx FAIL: ...` for R01–R15. See `references/rules.md`.
- CI runs `scripts/verify_report.py` on `evals/adversarial/` (at least 30) and `evals/good/` (at least 15) and fails when intercept is under 95% or the false-positive rate is over 10%. No language model is called. `evals/adversarial/keyword_salad_en.md` fails R09.
- The whisper CLI path does not supply a confidence score. Docs no longer say that path has a confidence floor. `CONFIDENCE_FLOOR` still applies when a caller passes a number.
- Caption cues keep their clock. A passing job writes `transcript.txt` as `[mm:ss] text` (or `[hh:mm:ss]` after one hour), `segments.json` (`start`, `end`, `text`), and `chunks/NN.txt` of about 8 minutes or about 6000 characters. Plain text with no clock stays unstamped.
- `caption_kind` is recorded when known. Automatic captions whose language is not the expected language are marked `caption_trust: low` in `status.json` and the scaffold frontmatter.
- A section may be `本节不适用：<reason>` plus one quote. If all four sections are that form, `verify_note.py --job` sets `no-extractable-content` and deletes `note.md`.
- `SKILL.md` is the agent flow: the host fetches, the agent reads the chunks and writes `note.md`, then verify, at most two repairs. Scripts still do not write the analysis. `references/note-examples.md` is a skeleton the author fills later.
- Withdrawn the committed live sample notes (`evals/results/live/*/note.md`). Those notes were generated by video-specific templates hardcoded in `scripts/knowledge_note.py`. They were not analysis of the transcripts. They are not evidence of a finished knowledge note.
- Hosts no longer synthesize a finished `note.md`. On a passing transcript they write `transcript.txt`, `status.json`, and `note.scaffold.md` (frontmatter, four empty section headings, and fill instructions). `status` is `transcript_ready`. `finished` stays false. `note` stays null.
- Removed the `_compose_*` helpers and the keyword router `compose()`.
- `scripts/test_no_overfit.py` fails if `scripts/` contains the retired template tokens. The token list lives in `evals/overfit_blacklist.txt`.
- Added `evals/adversarial/keyword_salad_en.md`, marked `expect: FAIL R09` and `expected-fail-pending`. The shape check still allows it. Rule R09 is not in this change.

## 0.2.0 — 2026-11-03

Knowledge-note contract.

- A finished note has to clear both bars. The transcript still has to pass the quality gate, and the note has to analyze it. The body sections are 问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步. Each section quotes the transcript. A path, a status, or a quote with no analysis is refused. A stop still writes `status.json` and no `note.md`.
- The mechanical check does not listen to the audio, and CI does not score summary quality. `evals/results/spotcheck.md` is still a human or agent reading. CI does not score that file.
- A finished job writes an Obsidian Markdown note (`note.md`) with YAML frontmatter. `status.json` stays the machine stub. A stop still writes no note.
- Feishu is not part of this skill. The README says so in English and in Chinese.
- Evidence is three layers. CI scores the fixture table. Committed public-URL receipts cover a short captioned YouTube video, a YouTube video with no caption track, and a captioned X video. `evals/results/spotcheck.md` is an agent reading, and CI does not score it.
- No live gibberish transcript was added. That refusal stays on the fixture rows.

## 0.1.0 — 2026-11-03

First tagged release.

- YouTube and Twitter/X video only. Other platforms are not fetched.
- Captions first. `ASR_BACKEND` defaults to off. No captions and no ASR ends as `not_finished`, and no note is written from the title.
- A note is allowed only when it cites a transcript that passes the quality gate and quotes a real stretch of that file.
- `scripts/smoke.sh` is the offline check. `bash scripts/smoke.sh --live` adds one short captioned YouTube URL ("Me at the zoo", `jNQXAC9IVRw`). `requirements-asr.txt` is the optional second rung.
- Checked-in evidence uses repo-relative paths. CI regenerates it with `--skip-live` and fails if `evals/results` changes.
- A finished sample is committed at `evals/results/live/youtube_KwhgfwOSToQ/` so the artifact shape is visible without a network.
- Prompts in `evals/evals.json` are agent or human assertions. CI runs the gate tests and the offline evidence script, not those prompts.
