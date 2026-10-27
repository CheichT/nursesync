# Eval case 6 — Certification and overtime breach

**Phase:** 1  
**Depends on:** `check_rules` + Scheduler fix loop (+ Rules Checker `fix_hint`)  
**Runs:** 3. All 3 must match the expected output below.

## Purpose

Prove `check_rules` reports **both** a certification miss and a weekly-hours breach, and that the Scheduler fixes **both** in a later draft.

## Input (scenario Cheich still needs to add)

A planted draft (or first Scheduler output) that includes **both**:

1. **Certification:** At least one shift has assignments but **no** nurse holding the required certification (ACLS). Example: Tuesday night `2026-11-03` night staffed only with non-ACLS nurses.
2. **Weekly hours:** At least one nurse is assigned enough shifts that total hours exceed **40** for the week (with 12h shifts, that means **4+** shifts), counting `hours_this_week` from the roster. Example: nurse `N010` on four shifts → 48 hours.

Keep nurse IDs consistent inside the fixture. Base week files may be reused for demand/availability/roster if the planted draft is the only broken piece.

**Fixture needed (Cheich):** planted Draft with both violations present so round-1 `check_rules` fails for both rules.

## Expected output (written before any run)

### After first `check_rules` on the planted draft

1. Result is **fail**.
2. Hard violations include **at least**:
   - One with `rule`: `certification` (nurse_id may be empty if the violation is shift-level; date/shift identify the shift).
   - One with `rule`: `weekly_hours`, with `nurse_id` set to the overtime nurse, `found` showing over 40 hours (e.g. 48), `limit` showing 40 hours max.
3. Each hard violation gets a `fix_hint` from the Rules Checker; code’s list wins if the agent list differs.

### Final draft (by round 3 at latest)

4. `check_rules` returns **pass** for hard rules: **0** hard `certification` and **0** hard `weekly_hours` violations (and no other hard failures left open).
5. Every shift has at least one ACLS nurse.
6. No nurse exceeds 40 hours for the week under the rules (at most 3 twelve-hour shifts unless `hours_this_week` allows fewer).
7. No invented nurses; shift times remain day `07:00`/`19:00`, night `19:00`/`07:00`.

## Pass / fail

- **Pass:** All 3 runs report both violations on the first check, then finish with both fixed (items 4–6).
- **Fail:** Only one of the two is reported; final draft still lacks ACLS on a shift or still has a nurse over 40 hours; or staff is invented.

## Notes

- Fix order in the Scheduler prompt prefers coverage/availability first; this case still requires both cert and hours to be clean by the end.
- Soft fairness does not fail this case.
