# Hall J retest receipt

Public record of the measured Hall J gate for `v1.0.0`. Gold note bodies and local ferry trees are outside this repository. This file quotes the measured gates and the gold checksum. It is not an eval dump. CI does not score this file. R01–R16 were not loosened.

Lane A is Claude Desktop with this skill loaded. The comparison set is `model-consensus-gold-v2`.

| Field | Value |
| :--- | :--- |
| protocol | `model-consensus-gold-v2` |
| retest_at | 2026-11-05T02:53:29+08:00 (Asia/Shanghai) |
| overall_pass | true |
| skill_hallucinations_per_note | 0.0 (need ≤0.2 and < baseline×0.5) |
| baseline_hallucinations_per_note | 1.0 |
| skill_core_recall | 0.913 (21/23; need ≥0.7 and ≥ baseline−0.1) |
| baseline_core_recall | 1.0 |
| should_reject | 1.0 (1/1, id `v12`) |
| gold_sha256 | `0eaa5f806d7e6ddc175dc62abfa7851f56b9805748b5b0a8d66268e7afa54dd1` (unchanged) |
| sample_v2 mechanical verify | 10/10 (unchanged; pull request #10, `548a96a`) |
| failure_categories | none |

Per-video skill rows from the same retest: v01 4/4 hall 0, v02 1/1 hall 0, v03 4/5 hall 0, v04 1/1 hall 0, v05 4/4 hall 0, v06 2/2 hall 0, v07 4/4 hall 0, v10 1/2 hall 0.
