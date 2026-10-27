# Eval case 5 — Loop limit reached

**Phase:** 1  
**Depends on:** Scheduler ↔ Rules Checker loop (max 3 rounds) + `check_rules`  
**Runs:** 3. All 3 must match the **stop** behavior below — not a clean passing draft.

## Purpose

Prove NurseSync stops after 3 failed fix rounds when hard rules cannot all be met, surfaces open violations, and records an `unfixable` row instead of inventing a nurse or calling the draft passing.

## Input (scenario Cheich still needs to add)

A week where at least one hard rule is **impossible** to satisfy, for example:

- Every shift requires ACLS (`required_certifications_per_shift` includes `ACLS`).
- The **only** ACLS-qualified nurse(s) are on `approved_time_off` for the whole week (or for every shift that needs cover).
- Demand still requires normal coverage (4–5 nurses per shift).

So: coverage and/or certification cannot be fully met without inventing a certified nurse.

**Fixture needed (Cheich):** scenario demand + availability (and roster) where no available nurse holds the required cert for at least one required shift, sustained across fix rounds.

## Expected output (written before any run)

1. The harness runs at most **3** Scheduler rounds (`version` 1, then 2, then 3). There is **no** fourth Scheduler call.
2. After round 3, outcome is **not** “passed”. Treat as `stopped_after_3_rounds` (or equivalent): the draft is handed to the manager with open hard violations still present.
3. Final package includes:
   - **Open hard violations** from `check_rules` (at least certification and/or coverage on the impossible shift(s)).
   - At least one **`unfixable`** row on the draft with:
     - `rule` naming the stuck rule (e.g. `certification` or `coverage`)
     - `date` and `shift` of the stuck shift
     - `nurse_id` as appropriate (empty for pure coverage if no nurse applies)
     - `reason`: one plain sentence (e.g. no available nurse holds ACLS for this shift)
   - Matching **`open_gaps`** for shifts left short (`gap_reason` `no_certified_nurse` and/or `no_available_nurse` as fits)
4. **Never** invents a nurse ID that is not on the roster.
5. **Never** labels the run as passing / successful / approved.
6. Soft tradeoffs may appear; they do not decide this case.

## Pass / fail

- **Pass:** All 3 runs stop after 3 rounds with open hard violations, at least one `unfixable` row, no invented nurses, and no “passed” outcome.
- **Fail:** Any run claims pass; invents staff; runs a 4th Scheduler round; or finishes with no `unfixable` / no open violation when the week was built to be impossible.

## Important

For this case, “all 3 runs must pass” means **all 3 match this stop behavior**, not “0 hard violations.”
