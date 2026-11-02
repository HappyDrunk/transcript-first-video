# Gate evidence

Generated 2026-11-02T16:27:00Z by `python3 scripts/run_evidence.py`.

Without a gate, a fluent note looks depositable (40 or more letters). With the gate, a note is allowed only when it cites a transcript file that passes the quality gate.

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

Reasons:

- `usable-en`: cites a transcript that passed the gate
- `empty-asr`: quality gate failed: empty or unusable transcript (no speech text after cleanup)
- `zh-en-loop-launder`: quality gate failed: looping repeats: the same segment appears 6 times (43% of segments); quality gate failed: language/ratio fail for expected Chinese: cjk=0, cjk_ratio=0.00, latin_ratio=1.00 (need cjk>=8 and cjk_ratio>=0.35); analyzer-laundering: the note is an essay about ASR or transcription failure without a usable transcript
- `usable-zh`: cites a transcript that passed the gate
- `clean-en-expected-zh`: quality gate failed: language/ratio fail for expected Chinese: cjk=0, cjk_ratio=0.00, latin_ratio=1.00 (need cjk>=8 and cjk_ratio>=0.35)
- `gibberish`: quality gate failed: gibberish: Latin vowel ratio 0.00 is too low to be speech
- `missing-path`: missing transcript path: evals/fixtures/does_not_exist.txt does not exist; note does not cite transcript path evals/fixtures/does_not_exist.txt; analyzer-laundering: the note is an essay about ASR or transcription failure without a usable transcript
- `missing-citation`: note does not cite transcript path evals/fixtures/usable_en_transcript.txt

## Host deposit behavior

These rows call `youtube_host.py --settle-transcript` (no network). That path still runs the gate and does not pretend a fetch happened.

| video id | status | note written | transcript written | exit | expect |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `usable-en` | finished | true | true | 0 | finished deposit, verifier allows |
| `stale-deposit-removed` | not_finished | false | false | 2 | rerun with empty text deletes the previous note and transcript |
| `empty-asr` | not_finished | false | false | 2 | empty transcript writes status only |
| `zh-loop` | quality_gate_failed | false | false | 2 | expected Chinese plus English loop writes status only |

## Live YouTube

URL: `https://www.youtube.com/watch?v=KwhgfwOSToQ`. Substitute: none; this is eval id 1.

Command: `python3 scripts/youtube_host.py https://www.youtube.com/watch?v=KwhgfwOSToQ --out evals/results/live --json`.

Result: finished via `caption-mirror` (en auto). Verifier allowed: True. Transcript characters: 17015.

yt-dlp did not return captions. The text came from the public mirror fallback. The note cites the transcript path. Title and description are not stored.

Excerpt:

> All right. Thank you so much, Basil, for the introduction. Hello there. Those of you in the audience, thank you so much for joining us today. My name is Kevin. Uh, technically we don't really have titles. So I am member of technical staff a

Attempts:

- yt-dlp: failed. ERROR: [youtube] KwhgfwOSToQ: Sign in to confirm you’re not a bot. This helps protect our community. Use --cookies-from-browser or --cookies for the authentication. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-d…
- caption-mirror: ok. en auto via yt.chocolatemoo53.com
