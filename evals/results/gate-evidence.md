# Gate evidence

Generated 2026-11-12T07:42:36Z by `python3 scripts/run_evidence.py`.

Two bars, both required. (A) No note without a usable transcript: the file has to exist and pass the quality gate. (B) A finished note has to analyze that transcript into reusable knowledge. The four sections are 问题与做法, 完整怎么做, 翻车或别用, and 今天立刻动手一步, and each one quotes a 40-character window of the transcript. A path, a status, or a quote with no analysis is refused.

This table is that mechanical check. It does not listen to the audio, so a fluent wrong caption can still pass. It does not send the note to a model, and it does not score how good a summary is. Those readings are evals/results/spotcheck.md, which CI does not score.

## Verifier

| case | eval | naive deposit | gate | exit |
| :--- | :--- | :--- | :--- | :--- |
| `usable-en` | 1 | would allow | allow | 0 |
| `empty-asr` | 2 | would allow | refuse | 2 |
| `zh-en-loop-launder` | 3 | would allow | refuse | 2 |
| `usable-zh` | 3 | would allow | allow | 0 |
| `clean-en-expected-zh` | 3 | would allow | refuse | 2 |
| `gibberish` |  | would allow | refuse | 2 |
| `missing-path` |  | would allow | refuse | 2 |
| `missing-citation` | 1 | would allow | refuse | 2 |
| `path-only` | 1 | would allow | refuse | 2 |
| `quote-stub` | 1 | would allow | refuse | 2 |
| `boilerplate-sections` | 1 | would allow | refuse | 2 |

Reasons:

- `usable-en`: cites a usable transcript, quotes it in each knowledge section, and the analysis is not a stub
- `empty-asr`: R01 FAIL: quality gate failed: empty or unusable transcript (no speech text after cleanup); R04 FAIL: quote is not verbatim for at least 40 characters: [00:00] Today we are repotting a root-bound pothos. Slide the plant out of the old pot and loosen th; quote is not verbatim for at least 40 characters: [00:30] Snip the black, mushy roots and keep the firm white ones. Put a handful of bark in the new p; quote is not verbatim for at least 40 characters: [01:00] Water until it runs out the bottom, then leave the pot in bright shade for three days. Do no; R05 FAIL: 缺时间戳，请用带时间戳的转写重跑; R13 FAIL: 今天立刻动手一步 needs a supporting ⏱ link; C04b FAIL: 主线论点: ⏱ 00:00 has no end quote within 15s; 主线论点: ⏱ 00:30 has no end quote within 15s; 主线论点: ⏱ 01:00 has no end quote within 15s; 可复用做法: ⏱ 00:30 has no end quote within 15s; 翻车或别用: ⏱ 01:00 has no end quote within 15s; 今天立刻动手一步: ⏱ 00:00 has no end quote within 15s; unused end quote [00:00]; unused end quote [00:30]; unused end quote [01:00]
- `zh-en-loop-launder`: R01 FAIL: quality gate failed: looping repeats: the same segment appears 6 times (43% of segments); quality gate failed: language/ratio fail for expected Chinese: cjk=0, cjk_ratio=0.00, latin_ratio=1.00 (need cjk>=8 and cjk_ratio>=0.35); R04 FAIL: quote is not verbatim for at least 40 characters: [00:00] Today we are repotting a root-bound pothos. Slide the plant out of the old pot and loosen th; quote is not verbatim for at least 40 characters: [00:30] Snip the black, mushy roots and keep the firm white ones. Put a handful of bark in the new p; quote is not verbatim for at least 40 characters: [01:00] Water until it runs out the bottom, then leave the pot in bright shade for three days. Do no; R05 FAIL: 缺时间戳，请用带时间戳的转写重跑; R13 FAIL: 今天立刻动手一步 needs a supporting ⏱ link; C04b FAIL: 主线论点: ⏱ 00:00 has no end quote within 15s; 主线论点: ⏱ 00:30 has no end quote within 15s; 主线论点: ⏱ 01:00 has no end quote within 15s; 可复用做法: ⏱ 00:30 has no end quote within 15s; 翻车或别用: ⏱ 01:00 has no end quote within 15s; 今天立刻动手一步: ⏱ 00:00 has no end quote within 15s; unused end quote [00:00]; unused end quote [00:30]; unused end quote [01:00]
- `usable-zh`: cites a usable transcript, quotes it in each knowledge section, and the analysis is not a stub
- `clean-en-expected-zh`: R01 FAIL: quality gate failed: language/ratio fail for expected Chinese: cjk=0, cjk_ratio=0.00, latin_ratio=1.00 (need cjk>=8 and cjk_ratio>=0.35)
- `gibberish`: R01 FAIL: quality gate failed: gibberish: Latin vowel ratio 0.00 is too low to be speech; R04 FAIL: quote is not verbatim for at least 40 characters: [00:00] Today we are repotting a root-bound pothos. Slide the plant out of the old pot and loosen th; quote is not verbatim for at least 40 characters: [00:30] Snip the black, mushy roots and keep the firm white ones. Put a handful of bark in the new p; quote is not verbatim for at least 40 characters: [01:00] Water until it runs out the bottom, then leave the pot in bright shade for three days. Do no; R05 FAIL: 缺时间戳，请用带时间戳的转写重跑; R13 FAIL: 今天立刻动手一步 needs a supporting ⏱ link; C04b FAIL: 主线论点: ⏱ 00:00 has no end quote within 15s; 主线论点: ⏱ 00:30 has no end quote within 15s; 主线论点: ⏱ 01:00 has no end quote within 15s; 可复用做法: ⏱ 00:30 has no end quote within 15s; 翻车或别用: ⏱ 01:00 has no end quote within 15s; 今天立刻动手一步: ⏱ 00:00 has no end quote within 15s; unused end quote [00:00]; unused end quote [00:30]; unused end quote [01:00]
- `missing-path`: R01 FAIL: missing transcript path: evals/fixtures/does_not_exist.txt does not exist; R04 FAIL: quote is not verbatim for at least 40 characters: [00:00] Today we are repotting a root-bound pothos. Slide the plant out of the old pot and loosen th; quote is not verbatim for at least 40 characters: [00:30] Snip the black, mushy roots and keep the firm white ones. Put a handful of bark in the new p; quote is not verbatim for at least 40 characters: [01:00] Water until it runs out the bottom, then leave the pot in bright shade for three days. Do no; R13 FAIL: 今天立刻动手一步 needs a supporting ⏱ link; C04b FAIL: 主线论点: ⏱ 00:00 has no end quote within 15s; 主线论点: ⏱ 00:30 has no end quote within 15s; 主线论点: ⏱ 01:00 has no end quote within 15s; 可复用做法: ⏱ 00:30 has no end quote within 15s; 翻车或别用: ⏱ 01:00 has no end quote within 15s; 今天立刻动手一步: ⏱ 00:00 has no end quote within 15s; unused end quote [00:00]; unused end quote [00:30]; unused end quote [01:00]
- `missing-citation`: C04a FAIL: missing frontmatter properties: transcript_path; transcript_path must resolve to evals/fixtures/usable_en_timed_transcript.txt
- `path-only`: R04 FAIL: 原文依据 needs at least one contiguous transcript quote; R13 FAIL: 今天立刻动手一步 needs a supporting ⏱ link; C04b FAIL: 主线论点: ⏱ 00:00 has no end quote within 15s; 主线论点: ⏱ 00:30 has no end quote within 15s; 主线论点: ⏱ 01:00 has no end quote within 15s; 可复用做法: ⏱ 00:30 has no end quote within 15s; 翻车或别用: ⏱ 01:00 has no end quote within 15s; 今天立刻动手一步: ⏱ 00:00 has no end quote within 15s
- `quote-stub`: R13 FAIL: missing 今天立刻动手一步; C04a FAIL: expected H2 sections in order: 先记住一句话 / 这场在谈什么、谁 / 主线论点 / 可复用做法 / 翻车或别用 / 今天立刻动手一步; expected 本文略去 on its own line after 今天立刻动手一步, before 原文依据; C04b FAIL: unused end quote [00:00]; unused end quote [00:30]; unused end quote [01:00]
- `boilerplate-sections`: C04a FAIL: empty section: 主线论点; C04b FAIL: 主线论点: ⏱ 00:00 needs three shared content tokens; 主线论点: ⏱ 00:30 needs three shared content tokens; 主线论点: ⏱ 01:00 needs three shared content tokens

## Host deposit behavior

YouTube rows call `youtube_host.py --settle-transcript`. The `x-usable` row calls `x_host.py --settle-transcript`. No network. A passing transcript writes `note.scaffold.md` and does not write a finished `note.md`. Both still run the gate and do not pretend a fetch happened.

| video id | status | finished note | scaffold | transcript | exit | expect |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `usable-en` | transcript_ready | false | true | true | 0 | gate pass writes a scaffold, not a finished note |
| `stale-deposit-preserved` | not_finished | false | true | true | 2 | failed rerun records the attempt and preserves the prior scaffold and transcript |
| `empty-asr` | not_finished | false | false | false | 2 | empty transcript writes status only |
| `zh-loop` | quality_gate_failed | false | false | false | 2 | expected Chinese plus English loop writes status only |
| `x-usable` | transcript_ready | false | true | true | 0 | x_host settle uses the same gate and writes a scaffold, not a finished note |

## Live YouTube

Other committed public-URL receipts are listed in `evals/results/live/README.md`. This section records only the one URL this script fetches.

URL: `https://www.youtube.com/watch?v=KwhgfwOSToQ`. Substitute: none; this is eval id 1.

Command: `python3 scripts/youtube_host.py https://www.youtube.com/watch?v=KwhgfwOSToQ --out evals/results/live --json`.

Result: transcript acquired via `caption-mirror` (en auto). Transcript characters: 17015.

The template knowledge note previously stored beside this transcript was withdrawn. It had been filled by video-specific templates, not written as analysis. The host does not write a finished knowledge note.

yt-dlp did not return captions. The text came from the public mirror fallback. Passing the quality gate is not a claim that the captions match the audio.

Excerpt:

> All right. Thank you so much, Basil, for the introduction. Hello there. Those of you in the audience, thank you so much for joining us today. My name is Kevin. Uh, technically we don't really have titles. So I am member of technical staff a

X/Twitter live fetch is not part of this run. The `x-usable` settle row covers that host offline.

Attempts:

- yt-dlp: failed. ERROR: [youtube] KwhgfwOSToQ: Sign in to confirm you’re not a bot. This helps protect our community. Use --cookies-from-browser or --cookies for the authentication. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-d…
- caption-mirror: ok. en auto via yt.chocolatemoo53.com
