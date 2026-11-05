---
name: transcript-first-video
description: Read YouTube and Twitter/X videos into usable knowledge without pretending a title or a post counts as watched. Use when the user pastes a YouTube or X/Twitter video link, asks to 通读 / summarize / extract methods from one of those videos, or asks an agent to build or run a caption→ASR→quality-gate pipeline. Other platforms are not promised. Also use when a prior run left needs-transcript / video-pending / ASR-quality-failed tags, or when a note claims the video was understood but no usable transcript exists.
---

# Transcript-first video reading

## What this skill does

Turn a **YouTube** or **Twitter/X video** URL into a transcript, then write the knowledge note yourself. The scripts fetch, chunk, and check. They do not write the analysis.

Those two are the primary platforms. This skill does not promise Bilibili, Douyin, Xiaohongshu, or any other site, and it is not a multi-platform summarizer.

Success takes both bars. (A) A usable transcript: captions or ASR that passes the quality gate. (B) A local `note.md` you wrote from that transcript. The note has four sections, 问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步. Sections 1–2 always quote the transcript. Sections 3–4 quote the transcript, or may say `本节不适用：` with a reason (proof quote optional). Those quotes stay in the local note so verify can ground the claims. The Feishu or chat body follows Language preference. It does not have to repeat the quotes. 中英文对照 is not the default. Chinese delivery prose defaults to 小白能懂. That is not a second question.

Failure that must be said out loud = no usable transcript, or nothing in the transcript worth extracting. Do not deposit a finished note in either case. Do not deliver one either.

## Language preference

Ask once, on install or the first run with no saved choice. This is the first user-facing step. It comes before fetch, before note writing, and before any other preference. The choices are `中文`, `英文`, and `中英文对照`.

Persist the answer in `language.txt` beside this `SKILL.md` in the installed skill folder, when that folder is writable. One line, exactly one of those three. Do not commit the file. If you cannot write there, keep the same line in the host project and read it before the next delivery. If nothing is saved, or the saved line is not one of the three, ask. Do not assume `中英文对照`. Do not fetch, and do not deliver, until the user has chosen.

- `中文` — Chinese prose only in the delivered note. No English transcript quote blocks in that body. A Latin proper noun the local note already keeps (Hard gate 2) may stay. Original-language quotes stay in the local `note.md` so verify and `claim_ground_check.py` can ground claims.
- `英文` — English prose only in the delivered note. Transcript quote blocks stay in the local verify artifact.
- `中英文对照` — analysis, plus contiguous original-language transcript quotes under the sections.

If the local note's prose is the other language, deliver a rendering of that prose only. Do not add a fact, a number, a name, or a cause the local note does not already ground.

The local `note.md` is the verify artifact. It keeps YAML frontmatter and the quotes R01–R17 check. `verify_note.py` and `claim_ground_check.py` read that file, not the delivered body. Keeping quotes there is not a requirement to paste them into Feishu or chat.

A Feishu or chat upload strips YAML frontmatter. Do not paste Obsidian or machine frontmatter into the delivered body. That includes `title`, `source_url`, `video_id`, `acquisition`, `gate_passed`, `transcript_path`, `quoted_window`, `caption_kind`, `caption_trust`, `platform_title`, and any other `---` block.

Chinese delivery prose is 小白能懂 unless the user later says otherwise. Explain a mechanism in plain words: 为什么, 是什么, 好处. A Latin proper noun the quote requires may stay. Do not stack jargon into headings or into the body. The four section headings stay as they are. Plain words may only restate what the local note already grounds. Do not add a mechanism, a cause, or a benefit the note does not already support. There is no style file and no second install question.

## What this skill does not do

- Fetch Bilibili, Douyin, Xiaohongshu, or other platforms. A link from those sites is not a promise.
- Treat title, description, post text, or thumbnails as a full watch.
- Let a script synthesize the analysis. `note.scaffold.md` is a blank form.
- Burn visual multi-turn by default (vision only when the picture itself is the information and the user asks).
- Clone an entire host desk (systemd stack, foreign inbox schemas, personal vault paths).
- Put cookies or API keys into the skill, logs, receipts, or git.
- Open a note with `课前` or `课前先记住一句话`. The opening heading is `## 先记住一句话`.
- Ship a thin claim-passing stub as the final 通读 when method-bearing arcs are still uncovered.

## Run

```text
0. Before any fetch, transcript, or note:
     If language.txt is missing, empty, or not exactly one of 中文 / 英文 / 中英文对照:
       Ask those three. This is the first thing you say. Persist one line in language.txt.
       Do not assume 中英文对照.
     Do not fetch, and do not write a note, until that file is valid.
     Chinese delivery prose is 小白能懂. Do not ask a second preference.
1. python3 scripts/youtube_host.py "<youtube url>"
   or python3 scripts/x_host.py "<x or twitter status url>"
   Job directory:
     transcript.txt     lines are [mm:ss] text, or [hh:mm:ss] text after one hour
     segments.json      [{start, end, text}] in seconds; null when the source had no clock
     chunks/NN.txt      about 8 minutes or about 6000 characters, timestamps kept
     status.json
     note.scaffold.md   frontmatter, four empty headings, fill instructions
2. If status is not transcript_ready
     Tell the user no usable transcript was acquired, and the reason. Stop.
     Do not write note.md.
3. Read every file in chunks/.
     If duration_seconds is greater than 300 (over 5 minutes), first write chunks/NN.notes.md
     inventory: each line is `[mm:ss]` + short verbatim excerpt + one-line restatement of that excerpt.
     Then write the note from those inventory points (do not invent beyond them).
4. Write note.md from the scaffold. Open with ## 先记住一句话. Never 课前.
     You write the analysis. The script does not.
     On a long video, cover the main method-bearing arcs.
     A verify pass on a few facts is not enough when those arcs are missing.
     If an analyzer times out, retry or hand-write from the full transcript.
5. If every section is 本节不适用
     python3 scripts/verify_note.py --job <dir>
     That sets status to no-extractable-content, deletes note.md, and leaves the transcript.
     Tell the user there was nothing to extract. Stop.
6. python3 scripts/verify_note.py --job <dir>
     If it refuses, the note is 未交 (not deposited). Edit note.md from the reasons.
     Do not skip the next step, and do not deliver.
7. python3 scripts/coverage_check.py --job <dir>
     This always runs after verify, before finished and before delivery.
     It is not a flag and not opt-in.
     A video longer than 5 minutes must pass C01–C03. At or under 5 minutes those
     three are skipped, and the command still runs.
     FAIL is 未交. verify and coverage share at most 2 repair rounds.
     One round is an edit, then both commands again.
8. If round 2 still refuses
     Tell the user which Rxx or Cxx line failed. Treat as 未交.
     Do not set finished. Do not deposit the note. Do not deliver.
9. When you deliver to Feishu or chat
     Do this only after language.txt is valid, verify has allowed the note,
     and coverage_check.py has allowed it.
     If language.txt is missing or invalid, ask and persist it. Do not send.
     Build that body from the local note in the saved language.
     中文 delivery is 小白能懂: plain words only, no added fact.
     Do not rewrite note.md to match the delivery wording. That wording does not loosen R01–R17 or coverage.
     Strip YAML frontmatter. Never paste it.
     中文: Chinese prose only. Leave transcript quote blocks in the local note.
     英文: English prose only. Leave transcript quote blocks in the local note.
     中英文对照: prose plus that section's contiguous original-language quotes.
     Keep the opening heading ## 先记住一句话. Never 课前.
     Always run, before send:
       python3 scripts/coverage_check.py --job <dir> --delivery <body>
     C04 FAIL is 未交. It uses the same 2 repair rounds. Do not send.
     A folder of note.md files is a complete sink. That file stays the verify artifact.
     finished stays false until verify and coverage have both allowed the note.
```

`transcript_ready` means the transcript passed the gate. `finished` stays false until verify and coverage have both allowed the note. `not_finished` and `quality_gate_failed` are stops. `no-extractable-content` is the all-N/A stop.

Commands and env var names: `scripts/README.md`.

## Sections

Open the note with `## 先记住一句话`, then keep these four, in this order:

1. 问题与做法
2. 完整怎么做
3. 翻车或别用
4. 今天立刻动手一步

Sections 翻车或别用 and 今天立刻动手一步 may be a single line `本节不适用：<one sentence reason>` when the transcript truly has nothing for that part. A proof quote is optional for those two sections.

Sections 问题与做法 and 完整怎么做 must not be whole-section `本节不适用`. If the material is thin, still write short claims that stay inside the quotes you cite.

Do not invent a step to fill a section. If all four sections are `本节不适用`, that is not a note. Delete `note.md` by running `verify_note.py --job`. Do not deposit it.

## How to write

`verify_note.py` enforces R01–R17. The list is `references/rules.md`. A failure line looks like `R07 FAIL: ...`. Fix the note from that line. Writing is a **required two-pass**. Do not skip Pass 1. R17 checks that a section's prose shares content words with that section's own quotes.

### Pass 1 — Extract only (no section prose yet)

1. Read every file in `chunks/` (and the transcript if needed).
2. Select contiguous verbatim blocks of at least 40 characters that will become `> [mm:ss] …` quotes. Prefer blocks that carry the methods, steps, warnings, and action advice you will need.
3. For a video longer than 5 minutes, first write `chunks/NN.notes.md` inventory: each line is `[mm:ss]` + short verbatim excerpt + one-line restatement of **that excerpt only**. Do not invent beyond the excerpt.
4. World knowledge, outside articles, and inferred causes are forbidden in this pass. If the transcript does not say it, it is not on the inventory.

### Pass 2 — Analyse only from selected blocks

Write the four sections into the local `note.md`. Every verifiable claim must sit on Pass-1 quotes in **that same section**. Quotes in this file are the verify evidence. Delivery is later, and Language preference decides whether those quotes appear in the Feishu or chat body. The YAML frontmatter never does.

- After each verifiable claim (any sentence that asserts a fact, number, name, step, or causal link), quote the transcript: `> [mm:ss] words copied verbatim`. Use `[hh:mm:ss]` when the stamp in the transcript has hours. The quote is 40–200 characters and is a contiguous verbatim stretch of the speech. Words that run across adjacent cues count; the cue clocks do not. One quote may support at most the next 3 prose sentences in that section.
- Prose may compress or merge quotes from the same section. Every fact in the prose must be supportable by that section's quotes. Do not add transcript-external explanation, examples, numbers, product names, or causal links (`because` / `所以` / `导致` / `因此`) unless the supporting quote itself states them.
- If a sentence needs a number, a proper noun, or a causal assertion that is not in the same-section quotes: delete it, or replace it with a short `转写未给出…` line. Do not fill the gap with plausible wording.
- Before you deposit, self-audit: for each prose sentence, name the supporting quote stamp in that section. If you cannot, retract the sentence.
- For a video longer than 5 minutes, take quotes from at least 3 different quartile stretches of the transcript, and keep the chunks/NN.notes.md inventory.
- 今天立刻动手一步 starts with a verb, is at most 2 sentences, and stays inside its section quotes (cross-language notes are not forced to share surface tokens with English imperatives).
- Do not write a number, a person's name, or a product name that is not in the supporting quotes for that section (R16) and not in the transcript (R07/R08).
- R17: same-script prose must share at least three content tokens with that section's own quotes (a Latin word of four letters, or a consecutive CJK pair). A number in the prose must be in those quotes. A quote moved from another section fails. Chinese prose on a Latin quote skips the token floor and still checks numbers.
- A platform title, if you record one, goes only in frontmatter `platform_title`. It does not enter the body. The hosts do not copy the platform title into the scaffold.
- Eval / intake rule: a note that fails `verify_note.py` is 未交, not a scored deposit. Disclosure still says the note was written with Claude plus this skill.

`caption_kind` is `auto` or `manual` when the host knows. `caption_trust: low` means the captions were automatic and their language was not the expected language. Treat that transcript as less reliable: stay close to the words, and say so if a claim is thin.

## Hard gates

Land these in the writing of the local `note.md`. R01–R17 stay as written. Do not loosen them.

(A) and (B) stay in force. No usable transcript means not finished: do not deposit a note, and do not deliver one. The checks below apply to prose in the local `note.md` against that section's quotes. They do not require those quotes in the Feishu or chat body, and they do not require English quote blocks there. Chinese-only delivery (`中文`) is allowed. `中英文对照` is a saved choice, not a default. Do not drop a quote from the local note, and do not add a fact while shortening the delivery, to make a language mode pass.

The 1.0.0 Hall J receipt is [evals/results/hall_j_retest_receipt.md](evals/results/hall_j_retest_receipt.md). That run used in-distribution eval notes. It is not a held-out 9. Do not paste the receipt into a note or into these instructions.

1. **Faithfulness / no invented vehicles:** Every concrete vehicle in prose — a tool, a list, a template, a metaphor, or an object the note says you write, make, or open — must be the same kind of thing in that section's quotes. You may paraphrase what the quote says. You may not add a concrete object the quote does not name. In the action section, paraphrase the imperative only. Delete decorative nouns the speaker did not say.
2. **ASR proper nouns keep Latin form:** When a quote has a near-miss token for a product or a person (a clipped spelling, a name split by a space, or brand-like capitals), keep the recognized Latin form in the prose. Do not replace it with a vague paraphrase that drops the name, unless the quote itself uses only that vague wording. If you are not sure the token is a name, leave the quote's Latin token unchanged in the prose.
3. **Mechanism and named-entity coverage:** In Pass 1, pick verbatim blocks that cover (a) how a core mechanism in this talk works, (b) the named people or works this talk hangs on, and (c) the speaker's ask-why or ask-how beats. If a long-video inventory line would be only color or anecdote, prefer a mechanism or named-entity line in the same quartile. Pass 2 turns those blocks into prose claims in 问题与做法 or 完整怎么做. Do not leave them only in unused inventory.
4. **Self-audit before deposit:** For each prose sentence, point to its same-section quote stamp. If a noun-vehicle fails (1) or an ASR name fails (2), delete or rewrite that sentence before deposit. A miss is a retry, not close enough.
5. **No invented ordinal scaffolds or causal overreach:** Do not number the talk into ordered layers, ranks, or a top and a bottom the speaker did not use, unless that framing is in the supporting quotes. You may name a concept the quote names without assigning it a rank. Do not write a causal conclusion (`所以`, `因此`, because, therefore) unless the quote carries that step. If the quoted words do not entail the sentence, delete it.

## Hard rules

These are required. They do not replace Hard gates A and B, and they do not loosen R01–R17.

1. The note opens with `## 先记住一句话`. Never `## 课前先记住一句话`. Never the prefix `课前` on that heading or any other heading. The four verify sections still follow, in that order. This heading does not replace them. R03 does not score it.
2. A long-form 通读 covers the video's main transcript arcs. A thin stub that only passes `verify_note.py` or `claim_ground_check.py` on a few facts is not done when method-bearing arcs are missing. Chit-chat, a sponsor read, and banter can be one line. If the analyzer times out, retry it or hand-write from the full transcript until those arcs are in the note. Do not invent an arc the transcript does not contain. Do not deposit or deliver the stub.

## Coverage gate C

The human bar for a long 通读 is **9/10 on detail depth and 9/10 on summary completeness**. Both count. Four grounded claims and a short Feishu body are below that bar even when every written sentence is faithful. Spotcheck stays a human reading. This gate does not emit a 9/10 score and does not call a model.

`scripts/coverage_check.py` is the deterministic floor under that bar. It always runs after `verify_note.py` and before `finished` or delivery. It is not opt-in. R01–R17 and the Hall thresholds stay as they are.

On a video longer than 5 minutes (`duration_seconds` > 300, or no clock and two or more `chunks/NN.txt` files):

- **C01.** Inventory is missing. Each `chunks/NN.txt` needs `chunks/NN.notes.md`, or the job has one `inventory.md` of `[mm:ss] excerpt | restatement` lines.
- **C02.** Quotes hit fewer than 3 duration quartiles (0–25, 25–50, 50–75, 75–100). That is the spread check. A note parked in one slice did not read the video.
- **C03.** Fewer than 9/10 of the inventory lines show up in the note, and never fewer than 3. `need = max(3, ceil(0.9 × lines))`. A line counts on an exact whole-second stamp or on 40 contiguous characters shared with the excerpt. That is the detail-depth floor. Banter may be one inventory line; that line still has to be represented. It does not excuse a missing method line.

At or under 5 minutes, C01–C03 are skipped. The command still runs. `verify_note.py` still requires the section quotes. R12 still treats exactly 300 seconds as long; C uses a strict greater-than 300.

**C04** runs whenever a Feishu or chat body is about to be sent (`--delivery`). Delivery prose letters (CJK plus Latin, YAML and quote lines removed) under 0.9× the same count in `note.md` fail. That is the summary-completeness floor. A full-arc body passes. A thin stub fails. Write the local prose in the delivery language so the comparison is the same text with quotes removed, not a short recap of a longer note.

FAIL lines look like `C03 FAIL: ...`. Exit is non-zero. FAIL means 未交. Repair stays inside the two rounds shared with verify.

## Analysis layer

The local `note.md` keeps the four sections 问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步, with the quotes R01–R17 check. `## 先记住一句话` comes first. The sentence under it has to be supportable by those quotes. It is not a new claim with no quote.

Before locking a long note, read the full transcript (every file in `chunks/`) for method-bearing arcs. Expand until those arcs are present in the delivery language. A local claim check on a short extract does not close the note.

A method, a step sequence, a warning, or a worked case stays in the note. Low-value chit-chat, a sponsor read, or pure banter can be one line.

If a full-transcript analyzer times out or returns a partial note, retry it, or write the missing arcs by hand from the transcript. Stop when the main arcs are covered. No usable transcript is still not finished: do not fill the gap from the title.

A host delivery that uses the seven-block labels (课堂开场, 核心拆解, 真实案例, 写好××的×条, 避坑指南, 课后作业) still opens with `先记住一句话`, never `课前`. Those labels do not replace the four sections in local `note.md`, and they do not skip verify.

## Pipeline (portable)

```text
link
  → normalize source + stable job id
  → captions / official subtitles?
       yes → timestamped transcript, segments.json, chunks/
       no  → refresh media URL → audio → ASR
  → quality gate
       pass → note.scaffold.md; the agent reads chunks and writes note.md
       fail → upgrade model once (e.g. small→medium) OR stop with a reason
  → verify_note.py --job
  → coverage_check.py --job always, before finished
  → coverage_check.py --job --delivery before Feishu or chat
  → verify and coverage share at most 2 repair rounds
  → all sections 本节不适用 → no-extractable-content, delete note.md
  → no usable text → say not finished; do not pretend
```

Prefer `--limit 1` (or equivalent) concurrency for ASR. Long work is background; chat stays free. Scheduling (cron / timer / routine) should **kick the worker**, not re-derive transcripts inside an LLM wake.

## Content acquisition order

1. Platform / official captions
2. Existing transcript cache for the same stable job id
3. Local or async ASR with quality gate (+ one model upgrade)
4. Explicit “not finished” (metadata-only only if the user accepts a degraded path **and** the note labels that boundary)

## Quality gate (why it exists)

Bad ASR still looks like “text”. Models will happily structure garbage into a confident wrong note.

Gate before analysis. Typical hard fails for expected Chinese speech:

- Too few CJK characters / absurd Latin ratio
- Looping repeats, gibberish, or cross-language hallucination

Gate fail ⇒ do **not** save as final knowledge. Retry with a stronger model into a **separate** transcript file, or stop and say what failed.

The gate reads the transcript text. It does not play the audio. A fluent wrong caption can still pass. CI checks the gate, the citation, the quotes inside the four sections, and that the analysis is not an empty stub. CI does not grade whether that analysis is the best reading of the talk. That reading is `evals/results/spotcheck.md`, and CI does not score it.

Read `references/pitfalls.md` before treating a Chinese ASR default as production-ready. `references/note-examples.md` is the shape of a good note and three bad ones. The bodies are placeholders until the author fills them. Do not invent a video to fill them.

## CJK ratio and English jargon

`--expected-lang zh` fails closed unless the transcript has at least 8 CJK characters and a CJK ratio of at least 0.35 among CJK plus Latin letters. The constants are `ZH_MIN_CJK` and `ZH_MIN_CJK_RATIO` in `scripts/quality_gate.py`. They are not command-line flags.

A Chinese talk dense with English technical terms (model names, API identifiers, product names) can fall under 0.35 and be refused even when the universal checks would pass. That false reject is intentional. The same ratio check is what stops an English hallucination loop from being filed as a Chinese talk. Holding a jargon-heavy talk back is the tradeoff; a wrong note is worse.

Tune by omitting `--expected-lang` when you know the talk mixes Chinese with English identifiers and you accept losing the script check. Loop, gibberish, and length checks still run. A confidence number is checked only when the caller passes one. The whisper CLI path does not supply a score, so there is no confidence floor on that path. Do not omit `--expected-lang` just to push a bad transcript through. There is no per-job flag to lower 0.35. The same idea applies to `--expected-lang en`, `ja`, or `ko`: pass it when you know the language, omit it when you do not.

## Stable identity and media URLs

- Job id must come from a durable content id (YouTube video id or X status id), never from a signed CDN playurl.
- Signed audio URLs expire. At worker time, **refresh** from the source URL; do not replay the URL saved at enqueue.
- Short vs long video does not change the rule: no transcript ⇒ not finished. Inline ASR failure must enqueue a recoverable job, not a warning-only deposit.

## Secrets

Environment variable **names** only in docs, for example:

- `YTDLP_COOKIES` (optional path to a cookies file for YouTube or X; never commit the file)
- `YTDLP_EXTRACTOR_ARGS` (optional yt-dlp extractor args)
- `INVIDIOUS_INSTANCE` (optional YouTube caption mirror, or `off`)
- `FX_TWITTER_API` (public X status API origin, default `https://api.fxtwitter.com`, or `off`; no key)
- `ASR_BACKEND`, `OPENAI_API_KEY`, `WHISPER_MODEL`, `WHISPER_UPGRADE_MODEL`, `WHISPER_LANGUAGE` (optional ASR)
- `OPENAI_TRANSCRIBE_MODEL`, `OPENAI_BASE_URL` (optional OpenAI ASR)

Missing or expired cookies ⇒ say so in the status. Keep the public fetch path. The bundled hosts do not read a Bilibili session cookie.

## Knowledge sinks

Write `note.md` only after a usable transcript, and only by reading the chunks. The host writes `note.scaffold.md`: frontmatter (`title` is the job id, not the platform title), empty headings, and fill instructions. `caption_kind` and, when set, `caption_trust` are in that frontmatter and in `status.json`.

`verify_note.py` still refuses a quote stub and refuses a note whose four sections are all `本节不适用`. A stop before `transcript_ready` writes `status.json` only.

Feishu is not required. This skill does not call Feishu and does not read a Feishu token. A Feishu wiki, a Notion database, or another sink can live in the user's own project and consume this Markdown. A folder of `.md` files is a complete sink.

When the sink is Feishu or chat, send the delivery body from Language preference, not the raw `note.md`. If language.txt is missing or invalid, ask and persist it. Do not upload yet. Strip YAML frontmatter before upload. When the choice is `中文` or `英文`, transcript quote blocks stay in the local `note.md`. 中文 prose is 小白能懂: plain words for 为什么, 是什么, and 好处, with no added fact. The body still opens with `## 先记住一句话`. A long 通读 in that body still covers the main method-bearing arcs.

Keep sinks channel-separated when the user maintains partitions (e.g. YouTube vs X vs WeChat vs official docs). Do not dump every medium into one catch-all folder.

This skill does not hardcode personal wiki tokens. Pass parent / sink config from the host project.

## Extending (slots)

| Slot | Responsibility |
|------|----------------|
| Fetchers | `url → {captions? , source_url, stable_id}` |
| ASR backends | audio → transcript + confidence signals |
| Quality gate | pass / upgrade / fuse |
| Sinks | transcript → note / table / inbox fields |
| Triggers | chat enqueue, cron drain, CI kick |

Bundled fetchers are YouTube (`youtube_host.py`) and Twitter/X video (`x_host.py`). They share the gate. Other platforms are a host-project choice, not a promise of this repo. Do not fork the pipeline to add one.

## Bundled resources

- `scripts/knowledge_note.py` — the finished-note shape check, `本节不适用` handling, and `render_scaffold`. It does not write the analysis.
- `scripts/verify_note.py` — R01–R17. `--job <dir>` reads the host directory. All-N/A sets `no-extractable-content` and deletes `note.md`. A failed verify means 未交.
- `scripts/claim_ground_check.py` — optional local helper. It counts sentences whose numbers, proper nouns, or long phrases are absent from that section's quotes. Deterministic. No language model. Not a public CI gate and not an LLM judge. It does not replace R01–R17.
- `scripts/coverage_check.py` — Coverage gate C. Always run after verify, before finished or delivery. Deterministic. No language model. Long videos fail closed on missing inventory, fewer than 3 quartiles, or under 9/10 of inventory lines. `--delivery` fails a body under 9/10 of the local prose letter count. It does not replace R01–R17 and it does not score a human 9/10.
- `references/rules.md` — what each rule refuses.
- `scripts/youtube_host.py` — YouTube. Captions first, optional ASR, otherwise not finished. A pass writes the timestamped transcript, `segments.json`, `chunks/`, and `note.scaffold.md`.
- `scripts/x_host.py` — Twitter/X video. Same gate and the same deposit. Captions if present, otherwise optional ASR. Post text is not a transcript.
- `scripts/README.md` — how to run both hosts, the note shape, the CJK false-reject tradeoff, and the env var names.
- `scripts/smoke.sh` — offline check: venv, yt-dlp, gate tests, fixture settle. `--live` adds one captioned YouTube URL. It does not turn ASR on.
- `requirements-asr.txt` — optional whisper install. Not the default. `ASR_BACKEND` stays off until set.
- `references/pitfalls.md` — production mistakes distilled from real failures (sanitized). Read when debugging “looks done but isn’t” or Chinese ASR issues.
- `references/note-examples.md` — skeletons for two good notes and three bad notes. The author fills the bodies. Do not invent a video for them.
- `evals/evals.json` — prompts for an agent or a person. CI does not run these prompts. CI runs `scripts/test_gate.py`, `scripts/test_no_overfit.py`, `scripts/test_claim_ground_check.py` (counts API on synthetic notes, not a note judge), `scripts/test_coverage_check.py` (synthetic jobs for gate C, not a 9/10 grader), `scripts/run_evidence.py --skip-live`, and `scripts/verify_report.py`. `scripts/claim_ground_check.py` is not a CI gate. Coverage C is deterministic and is on that CI path. Spotcheck stays human.
- `evals/results/gate-evidence.md` — layer ①, the fixture table CI checks.
- `evals/results/live/` — layer ②, committed public-URL receipts (captioned YouTube, no-caption stop, captioned X). The template notes were withdrawn.
- `evals/results/spotcheck.md` — layer ③. It records that withdrawal and still reads the fixture refusals. CI does not score it. It is not an audio check.
- `evals/results/hall_j_retest_receipt.md` — receipt for the in-distribution 1.0.0 Hall J run. Not a held-out 9. CI does not score it. Do not copy it into a note.
- `evals/results/` — paths in the evidence files are repo-relative.

## Packaging note

This folder follows the Agent Skills shape (`SKILL.md` + optional `references/` / `scripts/` / `evals/`). `scripts/` is a YouTube host, an X video host, and a verifier, not a queue or a desk. It does not invent credentials.
