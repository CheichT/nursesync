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
- **HTTP API:** shipped (`docs/api-v0.md`). UI uses list / get / approve / reject / change-demand / start-run / run status / usage via the Vite `/api` proxy. Sample JSON remains a fallback when the server is off.
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
| Agent notes | case `unusual` | Plain-text lines from the Demand agent (advisory only; never decide pass/fail) |
| Demand / availability flags | rows where `status` ≠ `ok` | status, note, key fields |
| Needs manual review | case `needs_manual_review` | `item_type`, `id`, `note` |
| Open gaps | `final_draft.open_gaps` | Unit, date, shift, needed vs assigned, `gap_reason` |
| Unresolved hard issues | `open_violations` / `unfixable` | Rule, nurse, date, shift, found/limit or reason |
| Soft tradeoffs | `soft_tradeoffs` | Note only — does **not** block approve by itself |

Use text labels, not color alone (e.g. “Hard — rest time”, “Soft — fairness”).

#### 2. Full schedule

- Week grid for the unit: each date × day/night from `final_draft.assignments`
- Shift times `07:00`–`19:00` / `19:00`–`07:00`

Each cell of the grid is a button. Clicking (or Enter on) a cell opens a popup for that date and shift: a heading with
the date and shift time, "N nurses working · M needed", the open-gap note when the shift is short, and each nurse
with **name and nurse id** (names come from `GET /api/roster`; if it fails the id still shows). Esc, Close or a click
outside closes it and focus returns to the cell. Read-only: nothing in the popup changes the case.

#### 3. How the agents decided

A read-only block above Attention (`src/DecisionPanel.jsx`). It shows a recommendation ("Ready for your review" or "Look at these first: ..."), then one step per agent: Demand (shifts sized, warnings), Availability (who can and cannot work, and why), Scheduler (its own `final_draft.notes`, with nurse ids shown as names) and the rules check (rounds and hard problems per round, labeled plain code, not AI). It only reads what is already on the case record; code still decides pass or fail.

#### Actions (draft screen)

| Action | Behavior |
| --- | --- |
| **Approve** | Allowed only when `status` is `waiting_approval` and `final_draft` is set. Open issues need an explicit acknowledgement (`decision_details.acknowledged_open_issues`). |
| **Change demand** | Edits `nurses_needed`; system retires this case (`out_of_date`) and opens a child. UI then follows `newer_case_id`. |
| **Reject** | Case becomes `rejected`. Manager builds the week by hand. |

Paid actions (Start weekly run, Report call-out) ask for confirmation in an in-app dialog (`src/ConfirmDialog.jsx`), not `window.confirm`, which some browsers block. On load the view opens the newest case that is waiting for a decision and has a draft, so the action buttons are usable at once. When a case is out of date, approved, rejected or still building, a line above the buttons says why they are off.

Disable **Approve** when `status` is `out_of_date`, when there is no draft, or when open issues are not acknowledged. Point to `newer_case_id` when present.

## Out of date

If a late call-out or demand change created a newer case:

- Refuse approve on the old case  
- Point the manager to `newer_case_id`

## Start weekly run

Manager control on the Approve AI draft tab (API connected only).

| Step | Behavior |
| --- | --- |
| **Start weekly run** | Show “N of M paid runs left today” from `GET /api/usage`. Disable when remaining is 0. Confirm with the cost and runs left (“about $0.50–$1.50 … N of M paid runs left today”) Then `POST /api/runs` with `{ unit, week_start }` (JSON content type). Defaults for mock data: unit `7W`, week `2026-11-02` (Monday). |
| **Poll** | Every 5 seconds, `GET /api/runs/{run_id}` until `state` is `done` or `failed`. Show “Running…” and a “run in progress” notice. Show the server `message` as-is (plain text). |
| **Reload mid-run** | On connect, if a case is still `building` and `GET /api/runs/{id}` knows the run, show the in-progress notice, select that case, and resume polling. If there is no such run (a call-out or demand change in flight, or a leftover after a restart), show no notice. |
| **Errors** | 409 / 422 / 429 / 503: show the server `message` as-is. Do not retry in a loop. |
| **When done** | Show outcome, refresh the case list, and open the new `case_id`. Stop polling if the user leaves the tab. |

Needs `NURSESYNC_LIVE=1` (else 503). One run at a time (409 if busy). Daily paid-ops cap (429 when used up). Costs about $0.50–$1.50 and can take a few minutes. **Do not describe as secure.**

## Nurse names

The case record only holds nurse ids. On connect the view calls `GET /api/roster` once (`{ nurses: [{ nurse_id, name }] }`) and shows names in the schedule grid, flags, issues and the call-out banner. If the call fails it shows ids. Names are mock roster data for now.

## Report call-out

Action on a case with `status` `waiting_approval` and a draft (API connected, live agents on, paid runs left).

| Step | Behavior |
| --- | --- |
| **Pick** | Choose one nurse and shift from the draft's assignments. Esc or Cancel closes the panel. |
| **Confirm** | Shows the nurse, date, shift, cost (about $0.15–$1.20) and paid runs left. |
| **Send** | `POST /api/cases/{case_id}/call-out` with `{ call_outs: [{ nurse_id, date, shift }] }`. The reply is `{ old, child }`: open `child`. The old case becomes `out_of_date`. |
| **Errors** | 503 (live agents off), 429 (daily limit), 409 (refused, nothing spent): show the server `message` as-is. |

Disabled when live agents are off, no paid runs are left, or the case is not waiting. **Do not describe as secure.**

## Accessibility (must ship with the UI)

- Every control keyboard-reachable; Esc closes dialogs  
- Buttons have clear labels (`aria-label` if icon-only)  
- Status not by color alone; muted labels use theme variables (readable in dark mode)  
- Logical headings: Start weekly run → Attention → Schedule → Notes → Actions  

## Run (dev)

```bash
# terminal 1 — local API (this computer only); live agents for weekly runs
cd backend && NURSESYNC_LIVE=1 ../.venv/bin/python -m app.serve --seed-samples

# terminal 2 — app (open http://localhost:5173)
npm run dev
```

## Not in this version

- Login / permissions  
- Shift Board notification to nurses  
- Fix-inputs flow for missing availability  
- Call-outs after a case is approved (only a case still waiting can take a call-out)  
