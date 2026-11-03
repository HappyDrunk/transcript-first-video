# scripts/

YouTube and Twitter/X video. Same quality gate, same note rule. Other platforms are not fetched here.

Run from the repo root. A host writes `note.md` only after the gate passes and `verify_note.py` accepts it. That file is Obsidian Markdown: YAML frontmatter (`title`, `source_url`, `video_id`, `acquisition`, `gate_passed`, `transcript_path`, `quoted_window`) and three body sections (Source, Transcript, Quoted window). `title` is the job id. The platform title and description are not stored. The quote is copied from the transcript. Feishu is not called. On failure the host writes `status.json` only and deletes a previous note for that same job id.

## Smoke

Offline:

```bash
bash scripts/smoke.sh
```

This creates `.venv` if it is missing, installs `requirements.txt` (yt-dlp), runs `scripts/test_gate.py`, settles `evals/fixtures/usable_en_transcript.txt`, and regenerates fixture evidence with `run_evidence.py --skip-live`. ASR stays off.

With a network, the same script also tries a short public captioned video ("Me at the zoo", `jNQXAC9IVRw`):

```bash
bash scripts/smoke.sh --live
```

`--live` still does not set `ASR_BACKEND`. No captions means `not_finished`. Whisper is a separate install: `pip install -r requirements-asr.txt`, then `ASR_BACKEND=whisper`. `ffmpeg` has to be on `PATH` for local whisper.

Evidence JSON and Markdown record repo-relative paths (`scripts/verify_note.py`, `evals/fixtures/...`). A machine path such as `/workspace/...` fails the evidence script. `--skip-live` keeps the checked-in live sample and does not delete `evals/results/live/`. CI runs that command and fails if `evals/results` changes.

## YouTube

```bash
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=KwhgfwOSToQ" --out artifacts
```

Captions first via `yt-dlp` (`pip install -r requirements.txt`, or `python3 -m yt_dlp` on `PATH`). If YouTube asks for a sign-in and `YTDLP_COOKIES` is unset, the host tries a public caption mirror unless `INVIDIOUS_INSTANCE=off`. The mirror is a third party: it can be wrong, and the quality gate cannot tell a fluent fake from real speech. The note title is the job id. The platform title and description are not written into the note. A filled example is `evals/results/live/youtube_jNQXAC9IVRw/note.md`.

## Twitter/X video

```bash
python3 scripts/x_host.py "https://x.com/USER/status/STATUS_ID" --out artifacts
```

`twitter.com` status URLs are the same input. Captions first, when yt-dlp can see a caption track. If it cannot, the host asks the public FxTwitter-style API at `https://api.fxtwitter.com` (no key) for a video file. It transcribes that file only when `ASR_BACKEND` is set. Post text is not a transcript. No caption and no ASR means not finished, and no note.

Deps: `yt-dlp` for captions and for its own audio download. `ffmpeg` when local whisper has to read media. The public API path needs neither a token nor a cookie. Set `FX_TWITTER_API=off` to skip that API and leave the attempt to yt-dlp. Set `YTDLP_COOKIES` to a cookies file path when a sign-in wall blocks yt-dlp. Do not commit the file or the cookie value.

A public X video often has no caption track. Without `ASR_BACKEND=whisper` or `ASR_BACKEND=openai` (and `OPENAI_API_KEY` for the latter), the honest result is not finished. That is a real stop.

yt-dlp may report a media id that is not the status id. Captions are kept only when the webpage URL is still that status.

A public check of `https://x.com/NASA/status/2102748685792596449` finished from yt-dlp English captions. The committed receipt is `evals/results/live/x_2102748685792596449/`. The note quotes that short caption and does not expand it. With yt-dlp missing, the same URL still returned a video from the public API and stopped at not finished: no caption track, `ASR_BACKEND` unset, post text not used.

## Check a note

```bash
python3 scripts/verify_note.py \
  --transcript artifacts/youtube_KwhgfwOSToQ/transcript.txt \
  --note artifacts/youtube_KwhgfwOSToQ/note.md
```

Exit 0 means allowed. Any other exit means do not deposit the note. Allowed requires all three: the file exists, the quality gate passed, and the note quotes 40 contiguous characters of the transcript (`QUOTE_WINDOW` in `verify_note.py`). Pasting the path under a rewritten title is refused.

## Environment variables

Names only. Do not commit values.

| Name | Meaning |
| :--- | :--- |
| `YTDLP_COOKIES` | Optional path to a cookies file for YouTube or X. The file stays out of git. |
| `YTDLP_EXTRACTOR_ARGS` | Optional yt-dlp extractor args, for example a player client. |
| `INVIDIOUS_INSTANCE` | YouTube only. Optional mirror base URL, comma-separated, or `off`. |
| `FX_TWITTER_API` | Public X status API origin. Default `https://api.fxtwitter.com`. `off` skips it. No key. Other hosts are refused. |
| `ASR_BACKEND` | `off` (default), `whisper`, or `openai`. Shared by both hosts. |
| `WHISPER_MODEL` | Local whisper model. Default `small`. |
| `WHISPER_UPGRADE_MODEL` | Optional second model if the first transcript fails the gate. |
| `WHISPER_LANGUAGE` | Optional language code passed to whisper. |
| `OPENAI_API_KEY` | Required when `ASR_BACKEND=openai`. Never commit the value. |
| `OPENAI_TRANSCRIBE_MODEL` | Default `whisper-1`. |
| `OPENAI_BASE_URL` | Optional API base. Default `https://api.openai.com/v1`. |

`--expected-lang zh` (or `en`, `ja`, `ko`) selects the caption track when one exists and fails the gate on a script mismatch. That is what blocks an English loop when the talk is Chinese. ASR audio extract needs `ffmpeg`.

## CJK ratio and English jargon

`--expected-lang zh` fails closed when Chinese characters are fewer than 8, or when the CJK ratio among CJK plus Latin letters is under 0.35. Those floors are `ZH_MIN_CJK` and `ZH_MIN_CJK_RATIO` in `quality_gate.py`. They are not command-line flags.

A real Chinese talk packed with English technical terms (API names, model names, `RAG`, `Kubernetes`) can sit under 0.35 and be refused even though a person was speaking, and even though the CJK count itself is above 8. The universal checks (length, loops, gibberish, confidence) can still pass on that same text. The false reject is intentional: this ratio check is what blocks an English hallucination loop when Chinese was expected. A wrong note is worse than holding the talk back.

Tune by omitting `--expected-lang` when you know the talk mixes Chinese with English identifiers and you accept losing the script check. Do not omit it just to force a bad transcript through. There is no flag to lower 0.35 for one job. Omit `--expected-lang` when you do not actually know the language. Pass `en`, `ja`, or `ko` only when you do.

## Offline

Settle does not fetch. It only gates a file you already have.

```bash
python3 scripts/youtube_host.py --settle-transcript evals/fixtures/empty_transcript.txt \
  --video-id empty-asr --expected-lang en --out /tmp/tfv

python3 scripts/x_host.py --settle-transcript evals/fixtures/usable_en_transcript.txt \
  --status-id 123456789012345678 --expected-lang en --out /tmp/tfv
```

Regenerate the checked-in pass/fail record. `--skip-live` skips the YouTube fetch; fixture mismatches still fail. CI uses that.

```bash
python3 scripts/test_gate.py
python3 scripts/run_evidence.py
python3 scripts/run_evidence.py --skip-live
```

`python3 scripts/quality_gate.py TRANSCRIPT --expected-lang zh` checks a transcript file alone.
