#!/usr/bin/env python3
"""Phase 6A.4 TDD red tests: renderer double-paren & in-sentence gloss dedup, collision priority, anti-repetition WARNs, and doc net-shrink."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import render_reading_note as rrn  # type: ignore
import verify_note  # type: ignore
import verify_rules as vr  # type: ignore

BASELINE_DELIVERY_BYTES = 17538
BASELINE_REVIEW_BYTES = 6380

BASE_QUOTE = (
    "First inspect the local cache and run the profiling script carefully to confirm all timings "
    "and verify every parameter before writing the final report."
)

ADJ_PAREN_RE = re.compile(r"[）)]\s*[（(]")


def _make_note(
    middle: str,
    quote: str = BASE_QUOTE,
    *,
    intro: str = "讲者演示如何检查并优化本地脚本运行耗时。 ⏱ 00:10",
) -> str:
    return (
        "---\n"
        'title: "Synthetic Polish Demo"\n'
        'source: "https://example.invalid/polish6a4"\n'
        'channel: "Example Channel"\n'
        'published: "2026-01-15"\n'
        'type: "讲座"\n'
        'caption_kind: "auto"\n'
        'skill_version: "a38d6184c820db77ea0b130d9f23428de03b3e2b"\n'
        'transcript_path: "transcript.txt"\n'
        "tags: [video-note]\n"
        "---\n\n"
        "## 先记住一句话\n\n"
        "先查缓存并核对日志，再按步骤排查耗时瓶颈。 ⏱ 00:10\n\n"
        "## 这场在谈什么、谁\n\n"
        f"{intro}\n\n"
        "## 主线论点\n\n"
        "### 核心机制\n\n"
        f"{middle}\n\n"
        "本文略去｜无\n\n"
        "## 原文依据\n\n"
        f"> [00:10] {quote}\n"
    )


def _render(note: str) -> str:
    return rrn.render_note(note.encode("utf-8"), keep_frontmatter=False).decode("utf-8")


def _verify(note: str, quote: str = BASE_QUOTE) -> dict:
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td) / "transcript.txt"
        tp.write_text(f"[00:10] {quote}\n", encoding="utf-8")
        return verify_note.verify(tp, note, expected_lang="en", job=True)


def test_t1_paren_classification_and_no_double_paren() -> None:
    q = BASE_QUOTE + " Here we discuss alpha isolator, beta metric, gamma scale, delta widget, and relu."

    # 1a. Full-width English original paren -> merge inside paren before closing ')'
    n_en_fw = _make_note(
        "系统采用甲级隔振器（alpha isolator）来分隔基础。 ⏱ 00:10\n\n"
        "> [!note] 术语：甲级隔振器（alpha isolator）\n"
        "> 短释：沿曲面滑动的组件\n"
        "> 一种用于隔离基础振动的通用工程组件。",
        q,
    )
    r_en_fw = _render(n_en_fw)
    assert "甲级隔振器（alpha isolator；注：沿曲面滑动的组件）" in r_en_fw, r_en_fw
    assert not ADJ_PAREN_RE.search(r_en_fw), f"adjacent parens found: {r_en_fw}"
    assert "一种用于隔离基础振动的通用工程组件。" in r_en_fw

    # 1b. Half-width English original paren with preceding space -> merge cleanly
    n_en_hw = _make_note(
        "系统采用甲级隔振器 (alpha isolator) 来分隔基础。 ⏱ 00:10\n\n"
        "> [!note] 术语：甲级隔振器（alpha isolator）\n"
        "> 短释：沿曲面滑动的组件\n"
        "> 一种用于隔离基础振动的通用工程组件。",
        q,
    )
    r_en_hw = _render(n_en_hw)
    assert "甲级隔振器 (alpha isolator；注：沿曲面滑动的组件)" in r_en_hw, r_en_hw
    assert not ADJ_PAREN_RE.search(r_en_hw), f"adjacent parens found: {r_en_hw}"

    # 1c. Chinese explanatory paren -> skip inline gloss, keep glossary entry
    n_zh_paren = _make_note(
        "结构一直承受乙级指标（也就是房屋日常承受的自重）的荷载。 ⏱ 00:10\n\n"
        "> [!note] 术语：乙级指标（beta metric）\n"
        "> 短释：日常承受的自重\n"
        "> 衡量基础受力的常用参考量。",
        q,
    )
    r_zh_paren = _render(n_zh_paren)
    assert "乙级指标（也就是房屋日常承受的自重）" in r_zh_paren, r_zh_paren
    assert "（注：" not in r_zh_paren and "；注：" not in r_zh_paren, r_zh_paren
    assert "衡量基础受力的常用参考量。" in r_zh_paren

    # 1d. Numeric/unit paren and Chinese-count paren -> skip inline gloss
    for prose in (
        "系统按丙级量纲（9.8 m/s²）校准传感器。 ⏱ 00:10",
        "系统按丙级量纲（约 3500 份）抽样核验。 ⏱ 00:10",
    ):
        n_num = _make_note(
            f"{prose}\n\n"
            "> [!note] 术语：丙级量纲（gamma scale）\n"
            "> 短释：校准时的基准单位\n"
            "> 用于对齐实验读数的通用单位。",
            q,
        )
        r_num = _render(n_num)
        assert "（注：" not in r_num and "；注：" not in r_num, r_num
        assert not ADJ_PAREN_RE.search(r_num), r_num

    # 1e. Nested parens, unclosed paren, and code span with ')' inside paren -> never crash, no double parens
    for prose in (
        "这里用到丁级组件（外层（内层）说明）完成校验。 ⏱ 00:10",
        "这里用到丁级组件（未闭合的括号继续写完。 ⏱ 00:10",
        "这里用到丁级组件（包含 `a)` 的说明）完成校验。 ⏱ 00:10",
    ):
        n_edge = _make_note(
            f"{prose}\n\n"
            "> [!note] 术语：丁级组件（delta widget）\n"
            "> 短释：完成校验的小模块\n"
            "> 通用的辅助校验模块。",
            q,
        )
        r_edge = _render(n_edge)
        assert "（注：" not in r_edge and "；注：" not in r_edge, (prose, r_edge)

    # 1f. Fallback branch (term only in inline code) when sentence ends with ')' -> skip inline gloss
    n_fb = _make_note(
        "最后把向量送进 `relu`（常见激活函数）。 ⏱ 00:10\n\n"
        "> [!note] 术语：relu\n"
        "> 短释：把负数归零的函数\n"
        "> 神经网络常用激活函数。",
        q,
    )
    r_fb = _render(n_fb)
    assert "（注：" not in r_fb, r_fb
    assert not ADJ_PAREN_RE.search(r_fb), r_fb
    assert "神经网络常用激活函数。" in r_fb


def test_t2_in_sentence_definition_and_ji_guard() -> None:
    q = BASE_QUOTE + " Here we explain alpha mode in detail."

    # Should SKIP inline gloss when already defined in-sentence
    for prose in (
        "系统切到甲级模式，即只读不写的保护状态。 ⏱ 00:10",
        "系统切到甲级模式，也就是只读不写的保护状态。 ⏱ 00:10",
        "系统切到甲级模式——只读不写的保护状态。 ⏱ 00:10",
        "系统切到甲级模式：只读不写的保护状态。 ⏱ 00:10",
        "这种只读不写的状态，也就是甲级模式。 ⏱ 00:10",
        "这种只读不写的状态叫做甲级模式。 ⏱ 00:10",
    ):
        n = _make_note(
            f"{prose}\n\n"
            "> [!note] 术语：甲级模式（alpha mode）\n"
            "> 短释：只读不写的保护态\n"
            "> 防止意外写入的安全状态。",
            q,
        )
        r = _render(n)
        assert "（注：" not in r and "；注：" not in r, f"should skip in-sentence def for {prose!r}, got: {r}"
        assert "防止意外写入的安全状态。" in r

    # Must NOT false-suppress on 即将 / 即使 / 立即 / 随即
    for prose in (
        "甲级模式即将上线并接受实测。 ⏱ 00:10",
        "甲级模式即使超时也会保留日志。 ⏱ 00:10",
        "异常出现后立即切到甲级模式保存现场。 ⏱ 00:10",
        "排查后随即启用甲级模式复测。 ⏱ 00:10",
    ):
        n = _make_note(
            f"{prose}\n\n"
            "> [!note] 术语：甲级模式（alpha mode）\n"
            "> 短释：只读不写的保护态\n"
            "> 防止意外写入的安全状态。",
            q,
        )
        r = _render(n)
        assert "甲级模式（注：只读不写的保护态）" in r, f"must NOT suppress gloss for {prose!r}, got: {r}"


def test_t3_doubt_and_gloss_same_position_collision_both_orders() -> None:
    q = BASE_QUOTE + " The pipeline calls `relu` at the end."
    doubt = "> [!warning] 原文出入\n> 存疑｜「最后」｜口播未交代具体层号"
    term = "> [!note] 术语：relu\n> 短释：把负数归零的函数\n> 神经网络常用激活函数。"

    # Order 1: doubt BEFORE term (both target sentence end before '。')
    n1 = _make_note(f"最后调用 `relu` 完成输出。 ⏱ 00:10\n\n{doubt}\n\n{term}", q)
    r1 = _render(n1)
    assert "（存疑：口播未交代具体层号）。" in r1, r1
    assert "（注：" not in r1, f"gloss must yield to doubt at same position (order 1): {r1}"
    assert "神经网络常用激活函数。" in r1

    # Order 2: term BEFORE doubt (both target sentence end before '。')
    n2 = _make_note(f"最后调用 `relu` 完成输出。 ⏱ 00:10\n\n{term}\n\n{doubt}", q)
    r2 = _render(n2)
    assert "（存疑：口播未交代具体层号）。" in r2, r2
    assert "（注：" not in r2, f"gloss must yield to doubt at same position (order 2): {r2}"
    assert "神经网络常用激活函数。" in r2


def test_t4_header_echo_and_choppy_paragraph_soft_warnings() -> None:
    # 4a. Header date echo in 这场在谈什么、谁 -> soft WARN (allowed=True)
    n_echo = _make_note(
        "第一步核对本地缓存。接着运行脚本并记录输出。 ⏱ 00:10",
        intro="这场讲座于 2026-01-15 发布，演示脚本耗时排查。 ⏱ 00:10",
    )
    res_echo = _verify(n_echo)
    assert res_echo["allowed"], res_echo["reasons"]
    assert any("文头复读 WARN" in w for w in res_echo["warnings"]), res_echo["warnings"]

    # 4b. Citing channel/speaker WITHOUT published date -> NO 文头复读 WARN
    n_clean_intro = _make_note(
        "第一步核对本地缓存。接着运行脚本并记录输出。 ⏱ 00:10",
        intro="Example Channel 讲者演示本地脚本耗时排查，面向想理解基础流程的读者。 ⏱ 00:10",
    )
    res_clean = _verify(n_clean_intro)
    assert res_clean["allowed"], res_clean["reasons"]
    assert not any("文头复读 WARN" in w for w in res_clean["warnings"]), res_clean["warnings"]

    # 4c. 3 consecutive 1-sentence prose paragraphs in H3 -> 碎段 WARN (allowed=True)
    choppy = "\n\n".join([
        "第一步先核对本地缓存。 ⏱ 00:10",
        "第二步运行性能分析脚本。 ⏱ 00:10",
        "第三步查看每条耗时记录。 ⏱ 00:10",
    ])
    res_choppy = _verify(_make_note(choppy))
    assert res_choppy["allowed"], res_choppy["reasons"]
    assert any("碎段 WARN" in w for w in res_choppy["warnings"]), res_choppy["warnings"]

    # 4c-neg. 2 consecutive 1-sentence paragraphs -> NO 碎段 WARN
    two_short = "\n\n".join([
        "第一步先核对本地缓存。 ⏱ 00:10",
        "第二步运行性能分析脚本。 ⏱ 00:10",
    ])
    res_two = _verify(_make_note(two_short))
    assert res_two["allowed"], res_two["reasons"]
    assert not any("碎段 WARN" in w for w in res_two["warnings"]), res_two["warnings"]

    # 4d. 5 consecutive 1-sentence list items -> NO 碎段 WARN
    bullets = "\n".join([
        "- 第一步先核对本地缓存。 ⏱ 00:10",
        "- 第二步运行性能分析脚本。 ⏱ 00:10",
        "- 第三步查看每条耗时记录。 ⏱ 00:10",
        "- 第四步整理最终排查报告。 ⏱ 00:10",
        "- 第五步复核全部指标。 ⏱ 00:10",
    ])
    res_bullets = _verify(_make_note(bullets))
    assert res_bullets["allowed"], res_bullets["reasons"]
    assert not any("碎段 WARN" in w for w in res_bullets["warnings"]), res_bullets["warnings"]


def test_t5_doc_net_shrink_and_anti_boilerplate_contracts() -> None:
    df_raw = (ROOT / "references" / "delivery-format.md").read_bytes()
    rg_raw = (ROOT / "references" / "review-guide.md").read_bytes()
    assert b"\r" not in df_raw and b"\r" not in rg_raw
    assert len(df_raw) <= BASELINE_DELIVERY_BYTES, f"delivery-format.md grew: {len(df_raw)} > {BASELINE_DELIVERY_BYTES}"
    assert len(rg_raw) <= BASELINE_REVIEW_BYTES, f"review-guide.md grew: {len(rg_raw)} > {BASELINE_REVIEW_BYTES}"
    df_text = df_raw.decode("utf-8")
    rg_text = rg_raw.decode("utf-8")
    assert "这场大会演讲于 2026-06-28" not in df_text, "delivery-format.md excerpt must drop header metadata echo"
    assert "勿复述文头" in df_text, "delivery-format.md must instruct not repeating header metadata"
    assert "概念讲解通常省略" in df_text, "delivery-format.md must clarify conceptual talks usually omit 可复用做法"
    assert "单句碎段" in rg_text, "review-guide.md must instruct merging choppy 1-sentence paragraphs"


def main() -> None:
    tests = [
        test_t1_paren_classification_and_no_double_paren,
        test_t2_in_sentence_definition_and_ji_guard,
        test_t3_doubt_and_gloss_same_position_collision_both_orders,
        test_t4_header_echo_and_choppy_paragraph_soft_warnings,
        test_t5_doc_net_shrink_and_anti_boilerplate_contracts,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL: {fn.__name__}: {exc}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
