"""The sample case records in docs/sample-cases are real, current CaseRecords."""

import pytest

from app.contract.case_record import CaseRecord
from app.sample_cases import OUT_DIR, build, render


def test_every_sample_file_is_a_valid_case_record_and_up_to_date():
    for name, case in build().items():
        path = OUT_DIR / f"{name}.json"
        assert path.exists(), f"{name}.json is missing: run python -m app.sample_cases"
        assert path.read_text() == render(case), f"{name}.json is out of date: run python -m app.sample_cases"
        assert CaseRecord.model_validate_json(path.read_text()) == case


def test_the_samples_cover_every_status_and_the_stopped_outcome():
    cases = build()
    assert {c.status for c in cases.values()} == {"waiting_approval", "approved", "rejected", "out_of_date"}
    assert {c.outcome for c in cases.values()} == {"passed", "stopped_after_3_rounds", "stopped_missing_input", "rejected"}
    assert {c.trigger for c in cases.values()} == {"weekly", "call_out"}


def test_the_readme_lists_every_sample_file():
    readme = (OUT_DIR / "README.md").read_text()
    missing = [name for name in build() if f"`{name}.json`" not in readme]
    assert missing == []


def test_the_samples_hold_up_the_behavior_the_readme_describes():
    cases = build()
    stopped = cases["stopped_missing_input"]
    assert stopped.final_draft is None and stopped.stop_reason and len(stopped.needs_manual_review) == 2
    assert [r.status for r in cases["needs_review"].demand_result.rows].count("needs_review") == 3
    assert any(n.id == "N999" for n in cases["needs_review"].needs_manual_review)
    assert cases["demand_change_old"].newer_case_id == cases["demand_change_child"].case_id
    assert cases["demand_change_child"].parent_case_id == cases["demand_change_old"].case_id
    assert cases["call_out_child"].trigger == "call_out" and cases["call_out_old"].status == "out_of_date"
    assert cases["approved_with_open_issues"].decision_details.acknowledged_open_issues is True
