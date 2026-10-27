# NurseSync approval view — sketch v0 (Phase 3)

> **Owner: Kerrian Gordon** (PRD section 3f). Source of truth: PRD 3b (manager step) and Draft / Violation formats in `models.py`.  
> This is a **UX/spec sketch**, not implemented UI yet. Version one does **not** send schedules to nurses.

## Purpose

Let the nurse manager review a draft and choose: **approve**, **change a demand number**, or **reject**. Nothing is final without this step.

## When it opens

- After a **passing** draft (`check_rules`: 0 hard violations), or  
- After **3** fix rounds with the best draft still carrying open hard violations / `unfixable` rows.

Show `case_id`, `snapshot_id`, draft `version`, and outcome (`passed` or `stopped_after_3_rounds`).

## Screen layout (one job: decide)

### 1. Attention first (above the schedule)

Show these blocks **before** the full grid. If a block is empty, hide it.

| Block | Source | Manager sees |
| --- | --- | --- |
| Open gaps | `draft.open_gaps` | Unit, date, shift, needed vs assigned, `gap_reason` |
| Needs manual review | `draft.needs_manual_review` | `item_type`, `id`, `note` |
| Unresolved hard issues | `open_violations` / `unfixable` | Rule, nurse, date, shift, found/limit or reason |
| Soft tradeoffs | `soft_tradeoffs` (e.g. fairness) | Note only — does **not** block approve by itself |

Use text labels, not color alone (e.g. “Hard — rest time”, “Soft — fairness”).

### 2. Full schedule

- Week grid for the unit: each date × day/night.
- Each cell: assigned `nurse_id`s (and names if roster is on hand), shift times `07:00`–`19:00` / `19:00`–`07:00`.
- Optional: expand a cell for certifications / hours.

### 3. Reasoning notes

- `draft.notes` as a short list (manager-facing, not for `check_rules`).

## Actions

| Action | Behavior |
| --- | --- |
| **Approve** | Case outcome `approved`. Manager posts the schedule themselves (out of scope to notify nurses in v1). |
| **Change demand** | Manager edits `nurses_needed` (and/or patient count if shown) for one or more demand rows. System updates `demand_result` and **reruns from the Scheduler only** (keep existing availability). Return to this view with the new draft. |
| **Reject** | Case outcome `rejected`. Stop. Manager builds the week by hand. |

Disable **Approve** when the case is marked `out_of_date` (late call-out started a newer run). Tell the manager why.

## Out of date

If a late call-out created a new case with `parent_case_id`, this view must:

- Refuse approve on the old case  
- Point the manager to the new run / message that a newer draft exists  

## Accessibility (must ship with the UI)

- Every control keyboard-reachable; Esc closes dialogs  
- Buttons have clear labels (`aria-label` if icon-only)  
- Status not by color alone  
- Logical headings: Attention → Schedule → Notes → Actions  

## Not in this sketch

- Live agent wiring  
- Shift Board notification to nurses  
- Full React implementation (follow-up once Phase 1 live loop is stable)

## Build note

Implement against the Draft JSON the harness/orchestrator already returns. Prefer a dedicated admin route/tab in the Shift Board app later; keep this spec as the acceptance checklist.
