"""A run that fails after its first save must not leave a case stuck in 'building'."""

import json
from pathlib import Path

import pytest

from app.callouts import run_call_out
from app.case_store import CaseStore
from app.contract.case_record import DemandChange
from app.contract.models import Callout, Draft
from app.decisions import change_demand
from app.harness.phase1 import DEFAULT_DATA, load_inputs
from app.harness.stand_ins import HintingRulesChecker, ScriptedAvailabilityAgent, ScriptedDemandAgent, ScriptedScheduler
from app.orchestrator import run_case, snapshot_id_for

REFERENCE = Draft(**json.loads((Path(DEFAULT_DATA) / "reference_draft.json").read_text()))


def raw(name):
    rows = json.loads((Path(DEFAULT_DATA) / name).read_text())
    return [{k: v for k, v in r.items() if k not in ("status", "note")} for r in rows]


def waiting(store, case_id="case-1"):
    inputs = load_inputs()
    return run_case(ScriptedDemandAgent(raw("demand.json")), ScriptedAvailabilityAgent(raw("availability.json")),
                    ScriptedScheduler([REFERENCE], case_id=case_id, snapshot_id=snapshot_id_for(case_id)),
                    HintingRulesChecker(), inputs.roster, inputs.rules, "7W", "2026-11-02", case_id, store=store)


def broken(case_id, snapshot_id):
    raise RuntimeError("no API key")


def test_change_demand_with_a_scheduler_that_cannot_start_saves_nothing(tmp_path):
    store = CaseStore(tmp_path)
    old = waiting(store)
    inputs = load_inputs()
    with pytest.raises(RuntimeError):
        change_demand(old, [DemandChange(unit="7W", date="2026-11-02", shift="day", nurses_needed=5)], "case-2",
                      broken, HintingRulesChecker(), inputs.roster, inputs.rules, store=store)
    assert store.list_ids() == ["case-1"] and store.load("case-1").status == "waiting_approval"


def test_a_call_out_with_a_scheduler_that_cannot_start_saves_nothing(tmp_path):
    store = CaseStore(tmp_path)
    old = waiting(store)
    inputs = load_inputs()
    call = Callout(nurse_id="N006", date="2026-11-04", shift="day", reported_at="2026-11-03T22:15:00")
    with pytest.raises(RuntimeError):
        run_call_out(old, [call], "case-2", broken, HintingRulesChecker(), inputs.roster, inputs.rules, store=store)
    assert store.list_ids() == ["case-1"] and store.load("case-1").status == "waiting_approval"


def test_run_case_cleans_up_when_the_final_save_fails(tmp_path, monkeypatch):
    store = CaseStore(tmp_path)
    real_save = CaseStore.save

    def flaky(self, record):
        if record.status != "building":
            raise OSError("disk full")
        return real_save(self, record)

    monkeypatch.setattr(CaseStore, "save", flaky)
    with pytest.raises(OSError):
        waiting(store)
    assert store.list_ids() == []  # the building record was removed, so the id can be used again
