# Spot-check

Reviewed 2026-11-03 by the agent that regenerated the committed notes, by reading those notes next to their transcript files.

**CI does not score this file.** The Actions job `gate` does not open it. A green check is the fixture table in [gate-evidence.md](gate-evidence.md). That table checks shape: a usable transcript, a citation, a quote in each knowledge section, and a refusal of empty or boilerplate analysis. It does not grade how good the analysis is, and it does not listen to the audio. Re-read these rows if the notes change. This file is the same kind of assertion as [../evals.json](../evals.json).

## What a "pass" means here

Both bars show up in the reading. (A) The quotes are contiguous text from the transcript file. (B) The four sections form reusable knowledge: a problem and a move, the steps, a limit, and one action for today. The reviewer did not listen to the audio. A pass here does not mean the captions match the soundtrack. The quality gate does not prove that either. Fluent wrong captions stay outside what this file can settle.

Rows that name a fixture are the agent's reading of a file the gate also refuses. The gate's exit code is layer ①. This table is not that exit code.

| id | claim | reading | where |
| :--- | :--- | :--- | :--- |
| knowledge-zoo | The short caption becomes an observation with a bound, not a zoo guide | Pass. 问题与做法 keeps one place and one trait: in front of the elephants, and long trunks. 完整怎么做 says there is no multi-step method. 翻车或别用 says the yell is not a method and refuses care, diet, age, and conservation. 今天立刻动手一步 says to write that one sentence and stop. Each blockquote is in the 217-character caption. The note does not add a species fact. | [live/youtube_jNQXAC9IVRw/note.md](live/youtube_jNQXAC9IVRw/note.md) |
| knowledge-x | The promo line becomes an invitation with a stop, not a schedule | Pass. The note names MAX POWER, Kennedy, the November dates, and `nasa.gov/maxpower`, which are the whole caption. It says not to add a ticket price, a map, or a registration step. 今天立刻动手一步 is to open that URL and stop if the page disagrees. The blockquotes are slices of the one caption line. The note does not describe footage. | [live/x_2102748685792596449/note.md](live/x_2102748685792596449/note.md) |
| knowledge-long | The talk becomes a method, a limit, and one action | Pass. 问题与做法 states the corner case in the quote: use FTE only when selling something very technical to a non-technical buyer, and sell the outcome rather than software alone or rented time. 完整怎么做 gives the spoken order: the need question, then a platform of shared primitives, no from-scratch builds, bespoke stays on one customer, and the hire is an engineer you would put in front of a customer. Those lines are in the transcript, not only in the blockquote. 翻车或别用 quotes the from-scratch sentence and calls the result a dev shop. 今天立刻动手一步 is two yes-or-no answers, then stop. The quotes are not the opening greeting. The note keeps the caption spelling Palunteer. It does not correct it, and it does not add the contract-value figures that appear later in the file. | [live/youtube_KwhgfwOSToQ/note.md](live/youtube_KwhgfwOSToQ/note.md) |
| stop-nocaption | A missing caption does not become a note | Pass. The directory has `status.json` only (`not_finished`, `note` null, `transcript` null). yt-dlp reported a sign-in wall. The caption mirror reported no caption track. ASR was off. This row does not claim a logged-in YouTube client would also see zero captions. | [live/youtube_C0DPdy98e4c/status.json](live/youtube_C0DPdy98e4c/status.json) |
| path-only | A path and a title are not a quote | Pass, as a reading. The fixture says the video was watched and pastes a path. It does not quote the repotting sentences. The gate also refuses this file. That refusal is layer ①, not a score of this row. | [../fixtures/path_only_note.md](../fixtures/path_only_note.md) |
| quote-stub | A real quote with no analysis is not knowledge | Pass, as a reading. The fixture has frontmatter and a real pothos quote, and the body is still Source / Transcript / Quoted window. There is no problem, no method, no limit, and no next action. The gate also refuses this file. The refusal checks shape. It is not a model grade of the prose. | [../fixtures/quote_stub_note.md](../fixtures/quote_stub_note.md) |
| boilerplate | Four headings and a copied-quote sentence are still a stub | Pass, as a reading. Each section quotes the transcript and then says the note is allowed because the quote was copied. The same sentence is the whole analysis. The gate also refuses this file. | [../fixtures/boilerplate_note.md](../fixtures/boilerplate_note.md) |
| launder | An essay about a failed transcription is not the video | Pass, as a reading. The fixture files the talk as "ASR quality failure cases" and says new hires can learn from the essay. The loop transcript is not that essay. The gate also refuses this file. | [../fixtures/laundered_essay_note.md](../fixtures/laundered_essay_note.md) |

## Not observed

A public URL whose captions are gibberish, or an English loop on a Chinese talk, was not part of this fetch. ASR stayed off, and no gibberish file was written to stand in for one. Those stops are the fixture rows `gibberish` and `zh-en-loop-launder` in the mechanical table.

This reading also did not play the videos. A caption can be fluent and wrong. Nothing in this file, and nothing in the mechanical table, detects that.
