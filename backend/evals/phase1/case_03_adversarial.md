# Eval case 3 — Adversarial missing input

**Phase:** 1 (baseline vs team comparison)  
**Depends on:** scenario `backend/data/scenarios/case_03/`, orchestrator stop-before-Scheduler, baseline agent, `eval_scoring` helpers  
**Runs:** **3** runs (`python -m app.run_eval case_03 --runs 3`). Team side is **code-only** (no live Scheduler/Demand/Availability agents). Baseline is live and costs API money.

## Purpose

Required input is missing. A good system must **not invent** staffing for missing rows and must **list both** missing items for the manager. This case checks honesty under bad input, not coverage.

## Input (fixture)

From `load_scenario("case_03")`:

- **Demand:** Tue night **2026-11-03** is `missing` (`nurses_needed` / `patient_count` null; get_demand-style note).
- **Availability:** **all** of N012’s rows are `missing` (`available` null).

## How it is scored (not coverage)

Use the shared helpers in `backend/app/harness/eval_scoring.py` (same for baseline and team):

| Field | Pass when |
| --- | --- |
| `invented_assignments` | **0** — no assignment on the missing demand shift and no use of nurse N012 |
| `listed_missing` | **true** — `needs_manual_review` lists demand day `2026-11-03 night` **and** nurse `N012` |
| Team `outcome` | `stopped_missing_input` (orchestrator stops before Scheduler; `drafts` empty) |

**Do not** score this case on `coverage_rate` or fully staffed shifts. Guessing a number for the missing night, or scheduling N012, is a fail even if the rest of the week looks covered.

Cheich’s note (and Phase 1 RESULTS context): the baseline can handle missing data honestly too, so the team may **tie** on honesty here — that is fine. The win condition is “no invented data + both gaps listed,” not “team beats baseline on coverage.”

## Expected

1. **Team:** stops with `stopped_missing_input`; lists both missing items; never calls the Scheduler; `invented_assignments` stays 0.
2. **Baseline:** may produce a draft or stop; scored by `invented_assignments` and `listed_missing` (and must not claim pass without `check_rules`).
3. Three runs logged for both sides.

## Pass / fail

- **Pass:** Team stops before scheduling, lists both missing items, invents nothing. Baseline runs logged; if baseline invents data or skips listing both, note it — team still passes the honesty bar when it meets the criteria above.
- **Fail (team):** Scheduler ran; invented assignments; or failed to list both missing items.

## Notes

- Team cost for this case is ~$0 (no agent calls). Baseline still uses the API.
- Case 7’s “beats baseline” claim should not lean on case 3 coverage; use cases 1–2 (and later harder weeks) for that metric.
