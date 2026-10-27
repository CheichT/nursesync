# Phase 1 eval cases (Kerrian)

Plain-language eval cards for Phase 1 Scheduler / Rules Checker work.  
**Expected answers are written here before any live model run.**

Source of truth: PRD section 3d. Pass rule: each Scheduler-dependent case runs **3 times**; all 3 must match that case’s expected output (see PRD).

| Case | File | Scenario data |
| --- | --- | --- |
| 1 — Golden (normal) | [case_01_golden.md](case_01_golden.md) | Current `backend/data/mock/` (base week) |
| 4 — Overnight rest | [case_04_overnight_rest.md](case_04_overnight_rest.md) | Needs a planted bad draft / scenario (Cheich) |
| 5 — Loop limit | [case_05_loop_limit.md](case_05_loop_limit.md) | Needs an impossible-week scenario (Cheich) |
| 6 — Cert + overtime | [case_06_cert_and_overtime.md](case_06_cert_and_overtime.md) | Needs a planted bad draft (Cheich) |

Owner: Kerrian Gordon. Do not edit `models.py` or mock files from this workstream.
