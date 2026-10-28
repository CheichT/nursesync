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
| `GET /api/roster` | | `{ "nurses": [{ "nurse_id", "name" }] }`. Lets the UI show names instead of ids. Free. Mock roster for now. |
| `GET /api/cases` | | `{ "cases": [summary...], "unreadable": [] }`, newest first. A summary has `case_id, status, outcome, unit, week_start, start_time, trigger, parent_case_id, newer_case_id`. |
| `GET /api/cases/{case_id}` | | The full `CaseRecord` (same shape as `docs/sample-cases/*.json`). |
| `POST /api/cases/{case_id}/approve` | `{ "acknowledge_open_issues": false }` (the body is optional) | The updated `CaseRecord`. |
| `POST /api/cases/{case_id}/reject` | `{}` (any JSON; it is ignored) | The updated `CaseRecord` (`status` and `outcome` are `rejected`). |
| `POST /api/runs` | `{ "unit": "7W", "week_start": "2026-11-02", "case_id": null }` | **202** `{ run_id, case_id, state, started_at, ... }` at once. The run goes on in the background (a few minutes, about $0.50 to $1.50). Poll `GET /api/runs/{run_id}` or the case itself. Needs `NURSESYNC_LIVE=1` (else 503). |
| `GET /api/runs/{run_id}` | | `{ state: "running" \| "done" \| "failed", outcome, message, finished_at }`. Kept only while the server runs; the case itself is saved. |
| `GET /api/usage` | | `{ capped, used_today, max_per_day, remaining, date }`: how many paid operations are left today. |
| `POST /api/cases/{case_id}/change-demand` | `{ "changes": [{ "unit", "date", "shift", "nurses_needed" }], "new_case_id": null }` | `{ "old": CaseRecord, "child": CaseRecord }`. After this, show `child`. `new_case_id` is optional (the server makes one). |
| `POST /api/cases/{case_id}/call-out` | `{ "call_outs": [{ "nurse_id", "date", "shift", "reported_at": null }], "new_case_id": null }` | `{ "old": CaseRecord, "child": CaseRecord }`. Only for a case still waiting for approval. Needs `NURSESYNC_LIVE=1` (else 503), counts against the daily cap (429), refusals (nurse not on roster, date outside the week, case already decided) are 409 and spend nothing. `reported_at` defaults to now. |

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
| 404 | No case (or run) with that id. |
| 415 | A POST without `Content-Type: application/json`. |
| 409 | Refused. Out of date (the message names the newer case), already decided, no draft to approve (the message is the `stop_reason`), open issues without `acknowledge_open_issues`, a demand row that does not exist, a new case id that is taken, or **another request is already changing this case** (one request per case at a time; it does not wait). **Nothing was saved.** |
| 429 | The daily limit of paid operations is used up. Nothing was started or spent. |
| 422 | The request is malformed or cannot start (an unknown unit, a week that is not a Monday, a week with no data) (a bad case id, an unknown field, a negative number, an empty `changes` list). |
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

## Starting a weekly run, and the daily cap

- **One run at a time.** A second `POST /api/runs` while one is running gets 409 "already in progress" and costs nothing.
- **Daily cap on paid operations** (weekly runs and demand changes): 10 a day by default. Set `NURSESYNC_MAX_PAID_OPS_PER_DAY`
  (0 stops all paid operations). It counts operations, not dollars, and it is saved in `backend/data/usage.json` so a restart
  does not reset it. An operation counts when it is accepted, even if it later fails (the money may be spent). A bad request
  (a wrong unit or week, a demand row that does not exist) is refused before it counts. An unreadable usage file stops paid
  operations instead of guessing.
- **A failed run** removes its unfinished case, and its status says so in plain words (details stay in the server log).
  A `building` case left by a crash is removed at the next server start.
- **For now only the mock data exists**: unit `7W`, week of `2026-11-02`. A real Shift Board source replaces it later.
- For the UI: a "Start weekly run" button posts to `/api/runs` (JSON content type), then polls `/api/runs/{id}` every few
  seconds until `state` is `done` or `failed`, shows the `message`, and shows the remaining count from `/api/usage`.

## What is NOT here yet

- Login or any permission checks (anyone who can reach the port can decide). Local only for now.
- Waiting in line: a second request for a case that is busy is refused at once (409), not queued. Other cases are not blocked.
- Roster and rules for change demand are not chosen by the case's unit yet.
- Roster and rules for change demand come from the mock data until a real Shift Board source exists.
