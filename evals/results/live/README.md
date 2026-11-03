# Live receipts

Public URLs. `ASR_BACKEND` was unset, so speech-to-text did not run. No cookies file and no API key were used. These are not fixture files, and they are not a private corpus.

Fetched 2026-11-03, except `youtube_KwhgfwOSToQ`. That transcript was already in the repo. On 2026-11-03 only its `note.md` was regenerated from that file, so the note shape matches the hosts. The transcript bytes were left as they were.

| Directory | Public URL | What came back |
| :--- | :--- | :--- |
| [youtube_jNQXAC9IVRw](youtube_jNQXAC9IVRw/) | <https://www.youtube.com/watch?v=jNQXAC9IVRw> | Finished. "Me at the zoo", 19 seconds. yt-dlp hit a sign-in wall. The public caption mirror returned an English manual caption. [note.md](youtube_jNQXAC9IVRw/note.md) quotes [transcript.txt](youtube_jNQXAC9IVRw/transcript.txt). |
| [youtube_C0DPdy98e4c](youtube_C0DPdy98e4c/) | <https://www.youtube.com/watch?v=C0DPdy98e4c> | `not_finished`. "TEST VIDEO", 18 seconds. yt-dlp hit a sign-in wall. The caption mirror reported no caption track. ASR stayed off. The directory is [status.json](youtube_C0DPdy98e4c/status.json) only. |
| [x_2102748685792596449](x_2102748685792596449/) | <https://x.com/NASA/status/2102748685792596449> | Finished from yt-dlp English captions. The caption is one short promo line. [note.md](x_2102748685792596449/note.md) quotes that line and does not expand it. |
| [youtube_KwhgfwOSToQ](youtube_KwhgfwOSToQ/) | <https://www.youtube.com/watch?v=KwhgfwOSToQ> | Finished via the caption mirror (English auto captions). This is the URL `scripts/run_evidence.py` records in `gate-evidence.md`. The note quotes the opening. The transcript file is longer. |

No directory here is a gibberish or looping transcript. Captions either passed the gate or were missing. Those refusals are the fixture rows `gibberish` and `zh-en-loop-launder` in [../gate-evidence.md](../gate-evidence.md).

`python3 scripts/run_evidence.py` without `--skip-live` refetches `youtube_KwhgfwOSToQ` only. It leaves the other directories in place.

Commands that produced the three new receipts:

```bash
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --out evals/results/live
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=C0DPdy98e4c" --out evals/results/live
python3 scripts/x_host.py "https://x.com/NASA/status/2102748685792596449" --out evals/results/live
```
