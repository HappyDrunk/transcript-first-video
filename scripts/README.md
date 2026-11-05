# scripts/

YouTube and Twitter/X video. Same quality gate, same note rule. Other platforms are not fetched here.

Run from the repo root. A host writes `transcript.txt`, `segments.json`, `chunks/NN.txt`, and `note.scaffold.md` when the gate passes. Caption lines in `transcript.txt` are `[mm:ss] text`, or `[hh:mm:ss] text` after one hour. `segments.json` stores `start`, `end`, and `text` in seconds. Chunks are about 8 minutes or about 6000 characters. Plain text with no clock stays unstamped, and those segment times are null. The scaffold is Obsidian Markdown: YAML frontmatter (`title`, `source_url`, `video_id`, `acquisition`, `gate_passed`, `transcript_path`, `quoted_window`, and `caption_kind` / `caption_trust` when set), four empty headings (问题与做法, 完整怎么做, 翻车或别用, 今天立刻动手一步), and fill instructions. `title` is the job id. The platform title and description are not stored. The scaffold is not a finished knowledge note. `caption_trust: low` means automatic captions were not in the expected language. Feishu is not called. On failure the host writes `status.json` only and deletes a previous transcript, segments, chunks, note, and scaffold for that same job id. The gate does not listen to the audio, and CI does not score summary quality.

## Smoke

After installing the whole repository directory, check that its scripts and references are present:

```bash
python3 scripts/install_check.py
```

Offline:

```bash
bash scripts/smoke.sh
```

This creates `.venv` if it is missing, installs `requirements.txt` (yt-dlp), runs `scripts/test_gate.py`, `scripts/test_no_overfit.py`, `scripts/test_claim_ground_check.py`, and `scripts/test_coverage_check.py`, settles `evals/fixtures/usable_en_transcript.txt`, regenerates fixture evidence with `run_evidence.py --skip-live`, and runs `scripts/verify_report.py`. ASR stays off. No language model is called. `test_claim_ground_check.py` checks a counts API on synthetic fixture notes. It does not score gold notes. `test_coverage_check.py` checks gate C on synthetic jobs. It does not score a human 9/10.

With a network, the same script also tries a short public captioned video ("Me at the zoo", `jNQXAC9IVRw`):

```bash
bash scripts/smoke.sh --live
```

`--live` still does not set `ASR_BACKEND`. No captions means `not_finished`. Whisper is a separate install: `pip install -r requirements-asr.txt`, then `ASR_BACKEND=whisper`. `ffmpeg` has to be on `PATH` for local whisper.

Evidence JSON and Markdown record repo-relative paths (`scripts/verify_note.py`, `evals/fixtures/...`). A machine path such as `/workspace/...` or `C:\Users\...` fails the evidence script. A Windows checkout prefix is stripped, then any remaining backslash is written as `/`. `--skip-live` keeps the checked-in live sample and does not delete `evals/results/live/`. CI runs that command and fails if `evals/results` changes.

## YouTube

```bash
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=KwhgfwOSToQ" --out artifacts
```

Captions first via `yt-dlp` (`pip install -r requirements.txt`, or `python3 -m yt_dlp` on `PATH`). If YouTube asks for a sign-in and `YTDLP_COOKIES` is unset, the host tries a public caption mirror unless `INVIDIOUS_INSTANCE=off`. The mirror is a third party: it can be wrong, and the quality gate cannot tell a fluent fake from real speech. The scaffold title is the job id. The platform title and description are not written into the scaffold. The host does not analyze the caption. Transcripts from two public runs, with the old template notes removed, are `evals/results/live/youtube_jNQXAC9IVRw/transcript.txt` and `evals/results/live/youtube_KwhgfwOSToQ/transcript.txt`.

## Twitter/X video

```bash
python3 scripts/x_host.py "https://x.com/USER/status/STATUS_ID" --out artifacts
```

`twitter.com` status URLs are the same input. Captions first, when yt-dlp can see a caption track. If it cannot, the host asks the public FxTwitter-style API at `https://api.fxtwitter.com` (no key) for a video file. It transcribes that file only when `ASR_BACKEND` is set. Post text is not a transcript. No caption and no ASR means not finished, and no note.

Deps: `yt-dlp` for captions and for its own audio download. `ffmpeg` when local whisper has to read media. The public API path needs neither a token nor a cookie. Set `FX_TWITTER_API=off` to skip that API and leave the attempt to yt-dlp. Set `YTDLP_COOKIES` to a cookies file path when a sign-in wall blocks yt-dlp. Do not commit the file or the cookie value.

A public X video often has no caption track. Without `ASR_BACKEND=whisper` or `ASR_BACKEND=openai` (and `OPENAI_API_KEY` for the latter), the honest result is not finished. That is a real stop.

yt-dlp may report a media id that is not the status id. Captions are kept only when the webpage URL is still that status.

A public check of `https://x.com/NASA/status/2102748685792596449` kept a transcript from yt-dlp English captions. The committed receipt is `evals/results/live/x_2102748685792596449/`. The template note that used to sit there was withdrawn. With yt-dlp missing, the same URL still returned a video from the public API and stopped at not finished: no caption track, `ASR_BACKEND` unset, post text not used.

## Check a note

```bash
python3 scripts/verify_note.py --job artifacts/youtube_KwhgfwOSToQ
```

Exit 0 means allowed. Any other exit means do not deposit the note. Allowed requires the transcript to pass the quality gate and a knowledge note: frontmatter plus the four sections, each quoting 40 contiguous characters of the transcript (`QUOTE_WINDOW` in `knowledge_note.py`). A section may instead be one line, `本节不适用：<reason>`, plus one quote. If every section is that line, the command sets `status` to `no-extractable-content` and deletes `note.md`. Pasting the path under a rewritten title is refused. So is a quote with no analysis. This check does not play the audio and does not grade an LLM summary. `--transcript` and `--note` still work for a fixture pair.

## Local claim counts

```bash
python3 scripts/claim_ground_check.py path/to/note.md --quiet
python3 scripts/test_claim_ground_check.py
```

`claim_ground_check.py` is an optional local helper. It counts prose sentences whose numbers, proper nouns, or long same-script phrases are absent from that section's blockquotes. Paths use `pathlib`. It writes only when you pass `--out`, and only to that path. It does not call a language model. Public CI runs `test_claim_ground_check.py`, which checks that counts API on synthetic fixture notes and does not score gold. CI does not run `claim_ground_check.py` as a gate or as an LLM judge. R01–R17 stay in `verify_note.py`.

## Coverage gate C

```bash
python3 scripts/coverage_check.py --job artifacts/youtube_KwhgfwOSToQ
python3 scripts/coverage_check.py --job artifacts/youtube_KwhgfwOSToQ --delivery path/to/body.md
python3 scripts/test_coverage_check.py
```

Grounded is not covered. The human bar for a long 通读 is 9/10 detail depth and 9/10 summary completeness. Both count. This script does not score that bar and does not call a model. It always runs after `verify_note.py` and before finished or a Feishu/chat send. On a video longer than 5 minutes it refuses a missing inventory (C01), quotes in fewer than 3 duration quartiles (C02), or fewer than 9/10 of the inventory lines (C03, at least 3). `--delivery` refuses a body whose CJK and Latin letters, after YAML and quote lines are removed, are under 0.9× `note.md` (C04). At or under 5 minutes, C01–C03 are skipped and the command still runs. Exit 0 is allowed. Exit 1 is FAIL (`Cxx FAIL: ...`). Exit 2 is usage. A thin grounded stub fails. A full-arc note passes. R01–R17 are unchanged. Spotcheck stays human.

Coverage C checks that the note uses the inventory the job already wrote: the rows exist (C01), note quotes spread across quartiles (C02), and at least 9/10 of those rows show up in the note (C03, at least 3). It does not prove the inventory itself was complete against the full transcript. A thin inventory can still pass. The gate stops "wrote an inventory and then ignored it." It does not stop "under-extracted at inventory time."

On a long job with a loaded inventory, the command may print `C WARN` when the row count is implausibly low: fewer than one line per 10 minutes, or fewer lines than `chunks/NN.txt` files when there are two or more chunks. That line does not change the exit code and does not loosen C01–C04. A run with no warning is still not a completeness proof. The same limit is in `references/rules.md`.

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

A real Chinese talk packed with English technical terms (API names, model names, `RAG`, `Kubernetes`) can sit under 0.35 and be refused even though a person was speaking, and even though the CJK count itself is above 8. The universal checks (length, loops, gibberish) can still pass on that same text. A confidence number is applied only when the caller passes one. The whisper CLI path does not. The false reject is intentional: this ratio check is what blocks an English hallucination loop when Chinese was expected. A wrong note is worse than holding the talk back.

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
python3 scripts/test_no_overfit.py
python3 scripts/test_claim_ground_check.py
python3 scripts/test_coverage_check.py
python3 scripts/run_evidence.py
python3 scripts/verify_report.py
python3 scripts/run_evidence.py --skip-live
```

`python3 scripts/quality_gate.py TRANSCRIPT --expected-lang zh` checks a transcript file alone.
