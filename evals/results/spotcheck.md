# Spot-check

Reviewed 2026-11-03 by the agent that added this file, by reading the committed notes next to their transcript files.

**CI does not score this file.** The Actions job `gate` does not open it. A green check is the fixture table in [gate-evidence.md](gate-evidence.md). Re-read these rows if the notes change. This file is the same kind of assertion as [../evals.json](../evals.json): a person or an agent can check it, and the mechanical gate is a different layer.

## What a "pass" means here

The quoted lines appear in the transcript file, and the note's other sentences are about the file (the path, the gate, how the text was acquired). The note does not continue the video in new words. The reviewer did not listen to the audio. A pass here does not mean the captions match the soundtrack. The quality gate does not prove that either.

Rows that name a fixture are the agent's reading of a file the gate also refuses. The gate's exit code is layer ①. This table is not that exit code.

| id | claim | reading | where |
| :--- | :--- | :--- | :--- |
| cite-zoo | The quote is in the transcript | Pass. Every blockquote line is in the transcript. The frontmatter window is those lines collapsed to 217 characters, which is the whole speech in the file (the file is 218 characters with its trailing newline). | [live/youtube_jNQXAC9IVRw/note.md](live/youtube_jNQXAC9IVRw/note.md) |
| no-extra-zoo | The note does not invent speech past the quote | Pass. Outside the quote, the note names the URL, the job id, `caption-mirror`, and the transcript path. It does not add a scene, a date, or a method. | same note |
| cite-x | The quote is the whole caption | Pass. The transcript file is one line plus a trailing newline (106 characters). The note quotes that line (105 characters). | [live/x_2102748685792596449/note.md](live/x_2102748685792596449/note.md) |
| no-extra-x | The note does not expand the promo line | Pass. The caption names a spaceport, a date range, and a URL. The note copies those words and does not describe footage, a crowd, or an announcement around them. | same note |
| stop-nocaption | A missing caption does not become a note | Pass. The directory has `status.json` only (`not_finished`, `note` null, `transcript` null). yt-dlp reported a sign-in wall. The caption mirror reported no caption track. ASR was off. This row does not claim a logged-in YouTube client would also see zero captions. | [live/youtube_C0DPdy98e4c/status.json](live/youtube_C0DPdy98e4c/status.json) |
| cite-long | The quote is a prefix of the long transcript | Pass. Nine blockquote lines match the start of the transcript. The frontmatter window is 339 characters. The transcript file is 17015 characters. | [live/youtube_KwhgfwOSToQ/note.md](live/youtube_KwhgfwOSToQ/note.md) |
| no-extra-long | The note does not summarize the rest of the talk | Pass. The quote stops at "FTE". The file goes on. The note does not retell the rest, and it does not correct caption spellings such as "Ripling". | same note |
| path-only | A path and a title are not a quote | Pass, as a reading. The fixture says the video was watched and pastes a path. It does not quote the repotting sentences. The gate also refuses this file. That refusal is layer ①, not a score of this row. | [../fixtures/path_only_note.md](../fixtures/path_only_note.md) |
| launder | An essay about a failed transcription is not the video | Pass, as a reading. The fixture files the talk as "ASR quality failure cases" and says new hires can learn from the essay. The loop transcript is not that essay. The gate also refuses this file. | [../fixtures/laundered_essay_note.md](../fixtures/laundered_essay_note.md) |

## Not observed

A public URL whose captions are gibberish, or an English loop on a Chinese talk, was not part of this fetch. ASR stayed off, and no gibberish file was written to stand in for one. Those stops are the fixture rows `gibberish` and `zh-en-loop-launder` in the mechanical table.
