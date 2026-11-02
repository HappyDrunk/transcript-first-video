# scripts/

Two commands. The host fetches a public YouTube transcript. The verifier is the hard gate before a note may be written to a vault.

Run both from the repo root. The host runs the gate, writes a note only on pass, then runs the verifier before it exits 0:

```bash
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=KwhgfwOSToQ" --out artifacts
```

Check an existing note on its own (path, or stdin with `--note -`):

```bash
python3 scripts/verify_note.py \
  --transcript artifacts/youtube_KwhgfwOSToQ/transcript.txt \
  --note artifacts/youtube_KwhgfwOSToQ/note.md
```

Exit 0 means allowed. Any other exit means do not deposit the note. On failure the host writes `status.json` only and deletes a previous note for that same job id.

Captions are tried first via `yt-dlp` (`pip install -r requirements.txt`, or `python3 -m yt_dlp` on `PATH`). If YouTube asks for a sign-in and `YTDLP_COOKIES` is unset, the host tries a public caption mirror unless `INVIDIOUS_INSTANCE=off`. The mirror is a third party: it can be wrong, and the quality gate cannot tell a fluent fake from real speech. No title or description is written into the note.

If there are still no captions, optional ASR runs only when configured. Missing deps or a missing key exit with `not finished` and do not invent a note.

| Name | Meaning |
| :--- | :--- |
| `YTDLP_COOKIES` | Optional path to a cookies file. The file stays out of git. |
| `YTDLP_EXTRACTOR_ARGS` | Optional yt-dlp extractor args, for example a player client. |
| `INVIDIOUS_INSTANCE` | Optional mirror base URL, comma-separated, or `off`. |
| `ASR_BACKEND` | `off` (default), `whisper`, or `openai`. |
| `WHISPER_MODEL` | Local whisper model. Default `small`. |
| `WHISPER_UPGRADE_MODEL` | Optional second model if the first transcript fails the gate. |
| `WHISPER_LANGUAGE` | Optional language code passed to whisper. |
| `OPENAI_API_KEY` | Required when `ASR_BACKEND=openai`. Never commit the value. |
| `OPENAI_TRANSCRIBE_MODEL` | Default `whisper-1`. |
| `OPENAI_BASE_URL` | Optional API base. Default `https://api.openai.com/v1`. |

`--expected-lang zh` (or `en`, `ja`, `ko`) selects the caption track and fails the gate on a script mismatch. That is what blocks an English loop when the talk is Chinese. ASR audio extract needs `ffmpeg`.

Offline settle does not fetch. It only gates a file you already have:

```bash
python3 scripts/youtube_host.py --settle-transcript evals/fixtures/empty_transcript.txt \
  --video-id empty-asr --expected-lang en --out /tmp/tfv
```

Regenerate the checked-in pass/fail record:

```bash
python3 scripts/test_gate.py
python3 scripts/run_evidence.py
```

`python3 scripts/quality_gate.py TRANSCRIPT --expected-lang zh` checks a transcript file alone.
