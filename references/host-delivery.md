# Host delivery

Optional notes for a host that sends the finished note somewhere other than a folder of Markdown files. `SKILL.md` does not call Feishu, a wiki, or chat, and it does not read a token. R01–R17 and Coverage C are unchanged. A folder of `.md` files is a complete sink.

The delivery body follows `language.txt`. Do not add a fact, a number, a name, or a cause the local `note.md` does not already ground. Strip machine YAML if this sink cannot keep it.

## Feishu or chat

This skill does not call the Feishu API and does not read a Feishu token. A Feishu wiki, a Notion database, or a chat channel can live in the host project and consume this Markdown.

When the sink is Feishu or chat, send the delivery body, not the raw `note.md`. If `language.txt` is missing or invalid, ask and persist it. Do not upload yet.

`verify_note.py` and `claim_ground_check.py` read the local `note.md`, not the delivered body. Quotes stay in that file so those checks can ground claims. The delivered body does not have to repeat them, except when `language.txt` is `中英文对照`.

Strip YAML frontmatter before upload. Do not paste Obsidian or machine frontmatter into the delivered body. That includes `title`, `source_url`, `video_id`, `acquisition`, `gate_passed`, `transcript_path`, `quoted_window`, `caption_kind`, `caption_trust`, `platform_title`, and any other `---` block.

- `中文` — Chinese prose only. Leave transcript quote blocks in the local note. Prose is 小白能懂: plain words for 为什么, 是什么, and 好处, with no added fact.
- `英文` — English prose only. Leave transcript quote blocks in the local note.
- `中英文对照` — prose plus that section's contiguous original-language quotes.

The body opens with `## 先记住一句话`. A long 通读 in that body still covers the main method-bearing arcs. Do not rewrite `note.md` to match the delivery wording. That wording does not loosen R01–R17 or Coverage C.

Before send, and only after `language.txt` is valid and both `verify_note.py --job` and `coverage_check.py --job` have allowed the note:

```bash
python3 scripts/coverage_check.py --job <dir> --delivery <body>
```

C04 FAIL is 未交. It uses the same two repair rounds shared with verify. Do not send. `finished` stays false until verify and coverage have both allowed the note.

This skill does not hardcode personal wiki tokens. Pass parent / sink config from the host project. Keep sinks channel-separated when the user maintains partitions (YouTube vs X vs WeChat vs official docs). Do not dump every medium into one catch-all folder.

## C04 on a host body

`--delivery` is how this host passes the Feishu or chat body. C04 runs whenever that body is about to be sent. Delivery prose letters (CJK plus Latin, YAML and quote lines removed) under 0.9× the same count in `note.md` fail. That is the summary-completeness floor. A full-arc body passes. A thin stub fails. Four grounded claims and a short Feishu body are below the human bar (9/10 detail depth and 9/10 summary completeness) even when every written sentence is faithful. The script does not score that bar and does not call a model.

Write the local prose in the delivery language so the comparison is the same text with quotes removed, not a short recap of a longer note.

## This host's past mistake

One host opened notes with `课前` or `课前先记住一句话`. The opening heading is `## 先记住一句话`. Do not put `课前` on that heading or on any other heading.

A host delivery that uses the seven-block labels (课堂开场, 核心拆解, 真实案例, 写好××的×条, 避坑指南, 课后作业) still opens with `先记住一句话`. Those labels do not replace the four sections in local `note.md`, and they do not skip verify.
