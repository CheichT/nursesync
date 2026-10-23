# Mock data

Made-up data only. No real patient or staff information. All names are invented.

One unit (Med-Surg), 16 nurses, 4 weeks (2026-11-02 to 2026-11-29).

## Files

| File | What it holds |
| --- | --- |
| `roster.json` | One manager (`admin-1`) and 16 nurses. Nurses have `unit`, `certifications`, `employment` and `max_weekly_hours`. |
| `availability.json` | Per nurse, per date: `status` (`available` or `unavailable`), `reason`, `note`. Same shape as Shift Board. |
| `shifts.json` | The already-scheduled shifts for **week 1 only** (2026-11-02 to 2026-11-08). Same shape as Shift Board. |
| `leave.json` | Leave requests: `vacation`, `pto`, `fmla`, `overtime`. Statuses `approved` or `pending`. |
| `demand.json` | Nurses needed per date and shift for all 4 weeks, with required certifications. |
| `callouts.json` | Call-outs reported against scheduled shifts. |

## Facts about the data

- Shifts are 12 hours: `day` 07:00 to 19:00 and `night` 19:00 to 07:00 (ends the next morning).
- Roster: 12 full-time nurses (40 hour limit) and 4 part-time nurses (24 hour limit). All 16 have BLS, 9 have ACLS, and 6 have Charge (all Charge nurses also have ACLS).
- Every shift needs 3 nurses, including at least 1 Charge and 1 ACLS.
- `demand.json` has two special rows: 2026-11-17 night has `nurses_needed: null` (missing), and 2026-11-23 day needs 4 with a note (needs review). Handoff status fields (`ok`, `needs_review`, `missing`) are written by orchestrator code, not stored here.

## Rule limits assumed when planting problems

These are assumptions. The real limits belong in `check_rules`, so change them there and re-check this file.

- Rest between shifts: at least 10 hours.
- Consecutive days worked: at most 3.
- Weekly hours: at most the nurse's `max_weekly_hours`.

## Planted problems in week 1 (for tests and evals)

Every other shift in `shifts.json` follows the rules. There are exactly 8 problems:

| # | Rule | Where | What is wrong |
| --- | --- | --- | --- |
| 1 | `rest_time` | n06, night 2026-11-06 then day 2026-11-07 | 0 hours of rest between shifts |
| 2 | `consecutive_shifts` | n04, 2026-11-05 to 2026-11-08 | 4 days in a row (limit 3) |
| 3 | `weekly_hours` | n04 | 48 hours (limit 40) |
| 4 | `weekly_hours` | n16 | 36 hours (limit 24) |
| 5 | `coverage` | night 2026-11-05 | 2 nurses (n14, n15), 3 needed |
| 6 | `certification` | night 2026-11-05 | No Charge nurse |
| 7 | `availability` | n12, day 2026-11-04 | Scheduled on a day marked unavailable (shift status `conflict`) |
| 8 | `availability` | n09, night 2026-11-06 | Scheduled during approved PTO (`l01`) |

## Call-out

`c01`: n08 reported sick for the night shift on 2026-11-03 (`s012`).
