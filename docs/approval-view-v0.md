# NurseSync approval view — v0 (Phase 3)

> **Owner: Kerrian Gordon** (PRD section 3b / 3f). Source of truth: PRD “Case record” and `backend/app/contract/case_record.py` (Cheich).  
> UI: admin tab **Approve AI draft** (`src/ApprovalView.jsx`) talks to Cheich’s local case API (`docs/api-v0.md`). Falls back to `docs/sample-cases/` if the API is down.  
> Version one does **not** send schedules to nurses. **No login — local only; do not describe as secure.**

## Closed with Cheich (2026-10-28)

- **Status:** only the orchestrator writes it. The UI reads stamped rows and notes.
- **Row fields:** as listed on the case record. Agents’ extras (`unusual`, agent-owned `needs_manual_review`) are **not** saved on the case yet — show stamped `demand_result` / `availability_result` flags and the case-level `needs_manual_review`.
- **Stop vs build:** a missing required row stops the run (no draft, no Approve). `needs_review` alone still builds.
- **Fix inputs:** missing availability has no “fix” action in product yet. Only a new run fixes it. UI can Reject or Change demand where allowed.
- **Demand change:** old case → `out_of_date`; child case starts. After submit, go to `newer_case_id`.
- **HTTP API:** shipped (`docs/api-v0.md`). UI uses list / get / approve / reject / change-demand via the Vite `/api` proxy. Sample JSON remains a fallback when the server is off.
- **CaseRecord shape** unchanged. Change demand needs `NURSESYNC_LIVE=1` on the server (costs money).

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
| `demand_result`, `availability_result` | Checked inputs (orchestrator-owned `status` on each row) |
| `manager_decision`, `decision_time`, `decision_details` | Filled after the manager acts |

Only offer decisions while `status` is `waiting_approval`.

## Screens

### A. Missing input (`outcome: stopped_missing_input`)

Opens when required Demand/Availability input was missing and the orchestrator **stopped before the Scheduler**. There is **no** `final_draft`.

**Show**
- `case_id`, `snapshot_id`, `start_time`, `status`, `outcome`
- `stop_reason` (primary message)
- Rows in `demand_result` / `availability_result` with `status: "missing"` (and their `note`s)
- `needs_manual_review` if present

**Do not show** a schedule grid or Approve.

**Actions**
| Action | Behavior |
| --- | --- |
| **Change demand** | Allowed when demand can be edited. Uses the **child case** rule below. If availability rows are also missing, warn that the new case may stop again (no availability fix action yet). |
| **Reject** | `status` → `rejected`, `outcome` → `rejected`. Manager builds the week by hand. |
| **Open linked case** | If `newer_case_id` is set, go there. |

### B. Draft ready (`waiting_approval` with a `final_draft`)

Opens after a **passing** draft (`outcome: passed`) or after **3** fix rounds (`outcome: stopped_after_3_rounds`) with the best draft still carrying issues.

Show `case_id`, `snapshot_id`, `start_time`, draft `version`, `status`, and `outcome`.

#### 1. Attention first (above the schedule)

Show these blocks **before** the full grid. Hide empty blocks.

| Block | Source | Manager sees |
| --- | --- | --- |
| Demand / availability flags | rows where `status` ≠ `ok` | status, note, key fields |
| Needs manual review | case `needs_manual_review` | `item_type`, `id`, `note` |
| Open gaps | `final_draft.open_gaps` | Unit, date, shift, needed vs assigned, `gap_reason` |
| Unresolved hard issues | `open_violations` / `unfixable` | Rule, nurse, date, shift, found/limit or reason |
| Soft tradeoffs | `soft_tradeoffs` | Note only — does **not** block approve by itself |

Use text labels, not color alone (e.g. “Hard — rest time”, “Soft — fairness”).

#### 2. Full schedule

- Week grid for the unit: each date × day/night from `final_draft.assignments`
- Shift times `07:00`–`19:00` / `19:00`–`07:00`

#### 3. Reasoning notes

- `final_draft.notes` as a short list (manager-facing, not for `check_rules`)

#### Actions (draft screen)

| Action | Behavior |
| --- | --- |
| **Approve** | Allowed only when `status` is `waiting_approval` and `final_draft` is set. Open issues need an explicit acknowledgement (`decision_details.acknowledged_open_issues`). |
| **Change demand** | Edits `nurses_needed`; system retires this case (`out_of_date`) and opens a child. UI then follows `newer_case_id`. |
| **Reject** | Case becomes `rejected`. Manager builds the week by hand. |

Disable **Approve** when `status` is `out_of_date`, when there is no draft, or when open issues are not acknowledged. Point to `newer_case_id` when present.

## Out of date

If a late call-out or demand change created a newer case:

- Refuse approve on the old case  
- Point the manager to `newer_case_id`

## Accessibility (must ship with the UI)

- Every control keyboard-reachable; Esc closes dialogs  
- Buttons have clear labels (`aria-label` if icon-only)  
- Status not by color alone; muted labels use theme variables (readable in dark mode)  
- Logical headings: Attention → Schedule → Notes → Actions  

## Run (dev)

```bash
# terminal 1 — local API (this computer only)
cd backend && ../.venv/bin/python -m app.serve --seed-samples

# terminal 2 — app (open http://localhost:5173)
npm run dev
```

## Not in this version

- Login / permissions  
- Shift Board notification to nurses  
- Fix-inputs flow for missing availability  
- Starting weekly runs or call-outs through the API  
