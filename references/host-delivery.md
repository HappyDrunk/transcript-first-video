# Host delivery

Generate the reading copy in the channel folder. Keep the evidence note in the job directory.

```text
python scripts/render_reading_note.py --task-dir "<job directory>" --output "<channel folder>/〈发布日期〉 〈频道〉 - 〈标题〉.md"
```

The renderer runs verify and coverage before writing the output. Rerun it after changing the manuscript or selection. A host with Feishu, chat, or a wiki can attach or link the generated Markdown file. The host project supplies its own destination and credentials. See the [delivery format](delivery-format.md).
