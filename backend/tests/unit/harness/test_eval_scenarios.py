"""The planted scenarios for eval cases 4, 5 and 6 give exactly the violations their eval cards expect."""

from app.contract.models import Draft
from app.harness.phase1 import MAX_ROUNDS, load_scenario, run_phase1
from app.harness.rules import check_rules
from app.harness.stand_ins import HintingRulesChecker, ScriptedScheduler


def _hard(inputs, draft):
    result = check_rules(draft, inputs.demand, inputs.availability, inputs.roster, inputs.rules)
    return result, [(v.rule, v.nurse_id, v.date, v.shift) for v in result.violations if v.severity == "hard"]


def test_case_4_plants_one_rest_violation():
    inputs, planted = load_scenario("case_04")
    result, hard = _hard(inputs, Draft(**planted))
    assert not result.passed
    assert hard == [("rest_time", "N002", "2026-11-03", "day")]
    clash = [v for v in result.violations if v.rule == "rest_time"][0]
    assert "0" in clash.found and clash.limit.startswith("10")


def test_case_6_plants_a_certification_miss_and_overtime():
    inputs, planted = load_scenario("case_06")
    result, hard = _hard(inputs, Draft(**planted))
    assert not result.passed
    assert sorted(hard) == [("certification", "", "2026-11-03", "night"), ("weekly_hours", "N001", "2026-11-07", "night")]
    overtime = [v for v in result.violations if v.rule == "weekly_hours"][0]
    assert overtime.found.startswith("48") and overtime.limit.startswith("40")


def test_case_5_has_no_acls_nurse_free_on_the_stuck_shift():
    inputs, planted = load_scenario("case_05")
    assert planted is None
    acls = {n.nurse_id for n in inputs.roster if "ACLS" in n.certifications}
    free = {r.nurse_id for r in inputs.availability
            if r.date == "2026-11-05" and r.shift == "night" and r.available} & acls
    assert free == set()


def test_case_5_stops_after_three_rounds_when_the_scheduler_cannot_fix_it():
    inputs, _ = load_scenario("case_05")
    good = __import__("json").loads(
        (__import__("pathlib").Path(__file__).resolve().parents[3] / "data" / "mock" / "reference_draft.json").read_text())
    # The reference draft puts ACLS nurses on the stuck shift, so it breaks availability and the loop cannot pass.
    scheduler = ScriptedScheduler([good, good, good], case_id="case-1")
    result = run_phase1(scheduler, HintingRulesChecker(), inputs, case_id="case-1")
    assert result.outcome == "stopped_after_3_rounds"
    assert result.rounds_used == MAX_ROUNDS
    assert result.final_draft is not None  # real drafts were checked, not rejected
    assert any(v.rule == "availability" for v in result.open_violations if v.severity == "hard")


def test_unknown_scenario_is_an_error():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_scenario("case_99")
