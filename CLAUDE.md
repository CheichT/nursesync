# NurseSync

Employee scheduling app (React + Vite). Employees mark availability, admin builds the schedule, conflicts trigger notifications.

## Run
- `npm install`
- `npm run dev` (local server)
- `npm run build` (must pass before finishing any task)

## Code map
- `src/App.jsx` — whole app (single file for now): login, employee tabs, admin tabs, styles in `GLOBAL_CSS`
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
- Icon-only buttons (pencil, theme toggle, calendar arrows) lack aria-labels
- Modals don't trap focus or close on Esc
- Calendar days have no accessible names
- Schedule Builder still uses a plain date input
- Swap is one-way handoff, not a two-way trade
