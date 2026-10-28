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

## Guards (why your fetch must look a certain way)

A web page in the manager's browser can call `127.0.0.1`, so "local only" is not enough. Three guards apply:

- **Host header** must be `127.0.0.1`, `localhost` or `[::1]`, else 400 (stops DNS rebinding).
- **Origin header on a POST** must be `http://localhost:5173` or `http://127.0.0.1:5173` (or absent, as with curl), else 403.
- **Every POST must send `Content-Type: application/json`**, even reject, else 415. Send `{}` when there is no body.

In React: `fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) })`.
Through the Vite proxy these all hold as long as you open the app at `localhost:5173`.

## Endpoints

| Method and path | Body | Returns |
| --- | --- | --- |
| `GET /api/health` | | `{ "ok": true, "live_agents": false }` |
| `GET /api/cases` | | `{ "cases": [summary...], "unreadable": [] }`, newest first. A summary has `case_id, status, outcome, unit, week_start, start_time, trigger, parent_case_id, newer_case_id`. |
| `GET /api/cases/{case_id}` | | The full `CaseRecord` (same shape as `docs/sample-cases/*.json`). |
| `POST /api/cases/{case_id}/approve` | `{ "acknowledge_open_issues": false }` (the body is optional) | The updated `CaseRecord`. |
| `POST /api/cases/{case_id}/reject` | `{}` (any JSON; it is ignored) | The updated `CaseRecord` (`status` and `outcome` are `rejected`). |
| `POST /api/cases/{case_id}/change-demand` | `{ "changes": [{ "unit", "date", "shift", "nurses_needed" }], "new_case_id": null }` | `{ "old": CaseRecord, "child": CaseRecord }`. After this, show `child`. `new_case_id` is optional (the server makes one). |

## New in the case record: the agents' notes

Two additive fields (older records without them still load):
- `unusual`: a list of one-line notes from the Demand agent ("Friday night is the busiest"). Advisory text.
- `input_review`: `needs_manual_review` items about the INPUTS (the agents' own items and nurses who are not on the
  roster). `needs_manual_review` is still the full list (the draft's items plus these), without repeats.

Both are untrusted text from an AI agent: show them as plain text, never as HTML. They are cleaned on the server (one
line, at most 20 items, at most 300 characters each) and never change a row's status or stop a run.

## Errors (always `{ "message": "plain sentence" }`, safe to show the manager)

| Status | Meaning |
| --- | --- |
| 400 | Wrong Host header. |
| 403 | A POST from a web page that is not the local app. |
| 404 | No case with that id. |
| 415 | A POST without `Content-Type: application/json`. |
| 409 | Refused. Out of date (the message names the newer case), already decided, no draft to approve (the message is the `stop_reason`), open issues without `acknowledge_open_issues`, a demand row that does not exist, a new case id that is taken, or **another request is already changing this case** (one request per case at a time; it does not wait). **Nothing was saved.** |
| 422 | The request is malformed (a bad case id, an unknown field, a negative number, an empty `changes` list). |
| 503 | Change demand while live agents are off. Nothing was changed. |
| 500 | Something unexpected. A generic message, no details. Nothing was changed: a run that fails halfway removes its unfinished case, so the id can be used again. |

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
curl -X POST http://127.0.0.1:8000/api/cases/demo-passed/approve -H 'Content-Type: application/json'
curl -X POST http://127.0.0.1:8000/api/cases/demo-open-issues/approve -H 'Content-Type: application/json' \
  -d '{"acknowledge_open_issues": true}'
curl -X POST http://127.0.0.1:8000/api/cases/demo-demand-change/change-demand -H 'Content-Type: application/json' \
  -d '{"changes":[{"unit":"7W","date":"2026-11-03","shift":"night","nurses_needed":4}]}'
```

## What is NOT here yet

- Login or any permission checks (anyone who can reach the port can decide). Local only for now.
- Starting a weekly run and applying a call-out through the API (both cost money; the code exists in `orchestrator.py`
  and `callouts.py`).
- Waiting in line: a second request for a case that is busy is refused at once (409), not queued. Other cases are not blocked.
- Spend limits: change demand has no cap on how often it can be called once live agents are on (about $0.30 to $1.20 each).
- Roster and rules for change demand are not chosen by the case's unit yet.
- Roster and rules for change demand come from the mock data until a real Shift Board source exists.
