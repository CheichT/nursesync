# Eval case 7 — Single-agent baseline

**Phase:** 1 (comparison); uses cases 1–3 inputs over time  
**Depends on:** single-agent baseline prompt + multi-agent Phase 1 loop + same synthetic data  
**Runs:** For each compared case, run **3** times on **both** the baseline and the multi-agent team. Compare averages (and per-run logs).

## Purpose

Show the multi-agent team beats one agent doing everything: **fewer hard-rule violations at equal or better coverage** on the same data (PRD success metric and case 7).

## Input

Run the **same** case inputs through:

1. **Baseline:** one agent with four tools — `get_demand`, `get_availability`, `get_roster`, `check_rules` (`baseline_v0.md`).
2. **Multi-agent:** Demand/Availability from files in Phase 1 (later from agents), Scheduler + Rules Checker loop, `check_rules` in code.

**Phase 1 scope for this card:** start with **case 1** (base mock week) for both sides. Cases **2** and **3** join when their scenario fixtures exist (Phase 2/3 data). Do not invent case 2/3 data here.

Same model for both sides: Claude API id `claude-sonnet-5-5`.

## Metrics to record (every run)

| Metric | How to read it |
| --- | --- |
| `hard_violation_count` | Hard violations on the **final** draft from the last `check_rules` |
| `fully_staffed_shifts` | Shifts where assigned count equals `nurses_needed` |
| `shifts_in_week` | Demand rows in the week (14 on the base week) |
| `coverage_rate` | `fully_staffed_shifts / shifts_in_week` |
| `rounds_used` | 1–3 |
| `outcome` | `passed` or `stopped_after_3_rounds` (or equivalent) |

## Expected output (written before any run)

1. Both sides produce a final Draft in the PRD format (or baseline wrapper that embeds that draft).
2. Logs include the metrics above for **each** of the 3 runs per side.
3. On case 1 (clean week), both sides **can** reach 0 hard violations and full coverage; the comparison still records the metrics.
4. Across the compared cases (at least case 1 in Phase 1; later 1–3):
   - Multi-agent **average** `hard_violation_count` is **≤** baseline average.
   - Multi-agent **average** `coverage_rate` is **≥** baseline average.
   - The PRD target: multi-agent has **fewer** hard violations at **equal or better** coverage. If both are perfect on case 1 (0 violations, full coverage), case 1 alone is a **tie on that week**; the case still passes its logging requirements, and the “beats baseline” claim is judged when case 2/3 (harder weeks) are included.
5. Neither side invents nurses or claims pass without `check_rules`.

## Pass / fail

- **Pass (Phase 1 minimum):** All required runs logged; metrics present; no invented data; on case 1 both sides follow hard rules when they report `passed`.
- **Pass (full case 7 claim):** After cases 1–3 exist, multi-agent average hard violations are lower than baseline at equal or better average coverage.
- **Fail:** Missing metrics; baseline or team skips `check_rules`; invented staff; or multi-agent is worse on both violations and coverage once 1–3 are runnable.

## Notes

- Code-only behavior is not this case; this is agent vs agent-team.
- Soft fairness is recorded if useful but does not decide pass/fail for case 7.
