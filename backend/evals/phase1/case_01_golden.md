# Eval case 1 — Golden example (normal input)

**Phase:** 1  
**Depends on:** Scheduler (and `check_rules` in code)  
**Runs:** 3. All 3 must match the expected output below.

## Purpose

Show that a clean week produces a full, rule-safe draft with no guessing.

## Input

- Unit: `7W`
- Week: Monday `2026-11-02` through Sunday `2026-11-08`
- Roster: 24 nurses (`backend/data/mock/roster.json`); N001–N008 hold ACLS
- Demand: 14 shifts, mostly 4 nurses, some 5; **62** total slots (`demand.json`)
- Availability: one row per nurse + date + shift; approved time off only (no call-outs, no missing rows)
- Rules: `rules.json` (10h rest, 40h week, 3 consecutive, ACLS on every shift, day `07:00`–`19:00`, night `19:00`–`07:00`)
- Reference: `reference_draft.json` is a known-good Draft shape for this week (0 hard violations)

This is the base mock week described in `backend/data/mock/README.md`.

## Expected output (written before any run)

A final Draft that:

1. **Coverage:** Every demand row has exactly `nurses_needed` assignments for that unit/date/shift. Total assignments = **62**. `open_gaps` is `[]`.
2. **Hard rules:** `check_rules` returns **pass** with **0** hard violations (rest, weekly hours, consecutive shifts, certification, availability, coverage).
3. **Availability:** No assignment places a nurse on a shift where `available` is false (including the approved time-off rows for N003, N006, N009, N015, N020).
4. **Times:** Every assignment uses exact shift times — day `07:00`/`19:00`, night `19:00`/`07:00`.
5. **Certification:** Every shift has at least one ACLS nurse.
6. **Hours / streak:** No nurse over 40 hours for the week (at most 3 shifts of 12h); no more than 3 shifts in a row.
7. **Labels:** Valid `case_id`, `snapshot_id`, `version` in `{1,2,3}` (passing on round 1 is ideal; still pass if fixed by round 3 with 0 hard violations at the end).
8. **Review lists:** `needs_manual_review` is `[]` (no missing / needs_review rows in this input). `unfixable` is `[]`. `suggestions` is `[]`.
9. **Notes:** `notes` may list short reasons for hard choices; notes are for the manager and must not invent data.

Soft fairness may still appear as a soft tradeoff (gap at most 2 on the reference week). Soft results **do not** fail this case.

## Pass / fail

- **Pass:** All 3 runs end with a draft that meets items 1–8 above (0 hard violations, full coverage).
- **Fail:** Any run ends with a hard violation, an open coverage gap, a nurse scheduled on time off, wrong shift times, or invented nurses/IDs.

## Not required for pass

- Matching `reference_draft.json` assignment-for-assignment (many valid schedules exist).
- Empty `notes`.
- Zero soft fairness tradeoffs.
