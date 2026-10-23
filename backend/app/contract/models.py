"""DRAFT: both owners must review before use.

The handoff formats: the fixed "forms" the agents and the checking code pass to each other.
Owner: Shared (Cheich and Kerrian).

Source of truth: CLAUDE.md, "Handoff rules". Only the forms Phase 1 needs are here.
Proposal, Approval and AuditEntry come later, with the approvals work.

Names use snake_case. The raw mock data and Shift Board use camelCase (employeeId),
so the tools in backend/app/tools/ do that conversion, not these models.
"""

from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

ShiftKind = Literal["day", "night"]
Certification = Literal["BLS", "ACLS", "Charge"]
RowStatus = Literal["ok", "needs_review", "missing"]
RuleName = Literal[
    "rest_time",
    "weekly_hours",
    "consecutive_shifts",
    "certification",
    "availability",
    "coverage",
]
Severity = Literal["hard", "soft"]


class Form(BaseModel):
    """Base for every form. Extra fields are an error, so a typo or an invented field is caught."""

    model_config = ConfigDict(extra="forbid")


class Nurse(Form):
    id: str
    name: str
    unit: str
    certifications: List[Certification]
    employment: Literal["full_time", "part_time"]
    max_weekly_hours: int


class DemandRow(Form):
    """How many nurses one shift needs. `status` is written by orchestrator code only."""

    date: str  # YYYY-MM-DD
    shift: ShiftKind
    start: str  # HH:MM
    end: str  # HH:MM (a night shift ends the next morning)
    unit: str
    nurses_needed: Optional[int] = None  # None when the number is missing
    required_certifications: Dict[str, int] = Field(default_factory=dict)  # e.g. {"Charge": 1}
    note: Optional[str] = None
    status: Optional[RowStatus] = None


class AvailabilityRow(Form):
    """Whether one nurse can work on one date. Includes approved time off as "unavailable".

    `availability` is the nurse's answer. `status` is about the data (ok, needs_review,
    missing) and is written by orchestrator code only.
    """

    nurse_id: str
    date: str  # YYYY-MM-DD
    availability: Literal["available", "unavailable"]
    reason: Optional[str] = None
    note: Optional[str] = None
    status: Optional[RowStatus] = None


class LeaveRequest(Form):
    """Only approved leave counts as time off. A pending request is information only."""

    id: str
    nurse_id: str
    type: Literal["vacation", "pto", "fmla", "overtime"]
    start: str  # YYYY-MM-DD
    end: str  # YYYY-MM-DD
    note: Optional[str] = None
    status: Literal["pending", "approved", "denied"]


class Callout(Form):
    id: str
    nurse_id: str
    shift_id: str
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    reason: Optional[str] = None
    reported_at: str  # ISO date and time


class Snapshot(Form):
    """One run reads one snapshot. Every agent and `check_rules` read the same one."""

    snapshot_id: str
    unit: str
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    nurses: List[Nurse]
    demand: List[DemandRow]
    availability: List[AvailabilityRow]
    leave: List[LeaveRequest] = Field(default_factory=list)
    callouts: List[Callout] = Field(default_factory=list)


class Assignment(Form):
    """One nurse on one shift. A draft schedule is a list of these."""

    nurse_id: str
    date: str  # YYYY-MM-DD
    shift: ShiftKind


class Violation(Form):
    """One rule that a draft breaks. `nurse_id` is empty for coverage."""

    rule: RuleName
    severity: Severity
    nurse_id: str = ""
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    found: Union[int, float, str]  # what the draft has, e.g. 2 nurses
    limit: Union[int, float, str]  # what the rule allows, e.g. 3 nurses
    fix_hint: str


class Unfixable(Form):
    """A violation that cannot be fixed. The shift stays an open gap. Never invent a nurse."""

    rule: RuleName
    nurse_id: str = ""
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    reason: str  # one plain sentence
