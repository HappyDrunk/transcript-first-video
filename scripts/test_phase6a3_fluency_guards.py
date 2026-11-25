#!/usr/bin/env python3
"""Phase 6A.3 TDD red tests: C04c approximate scale guards, glossary/original grounding, and fluency doc contracts."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_rules as vr  # type: ignore

BASELINE_DELIVERY_BYTES = 17546
BASELINE_REVIEW_BYTES = 6382


def _make_note(body: str, quotes: list[str], extra_blocks: str = "") -> str:
    quote_block = "\n".join(quotes)
    return f"""---
title: "Synthetic Demo"
source: "https://example.com/watch?v=demo123"
channel: "Demo Channel"
published: "2026-01-01"
type: "讲座"
caption_kind: "auto"
skill_version: "13f07d8dda7862fadef83b3c730be01f6ee7ed73"
transcript_path: "transcript.txt"
tags: [video-note]
---

## 先记住一句话

这是一段合成测试结论。 ⏱ 00:10

## 这场在谈什么、谁

这场讲座讲解合成测试案例。 ⏱ 00:10

## 主线论点

### 测试小节

{body}
{extra_blocks}
本文略去｜无

## 原文依据

{quote_block}
"""


def _run_c04c(body: str, quote_text: str, extra_blocks: str = "", extra_quote: str = "") -> tuple[bool, list[str]]:
    quotes = [f"> [00:10] {quote_text}"]
    transcript_lines = [f"[00:10] {quote_text}"]
    if extra_quote:
        quotes.append(f"> [00:40] {extra_quote}")
        transcript_lines.append(f"[00:40] {extra_quote}")
    note = _make_note(body, quotes, extra_blocks=extra_blocks)
    transcript = "\n".join(transcript_lines) + "\n"
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td) / "transcript.txt"
        np = Path(td) / "note.md"
        tp.write_text(transcript, encoding="utf-8")
        np.write_text(note, encoding="utf-8")
        ctx = vr.build_context(tp, note)
        findings: list[dict] = []
        _name, ok, detail = vr.c04c_grounding(ctx, findings=findings)
        return ok, [detail] if not ok else []


def test_t1_centuries_approximate_and_exact_reject() -> None:
    ok_good, det = _run_c04c(
        "这种做法已经延续了数百年。 ⏱ 00:10",
        "This practice has been around for centuries in many historic buildings around the world.",
    )
    assert ok_good, f"T1 good should pass, got: {det}"

    ok_bad, _ = _run_c04c(
        "这种做法已经延续了 500 年。 ⏱ 00:10",
        "This practice has been around for centuries in many historic buildings around the world.",
    )
    assert not ok_bad, "T1 bad ('500 年' vs 'for centuries') MUST fail C04c"


def test_t2_billions_scale_label_and_exact_reject() -> None:
    ok_good, det = _run_c04c(
        "地震造成的损失以十亿美元计。 ⏱ 00:10",
        "Billions of dollars of damages were inflicted on garages, offices, and warehouses.",
    )
    assert ok_good, f"T2 good ('以十亿美元计' vs 'Billions') should pass, got: {det}"

    ok_bad1, _ = _run_c04c(
        "地震造成的损失达到三十亿美元。 ⏱ 00:10",
        "Billions of dollars of damages were inflicted on garages, offices, and warehouses.",
    )
    assert not ok_bad1, "T2 bad1 ('三十亿' vs 'billions') MUST fail C04c"

    ok_bad2, _ = _run_c04c(
        "地震造成的损失达到十亿美元。 ⏱ 00:10",
        "Two billion dollars of damages were inflicted on garages, offices, and warehouses.",
    )
    assert not ok_bad2, "T2 bad2 ('十亿' vs 'two billion') MUST fail C04c"

    ok_bad3, _ = _run_c04c(
        "地震造成的损失达到十亿美元。 ⏱ 00:10",
        "Billions of dollars of damages were inflicted on garages, offices, and warehouses.",
    )
    assert not ok_bad3, "T2 bad3 (exact '损失达到十亿美元' vs 'billions') MUST fail C04c"

    ok_bad4, _ = _run_c04c(
        "整个步骤耗时十秒。 ⏱ 00:10",
        "This browser engine has evolved over decades in active development.",
    )
    assert not ok_bad4, "T2 bad4 ('耗时十秒' vs 'decades') MUST fail C04c"


def test_t3_dozens_and_decades_guard() -> None:
    for body, quote in [
        ("需要处理数十个样本。 ⏱ 00:10", "We need to process dozens of samples across the benchmark suite every week."),
        ("一共准备了 24 个样本。 ⏱ 00:10", "We prepared two dozen samples across the benchmark suite every single week."),
        ("这套技术演进了数十年。 ⏱ 00:10", "This engineering approach has evolved over decades in real production systems."),
        ("这套工具存在了 20 年。 ⏱ 00:10", "This browser engine has been around for two decades in active development."),
    ]:
        ok, det = _run_c04c(body, quote)
        assert ok, f"T3 good failed for {body!r}: {det}"

    for body, quote in [
        ("需要处理 12 个样本。 ⏱ 00:10", "We need to process dozens of samples across the benchmark suite every week."),
        ("这套技术演进了 10 年。 ⏱ 00:10", "This engineering approach has evolved over decades in real production systems."),
        ("这套技术演进了十年。 ⏱ 00:10", "This engineering approach has evolved over decades in real production systems."),
        ("这种做法延续了百年。 ⏱ 00:10", "This practice has been around for centuries in many historic buildings around the world."),
        ("整个过程大约十秒。 ⏱ 00:10", "The whole step took about 80 seconds on a warm local machine."),
        ("样本总数十二个。 ⏱ 00:10", "The benchmark contained 80 samples across the entire evaluation suite."),
        ("实验分成十组进行。 ⏱ 00:10", "The study split participants into 80 groups across the entire evaluation."),
        ("他登上十楼查看设备。 ⏱ 00:10", "The engineer inspected equipment on floor 80 of the high-rise tower."),
        ("模型参数十个即可。 ⏱ 00:10", "The compact controller requires 80 parameters for stable operation."),
    ]:
        ok, _ = _run_c04c(body, quote)
        assert not ok, f"T3 bad MUST fail C04c for {body!r} vs {quote!r}"


def test_t4_thousands_millions_and_wrong_decimal() -> None:
    for body, quote in [
        ("现场有数千人受伤。 ⏱ 00:10", "Thousands of people were injured during the afternoon shaking across the valley."),
        ("系统服务了上千名用户。 ⏱ 00:10", "Thousands of users relied on the system during the afternoon traffic spike."),
        ("模型覆盖数百万条记录。 ⏱ 00:10", "The pipeline indexes millions of records across distributed storage clusters."),
    ]:
        ok, det = _run_c04c(body, quote)
        assert ok, f"T4 good failed for {body!r}: {det}"

    for body, quote in [
        ("现场有 3000 人受伤。 ⏱ 00:10", "Thousands of people were injured during the afternoon shaking across the valley."),
        ("输出自身耗时 3.097 秒。 ⏱ 00:10", "The built-in print call took 0.774 seconds per call in the profiler table."),
    ]:
        ok, _ = _run_c04c(body, quote)
        assert not ok, f"T4 bad MUST fail C04c for {body!r}"


def test_t5_original_english_hyphen_and_same_slice_type1() -> None:
    # Good 1: hyphenated canonical spelling against spaced ASR without needing correction
    ok_h, det_h = _run_c04c(
        "对外提供拆分视野接口（split-horizon APIs）。 ⏱ 00:10",
        "We often talk about split Horizon apis for public versus private endpoints in microservices.",
    )
    assert ok_h, f"T5 hyphenated canonical English should pass: {det_h}"

    # Good 2: parenthetical canonical English backed by same-slice Type-1 speech correction
    corr_block = "\n> [!warning] 原文出入\n> 字幕写作 cap Theory，实为 CAP theorem。\n"
    ok_c, det_c = _run_c04c(
        "大家常谈 CAP 定理（CAP theorem）。 ⏱ 00:10",
        "We can talk about cap Theory in distributed systems when making resilience tradeoffs.",
        extra_blocks=corr_block,
    )
    assert ok_c, f"T5 same-slice Type-1 correction should support parenthetical English: {det_c}"

    # Bad 1: same sentence WITHOUT correction
    ok_nocorr, _ = _run_c04c(
        "大家常谈 CAP 定理（CAP theorem）。 ⏱ 00:10",
        "We can talk about cap Theory in distributed systems when making resilience tradeoffs.",
    )
    assert not ok_nocorr, "T5 bad1 (without Type-1 correction) MUST fail"

    # Bad 2: correction exists ONLY for a different slice's quote
    ok_other, _ = _run_c04c(
        "大家先看常规话题（CAP theorem）。 ⏱ 00:10\n\n另一段提到定理。 ⏱ 00:40",
        "This first slice talks only about timeouts and retries in distributed services.",
        extra_blocks=corr_block,
        extra_quote="Later we can talk about cap Theory in distributed systems tradeoffs.",
    )
    assert not ok_other, "T5 bad2 (cross-slice borrowed correction) MUST fail"

    # Bad 3: fabricated English parenthetical
    ok_fab, _ = _run_c04c(
        "对外提供拆分视野接口（split-brain APIs）。 ⏱ 00:10",
        "We often talk about split Horizon apis for public versus private endpoints in microservices.",
    )
    assert not ok_fab, "T5 bad3 (fabricated split-brain APIs) MUST fail"

    # Bad 4: fabricated glossary term absent from transcript
    bad_term_block = "\n> [!note] 术语：脑裂（split-brain）\n> 集群分区后两侧各自认为自己是主节点。\n"
    note = _make_note(
        "对外提供拆分视野接口。 ⏱ 00:10",
        ["> [00:10] We often talk about split Horizon apis for public versus private endpoints in microservices."],
        extra_blocks=bad_term_block,
    )
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td) / "transcript.txt"
        np = Path(td) / "note.md"
        tp.write_text("[00:10] We often talk about split Horizon apis for public versus private endpoints in microservices.\n", encoding="utf-8")
        np.write_text(note, encoding="utf-8")
        ctx = vr.build_context(tp, note)
        blocks = [b for s in ctx.sections for b in s.blocks]
        term_issues = vr.explanation_issues(blocks, ctx.speech, [])
        assert term_issues, "T5 bad4 (fabricated glossary term) MUST fail explanation_issues"


    # Bad 5: Type-1 laundering that changes English spoken number words ('two dozen' -> 'ten dozen')
    assert vr._discrepancy_type1_laundering_issue("two dozen", "ten dozen") is not None, (
        "T5 bad5 ('two dozen' -> 'ten dozen') MUST be rejected by Type-1 laundering guard"
    )
    assert vr._discrepancy_type1_laundering_issue("cap Theory", "CAP theorem") is None, (
        "T5 good ('cap Theory' -> 'CAP theorem') should pass Type-1 laundering guard"
    )

    # Bad 6: cross-section borrowed correction even when original text appears in both sections
    cross_sec_note = _make_note(
        "大家常谈 CAP 定理（CAP theorem）。 ⏱ 00:10\n\n### 第二小节\n\n这里又提到定理。 ⏱ 00:40",
        [
            "> [00:10] We can talk about cap Theory in distributed systems when making resilience tradeoffs.",
            "> [00:40] Later we can talk about cap Theory again in distributed systems tradeoffs.",
        ],
        extra_blocks=corr_block,
    )
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td) / "transcript.txt"
        tp.write_text(
            "[00:10] We can talk about cap Theory in distributed systems when making resilience tradeoffs.\n"
            "[00:40] Later we can talk about cap Theory again in distributed systems tradeoffs.\n",
            encoding="utf-8",
        )
        ctx_cs = vr.build_context(tp, cross_sec_note)
        _n, ok_cs, _d = vr.c04c_grounding(ctx_cs, findings=[])
        assert not ok_cs, "T5 bad6 (cross-section borrowed Type-1 correction) MUST fail C04c"


def test_t6_fluency_doc_contracts_and_byte_caps() -> None:
    df_path = ROOT / "references" / "delivery-format.md"
    rg_path = ROOT / "references" / "review-guide.md"
    df_raw = df_path.read_bytes()
    rg_raw = rg_path.read_bytes()
    df_bytes = len(df_raw)
    rg_bytes = len(rg_raw)
    df_text = df_raw.decode("utf-8")
    rg_text = rg_raw.decode("utf-8")

    assert b"\r" not in df_raw, "delivery-format.md must use LF line endings"
    assert b"\r" not in rg_raw, "review-guide.md must use LF line endings"
    assert df_bytes <= BASELINE_DELIVERY_BYTES, f"delivery-format.md grew: {df_bytes} > {BASELINE_DELIVERY_BYTES}"
    assert rg_bytes <= BASELINE_REVIEW_BYTES, f"review-guide.md grew: {rg_bytes} > {BASELINE_REVIEW_BYTES}"
    assert "每段 2–4 句" not in df_text, "Rigid '每段 2–4 句' constraint must be removed"
    assert "能短" not in rg_text, "Stiff '能短' review prompt must be replaced with '承接'"
    assert "首次出场" in df_text, "delivery-format.md must require recurring demo/experiment first appearance"
    assert "段间留承接" in df_text, "delivery-format.md must guide natural paragraph transitions"
    assert "不把个例升格" in rg_text, "review-guide.md must guard opening/heading scope compression"


def main() -> None:
    tests = [
        test_t1_centuries_approximate_and_exact_reject,
        test_t2_billions_scale_label_and_exact_reject,
        test_t3_dozens_and_decades_guard,
        test_t4_thousands_millions_and_wrong_decimal,
        test_t5_original_english_hyphen_and_same_slice_type1,
        test_t6_fluency_doc_contracts_and_byte_caps,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {fn.__name__}: {e}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
