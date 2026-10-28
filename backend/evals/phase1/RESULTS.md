# Phase 1 eval results (Kerrian)

Ran on `main` after baseline/Scheduler prompt fixes (#25).  
Model: `claude-sonnet-5-5`. Setup check: **Connected**.

Pass rule: live Scheduler cases ×3 must match the card; case 5 expects stop-after-3, not a clean pass. Cases 13–14 are code-only (one run).

## case_01 — Golden (normal)

| Run | Result | Rounds | Hard violations | Notes |
| --- | --- | --- | --- | --- |
| 1 | pass | 1 | 0 | Full week covered |
| 2 | pass | 1 | 0 | |
| 3 | pass | 1 | 0 | |

**Card:** pass

## case_04 — Overnight rest

| Run | Result | Rounds | Hard violations | Notes |
| --- | --- | --- | --- | --- |
| 1 | pass | 2 | 0 final | Round 1 planted rest fail; fixed by round 2 |
| 2 | pass | 2 | 0 final | |
| 3 | pass | 2 | 0 final | |

**Card:** pass

## case_05 — Loop limit

| Run | Result | Rounds | Hard violations | Notes |
| --- | --- | --- | --- | --- |
| 1 | pass (stop) | 3 | 1 open | `certification` on 2026-11-05 night; 1 unfixable |
| 2 | pass (stop) | 3 | 1 open | Same |
| 3 | pass (stop) | 3 | 1 open | Same |

Outcome each run: `stopped_after_3_rounds` (not called passing). Matches card.

**Card:** pass

## case_06 — Cert + overtime

| Run | Result | Rounds | Hard violations | Notes |
| --- | --- | --- | --- | --- |
| 1 | pass | 2 | 0 final | Planted cert + weekly_hours fixed by round 2 |
| 2 | pass | 2 | 0 final | |
| 3 | pass | 2 | 0 final | |

**Card:** pass

## case_07 — Single-agent baseline vs team

| Run | Baseline | Team | Notes |
| --- | --- | --- | --- |
| 1 | pass; 0 hard; 14/14 coverage; `shifts_in_week` 14 | pass; 1 round; 0 hard | Tie on clean case-1 week |
| 2 | pass; 0 hard; 14/14 | pass; 1 round; 0 hard | |
| 3 | pass; 0 hard; 14/14 | pass; 1 round; 0 hard | |

**Surprising / expected:** On case 1 alone both sides are perfect, so the “team beats baseline” claim is a **tie** until harder cases 2–3 exist. Logging and metrics look correct after the baseline prompt fix.

**Card:** pass (Phase 1 minimum — metrics + clean runs)

## case_13 — Misreported verdict (code-only)

| Check | Result |
| --- | --- |
| Code found 2 hard violations | yes (`code_found`: 2) |
| Mismatch detected | yes |
| Scheduler received both | yes (`sent_to_scheduler`: 2) |

**Card:** pass

## case_14 — Lost or stale verdict (code-only)

| Sub-case | Outcome | Pass |
| --- | --- | --- |
| A missing | not passed; “check result is missing” | yes |
| B unparseable | not passed; parse error | yes |
| C stale | not passed; version mismatch | yes |

**Card:** pass

---

## Summary

| Case | Card result |
| --- | --- |
| 01 | pass |
| 04 | pass |
| 05 | pass (stop behavior) |
| 06 | pass |
| 07 | pass (tie on easy week) |
| 13 | pass |
| 14 | pass |

No failures to report. Did not edit `check_rules` or `models.py`.
