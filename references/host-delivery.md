# Host delivery

Generate the reading copy in the channel folder. Keep the evidence note in the job directory.

```text
python scripts/render_reading_note.py --require-review --task-dir "<job directory>" --output-dir "<channel folder>"
```

The renderer runs verify and coverage before writing the output. If you change the manuscript or selection, obtain a fresh review receipt before rerunning with `--require-review`. A host with Feishu, chat, or a wiki can attach or link the generated Markdown file. The host project supplies its own destination and credentials. See the [delivery format](delivery-format.md).
