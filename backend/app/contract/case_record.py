"""DRAFT: both owners must review before use.

The case record and the snapshot: the Phase 2 forms. Owner: Cheich. Kerrian's approval view reads
the case record (see docs/approval-view-v0.md).

Reuses the Phase 1 forms (rows, Draft, Violation) unchanged. If this file and the PRD disagree,
the PRD wins.
"""

from typing import List, Literal, Optional

from pydantic import Field

from app.contract.models import (
    AvailabilityRow,
    DemandRow,
    Day,
    Draft,
    Form,
    NeedsManualReview,
    Nurse,
    RulesConfig,
    SoftTradeoff,
    Unfixable,
    Violation,
)

CaseState = Literal["running", "awaiting_approval", "approved", "rejected", "out_of_date", "failed"]
Outcome = Literal["passed", "stopped_after_3_rounds"]
DecisionAction = Literal["approve", "change_demand", "reject"]


class Snapshot(Form):
    """Everything one run reads, frozen at the start. Every agent and check_rules use this same copy."""

    snapshot_id: str
    unit: str
    week_start: Day
    created_at: str  # ISO date and time
    roster: List[Nurse]
    rules: RulesConfig


class StatusCounts(Form):
    ok: int = 0
    needs_review: int = 0
    missing: int = 0


class DemandResult(Form):
    rows: List[DemandRow]
    counts: StatusCounts


class AvailabilityResult(Form):
    rows: List[AvailabilityRow]
    counts: StatusCounts


class RoundSummary(Form):
    version: int
    error: str = ""
    hard_violations: int = 0
    agent_list_matched: Optional[bool] = None
    note: str = ""


class DemandChange(Form):
    unit: str
    date: Day
    shift: Literal["day", "night"]
    nurses_needed: int = Field(ge=0)


class ManagerDecision(Form):
    action: DecisionAction
    decided_at: str  # ISO date and time
    demand_changes: List[DemandChange] = Field(default_factory=list)
    acknowledged_open_issues: bool = False  # the manager approved a draft that still had open issues
    new_case_id: Optional[str] = None  # change_demand: the new run this decision started


class CaseRecord(Form):
    """One run, start to finish. `final_draft` is empty when no round produced a valid draft."""

    case_id: str
    parent_case_id: Optional[str] = None
    snapshot_id: str
    unit: str
    week_start: Day
    created_at: str
    state: CaseState
    outcome: Optional[Outcome] = None
    demand_result: DemandResult
    availability_result: AvailabilityResult
    rounds: List[RoundSummary] = Field(default_factory=list)
    final_draft: Optional[Draft] = None
    open_violations: List[Violation] = Field(default_factory=list)
    soft_tradeoffs: List[SoftTradeoff] = Field(default_factory=list)
    unfixable: List[Unfixable] = Field(default_factory=list)
    needs_manual_review: List[NeedsManualReview] = Field(default_factory=list)
    newer_case_id: Optional[str] = None  # set when state is out_of_date: the run that replaced this one
    manager_decision: Optional[ManagerDecision] = None
