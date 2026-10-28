# Phase 1 eval cases (Kerrian)

Plain-language eval cards for Phase 1 Scheduler / Rules Checker / baseline work.  
**Expected answers are written here before any live model run.**

Source of truth: PRD section 3d.  
Scheduler-dependent cases run **3 times**; all 3 must match that case’s expected output.  
Code-only paths (parts of 13–14) run once per sub-case unless a live agent is involved.

| Case | File | Scenario data |
| --- | --- | --- |
| 1 — Golden (normal) | [case_01_golden.md](case_01_golden.md) | Current `backend/data/mock/` (base week) |
| 4 — Overnight rest | [case_04_overnight_rest.md](case_04_overnight_rest.md) | `backend/data/scenarios/case_04/` (`load_scenario("case_04")`) |
| 5 — Loop limit | [case_05_loop_limit.md](case_05_loop_limit.md) | `backend/data/scenarios/case_05/` (`load_scenario("case_05")`) |
| 6 — Cert + overtime | [case_06_cert_and_overtime.md](case_06_cert_and_overtime.md) | `backend/data/scenarios/case_06/` (`load_scenario("case_06")`) |
| 7 — Single-agent baseline | [case_07_baseline.md](case_07_baseline.md) | Same data as compared cases; start with case 1 |
| 13 — Misreported verdict | [case_13_misreported_verdict.md](case_13_misreported_verdict.md) | Draft with 2 hard violations + dropping Rules Checker |
| 14 — Lost or stale verdict | [case_14_lost_or_stale_verdict.md](case_14_lost_or_stale_verdict.md) | Missing / unparseable / stale check result |

Owner: Kerrian Gordon. Do not edit `models.py` or mock files from this workstream.

**Live run results:** [RESULTS.md](RESULTS.md)
