"""Sample case records for the approval UI. Owner: Cheich. Made-up data, built by the real code (no API calls).

Every file in docs/sample-cases/ is a real CaseRecord, so the UI can be built against the true shape before there is
an API. A test regenerates them and fails if the committed files are out of date.

Regenerate:  cd backend && ../.venv/bin/python -m app.sample_cases
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.callouts import run_call_out
from app.contract.case_record import CaseRecord, DemandChange
from app.contract.models import Callout, Draft, OpenGap, Unfixable
from app.decisions import approve, change_demand, reject
from app.harness.phase1 import DEFAULT_DATA, load_inputs
from app.harness.stand_ins import HintingRulesChecker, ScriptedAvailabilityAgent, ScriptedDemandAgent, ScriptedScheduler
from app.orchestrator import run_case, snapshot_id_for

OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "sample-cases"
WEEK = "2026-11-02"
NOW = lambda: datetime(2026, 11, 1, 9, 0, 0)  # a fixed clock, so regenerating gives identical files
REFERENCE = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))


def _raw(name: str) -> List[Dict[str, Any]]:
    rows = json.loads((Path(DEFAULT_DATA) / name).read_text())
    return [{k: v for k, v in r.items() if k not in ("status", "note")} for r in rows]


def _scheduler(drafts: List[Draft], case_id: str) -> ScriptedScheduler:
    return ScriptedScheduler(drafts, case_id=case_id, snapshot_id=snapshot_id_for(case_id))


def _run(case_id: str, demand: Optional[List[dict]] = None, availability: Optional[List[dict]] = None,
         drafts: Optional[List[Draft]] = None) -> CaseRecord:
    inputs = load_inputs()
    return run_case(ScriptedDemandAgent(demand if demand is not None else _raw("demand.json")),
                    ScriptedAvailabilityAgent(availability if availability is not None else _raw("availability.json")),
                    _scheduler(drafts or [REFERENCE], case_id), HintingRulesChecker(), inputs.roster, inputs.rules,
                    "7W", WEEK, case_id, now=NOW)


def _swap(draft: Draft, date: str, shift: str, old: str, new: str) -> Draft:
    return draft.model_copy(update={"assignments": [
        a.model_copy(update={"nurse_id": new}) if (a.nurse_id, a.date, a.shift) == (old, date, shift) else a
        for a in draft.assignments]})


def build() -> Dict[str, CaseRecord]:
    inputs = load_inputs()
    cases: Dict[str, CaseRecord] = {}

    cases["passed"] = _run("demo-passed")

    # a week with things for the manager to look at first, but a draft that still passes
    demand = _raw("demand.json")
    demand[0]["nurses_needed"] = 4  # 24 patients at 5 per nurse needs 5: ratio mismatch
    demand[5].update(patient_count=5, nurses_needed=1)  # Wed night: far below the night-shift median
    demand[9]["flag"] = "Census may rise on Friday night."  # the agent flagged doubt
    availability = _raw("availability.json") + [
        {"nurse_id": "N999", "date": WEEK, "shift": "day", "available": True, "reason": "none"}]  # not on the roster
    cases["needs_review"] = _run("demo-needs-review", demand, availability)

    # three rounds, and the draft still breaks rules: the best draft with its open issues
    gap_draft = REFERENCE.model_copy(update={
        "assignments": [a for a in REFERENCE.assignments if (a.nurse_id, a.date, a.shift) != ("N006", "2026-11-04", "day")],
        "open_gaps": [OpenGap(unit="7W", date="2026-11-04", shift="day", nurses_needed=5, nurses_assigned=4,
                              gap_reason="no_available_nurse")],
        "unfixable": [Unfixable(rule="coverage", date="2026-11-04", shift="day",
                                reason="No other nurse is available to cover this shift without breaking a rule.")],
        "notes": ["N006 is unavailable on Wednesday day and no one else could take the shift within the rules."]})
    cases["open_issues"] = _run("demo-open-issues", drafts=[gap_draft])

    # a required input is missing, so the run stops before the Scheduler
    stuck_demand = _raw("demand.json")
    stuck_demand[3].update(patient_count=None, nurses_needed=None, flag="get_demand returned an error for this shift")
    stuck = _run("demo-stopped-missing-input", stuck_demand, [r for r in _raw("availability.json") if r["nurse_id"] != "N012"])
    cases["stopped_missing_input"] = stuck

    # manager decisions
    cases["approved"] = approve(cases["passed"], now=NOW)
    cases["approved_with_open_issues"] = approve(cases["open_issues"], acknowledge_open_issues=True, now=NOW)
    cases["rejected"] = reject(cases["stopped_missing_input"], now=NOW)

    # change demand: a demand row is missing, the manager fills it in, a child case starts
    only_demand_missing = _run("demo-demand-change", stuck_demand)  # availability complete, one demand row missing
    cases["demand_change_before"] = only_demand_missing  # the same case before the manager acts (the API can change it)
    old, child = change_demand(
        only_demand_missing, [DemandChange(unit="7W", date="2026-11-03", shift="night", nurses_needed=4)],
        "demo-demand-change-2", lambda c, s: _scheduler([REFERENCE], c), HintingRulesChecker(), inputs.roster,
        inputs.rules, now=NOW)
    cases["demand_change_old"], cases["demand_change_child"] = old, child

    # a late call-out: the waiting case becomes out_of_date and a call_out child case starts
    call = Callout(nurse_id="N006", date="2026-11-04", shift="day", reported_at="2026-11-03T22:15:00")
    old, child = run_call_out(
        _run("demo-call-out"), [call], "demo-call-out-2",
        lambda c, s: _scheduler([_swap(REFERENCE, "2026-11-04", "day", "N006", "N002")], c),
        HintingRulesChecker(), inputs.roster, inputs.rules, now=NOW)
    cases["call_out_old"], cases["call_out_child"] = old, child
    return cases


def render(case: CaseRecord) -> str:
    return case.model_dump_json() + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, case in build().items():
        (OUT_DIR / f"{name}.json").write_text(render(case))
        print(f"{name}.json  {case.status:17} {case.outcome or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
