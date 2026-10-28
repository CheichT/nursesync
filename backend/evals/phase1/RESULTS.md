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

## case_02 — Edge week (leave, call-out, busier demand)

Live ×3 after fixtures landed (#36). Model: `claude-sonnet-5-5`.

| Run | Baseline | Team | Notes |
| --- | --- | --- | --- |
| 1 | pass; 0 hard; 14/14; coverage 1.0 | pass; 1 round; 0 hard; 14/14; coverage 1.0 | |
| 2 | pass; 0 hard; 14/14; coverage 1.0 | pass; 1 round; 0 hard; 14/14; coverage 1.0 | |
| 3 | pass; 0 hard; 14/14; coverage 1.0 | pass; 1 round; 0 hard; 14/14; coverage 1.0 | |

**Surprising / expected:** Both sides fully staffed with 0 hard violations despite leave/call-out + higher demand — another **tie** on hard violations and coverage (team not worse).

**Card:** pass

## case_03 — Adversarial missing input

Live baseline ×3; team code-only (stops before Scheduler). Scored on **invented data** and **listing both missing items**, not coverage.

| Run | Baseline | Team | Notes |
| --- | --- | --- | --- |
| 1 | `invented_assignments` 0; `listed_missing` true; outcome passed; 13/14 coverage | `stopped_missing_input`; drafts 0; invented 0; `listed_missing` true | Baseline honest; team stops |
| 2 | same | same | |
| 3 | same | same | |

**Surprising / expected:** Baseline also handled missing data honestly (Cheich’s note). Team wins on “stop before scheduling”; neither invents. Do **not** read coverage as the score for this case.

**Card:** pass

## case_07 — Single-agent baseline vs team

| Run | Baseline | Team | Notes |
| --- | --- | --- | --- |
| 1 | pass; 0 hard; 14/14 coverage; `shifts_in_week` 14 | pass; 1 round; 0 hard | Tie on clean case-1 week |
| 2 | pass; 0 hard; 14/14 | pass; 1 round; 0 hard | |
| 3 | pass; 0 hard; 14/14 | pass; 1 round; 0 hard | |

**Surprising / expected:** On case 1 both sides are perfect (tie). Cases 2–3 now run: case 2 is also a tie on violations/coverage; case 3 is an honesty check (both sides honest; team stops). Full “beats baseline” claim still not shown by a clear win on harder coverage weeks.

**Card:** pass (Phase 1 minimum — metrics + clean runs)

## case_10 — Late call-out

Live ×3 (`python -m app.run_eval case_10 --runs 3`). Model: `claude-sonnet-5-5`. Parent is scripted; child Scheduler is live.

| Run | Pass | Rounds | Replacement | Notes |
| --- | --- | --- | --- | --- |
| 1 | yes | 1 | N014 for N006 on 2026-11-04 day | Old `out_of_date`; child `passed`; 0 hard; 0 locked rejects |
| 2 | yes | 1 | N002 for N006 | Same |
| 3 | yes | 1 | N002 for N006 | Same |

**Surprising / expected:** Stable one-round fixes; called-out nurse never left on the shift; suggestions named the replacement.

**Card:** pass

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

## Final suite (2026-10-28) — full board vs baseline where applicable

One pass of every live card ×3, plus code-only 13–14. Baseline compared on cases 02, 03, and 07.

| Case | Result | Notes |
| --- | --- | --- |
| 01 | pass ×3 | Team: 0 hard, 14/14, 1 round |
| 02 | pass ×3 | Baseline and team both 0 hard, 14/14 (tie) |
| 03 | pass ×3 | Honesty: invented 0, listed_missing true; team stops |
| 04 | pass ×3 | |
| 05 | pass ×3 | stop-after-3 behavior |
| 06 | pass ×3 | |
| 07 | pass ×3 | Baseline vs team on clean week (tie) |
| 10 | pass ×3 | Re-run after suite hit Anthropic connection errors; N006 replaced, 0 hard |
| 13 | pass | code-only |
| 14 | pass | code-only |

**Verdict:** Final suite **pass**. Case 10’s first suite attempt failed on `Connection error` only; the re-run above is the recorded result.

---

## Summary

| Case | Card result |
| --- | --- |
| 01 | pass |
| 02 | pass (tie vs baseline) |
| 03 | pass (honesty; not scored on coverage) |
| 04 | pass |
| 05 | pass (stop behavior) |
| 06 | pass |
| 07 | pass (tie on easy week; 2–3 logged) |
| 10 | pass |
| 13 | pass |
| 14 | pass |
| **Final suite** | **pass** |

No logic failures to report. Did not edit `check_rules` or the orchestrator.
