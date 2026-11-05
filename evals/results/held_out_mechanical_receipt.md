# Mechanical held-out receipt

Public record of a box-side mechanical pass on 10 YouTube videos. Note bodies, draft-gold files, and per-video verify dumps stay outside this repository. This file is the thin receipt. CI does not score it. It is not an eval dump.

`held_out_nine_claimed=false`

This slate is not 冲9, not a held-out 9, and not a human ≥9. A signed or blind gold set, with hall and recall scored against that gold, is still required before any 9 claim. That requirement is the Unreleased note in `CHANGELOG.md`. The in-distribution Hall J receipt is `evals/results/hall_j_retest_receipt.md`. That run is a different set.

| Field | Value |
| :--- | :--- |
| when | 2026-11-04T20:06:06-0800 (America/Los_Angeles, box-local) |
| slate | 10 YouTube videos |
| tooling at measurement | branch `cursor/language-preference-7856` (R01–R17 + Coverage C) |
| verify | pass 10/10 |
| Coverage C | pass 10/10 |
| gold_status | `draft_assistant_not_user_signed` (every video) |
| human_score_ge_9 | false |
| held_out_nine_claimed | false |
| skill_hall / skill_core_recall vs signed gold | not completed |

Draft gold was assistant-proposed. It was not user-signed, and it was not a frozen `model-consensus-gold-v2` gold. `skill_hallucinations_per_note` and `skill_core_recall` against signed gold were not run.

## Videos

Mechanical verify and Coverage C only. `claim_fail` is the deterministic same-section unsupported count from that run (`claim_ground_check`), not a hall score.

| video_id | channel | duration_sec | verify | coverage | claim_fail |
| :--- | :--- | ---: | :--- | :--- | ---: |
| `IEe-5VOv0Js` | Stripe | 1826 | PASS | PASS | 1 |
| `SXCfs7mitPo` | OpenAI | 1180 | PASS | PASS | 0 |
| `Bx6sUDRMx-8` | OpenAI | 2016 | PASS | PASS | 1 |
| `owmJyKVu5f8` | The Pragmatic Engineer | 1700 | PASS | PASS | 0 |
| `96jN2OCOfLs` | Sequoia Capital | 1789 | PASS | PASS | 1 |
| `Th8JoIan4dg` | Y Combinator | 1941 | PASS | PASS | 0 |
| `9Az0q2XHtH8` | GOTO Conferences | 1784 | PASS | PASS | 0 |
| `obB2IvCv-K0` | CNCF [Cloud Native Computing Foundation] | 1144 | PASS | PASS | 0 |
| `HDZnJ3kaAu8` | LeadDev | 1542 | PASS | PASS | 0 |
| `fhefMQ-Q6Fs` | Plato HQ | 1805 | PASS | PASS | 0 |

## Why the draft-gold overlap is not the hall / recall bar

The box summary also recorded these draft-gold overlap means. They are copied here so they are not mistaken for a new measurement. They are not Claude's hall≤0.2 / recall≥0.85 bar, and they are not `skill_hallucinations_per_note` or `skill_core_recall`.

| Draft-gold figure (unsigned) | Mean on this slate |
| :--- | ---: |
| draft-gold quote coverage in the note | 1.0 |
| draft-core recall, full note | 1.0 |
| draft-core recall, prose only | 0.0 |
| claim_ground unsupported count | 0.3 |

Every video on the slate recorded full-note draft-core recall 1.0 and prose-only draft-core recall 0.0. Do not treat either figure as recall against signed gold.

- The draft gold was not user-signed. Overlap with an unsigned draft is not a Hall pass.
- Draft-gold claims were sampled from the same inventory windows used to seed the note quotes. Quote coverage of 1.0 is the circular result of that sampling. It is not independent held-out recall.
- Full-note recall counts English section quotes inside the local verify note, so 1.0 is easy on this slate.
- Prose-only recall of 0.0 is Chinese prose against English draft claims (script mismatch). That gap does not by itself show the notes lack method arcs, and it is still not signed-gold recall.
- Coverage C pass on this slate is the deterministic floor (the note used the inventory that was written, including quartile spread). It is not a human 9/10 on detail depth. A thin inventory can still pass that floor. See `scripts/README.md`.

## Still required before any 9 claim

Signed or blind gold, then hall and core recall scored against that gold. Until that exists, `held_out_nine_claimed` stays false.
