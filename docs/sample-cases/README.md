# Sample case records (for the approval UI)

Made-up data. Several files are the SAME case in different states (`passed`/`approved`, `open_issues`/`approved_with_open_issues`, `stopped_missing_input`/`rejected`, `demand_change_before`/`demand_change_old`), so there are fewer case ids than files. Every `.json` file here is a real `CaseRecord` built by the real orchestrator code with scripted
agents (no API calls), so you can build the UI against the true shape before there is an API.
Shape: `backend/app/contract/case_record.py`. Rules: the PRD, "Case record".
Regenerate: `cd backend && ../.venv/bin/python -m app.sample_cases` (a test fails if these files are out of date).

| File | `status` | `outcome` | What it shows |
| --- | --- | --- | --- |
| `passed.json` | `waiting_approval` | `passed` | Clean week. Approve is allowed. |
| `needs_review.json` | `waiting_approval` | `passed` | Three flagged demand rows (ratio mismatch, outlier, agent flag) and a nurse not on the roster in `needs_manual_review`. The draft still built. Show the flags first. |
| `open_issues.json` | `waiting_approval` | `stopped_after_3_rounds` | Best draft after 3 rounds: an open `coverage` violation, an `open_gaps` row, an `unfixable` row. Approving needs an explicit acknowledgement. |
| `stopped_missing_input.json` | `waiting_approval` | `stopped_missing_input` | No draft. `stop_reason` says what is missing; `needs_manual_review` lists the demand day and the nurse. No Approve. Reject or fix inputs. |
| `approved.json` | `approved` | `passed` | After Approve: `manager_decision: "approved"`, `decision_time`, `decision_details`. |
| `approved_with_open_issues.json` | `approved` | `stopped_after_3_rounds` | Approved with `decision_details.acknowledged_open_issues: true`. |
| `rejected.json` | `rejected` | `rejected` | After Reject. |
| `demand_change_before.json` | `waiting_approval` | `stopped_missing_input` | The same case as `demand_change_old`, before the manager acts: one demand row missing, availability complete. Change demand is the way forward. The API seeds this one. |
| `demand_change_old.json` | `out_of_date` | `stopped_missing_input` | The case the manager changed demand on. `newer_case_id` and `decision_details` (`action: change_demand`, the changes) point to the new case. No Approve. |
| `demand_change_child.json` | `waiting_approval` | `passed` | The new case: `parent_case_id` set, the edited row is `ok` with the note "set by manager (was missing)". Go here after the form is submitted. |
| `call_out_old.json` | `out_of_date` | `passed` | The waiting case a late call-out replaced. `newer_case_id` is set. No Approve. |
| `call_out_child.json` | `waiting_approval` | `passed` | `trigger: call_out`, `affected_shifts`, `callouts`, `parent_case_id`. The replacement is in `final_draft.assignments`. |

Notes for the UI
- Rows to show first: `demand_result.rows` and `availability_result.rows` where `status` is not `ok` (use `note`), then
  `needs_manual_review`, `open_violations` / `unfixable`, `final_draft.open_gaps`, and `soft_tradeoffs`.
- A case with `final_draft: null` has nothing to approve.
- The agents' own `unusual` and `needs_manual_review` extras are not in the record yet. Only stamped rows and notes are.
- There is no API yet. Read these files directly for now.
