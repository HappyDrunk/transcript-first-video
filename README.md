# transcript-first-video

[English](#english) · [中文](#中文)

# English

YouTube and Twitter/X video only. Other sites are not fetched. This is a transcript-first gate, not a summarizer. The scripts fetch and check. You write the note.

A finished note needs both bars. (A) The spoken words are written down and pass the quality gate. (B) The local `note.md` analyzes that transcript. No usable transcript means not finished. A title, a blurb, or a post is not a watch. The gate does not listen to the audio.

## Install

Ask language once, before any fetch. The choices are `中文`, `英文`, and `中英文对照`. Save one line in `language.txt` beside the installed `SKILL.md`. If it is missing or not one of those three, ask. Do not assume `中英文对照`.

```text
Install this skill: https://github.com/HappyDrunk/transcript-first-video
```

Or clone the folder and leave the name as it is:

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git ~/.agents/skills/transcript-first-video
```

The full rule is [Language preference](SKILL.md#language-preference) in [SKILL.md](SKILL.md). If this page and that file disagree, follow the file.

## Note shape

Open with `## 先记住一句话`. Then four sections, in order: 问题与做法, 完整怎么做, 翻车或别用, 今天立刻动手一步. Never `课前`.

The local `note.md` keeps YAML frontmatter and the quotes `verify_note.py` checks. Feishu or chat delivery strips that frontmatter.

Chinese delivery prose is **小白能懂** by default. Say 为什么, 是什么, and 好处 in plain words. A Latin proper noun from the quote may stay. Do not stack jargon in headings or in the body. Do not add a fact the local note does not already ground. English quotes stay in the local note when the language is `中文`. `英文` is English prose only. `中英文对照` adds contiguous original-language quotes under the sections. This is not a second install question.

## Read-feel knobs

Constants are the skeleton and the hard gates: the opening heading, the four sections, R01–R17, and Coverage C. Variables are read-feel. They are not an install wizard. Set them only when someone asks. They do not loosen faithfulness.

| Knob | What it changes |
| :--- | :--- |
| 语气 | How formal the sentences sound |
| 密度 | How tight or open the paragraphs are |
| 比喻 | A metaphor only when the quote already supports it |
| 类比 | An analogy only when the quote already supports it |
| 专名 | A Latin proper noun stays as the quote has it, unless you are told to gloss it |

## Run

```bash
pip install -r requirements.txt
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --out artifacts
python3 scripts/x_host.py "https://x.com/USER/status/STATUS_ID" --out artifacts
python3 scripts/verify_note.py --job artifacts/youtube_<id>
python3 scripts/coverage_check.py --job artifacts/youtube_<id>
```

The host writes a scaffold, not the analysis. `verify_note.py` is R01–R17. `coverage_check.py` runs after that, before finished or delivery. On a video longer than 5 minutes it checks inventory, quartiles, and inventory hit-rate. `--delivery` checks that the Feishu or chat body is not a thin stub. `ASR_BACKEND` is off until you set it. Offline check: `bash scripts/smoke.sh`. More commands: [scripts/README.md](scripts/README.md).

## Evidence

CI scores the fixture table, not a model grade of the summary: [evals/results/gate-evidence.md](evals/results/gate-evidence.md). Public-URL receipts, with the old template notes withdrawn: [evals/results/live/](evals/results/live/). A human reading of the refusals: [evals/results/spotcheck.md](evals/results/spotcheck.md). The 1.0.0 Hall J receipt is [evals/results/hall_j_retest_receipt.md](evals/results/hall_j_retest_receipt.md). That run used in-distribution notes. It is not a held-out 9.

How to change this repo: [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md).

## License

MIT. Copyright (c) 2026 HappyDrunk. Full text: [LICENSE](LICENSE).

# 中文

只抓 YouTube 和 Twitter/X 的视频。别的网站不抓。这是一道「先有文稿才许写笔记」的门槛，不是摘要器。脚本负责抓取和核对。笔记由你来写。

写完要过两道。（A）嘴里的话落成文字，并且过了质量检查。（B）本地 `note.md` 分析这段文稿。没有能用的文稿，就是没看完。标题、简介、帖子都不算看过。门槛不听音频。

## 安装

抓视频之前，先问一次语言。选项是 `中文`、`英文`、`中英文对照`。在装好的 `SKILL.md` 旁边，把答案写成一行 `language.txt`。文件没有，或者不是这三样，就问。不要默认中英文对照。

```text
帮我安装这个skill：https://github.com/HappyDrunk/transcript-first-video
```

或者自己克隆，文件夹名留着：

```bash
git clone https://github.com/HappyDrunk/transcript-first-video.git ~/.agents/skills/transcript-first-video
```

完整规矩在 [SKILL.md](SKILL.md) 的 [Language preference](SKILL.md#language-preference)。这页和那个文件要是说得不一样，以那个文件为准。

## 笔记长什么样

先写 `## 先记住一句话`。然后四节，按这个顺序：问题与做法、完整怎么做、翻车或别用、今天立刻动手一步。不要写 `课前`。

本地 `note.md` 留着 YAML 前置字段，和 `verify_note.py` 要核对的引文。交给飞书或聊天时，去掉前置字段。

中文交付正文默认是 **小白能懂**。用白话写为什么、是什么、好处。引文里的拉丁专名可以留着。标题和正文不要堆术语。不要加本地笔记没有落住的事实。语言是 `中文` 时，英文引文留在本地笔记里。`英文` 只交付英文正文。`中英文对照` 在各节下面加上连续的原文引文。这不是第二道安装提问。

## 读感旋钮

常量是骨架和硬门槛：开头标题、四节、R01–R17、Coverage C。变量是读感。安装时不问。只有人开口要改，才动。它们不放宽忠实度。

| 旋钮 | 改什么 |
| :--- | :--- |
| 语气 | 句子正式还是口语 |
| 密度 | 段落紧还是松 |
| 比喻 | 只用引文已经撑得住的比喻 |
| 类比 | 只用引文已经撑得住的类比 |
| 专名 | 拉丁专名按引文保留，除非明确要求改写成解释 |

## 怎么跑

```bash
pip install -r requirements.txt
python3 scripts/youtube_host.py "https://www.youtube.com/watch?v=jNQXAC9IVRw" --out artifacts
python3 scripts/x_host.py "https://x.com/USER/status/STATUS_ID" --out artifacts
python3 scripts/verify_note.py --job artifacts/youtube_<id>
python3 scripts/coverage_check.py --job artifacts/youtube_<id>
```

主机写下的是脚手架，不是分析。`verify_note.py` 是 R01–R17。`coverage_check.py` 在它之后跑，标完成或交付之前一定要跑。超过五分钟的视频要查清单、时间四分位，和清单命中。`--delivery` 用来拒绝飞书或聊天里过薄的正文。`ASR_BACKEND` 不设置就是关着。离线核对：`bash scripts/smoke.sh`。更多命令见 [scripts/README.md](scripts/README.md)。

## 证据

CI 打分的是夹具表，不是给摘要质量打分：[evals/results/gate-evidence.md](evals/results/gate-evidence.md)。公开网址的回执，旧模板笔记已撤回：[evals/results/live/](evals/results/live/)。人读拒绝样本：[evals/results/spotcheck.md](evals/results/spotcheck.md)。`v1.0.0` 的 Hall J 回执在 [evals/results/hall_j_retest_receipt.md](evals/results/hall_j_retest_receipt.md)。那次用的是分布内的笔记。不是留出集上的 9 分。

怎么改这个仓库：[CONTRIBUTING.md](CONTRIBUTING.md)，[CHANGELOG.md](CHANGELOG.md)。

## 许可

MIT。Copyright (c) 2026 HappyDrunk。全文见 [LICENSE](LICENSE)。
