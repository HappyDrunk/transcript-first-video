# scripts/

YouTube and Twitter/X video. Same quality gate, same note rule. Other platforms are not fetched here.


Run from the repo root. A successful acquisition writes `transcript.txt`, `segments.json`, `chunks/NN.txt`, and `note.scaffold.md`. Caption lines retain their clocks and the sidecar keeps available start and end times. Plain speech has null segment times. The scaffold provides the properties and blank headings for the [single-note format](../references/delivery-format.md).

A failed re-acquisition records `last_attempt` on an existing job and preserves its files and status. A successful replacement archives the old `note.md`, any historical `delivery.md`, and `selection.md` under numbered `.prev` names as needed. Historical chunk notes are kept with the archived chunks. A replacement resets the shared repair state.

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

Write `selection.md` and `note.md` in the job directory. For channel delivery, generate the reading copy.

```bash
python3 scripts/render_reading_note.py --task-dir artifacts/youtube_KwhgfwOSToQ --output "channel/〈发布日期〉 〈频道〉 - 〈标题〉.md"
```

The renderer runs verify and coverage in order. It writes the reading copy when both checks mark the current inputs `finished`. Add `--keep-frontmatter` to retain the opening YAML block. The job directory keeps the evidence note and its inputs. See the [delivery format](../references/delivery-format.md).

For standalone checks, run these commands in order.

```bash
python3 scripts/verify_note.py --job artifacts/youtube_KwhgfwOSToQ
python3 scripts/coverage_check.py --job artifacts/youtube_KwhgfwOSToQ
```

Verify checks R01, R04, R05, R13–R15, and C04a–d. Exit 0 means allowed, 2 means refused, and 1 indicates usage or a read error. `--transcript` and `--note` still support standalone checks. For `--job`, `transcript_path` resolves from the job directory. A historical all-N/A note is archived and recorded as `no-extractable-content`.

## Local claim counts

```bash
python3 scripts/claim_ground_check.py path/to/note.md --quiet
python3 scripts/test_claim_ground_check.py
```

`claim_ground_check.py` is an optional local helper. It counts prose sentences whose numbers, proper nouns, or long same-script phrases are absent from that section's blockquotes. Paths use `pathlib`. It writes only when you pass `--out`, and only to that path. It does not call a language model. Public CI runs `test_claim_ground_check.py`, which checks that counts API on synthetic fixture notes and does not score gold. CI does not run `claim_ground_check.py` as a gate or as an LLM judge. This helper reads historical section-level quotes. Use the two checks above for the single-note workflow.


## Coverage

S01 checks `selection.md` on every job. Ranges must cover the full transcript in order. At least 90% of the retained units and at least three units must have verified end quotes. Evidence and body links must stay in retained units, and `本文略去` must list the omitted ranges. Omitting over half the runtime prints a warning.

C02 checks at least three quartiles on long jobs. Without a reliable clock, coverage can still report character-position diagnostics, while verify refuses delivery with「缺时间戳，请用带时间戳的转写重跑」.

Coverage exits 0 on a pass, 1 on FAIL, and 2 on usage error. A pass writes `finished: true` only with a successful verify on the same note, transcript, and selection. Run both commands after editing any of those files. `--json` reports failures, warnings, and checks that did not run. The compatibility option `--delivery` accepts the same note or a byte-for-byte copy.

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
