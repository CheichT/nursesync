# Mock data

Made-up data only. No real patient or staff information. All names are invented.

One unit (7W), 24 nurses, one week (Monday 2026-11-02 to Sunday 2026-11-08). The files follow the PRD's "Phase 1 input files" and "Draft format" exactly.

## Files

| File | What it holds |
| --- | --- |
| `roster.json` | 24 nurses: `nurse_id`, `name`, `unit`, `certifications`, `hours_this_week`. Eight nurses (N001 to N008) hold ACLS. |
| `demand.json` | 14 rows (7 days x 2 shifts): `patient_count` and `nurses_needed` (patients divided by 5, rounded up). Always 4 or 5 nurses. |
| `availability.json` | 336 rows, one per nurse, date and shift: `available`, `reason` (`none` or `approved_time_off`), `status`, `note`. |
| `rules.json` | The limits `check_rules` uses: 10 hours rest, 40 hours a week, 3 shifts in a row, ACLS on every shift, 1 nurse per 5 patients, fairness gap 2. |
| `reference_draft.json` | A correct draft in the PRD's Draft format. It has 0 hard-rule violations and a fairness gap of 2. |
| `leave.json` | Leave requests in the Shift Board shape (`employeeId`). Not a PRD format. Only **approved** requests appear as time off in `availability.json`. Pending ones (an FMLA request and an overtime request) are information only. |

## Facts about the data

- Two 12-hour shifts: `day` 07:00 to 19:00 and `night` 19:00 to 07:00 (ends the next morning).
- At the 40-hour limit each nurse works at most 3 shifts a week. The reference draft has 62 assignments: 10 nurses work 2 shifts and 14 work 3.
- Approved time off: N003 (Nov 4), N006 (Nov 5), N009 (Nov 6), N015 (Nov 2 to 3), N020 (Nov 7 to 8). It shows as `available: false` with `reason: approved_time_off`.
- The base case has no call-outs, no missing data and no conflicts, so it matches PRD eval case 1.

## Not here yet

Call-outs, missing or malformed rows, and the demand outlier belong to Phase 2 and 3 evals. They will be added as separate scenario files when those phases start. Drafts with planted violations for `check_rules` tests will live with those tests.

## How it was made

A script built a feasible week, then a second, independent script checked the saved files against every hard rule in the PRD. Changing a rule limit means regenerating and re-checking this data.
