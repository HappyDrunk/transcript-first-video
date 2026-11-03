# Pitfalls (sanitized production lessons)

These patterns came from real video-processing failures. They are stated as rules so implementers do not rediscover them the hard way. No secrets, account cookies, or private table ids are included.

Bundled hosts in this repo are YouTube and Twitter/X video only. Lessons below that name Bilibili are about expired media URLs and Chinese ASR. This repo does not ship a Bilibili, Douyin, or Xiaohongshu fetcher.

## 1. Title / tweet is not a watch

**Mistake:** Deposit a final note from title, description, engagement stats, or surrounding tweet text while the video itself was never transcribed.

**Fix:** Completion requires a usable transcript (or an explicitly labeled metadata-only degradation the user accepted). Tags like `needs-transcript` / `video-pending` must not coexist with a “fully understood” status. The note also has to quote a contiguous stretch of the transcript (40 characters) inside each knowledge section: 问题与做法, 完整怎么做, 翻车或别用, 今天立刻动手一步. A pasted path under a rewritten title is not a quote. A quote with no analysis is not knowledge. The quote check does not listen to the audio. A fluent wrong caption can still pass it.

## 2. Short video ≠ exempt

**Mistake:** Fail inline ASR on a 20-second clip, append “video not transcribed”, and still mark the item fully archived / knowledge-ready.

**Fix:** Duration does not decide completeness. Inline failure must create or reuse a recoverable video job. Only transcript success (or clear user-accepted degrade) closes the loop.

## 3. Jobs without a consumer

**Mistake:** Create `needs-transcript` jobs from the inbox path, then rely on humans to remember `process_video_jobs` by hand. Items rot for days.

**Fix:** Production needs a scheduled worker (timer / cron / routine kick). Manual rerun is for verification, not the happy path.

## 4. Ephemeral CDN URLs as identity or playback

**Mistake:** Persist a signed Bilibili (or similar) CDN audio URL as the job id or as the only media handle; worker later 403s.

**Fix:** Stable id = platform + durable content id. At run time, refresh media from the canonical source URL.

## 5. English ASR on Chinese speech

**Mistake:** Default English recognition on Chinese Bilibili audio → Latin hallucination, loops, multilingual garbage → analyzer “helpfully” writes a note about the ASR failure as if that were the video’s topic.

**Fix:** Set expected language for the content. Run a quality gate **before** analysis. Do not let the analyzer be the hallucination detector.

**False reject:** `--expected-lang zh` also refuses a real Chinese talk when English technical terms pull the CJK ratio under 0.35, even if there are more than 8 CJK characters. That fail-closed is intentional. Omit `--expected-lang` only when you accept losing the script check; loop, gibberish, and confidence checks still run. `ZH_MIN_CJK` and `ZH_MIN_CJK_RATIO` live in `scripts/quality_gate.py`. They are not command-line flags. Do not lower them to force a bad transcript through.

## 6. “Has Chinese characters” is not quality

**Mistake:** After forcing `language=zh`, accept any mostly-CJK transcript even when nouns / domain terms are garbage and confidence is low.

**Fix:** Gate on confidence / repeat / semantic sanity, not character script alone. Prefer a production floor like `small` (or higher) for Chinese; use `tiny`/`base` only for diagnosis. On soft fail, auto-retry once at `medium` into a **separate** transcript file; then stop and escalate (cloud ASR / human) instead of looping forever.

## 7. Analyzer launders bad transcripts

**Mistake:** Save a low-quality transcript, run the analyzer, get a polished wrong essay, mark as knowledge.

**Fix:** No pass ⇒ no final note. If analysis still revolves around “ASR failed” instead of the video’s subject, treat as gate failure and upgrade / stop. The other direction holds too: a passing transcript plus a quote stub is not a finished note. Analysis has to say the problem, the method, the limit, and one next action, each grounded in the transcript. That requirement does not lower the gate, and it does not mean anyone listened to the audio.

## 8. Secrets in the trail

**Mistake:** Print SESSDATA / cookies / API keys into logs, receipts, docs, or commits.

**Fix:** Env var names only. Mention validity (“expired”) without values. Prefer public API paths first; cookies are optional accelerators. The bundled YouTube and X hosts do not read a Bilibili session cookie.

## 9. Host clone instead of capability extract

**Mistake:** Copy another machine’s full systemd + `.env` + inbox field map onto a new agent host, then wonder why paths and schemas break.

**Fix:** Port the capability layer (jobs + fetch captions/audio + ASR + gate + sink adapter). Keep foreign desk schemas out of the portable skill.

## 10. Mixed knowledge sinks

**Mistake:** Drop YouTube, WeChat, and X notes into one undifferentiated folder “for convenience”.

**Fix:** Route by source channel when the project maintains partitions. Unknown source should fail closed or ask, not silently default into the wrong shelf.
