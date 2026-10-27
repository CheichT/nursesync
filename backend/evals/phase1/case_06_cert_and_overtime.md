# Eval case 6 — Certification and overtime breach

**Phase:** 1  
**Depends on:** `check_rules` + Scheduler fix loop (+ Rules Checker `fix_hint`)  
**Runs:** 3. All 3 must match the expected output below.

## Purpose

Prove `check_rules` reports **both** a certification miss and a weekly-hours breach, and that the Scheduler fixes **both** in a later draft.

## Input

**Fixture (on `main`):** `backend/data/scenarios/case_06/` — load with `load_scenario("case_06")`.

- Base mock week plus planted draft `planted_draft.json` as the **round-1 Scheduler output**.
- **Certification:** Tuesday night `2026-11-03` has **no** ACLS nurse (**N013** replaces **N004** on that shift).
- **Weekly hours:** **N001** works **4** shifts → **48** hours (over the 40-hour limit).

## Expected output (written before any run)

### After first `check_rules` on the planted draft

1. Result is **fail**.
2. Hard violations include **exactly these two** (per scenario tests):
   - `rule`: `certification` on date `2026-11-03`, shift `night`
   - `rule`: `weekly_hours`, `nurse_id`: `N001`, `found` showing **48** hours (wording may vary), `limit` **40** hours max
3. Each hard violation gets a `fix_hint` from the Rules Checker; code’s list wins if the agent list differs.

### Final draft (by round 3 at latest)

4. `check_rules` returns **pass** for hard rules: **0** hard `certification` and **0** hard `weekly_hours` violations (and no other hard failures left open).
5. Every shift has at least one ACLS nurse (including `2026-11-03` night).
6. **N001** does not exceed 40 hours for the week (at most 3 twelve-hour shifts unless roster `hours_this_week` forces fewer).
7. No invented nurses; shift times remain day `07:00`/`19:00`, night `19:00`/`07:00`.

## Pass / fail

- **Pass:** All 3 runs report both violations on the first check, then finish with both fixed (items 4–6).
- **Fail:** Only one of the two is reported; final draft still lacks ACLS on Tue night or still has N001 over 40 hours; or staff is invented.

## Notes

- Fix order in the Scheduler prompt prefers coverage/availability first; this case still requires both cert and hours to be clean by the end.
- Soft fairness does not fail this case.
