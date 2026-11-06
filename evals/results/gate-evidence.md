# Gate evidence

Generated 2026-11-06T02:14:09Z by `python3 scripts/run_evidence.py`.

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
- `empty-asr`: R01 FAIL: quality gate failed: empty or unusable transcript (no speech text after cleanup)
- `zh-en-loop-launder`: R01 FAIL: quality gate failed: looping repeats: the same segment appears 6 times (43% of segments); quality gate failed: language/ratio fail for expected Chinese: cjk=0, cjk_ratio=0.00, latin_ratio=1.00 (need cjk>=8 and cjk_ratio>=0.35); analyzer-laundering: the note is an essay about ASR or transcription failure without a usable transcript
- `usable-zh`: cites a usable transcript, quotes it in each knowledge section, and the analysis is not a stub
- `clean-en-expected-zh`: R01 FAIL: quality gate failed: language/ratio fail for expected Chinese: cjk=0, cjk_ratio=0.00, latin_ratio=1.00 (need cjk>=8 and cjk_ratio>=0.35)
- `gibberish`: R01 FAIL: quality gate failed: gibberish: Latin vowel ratio 0.00 is too low to be speech
- `missing-path`: R01 FAIL: missing transcript path: evals/fixtures/does_not_exist.txt does not exist; analyzer-laundering: the note is an essay about ASR or transcription failure without a usable transcript
- `missing-citation`: R02 FAIL: note does not cite transcript path evals/fixtures/usable_en_transcript.txt; note is missing Obsidian frontmatter (title, source_url, video_id, acquisition, gate_passed, transcript_path, quoted_window); R03 FAIL: finished note is missing knowledge section 问题与做法, 完整怎么做, 翻车或别用, 今天立刻动手一步; R04 FAIL: note does not quote a transcript window (need 40 contiguous characters from the transcript; a path or a title is not a quote)
- `path-only`: R02 FAIL: note is missing Obsidian frontmatter (title, source_url, video_id, acquisition, gate_passed, transcript_path, quoted_window); R03 FAIL: finished note is missing knowledge section 问题与做法, 完整怎么做, 翻车或别用, 今天立刻动手一步; R04 FAIL: note does not quote a transcript window (need 40 contiguous characters from the transcript; a path or a title is not a quote)
- `quote-stub`: R03 FAIL: finished note is missing knowledge section 问题与做法, 完整怎么做, 翻车或别用, 今天立刻动手一步
- `boilerplate-sections`: R04 FAIL: section 今天立刻动手一步 quote is not verbatim in the transcript: Put a handful of bark in the new pot so water can drain. Set the plant in the mi; R10 FAIL: boilerplate analysis in section 问题与做法: the section is a quote stub rather than a reusable claim; boilerplate analysis in section 完整怎么做: the section is a quote stub rather than a reusable claim; boilerplate analysis in section 翻车或别用: the section is a quote stub rather than a reusable claim; boilerplate analysis in section 今天立刻动手一步: the section is a quote stub rather than a reusable claim; R13 FAIL: 今天立刻动手一步 does not start with a verb; R17 FAIL: section 问题与做法 shares 0 content tokens with its quotes; need 3; section 完整怎么做 shares 0 content tokens with its quotes; need 3; section 翻车或别用 shares 0 content tokens with its quotes; need 3; section 今天立刻动手一步 shares 0 content tokens with its quotes; need 3

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
