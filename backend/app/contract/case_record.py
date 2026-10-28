"""Phase 2 case record and snapshot.

Owner: Cheich. Kerrian's approval view reads this shape (see docs/approval-view-v0.md).
**Kerrian Gordon signed off 2026-10-28** on the fields the approval UI and evals consume
(`status`, `start_time`, `outcome`, `final_draft`, review lists, `unusual`, decision fields).
No form fields were changed in that sign-off.

Reuses the Phase 1 forms (rows, Draft, Violation) unchanged. If this file and the PRD disagree,
the PRD wins.
"""

from typing import List, Literal, Optional

from pydantic import Field

from app.contract.models import (
    AvailabilityRow,
    Callout,
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

# Names follow the PRD ("Case record"). If this file and the PRD disagree, the PRD wins.
CaseStatus = Literal["building", "waiting_approval", "approved", "rejected", "out_of_date"]
Outcome = Literal["passed", "stopped_after_3_rounds", "stopped_missing_input", "rejected"]
Trigger = Literal["weekly", "call_out"]
Decision = Literal["approved", "rejected"]
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


class ShiftRef(Form):
    """One date and shift. A weekly run lists every shift of the week; a call-out run lists only the affected ones."""

    date: Day
    shift: Literal["day", "night"]


class VersionViolations(Form):
    """The hard violations check_rules found on one draft version."""

    version: int
    violations: List[Violation]


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


class DecisionDetails(Form):
    """What the manager did, beyond the PRD's approved/rejected. A demand change is not approved or rejected:
    it retires this case and starts a new one."""

    action: DecisionAction
    demand_changes: List[DemandChange] = Field(default_factory=list)
    acknowledged_open_issues: bool = False  # the manager approved a draft that still had open issues
    new_case_id: Optional[str] = None  # change_demand: the new run this decision started


class CaseRecord(Form):
    """One run, start to finish.

    `needs_manual_review` is the draft's items plus `input_review` (items about the inputs: the agents' own items and
    nurses not on the roster), without repeats. Child cases inherit `input_review` and `unusual`.
    `drafts` and `violations` hold every checked version. `final_draft` is the best one (empty when no round
    produced a valid draft) and `open_violations`, `unfixable` and `needs_manual_review` belong to it.
    A run that stops for missing input has no drafts, outcome stopped_missing_input and a plain `stop_reason`.
    """

    case_id: str
    snapshot_id: str
    start_time: str  # ISO date and time
    trigger: Trigger = "weekly"
    affected_shifts: List[ShiftRef]
    parent_case_id: Optional[str] = None
    callouts: List[Callout] = Field(default_factory=list)  # call_out runs: who called out, and when
    unit: str
    week_start: Day
    status: CaseStatus
    outcome: Optional[Outcome] = None
    stop_reason: str = ""
    demand_result: DemandResult
    availability_result: AvailabilityResult
    drafts: List[Draft] = Field(default_factory=list)
    violations: List[VersionViolations] = Field(default_factory=list)
    rounds_used: int = Field(default=0, ge=0, le=3)
    rounds: List[RoundSummary] = Field(default_factory=list)
    final_draft: Optional[Draft] = None
    open_violations: List[Violation] = Field(default_factory=list)
    soft_tradeoffs: List[SoftTradeoff] = Field(default_factory=list)
    unfixable: List[Unfixable] = Field(default_factory=list)
    needs_manual_review: List[NeedsManualReview] = Field(default_factory=list)
    unusual: List[str] = Field(default_factory=list)  # one-line notes from the Demand agent (advisory text)
    input_review: List[NeedsManualReview] = Field(default_factory=list)  # review items about the INPUTS (agents, roster)
    newer_case_id: Optional[str] = None  # set when status is out_of_date: the run that replaced this one
    manager_decision: Optional[Decision] = None
    decision_time: Optional[str] = None
    decision_details: Optional[DecisionDetails] = None
