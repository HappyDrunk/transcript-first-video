# Live receipts

Public URLs. `ASR_BACKEND` was unset, so speech-to-text did not run. No cookies file and no API key were used. These are not fixture files, and they are not a private corpus.

Fetched 2026-11-03. `note.md` in each finished directory was regenerated from the transcript already in that directory, so the note is a knowledge note (问题与做法, 完整怎么做, 翻车或别用, 今天立刻动手一步) instead of a quote stub. The transcript bytes and `status.json` were left as they were. No directory was refetched for this rewrite.

| Directory | Public URL | What came back |
| :--- | :--- | :--- |
| [youtube_jNQXAC9IVRw](youtube_jNQXAC9IVRw/) | <https://www.youtube.com/watch?v=jNQXAC9IVRw> | Finished. "Me at the zoo", 19 seconds. yt-dlp hit a sign-in wall. The public caption mirror returned an English manual caption. [note.md](youtube_jNQXAC9IVRw/note.md) analyzes that caption: elephants, long trunks, and an explicit stop. It does not add a zoo guide. |
| [youtube_C0DPdy98e4c](youtube_C0DPdy98e4c/) | <https://www.youtube.com/watch?v=C0DPdy98e4c> | `not_finished`. "TEST VIDEO", 18 seconds. yt-dlp hit a sign-in wall. The caption mirror reported no caption track. ASR stayed off. The directory is [status.json](youtube_C0DPdy98e4c/status.json) only. |
| [x_2102748685792596449](x_2102748685792596449/) | <https://x.com/NASA/status/2102748685792596449> | Finished from yt-dlp English captions. The caption is one short promo line. [note.md](x_2102748685792596449/note.md) treats it as a dated invitation (MAX POWER, Kennedy, November 7-8, the URL) and does not invent a price or a map. |
| [youtube_KwhgfwOSToQ](youtube_KwhgfwOSToQ/) | <https://www.youtube.com/watch?v=KwhgfwOSToQ> | Finished via the caption mirror (English auto captions). This is the URL `scripts/run_evidence.py` records in `gate-evidence.md`. [note.md](youtube_KwhgfwOSToQ/note.md) is a knowledge note: the FTE corner case, the two questions, the dev-shop limit, and one action for today. The quotes are from the body of the talk. The transcript file is longer than the quotes. Caption spellings are left as caption spellings. |

No directory here is a gibberish or looping transcript. Captions either passed the gate or were missing. Those refusals are the fixture rows `gibberish` and `zh-en-loop-launder` in [../gate-evidence.md](../gate-evidence.md).

`python3 scripts/run_evidence.py` without `--skip-live` refetches `youtube_KwhgfwOSToQ` only. It leaves the other directories in place.

Commands that produced the three new receipts:

```bash
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --out evals/results/live
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=C0DPdy98e4c" --out evals/results/live
python3 scripts/x_host.py "https://x.com/NASA/status/2102748685792596449" --out evals/results/live
```
