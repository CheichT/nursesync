# Eval case 14 — Lost or stale verdict

**Phase:** 1  
**Depends on:** Phase 1 harness + `check_rules` result handling  
**Runs:** Once per sub-case (code paths are deterministic). Document all three sub-cases below.

## Purpose

Prove a missing, unparseable, or stale `check_rules` result is a **failure**, never a pass, and the manager is told; the draft is never called passing.

## Input (three sub-cases)

Use a normal draft/`check_rules` setup, then break the verdict in one of these ways:

| Sub-case | What goes wrong |
| --- | --- |
| **A — Missing** | No `check_rules` result is returned (tool/harness gets `None` / empty / raised “unavailable”). |
| **B — Unparseable** | Result body cannot parse into the check-result form (garbage JSON or wrong shape). |
| **C — Stale** | Result is labeled with an older `case_id` and/or `version` than the draft just checked (e.g. draft `version` 2, result says `version` 1). |

Phase 1 harness already rejects drafts with the wrong `case_id` / `snapshot_id` / `version` and treats agent failures as failed rounds. This card locks the eval expectation for a bad **check** verdict specifically; fixtures may simulate a bad check result or a draft/check pair that the harness must refuse to call passing.

## Expected output (written before any run)

For **each** sub-case A, B, and C:

1. Outcome is **failure** for that check round (not pass).
2. The draft is **never** labeled passing / approved / successful based on that verdict.
3. The harness **stops** escalating as if the rules were clean — it does not advance a “passed” Phase 1 result.
4. A clear message is available for the manager (log/report text) that the check result was missing, unparseable, or stale/mismatched.
5. No invented nurses and no silent ignore of the bad verdict.

If the harness retries within the same round, the final case outcome still must not be `passed` while only a bad verdict was obtained.

## Pass / fail

- **Pass:** All three sub-cases fail closed; manager-facing note present; no `passed` outcome from a bad verdict.
- **Fail:** Any sub-case treats missing/unparseable/stale as pass; or continues the loop as though hard violations were zero.

## Notes

- PRD wording says “orchestrator”; Phase 1 owner of this behavior is the **harness**.
- Distinct from case 13: here the check result itself is wrong or absent, not the Rules Checker hint list.
- Soft tradeoffs do not apply.
