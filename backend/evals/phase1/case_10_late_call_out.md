# Eval case 10 — Late call-out

**Phase:** 3 (call-out while a draft is waiting for approval)  
**Depends on:** `run_call_out`, Scheduler call-out mode (locked assignments), live Scheduler + Rules Checker  
**Runs:** **3** live (`cd backend && ../.venv/bin/python -m app.run_eval case_10 --runs 3`). Costs money (Scheduler on the child case).

## Purpose

A clean weekly case is waiting. Nurse **N006** calls out of **Wed 2026-11-04 day**. The system must mark the old case `out_of_date`, build a child with `trigger: call_out`, replace only the affected shift, and leave the rest of the week locked.

## Input

- Parent: scripted Demand/Availability + reference draft (free). Status `waiting_approval`, outcome `passed`.
- Call-out: `N006`, `2026-11-04`, `day`, reported `2026-11-03T22:15:00`.
- Child: live Scheduler (unless the harness injects a stand-in) with `affected_shifts` / `locked_assignments` / `earlier_assignments`.

## Pass when (all must hold)

| Check | Expected |
| --- | --- |
| Old case | `status: out_of_date`, `newer_case_id` set |
| Child | `trigger: call_out`, `status: waiting_approval`, `outcome: passed` |
| Coverage of rules | `hard_violations: 0` on the child (whole week) |
| Called-out nurse | `N006` **not** on 2026-11-04 day |
| Locks | No successful change to locked assignments (a bad draft is rejected; may show as a round error) |
| Draft | Child has a `final_draft` |

## Metrics to log

`old_status`, `newer_case_id`, `child_outcome`, `rounds_used`, `round_errors`, `locked_changes_rejected`, `hard_violations`, `called_out_still_on_shift`, `shift_before` / `shift_after`, `suggestions`, `scheduler_calls`.

## Fail when

- Old case still approvable, or child does not pass
- N006 still on the shift
- Draft changes locked assignments and that is accepted
- Invented nurses

## Notes

- `check_rules` still judges the **whole** week.
- Suggestions list replacements; they do not decide pass/fail.
- Soft fairness does not decide this case.
