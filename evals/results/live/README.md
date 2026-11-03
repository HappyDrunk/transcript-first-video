# Live receipts

Public URLs. `ASR_BACKEND` was unset, so speech-to-text did not run. No cookies file and no API key were used. These are not fixture files, and they are not a private corpus.

Fetched 2026-11-03. The `note.md` files that used to sit in the finished directories were withdrawn. They were generated from video-specific templates hardcoded in `scripts/knowledge_note.py`, not written as analysis. They are not knowledge notes. Transcripts and `status.json` remain. No directory was refetched for the withdrawal.

| Directory | Public URL | What came back |
| :--- | :--- | :--- |
| [youtube_jNQXAC9IVRw](youtube_jNQXAC9IVRw/) | <https://www.youtube.com/watch?v=jNQXAC9IVRw> | Transcript kept. Template note withdrawn. "Me at the zoo", 19 seconds. yt-dlp hit a sign-in wall. The public caption mirror returned an English manual caption. [transcript.txt](youtube_jNQXAC9IVRw/transcript.txt) is that caption. [status.json](youtube_jNQXAC9IVRw/status.json) does not point at a finished note. |
| [youtube_C0DPdy98e4c](youtube_C0DPdy98e4c/) | <https://www.youtube.com/watch?v=C0DPdy98e4c> | `not_finished`. "TEST VIDEO", 18 seconds. yt-dlp hit a sign-in wall. The caption mirror reported no caption track. ASR stayed off. The directory is [status.json](youtube_C0DPdy98e4c/status.json) only. |
| [x_2102748685792596449](x_2102748685792596449/) | <https://x.com/NASA/status/2102748685792596449> | Transcript kept. Template note withdrawn. Captions came from yt-dlp. The caption is one short promo line. [transcript.txt](x_2102748685792596449/transcript.txt) is that line. [status.json](x_2102748685792596449/status.json) does not point at a finished note. |
| [youtube_KwhgfwOSToQ](youtube_KwhgfwOSToQ/) | <https://www.youtube.com/watch?v=KwhgfwOSToQ> | Transcript kept. Template note withdrawn. Captions came from the public mirror (English auto captions). This is the URL `scripts/run_evidence.py` records in `gate-evidence.md`. [transcript.txt](youtube_KwhgfwOSToQ/transcript.txt) is the caption file. [status.json](youtube_KwhgfwOSToQ/status.json) does not point at a finished note. |

No directory here is a gibberish or looping transcript. Captions either passed the gate or were missing. Those refusals are the fixture rows `gibberish` and `zh-en-loop-launder` in [../gate-evidence.md](../gate-evidence.md).

`python3 scripts/run_evidence.py` without `--skip-live` refetches `youtube_KwhgfwOSToQ` only. It leaves the other directories in place. A passing refetch writes `note.scaffold.md`, not a finished `note.md`.

Commands that produced the three caption receipts:

```bash
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --out evals/results/live
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=C0DPdy98e4c" --out evals/results/live
python3 scripts/x_host.py "https://x.com/NASA/status/2102748685792596449" --out evals/results/live
```
