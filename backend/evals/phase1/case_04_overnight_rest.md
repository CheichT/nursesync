# Eval case 4 — Edge case (overnight turnaround)

**Phase:** 1  
**Depends on:** `check_rules` + Scheduler fix loop (+ Rules Checker `fix_hint`)  
**Runs:** 3. All 3 must match the expected output below.

## Purpose

Prove rest-time is measured from the real end of a night shift (next morning), and that the Scheduler can fix a planted overnight clash.

## Input (scenario Cheich still needs to add)

Start from the base mock week, then plant **one** rest violation:

- Nurse **N003** (example ID; any roster nurse is fine if kept consistent in the fixture) is assigned:
  - Monday night: date `2026-11-02`, shift `night`, `shift_start` `19:00`, `shift_end` `07:00`
  - Tuesday day: date `2026-11-03`, shift `day`, `shift_start` `07:00`, `shift_end` `19:00`
- That is **0 hours** of rest between shifts (night ends Tuesday 07:00; day starts Tuesday 07:00).
- All other assignments may be valid; only this clash is required for the first failing check.

**Fixture needed (Cheich):** a Phase 1 scenario folder or planted draft the harness feeds as the round-1 Scheduler output *or* as the seed the Scheduler must correct after `check_rules` fails. Until that file exists, this card still locks the expected answers.

## Expected output (written before any run)

### After first `check_rules` on the planted draft

1. Result is **fail** (not pass).
2. At least one **hard** violation with:
   - `rule`: `rest_time`
   - `nurse_id`: the planted nurse (e.g. `N003`)
   - `date`: `2026-11-03` (the day shift that has no rest)
   - `shift`: `day`
   - `found`: states essentially **0 hours of rest** (wording may vary; must mean zero rest)
   - `limit`: **10 hours** of rest (per `rules.min_rest_hours`)
3. Rules Checker adds a one-sentence `fix_hint` (e.g. remove the nurse from Tuesday day, or move Monday night to someone else). Code’s violation list remains authoritative if the agent list differs.

### Final draft (by round 3 at latest)

4. `check_rules` returns **pass** on hard rules for rest: **0** `rest_time` hard violations.
5. That nurse is **not** on both Monday night and Tuesday day.
6. Coverage / other hard rules: final draft must not introduce a new unresolved hard violation that leaves the run failing. Prefer keeping other shifts intact while fixing this clash.
7. Shift times on every assignment remain day `07:00`/`19:00`, night `19:00`/`07:00`.
8. No invented nurses.

## Pass / fail

- **Pass:** All 3 runs show the initial rest fail (items 1–2), then a final draft with **0 rest violations** (items 4–5).
- **Fail:** Rest clash never flagged; final draft still has the night→day pair; or the agent invents staff to “fix” it.

## Notes

- Soft tradeoffs do not fail this case.
- Exact `fix_hint` wording may vary; the violation identity (`rule`, `nurse_id`, `date`, `shift`) must be stable.
