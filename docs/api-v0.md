# NurseSync case API — v0 (for the approval UI)

> **Owner: Cheich Toure.** Code: `backend/app/api.py` (endpoints) and `backend/app/serve.py` (the server).
> It wraps `decisions.py` and the case store. The rules live there; the API only turns refusals into messages.
> **There is no login. It runs on this computer only (127.0.0.1) and must not be described as secure.**

## Run it

```bash
cd backend
../.venv/bin/pip install -r requirements.txt            # once
../.venv/bin/python -m app.serve --seed-samples         # http://127.0.0.1:8000
```

- `--seed-samples` adds the sample cases the store does not have yet (the undecided version of each case, 8 case ids).
  Several files in `docs/sample-cases/` are the same case in different states, and a store holds one state per case id.
- Cases are saved in `backend/data/cases/` (gitignored). Delete that folder to start fresh.
- Interactive docs (try it in the browser): http://127.0.0.1:8000/docs
- **Live agents are OFF by default** (they cost money). Change demand needs `NURSESYNC_LIVE=1` and a key in `.env`:
  `NURSESYNC_LIVE=1 ../.venv/bin/python -m app.serve`. Each change-demand call runs the Scheduler loop: about
  $0.30 to $1.20 and it can take a few minutes.

## Endpoints

| Method and path | Body | Returns |
| --- | --- | --- |
| `GET /api/health` | | `{ "ok": true, "live_agents": false }` |
| `GET /api/cases` | | `{ "cases": [summary...], "unreadable": [] }`, newest first. A summary has `case_id, status, outcome, unit, week_start, start_time, trigger, parent_case_id, newer_case_id`. |
| `GET /api/cases/{case_id}` | | The full `CaseRecord` (same shape as `docs/sample-cases/*.json`). |
| `POST /api/cases/{case_id}/approve` | `{ "acknowledge_open_issues": false }` | The updated `CaseRecord`. |
| `POST /api/cases/{case_id}/reject` | none | The updated `CaseRecord` (`status` and `outcome` are `rejected`). |
| `POST /api/cases/{case_id}/change-demand` | `{ "changes": [{ "unit", "date", "shift", "nurses_needed" }], "new_case_id": null }` | `{ "old": CaseRecord, "child": CaseRecord }`. After this, show `child`. `new_case_id` is optional (the server makes one). |

## Errors (always `{ "message": "plain sentence" }`, safe to show the manager)

| Status | Meaning |
| --- | --- |
| 404 | No case with that id. |
| 409 | Refused. Out of date (the message names the newer case), already decided, no draft to approve (the message is the `stop_reason`), open issues without `acknowledge_open_issues`, a demand row that does not exist, a new case id that is taken. **Nothing was saved.** |
| 422 | The request is malformed (a bad case id, an unknown field, a negative number, an empty `changes` list). |
| 503 | Change demand while live agents are off. Nothing was changed. |
| 500 | Something unexpected. A generic message, no details. Nothing was changed. |

The UI should also follow the same rules as the sketch: offer decisions only while `status` is `waiting_approval`, hide
Approve when `final_draft` is null, and ask for the acknowledgement when the draft has open issues. The API enforces
all of it anyway, so a stale screen cannot approve something it should not.

## Calling it from the React app (dev)

The Vite dev server runs on port 5173. Either call `http://127.0.0.1:8000` directly (CORS allows only
`http://localhost:5173` and `http://127.0.0.1:5173`), or add a proxy in `vite.config.js`:

```js
server: { proxy: { "/api": "http://127.0.0.1:8000" } }
```

Examples:

```bash
curl http://127.0.0.1:8000/api/cases
curl -X POST http://127.0.0.1:8000/api/cases/demo-passed/approve -H 'Content-Type: application/json' -d '{}'
curl -X POST http://127.0.0.1:8000/api/cases/demo-open-issues/approve -H 'Content-Type: application/json' \
  -d '{"acknowledge_open_issues": true}'
curl -X POST http://127.0.0.1:8000/api/cases/demo-demand-change/change-demand -H 'Content-Type: application/json' \
  -d '{"changes":[{"unit":"7W","date":"2026-11-03","shift":"night","nurses_needed":4}]}'
```

## What is NOT here yet

- Login or any permission checks (anyone who can reach the port can decide). Local only for now.
- Starting a weekly run and applying a call-out through the API (both cost money; the code exists in `orchestrator.py`
  and `callouts.py`).
- One decision at a time: a lock covers every decision, including a long change-demand run.
- Roster and rules for change demand come from the mock data until a real Shift Board source exists.
