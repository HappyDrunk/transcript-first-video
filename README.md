# transcript-first-video

Transcript-first video reading skill: captions → ASR → quality gate → analyze. A title, description, or thumbnail is never a watch. If there is no usable transcript, the task is not finished.

**字幕优先的视频阅读技能：** 官方字幕或通过质量门的 ASR 文本，才算读过。没有可用文稿就明确说未完成，不把标题当成已看。

## Install

Clone this repository, or copy this folder into an agent's skills directory. Follow [`SKILL.md`](SKILL.md).

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git
```

Cloning the repo is the skill. Place the folder where your agent loads skills (often `skills/transcript-first-video/` next to the host worker).

## Contents

| Path | Role |
|------|------|
| [`SKILL.md`](SKILL.md) | Skill policy: pipeline, quality gate, secrets rules |
| [`references/pitfalls.md`](references/pitfalls.md) | Production mistakes (sanitized) |
| [`evals/evals.json`](evals/evals.json) | Starter prompts for with-skill vs without-skill evals |
| [`scripts/`](scripts/) | Placeholder for host-project worker CLIs |

Runnable enqueue / ASR workers live in the host project. This package ships policy, pitfalls, and evals. It does not invent credentials.

## Secrets

No secrets in this repository. Docs name environment variables only, for example `BILIBILI_SESSDATA` (optional; never print the value) and whatever ASR or LLM key names your runtime already uses. Do not commit cookie values or API keys.

## License

[MIT](LICENSE) — Copyright (c) 2026 HappyDrunk
