# Eval case 2 — Edge week (leave, call-out, busier demand)

**Phase:** 1 (baseline vs team comparison)  
**Depends on:** scenario `backend/data/scenarios/case_02/`, Scheduler + Rules Checker loop, baseline agent  
**Runs:** **3** live runs. Each run scores **baseline** and **team** on the same inputs (`python -m app.run_eval case_02 --runs 3`).

## Purpose

A harder week than the golden case: fewer nurses available and two shifts that need more staff. Compare whether the multi-agent team keeps hard violations and coverage at least as good as the single-agent baseline.

## Input (fixture)

From `load_scenario("case_02")` (mock week with these replacements):

- **Availability:** N011 and N013 on approved leave **all week**; N004 (ACLS) **call_out** from Wed 2026-11-04 onward (available Mon–Tue).
- **Demand:** Thu night 2026-11-05 and Sat day 2026-11-07 need **5** nurses instead of 4 (week total **64** nurse-shifts vs 62).
- No planted draft — live Scheduler from round 1.

## Metrics (every run, both sides)

| Metric | Meaning |
| --- | --- |
| `outcome` | `passed` or `stopped_after_3_rounds` |
| `rounds_used` | 1–3 (team) |
| `hard_violations` / `hard_violation_count` | Hard violations on the final draft |
| `fully_staffed_shifts` / `shifts_in_week` / `coverage_rate` | Coverage |
| `open_gaps_listed` | Gaps left for the manager |

## Expected (before runs)

1. Both sides produce a Draft (or stop after 3 with a best draft). Neither invents nurses.
2. An unavoidable gap is acceptable if leave/call-out + higher demand leave no legal cover.
3. Team average hard violations ≤ baseline; team average coverage ≥ baseline (same as case 7 claim).

## Pass / fail

- **Pass:** Three runs logged for both sides; no invented staff; metrics present; team not worse on both violations and coverage.
- **Fail:** Missing metrics; invented nurses; team clearly worse on both hard violations and coverage across the three runs.

## Notes

- The unchanged mock reference draft breaks `availability` and `coverage` on this fixture (see unit tests). Live agents should do better than that planted-blind draft.
- Soft fairness does not decide pass/fail.
