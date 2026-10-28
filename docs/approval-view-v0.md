# NurseSync approval view — sketch v0 (Phase 3)

> **Owner: Kerrian Gordon** (PRD section 3f).  
> Source of truth: PRD 3b (manager step) and `backend/app/contract/case_record.py` (Cheich).  
> This is a **UX/spec sketch**, not implemented UI yet. Version one does **not** send schedules to nurses.

## Purpose

Let the nurse manager review one **case record** and choose: **approve**, **change a demand number**, or **reject**. Nothing is final without this step.

## Data source

Read a `CaseRecord` (not a bare Draft). Important fields:

| Field | Meaning |
| --- | --- |
| `case_id`, `snapshot_id` | Labels for this run |
| `start_time` | When the run started (ISO). **Not** `created_at`. |
| `status` | Case lifecycle: `building`, `waiting_approval`, `approved`, `rejected`, `out_of_date`. **Not** `state`. |
| `outcome` | How the loop ended: `passed`, `stopped_after_3_rounds`, `stopped_missing_input`, or `rejected` |
| `stop_reason` | Plain sentence when the run stopped early (esp. missing input) |
| `parent_case_id` / `newer_case_id` | Child / replacement links |
| `final_draft`, `open_violations`, `unfixable`, `needs_manual_review`, `soft_tradeoffs` | What to show when a draft exists |
| `demand_result`, `availability_result` | Checked inputs (with orchestrator-owned `status` on each row) |
| `manager_decision`, `decision_time`, `decision_details` | Filled after the manager acts |

Only offer decisions while `status` is `waiting_approval`.

## Screens

### A. Missing input (`outcome: stopped_missing_input`)

Opens when required Demand/Availability input was missing and the orchestrator **stopped before the Scheduler**. There is **no** `final_draft`.

**Show**
- `case_id`, `snapshot_id`, `start_time`, `status`, `outcome`
- `stop_reason` (primary message)
- Which inputs failed: rows in `demand_result` / `availability_result` with `status: "missing"` (and their `note`s)
- `needs_manual_review` if present

**Do not show** a schedule grid or Approve.

**Actions**
| Action | Behavior |
| --- | --- |
| **Change demand** | Allowed only if enough demand context exists to edit; otherwise hide. Uses the **child case** rule below. |
| **Reject** | `status` → `rejected`, `outcome` → `rejected`. Manager builds the week by hand. |
| **Open linked case** | If `newer_case_id` is set, go there. |

### B. Draft ready (`waiting_approval` with a `final_draft`)

Opens after a **passing** draft (`outcome: passed`) or after **3** fix rounds (`outcome: stopped_after_3_rounds`) with the best draft still carrying issues.

Show `case_id`, `snapshot_id`, `start_time`, draft `version`, `status`, and `outcome`.

#### 1. Attention first (above the schedule)

Show these blocks **before** the full grid. Hide empty blocks.

| Block | Source | Manager sees |
| --- | --- | --- |
| Open gaps | `final_draft.open_gaps` | Unit, date, shift, needed vs assigned, `gap_reason` |
| Needs manual review | `needs_manual_review` (case) / draft list | `item_type`, `id`, `note` |
| Unresolved hard issues | `open_violations` / `unfixable` | Rule, nurse, date, shift, found/limit or reason |
| Soft tradeoffs | `soft_tradeoffs` | Note only — does **not** block approve by itself |

Use text labels, not color alone (e.g. “Hard — rest time”, “Soft — fairness”).

#### 2. Full schedule

- Week grid for the unit: each date × day/night from `final_draft.assignments`
- Shift times `07:00`–`19:00` / `19:00`–`07:00`
- Optional: expand a cell for certifications / hours from the snapshot roster

#### 3. Reasoning notes

- `final_draft.notes` as a short list (manager-facing, not for `check_rules`)

#### Actions (draft screen)

| Action | Behavior |
| --- | --- |
| **Approve** | `status` → `approved`. If open issues remain, require an explicit acknowledge (`decision_details.acknowledged_open_issues`). Manager posts the schedule themselves (no send-to-nurses in v1). |
| **Change demand** | See **Demand change = child case** below. |
| **Reject** | `status` → `rejected`, `outcome` → `rejected`. Manager builds the week by hand. |

Disable **Approve** when `status` is `out_of_date`. Tell the manager why and link `newer_case_id` if set.

### C. Out of date (`status: out_of_date`)

Read-only banner: a newer run replaced this one. Link to `newer_case_id`. No approve / change demand / reject on this record.

## Demand change = child case (locked)

**Decision (Kerrian, 2026-10-28): option B — child case.**

When the manager changes one or more `nurses_needed` values:

1. Record the decision on the **current** case (`decision_details.action: "change_demand"`, list of `demand_changes`).
2. Mark the current case `out_of_date` and set `newer_case_id` to the new run.
3. Start a **new** case with its own `case_id` and snapshot; set `parent_case_id` to the old case.
4. Rerun from the **Scheduler only**, keeping the existing availability result; apply the manager’s demand edits (those rows become `ok` with a plain note).
5. Open the approval view on the **new** case when it reaches `waiting_approval`.

Do **not** mutate demand in place on the same case and pretend it is still one continuous approval. History stays one case per run.

## Accessibility (must ship with the UI)

- Every control keyboard-reachable; Esc closes dialogs  
- Buttons have clear labels (`aria-label` if icon-only)  
- Status not by color alone  
- Logical headings per screen (e.g. Missing input → Details → Actions; or Attention → Schedule → Notes → Actions)

## Not in this sketch

- Shift Board notification to nurses  
- Full React implementation (follow-up once case-record JSON is stable in the UI)

## Build note

Implement against `CaseRecord` from the orchestrator / case store. Prefer a dedicated admin route/tab in the Shift Board app; keep this spec as the acceptance checklist.
