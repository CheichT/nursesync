# NurseSync

Employee scheduling app (React + Vite). Employees mark availability, admin builds the schedule, conflicts trigger notifications.

## Run
- `npm install`
- `npm run dev` (local server)
- `npm run build` (must pass before finishing any task)

## Code map
- `src/App.jsx` — whole app (single file for now): login, employee tabs, admin tabs, styles in `GLOBAL_CSS`
- `src/themes.js` (6 palettes, light and dark), `src/AppearanceMenu.jsx` (Choose your look), `src/NurseHome.jsx`, `src/ManagerHome.jsx` (home screens). `npm run build` also checks palette contrast (4.5 to 1).
- `src/storage.js` — localStorage stand-in for `window.storage`. Per-device only, not shared between users. Replace with a real backend later.
- Data shape (see `emptyData()` in App.jsx): roster, availability, shifts, swaps, leave, notifications

## Rules
- Keep responses short, plain language, bullets.
- Admin approval stays required for swaps and leave.
- No real auth yet (pick-a-name login). Don't claim it is secure.
- FMLA is a request flow only. No legal logic.
- Commit messages: clear and descriptive.

## Testing checklist (run after every change)
- [ ] `npm run build` passes
- [ ] Employee flow: mark availability, view My Week, request swap, request leave
- [ ] Admin flow: add shift, conflict flagged, approve/deny swap and leave, Daily Breakdown
- [ ] Notifications show up for the right person
- [ ] Light and dark mode both readable
- [ ] Phone width (~380px): nothing overflows, buttons tappable
- [ ] Accessibility: every control reachable and usable by keyboard (Tab, Enter, Esc closes modals)
- [ ] Accessibility: buttons and inputs have clear labels (icon-only buttons need aria-label), focus is visible
- [ ] Accessibility: headings in logical order, status not shown by color alone, text contrast OK

## Known gaps (good first tasks)
- Modals close on Esc but don't trap focus
- Schedule Builder still uses a plain date input
- Swap is one-way handoff, not a two-way trade

## Multi-agent plan (source of truth: the PRD PDF / Google Doc)
NurseSync = the scheduling app above + 4 AI agents that draft the weekly nurse schedule. The manager reviews and approves.

### Core principle
- Code decides if a schedule is safe, not the AI. `check_rules` is plain code.

### Roles
- Orchestrator: plain code, not an AI agent. Runs the flow, writes status fields, enforces the snapshot rule.
- Demand agent: needed staffing per shift. Runs in parallel with Availability.
- Availability agent: who can work when, including approved time off.
- Scheduler agent: builds the draft, then fixes violations. Does NOT call `check_rules`.
- Rules Checker agent: calls `check_rules` and passes violations back to the Scheduler.

### Flow
1. Demand and Availability run in parallel.
2. Scheduler drafts the week.
3. Scheduler and Rules Checker loop, max 3 rounds.
4. Human manager approves. Nothing is final without approval.

### Handoff rules
- Every run uses one snapshot with a `snapshot_id`. All agents and `check_rules` read that same snapshot.
- Demand and Availability rows have `status`: `ok`, `needs_review` or `missing`. Only orchestrator code writes status.
- `missing`: leave the shift or nurse unscheduled, list it as an open gap, never guess.
- `needs_review`: use the value and add a flag to the reasoning notes.
- `check_rules` reads only `assignments` + the snapshot.
- Violation fields: rule (`rest_time`, `weekly_hours`, `consecutive_shifts`, `certification`, `availability`, `coverage`), severity (`hard`/`soft`), nurse_id (empty for coverage), date, shift, found, limit, `fix_hint`.
- Fix order for hard violations: coverage and availability first, then the rest by date and then shift. Ignore soft tradeoffs while fixing.
- Unfixable violation: add an unfixable row (rule, nurse_id, date, shift, one plain sentence why) and leave the shift as an open gap. Never invent a nurse.

### Tools
`get_demand`, `get_availability`, `get_roster`, `check_rules`, `get_callouts`

### Build order
- Phase 1: synthetic data, handoff formats, `check_rules` + unit tests.
- Then: Scheduler and Rules Checker loop, then Demand and Availability, then the manager approval UI.
- Evals: 12 cases plus a single-agent baseline to compare against.

### API key
- Only needed once agents actually run (Phase 1 Scheduler/Rules Checker loop).
- Put it in `.env` as `ANTHROPIC_API_KEY`. Never prefix with `VITE_` (it would ship to the browser). Never commit `.env`.

### Project hygiene
- Owners: Cheich Toure and Kerrian Gordon. Keep NurseSync separate from other projects.
- Commit messages: clear and descriptive.
- Don't touch `NurseSync.zip` (untracked, not for commit).
