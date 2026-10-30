# NurseSync demo script (about 5 minutes)

For the live demo and the Loom recording. Mock data only. There is no login and the app is not secure; say so once, early.

## Before you start (10 minutes ahead)

- [ ] Terminal 1: `cd backend && NURSESYNC_LIVE=1 ../.venv/bin/python -m app.serve --seed-samples` (live agents on). Check `http://127.0.0.1:8000/api/health` says `live_agents: true`.
- [ ] Terminal 2: `npm run dev`, then open `http://localhost:5173` in Chrome.
- [ ] Fuller demo data (optional): on the sign-in screen click **Load sample schedule** for 24 nurses and a full week (Nov 2 to 8). It replaces what is saved in that browser; **Clear names** resets it.
- [ ] Clean demo data for the short script below: open the Console (Cmd+Option+J), paste the snippet at the bottom, press Enter, reload.
- [ ] Open the AI draft once so the ready case `run-7W-2026-11-02-134649-8c28` is selected.
- [ ] Paid runs left today: check "N of 4 paid runs left" on the AI draft screen. A live run needs 1.
- [ ] Close every other tab and app. Turn on Do Not Disturb. Hide bookmarks. Never show `.env` or the API key.
- [ ] Browser window about 1280 px wide, zoom 100%. For a phone shot, use the Chrome device toolbar at 375 px.

## The script

1. **The problem (30 s).** Nurse managers build schedules by hand; rules like rest time get missed, and a call-out sends everyone back to the spreadsheet.
2. **Nurse side (60 s).** Pick **Ana**. On Home, show next shift and week. Mark availability: tap a day, choose Not available, pick a reason. Request a day off, then show the **Pending** chip.
3. **Manager side (45 s).** Switch to **Acting Supervisor**. Home shows "N things need you". Open Requests, then Leave, and approve Ana's day off. Switch back to Ana: the chip now says **Approved**.
4. **Build Schedule (45 s).** Try to add a second shift for a nurse on a day she already works: it is refused, one shift per nurse per day. Tap a nurse to show her whole month.
5. **The AI draft (90 s).** Open the ready case. Show **How the agents decided**: the recommendation, then each agent's step and the Scheduler's reasoning, with the rules check labeled plain code. Click a shift in the grid to show who is working, by name and ID.
6. **Live run (optional, about 2 minutes of waiting).** Start a weekly run at the start of step 5 and keep talking; confirm in the dialog. If it is not done when you reach the end, open the ready case instead. A run costs about $0.50 to $1.50.
7. **Why you can trust it (30 s).** Code decides if a schedule is safe, not the AI. The manager approves. Missing data stays an open gap and nothing is guessed. 403 tests, evals against a single-agent baseline, and an honest tie on the easy weeks.
8. **Limits (15 s).** Mock data, no login, per-device data, shift swaps are one-way. Next: a real Shift Board and a login.

## If something goes wrong

- **Live run fails or is slow:** say it runs in the background and open the ready case `run-7W-2026-11-02-134649-8c28`.
- **API is down:** the AI draft falls back to bundled samples, clearly labeled. Click Reconnect API after restarting the server.
- **Report call-out** is a paid, slow action. Show the finished example instead: open `demo-call-out-2`.
- **Confirm dialog:** Cancel is focused first, so Enter never spends money by accident.

## Loom tips

- Record the browser tab, not the full screen. 1080p, mic check first.
- Do one take of each section if you want; Loom lets you trim the start and end.
- Keep it under 5 minutes. Put the repo link in the Loom description: https://github.com/CheichT/nursesync

## Clean demo data (paste in the browser Console)

```js
const now = Date.now();
const names = ['Ana', 'James', 'Sasha', 'Priya', 'Marcus'];
const roster = [{ id: 'admin-1', name: 'Acting Supervisor', isAdmin: true }, ...names.map((n, i) => ({ id: 'n' + i, name: n, isAdmin: false }))];
const sh = (id, date, kind) => ({ id: id + date + kind, employeeId: id, date, start: kind === 'day' ? '07:00' : '19:00', end: kind === 'day' ? '19:00' : '07:00', status: 'scheduled' });
const plan = { n0: [['2026-11-02','day'],['2026-11-04','day'],['2026-11-06','night'],['2026-11-09','day'],['2026-11-11','night'],['2026-11-13','day'],['2026-11-16','day'],['2026-11-18','night'],['2026-11-20','day']], n1: [['2026-11-03','night'],['2026-11-05','day']], n2: [['2026-11-02','night']] };
const shifts = Object.entries(plan).flatMap(([id, l]) => l.map(([d, k]) => sh(id, d, k)));
const availability = { n0: { '2026-11-24': { status: 'unavailable', reason: 'Appointment', note: '' }, '2026-11-25': { status: 'unavailable', reason: 'Appointment', note: '' } } };
const leave = [{ id: 'l1', employeeId: 'n0', type: 'vacation', start: '2026-11-26', end: '2026-11-28', note: '', status: 'approved', createdAt: now }];
localStorage.setItem('nursesync:scheduler-data', JSON.stringify({ roster, availability, shifts, swaps: [], leave, notifications: [] }));
location.reload();
```
