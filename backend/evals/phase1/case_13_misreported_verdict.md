# Eval case 13 — Misreported verdict

**Phase:** 1  
**Depends on:** Phase 1 harness (code) + Rules Checker agent + Scheduler  
**Runs:** Once is enough for the **code** mismatch path; if the Rules Checker is a live model, run the agent step 3 times and require the harness behavior every time.

## Purpose

Prove the harness trusts **`check_rules`**, not the Rules Checker agent, when the agent drops a violation.

## Input (scenario / stand-in)

1. A draft that `check_rules` scores with **exactly 2 hard violations** (any two distinct hard rows; coverage holes from removing assignments are fine — see harness tests).
2. A Rules Checker that returns only **1** of those violations (drops one), with or without `fix_hint`s on what it returns.

Phase 1 can use the existing scripted stand-in pattern (`DroppingRulesChecker`-style) until a live agent is wired. The expected harness behavior is the same.

## Expected output (written before any run)

1. `check_rules` finds **2** hard violations (code list length 2).
2. Rules Checker agent returns a list that does **not** match the code list (only 1 hard row, or different keys).
3. Harness detects the mismatch (`agent_list_matched` false / equivalent log note).
4. Harness **keeps the code’s list of 2** as the violations sent onward.
5. Scheduler’s next fix round (if any) receives **both** violations (same `rule` + `nurse_id` + `date` + `shift` keys as the code list). Hints may be missing on a dropped row; that is acceptable. The count and identity of hard violations must be the code’s.
6. The run is **never** treated as passing solely because the agent reported fewer violations.
7. No draft is labeled passing while those 2 hard violations remain unfixed.

## Pass / fail

- **Pass:** Mismatch detected; code’s 2 violations are what the Scheduler sees; agent cannot shrink the authoritative list.
- **Fail:** Harness adopts the agent’s 1-violation list; Scheduler only hears about one; or the draft is called passing while code still has 2 hard violations.

## Notes

- PRD says “orchestrator”; in Phase 1 that job is the **harness** in `backend/app/harness/phase1.py`.
- Soft tradeoffs are irrelevant here; this case is about hard violation list authority.
