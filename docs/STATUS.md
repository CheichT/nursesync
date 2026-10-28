# NurseSync status and handoff

> Written 2026-10-28 by Cheich's side so the project can continue without any one session. Rough completion: **about
> 95%**. Version one is local only: **no login, nothing is sent to nurses, and nothing here is secure.**

## What it is

A scheduling app (React + Vite, repo root) plus an AI back end (Python, `backend/`) that drafts a hospital unit's weekly
nurse schedule. Four AI agents (Demand, Availability, Scheduler, Rules Checker) are run by plain code (the orchestrator).
**Code decides if a schedule is safe, not the AI**: `check_rules` is plain code. A human manager approves everything.

Source of truth: the PRD (Google Doc "NurseSync PRD - Cheich Toure and Kerrian Gordon", id
`1K_PYd9GuXEXMdO2GwT14reNq57oIvMj8hxmfbIy1_1Q`). If code and the PRD disagree, the PRD wins. **Six suggested edits are
waiting in that doc (Tools, Review suggested edits). Someone must accept them.**

## Who owns what

- **Cheich:** the Python back end: contract (`backend/app/contract`), orchestrator, decisions, case store, call-outs,
  API, harness, live agents' code, samples, tests.
- **Kerrian:** the agent prompts (`backend/app/agents/*/prompts`), the eval cards and results (`backend/evals/phase1`),
  and the approval UI (`src/ApprovalView.jsx`, `docs/approval-view-v0.md`).

## How to run it

```bash
npm install && npm run dev                     # the app at http://localhost:5173 (log in as "Acting Supervisor")
npm run build                                  # must pass before finishing any task
cd backend && ../.venv/bin/python -m pytest -q # 375 tests, no API calls, no cost
cd backend && ../.venv/bin/python -m app.serve --seed-samples   # case API at http://127.0.0.1:8000 (docs at /docs)
cd backend && ../.venv/bin/python -m app.check_connection       # one tiny live call; never prints the key
cd backend && ../.venv/bin/python -m app.run_eval case_10 --runs 3   # live evals cost money (see below)
cd backend && ../.venv/bin/python -m app.sample_cases           # regenerate docs/sample-cases (a test fails if stale)
```

The API key lives only in the repo-root `.env` (`ANTHROPIC_API_KEY=...`, never prefixed `VITE_`, never committed).
In the app, open the admin tab **Approve AI draft**. It talks to the API through the Vite proxy and falls back to the
bundled samples (clearly labeled) when the API is down.

## The flow

1. `orchestrator.run_case` freezes a snapshot, runs Demand and Availability in parallel (retry once), and **code**
   writes every row's `status` (`ok`, `needs_review`, `missing`). Malformed results are rejected whole.
2. **Any `missing` required row stops the run** before the Scheduler (`stopped_missing_input`).
3. Otherwise the Scheduler drafts and `check_rules` judges, up to 3 rounds; the Rules Checker only adds `fix_hint`s.
4. The manager approves, rejects, or changes a demand number (`decisions.py`). A demand change makes a **child case**
   and the old case becomes `out_of_date`. A late call-out (`callouts.py`) does the same with the rest of the week
   locked; code rejects any draft that changes a locked assignment.
5. Case records are JSON files in `backend/data/cases/` (gitignored). The shape is `contract/case_record.py`.

Rules worth remembering: the agents' advisory extras (`unusual`, review items) are untrusted text, cleaned in
`agent_output.py` and never decide anything. Approved leave **overrides** an agent that says "available" (the only place
code overrides an agent). Every POST to the API needs `Content-Type: application/json`.

## Where things are

| Area | Files |
| --- | --- |
| Contract (forms) | `backend/app/contract/models.py`, `case_record.py` |
| Rules (plain code) | `backend/app/harness/rules.py` (`check_rules`), `phase1.py` (the loop) |
| Orchestration | `backend/app/orchestrator.py`, `decisions.py`, `callouts.py`, `case_store.py`, `agent_output.py` |
| Live agents | `backend/app/agents/{scheduler,rules_checker,baseline,demand,availability}/` |
| API | `backend/app/api.py`, `serve.py`, docs in `docs/api-v0.md` |
| Evals | `backend/app/run_eval.py`, `harness/eval_scoring.py`, cards in `backend/evals/phase1/` |
| Test data | `backend/data/mock/`, `backend/data/scenarios/`, `docs/sample-cases/` |

## Cost (live agents, rough estimates)

Scheduler call about $0.15 to $1.20; Demand + Availability together about $0.30; a full weekly run about $0.50 to $1.50;
change demand $0.30 to $1.20 (off unless `NURSESYNC_LIVE=1`). Final run of every eval is about $5 to $10. All unit tests
are free.

## Results so far

Phase 1 evals 1, 4, 5, 6, 7, 13, 14 pass (3 runs each). Cases 2 and 3 pass but are **ties** with the single-agent baseline
(case 3: both handle missing data honestly; the team stops, the baseline builds a partial draft). Case 10 (late
call-out) passed three live runs (Kerrian, 2026-10-28): replaced the called-out nurse in 1 round each, 0 violations, no
locked changes. See `backend/evals/phase1/RESULTS.md`.

## What is left

- Final full-suite vs baseline: **done 2026-10-28** (see `backend/evals/phase1/RESULTS.md` “Final suite”). Case 10 needed a re-run after transient connection errors.
- API: start a weekly run and apply a call-out through the API (both cost money; need guards and a spend cap); choose
  roster and rules by the case's unit.
- Real Shift Board data in place of mock files; Availability batching for units of about 50 nurses (output is cut off
  and rows become `missing`, never guessed); wire `get_callouts` into the Availability agent for weekly runs.
- A call-out after a case is approved (the PRD only covers one still waiting); a login.
- Kerrian leftovers from 2026-10-28: Agent notes for `unusual`, case 10 card + ×3 RESULTS, and contract sign-off notes
  on `models.py` / `case_record.py` (shipped on her follow-up PR).
- Housekeeping: PRD suggested edits accepted (2026-10-28); PRD PDF re-exported into the repo root. `cheich/agent-prompts-v0`
  is an old unmerged branch.

## How we work

- `main` needs 1 approving review. The author of a PR cannot approve it, so Cheich uses the admin bypass on his own
  PRs; Cheich approves Kerrian's PRs. Never merge without an explicit yes.
- Commit messages are clear and descriptive. Do not commit `.env`, `NurseSync.zip`, the `.pptx` or the `.jpg`.
- Keep answers short, plain language, bullets. Do not claim the app is secure.
- Do not edit `check_rules`, `models.py`, `decisions.py`, the orchestrator or the API from the Kerrian side without
  asking Cheich first.
