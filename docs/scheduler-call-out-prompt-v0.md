# Scheduler prompt: call-out section (PROPOSAL for Kerrian, v0)

> **Owner: Kerrian Gordon** (prompts). Drafted by Cheich's side so the code and the prompt agree. Nothing here is
> in `scheduler_v0.md` yet. Edit freely; the message fields below are what the code sends today.
> Source of truth: the PRD, "Late call-outs" and the Scheduler prompt's "For a call-out (phase 3)" paragraph.

## When it applies

Only when the user message has `"mode": "call_out"`. Otherwise ignore this whole section.

## Extra fields in the message (call-out runs only)

- `affected_shifts`: list of `{date, shift}`. These are the only shifts you may change.
- `locked_assignments`: the rest of the week from the earlier draft. **Do not change, remove or add any assignment
  outside `affected_shifts`.** Copy them into your draft exactly as given (same unit, date, shift, nurse_id,
  shift_start, shift_end).
- `earlier_assignments`: who the earlier draft had on the affected shifts, except the nurse who called out. Keep
  these nurses where the rules allow, so fewer people's plans change.
- `availability`: already updated. The nurse who called out has `available: false` and `reason: "call_out"` for
  that shift. Never schedule them there.

## What to do

1. Build the full week: every locked assignment unchanged, plus assignments for each affected shift.
2. Put each replacement you add into `suggestions`: `{date, shift, nurse_id, reason}`. One plain sentence of
   reasoning. A suggestion must name a nurse on the roster and an affected shift.
3. If no nurse can cover an affected shift, leave it short, add an `open_gaps` row, and add an `unfixable` row if
   a rule blocks it. Never invent a nurse. The manager decides what to do with a gap.
4. On fix rounds, change only the affected shifts. The same fix order applies (coverage and availability first).
5. `check_rules` checks the whole week. A replacement's other shifts affect rest time and weekly hours.

## What code enforces (so you cannot break it by accident)

- A draft that changes any locked assignment fails the round. The error names the first change.
- A suggestion for a nurse not on the roster, or for a shift that is not affected, fails the round.
- `check_rules` decides pass or fail. Your notes and suggestions never change that.
