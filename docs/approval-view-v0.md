# NurseSync approval view — v0 (Phase 3)

> **Owner: Kerrian Gordon** (PRD section 3b / 3f). Source of truth: PRD “Case record” and `backend/app/contract/case_record.py`.  
> UI: admin tab **Approve AI draft** (`src/ApprovalView.jsx`) against `docs/sample-cases/` until there is an API.  
> Version one does **not** send schedules to nurses.

## Closed with Cheich (2026-10-28)

- **Status:** only the orchestrator writes it. The UI reads stamped rows and notes.
- **Row fields:** as listed on the case record. Agents’ extras (`unusual`, agent-owned `needs_manual_review`) are **not** saved on the case yet — show stamped `demand_result` / `availability_result` flags and the case-level `needs_manual_review`.
- **Stop vs build:** a missing required row stops the run (no draft, no Approve). `needs_review` alone still builds.
- **Fix inputs:** missing availability has no “fix” action in product yet. Only a new run fixes it. UI can Reject or Change demand where allowed.
- **Demand change:** old case → `out_of_date`; child case starts. After submit, go to `newer_case_id`.
- **No API yet:** load sample JSON directly. Approve / reject / change-demand are local mirrors of `backend/app/decisions.py` until Cheich wires an endpoint.

## Purpose

Let the nurse manager review a draft and choose: **approve**, **change a demand number**, or **reject**. Nothing is final without this step.

## When it opens

- After a **passing** draft (`check_rules`: 0 hard violations), or  
- After **3** fix rounds with the best draft still carrying open hard violations / `unfixable` rows, or  
- After **stopped_missing_input** (show `stop_reason`; no Approve).

Show `case_id`, `snapshot_id`, `start_time`, draft `version` (if any), and outcome.

## Screen layout (one job: decide)

### 1. Attention first (above the schedule)

Show these blocks **before** the full grid. If a block is empty, hide it.

| Block | Source | Manager sees |
| --- | --- | --- |
| Demand / availability flags | rows where `status` ≠ `ok` | status, note, key fields |
| Needs manual review | case `needs_manual_review` | `item_type`, `id`, `note` |
| Open gaps | `final_draft.open_gaps` | Unit, date, shift, needed vs assigned, `gap_reason` |
| Unresolved hard issues | `open_violations` / `unfixable` | Rule, nurse, date, shift, found/limit or reason |
| Soft tradeoffs | `soft_tradeoffs` | Note only — does **not** block approve by itself |

Use text labels, not color alone (e.g. “Hard — rest time”, “Soft — fairness”).

### 2. Full schedule

- Week grid for the unit: each date × day/night from `final_draft.assignments`.
- Each cell: assigned `nurse_id`s; shift times `07:00`–`19:00` / `19:00`–`07:00`.

### 3. Reasoning notes

- `final_draft.notes` as a short list (manager-facing, not for `check_rules`).

## Actions

| Action | Behavior |
| --- | --- |
| **Approve** | Allowed only when `status` is `waiting_approval` and `final_draft` is set. Open issues need an explicit acknowledgement (`decision_details.acknowledged_open_issues`). |
| **Change demand** | Edits `nurses_needed`; system retires this case (`out_of_date`) and opens a child. UI then follows `newer_case_id`. |
| **Reject** | Case becomes `rejected`. Manager builds the week by hand. |

Disable **Approve** when `status` is `out_of_date`, when there is no draft, or when open issues are not acknowledged. Point to `newer_case_id` when present.

## Accessibility (must ship with the UI)

- Every control keyboard-reachable; Esc closes dialogs  
- Buttons have clear labels (`aria-label` if icon-only)  
- Status not by color alone  
- Logical headings: Attention → Schedule → Notes → Actions  

## Not in this version

- Live agent / API wiring  
- Shift Board notification to nurses  
- Fix-inputs flow for missing availability  
