# Eval scenarios

Made-up data only. Each folder is the base mock week (`../mock/`) with one change. Any file in a folder replaces the mock file of the same name. `planted_draft.json` is the draft the harness feeds in as the round-1 Scheduler output. Load one with `load_scenario("case_04")` in `app/harness/phase1.py`.

| Folder | Eval card | What is planted | What `check_rules` finds on round 1 |
| --- | --- | --- | --- |
| `case_04/` | Case 4, overnight rest | N002 works Mon night 2026-11-02 and also Tue day 2026-11-03 (swapped in for N018) | One hard violation: `rest_time`, N002, 2026-11-03 day (0 hours of rest) |
| `case_05/` | Case 5, loop limit | `availability.json`: all 8 ACLS nurses (N001 to N008) are off on Thu night 2026-11-05. No planted draft. | Nothing can fix it: no ACLS nurse is available for that shift, so the loop must stop after 3 rounds |
| `case_06/` | Case 6, cert and overtime | Tue night 2026-11-03 has no ACLS nurse (N013 replaces N004), and N001 works 4 shifts (48 hours) | Two hard violations: `certification` on 2026-11-03 night, `weekly_hours` for N001 |

| `case_02/` | Case 2, edge case | `availability.json`: N011 and N013 on approved leave all week, N004 (ACLS) called out from Wed 2026-11-04 on. `demand.json`: two shifts need 5 instead of 4 (Thu night, Sat day), so the week needs 64 nurse-shifts instead of 62 with fewer nurses to cover it. | With the unchanged mock draft: `availability` violations for those nurses, and `coverage` on the two busier shifts. A gap may be unavoidable. |
| `case_03/` | Case 3, adversarial input | `availability.json`: all of N012's rows are `missing`. `demand.json`: Tue night 2026-11-03 is `missing` (get_demand error). | The team must stop before the Scheduler and list both. A baseline that schedules N012 or staffs that night is guessing (counted as `invented_assignments`). |

Cases 2, 3 and 7 compare the single-agent baseline with the team: `python -m app.run_eval case_02 --runs 3` (live, costs money). Case 3 costs the team nothing, because it stops before any agent runs.

Tests in `tests/unit/harness/test_eval_scenarios.py` and `tests/unit/harness/test_eval_cases_2_3.py` prove each scenario gives exactly the results above.
