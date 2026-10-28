# Scheduler prompt: call-out section

> **Owner: Kerrian Gordon.** Landed in `backend/app/agents/scheduler/prompts/scheduler_v0.md` under **Call-out runs**.
> This file is a pointer only. Edit the Scheduler prompt, not a second copy here.
> Source of truth: the PRD (“Late call-outs” and Scheduler call-out behavior) and the live message fields Cheich’s wrapper sends (`mode`, `affected_shifts`, `locked_assignments`, `earlier_assignments`).

## Summary

When `"mode": "call_out"`:

- Change only `affected_shifts`; copy `locked_assignments` unchanged.
- Prefer keeping `earlier_assignments` on affected shifts where rules allow.
- Put replacements in `suggestions`; never invent a nurse; use `open_gaps` / `unfixable` when uncovered.
- `check_rules` still checks the whole week.
