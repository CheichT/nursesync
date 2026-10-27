"""DRAFT: both owners must review before use.

The handoff formats: the fixed "forms" the agents and the checking code pass to each other.
Owner: Cheich (formats), reviewed by Kerrian.

Source of truth: the PRD (Google Doc), sections 3b "Handoff format", "Phase 1 input files",
"Draft format" and "Violation format". If this file and the PRD disagree, the PRD wins.
Field names match the PRD exactly (snake_case). Only the Phase 1 forms are here.
The case record and the snapshot are Phase 2, so they are not here yet.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

ShiftKind = Literal["day", "night"]
RowStatus = Literal["ok", "needs_review", "missing"]
AvailabilityReason = Literal["none", "approved_time_off", "call_out"]
RuleName = Literal[
    "rest_time",
    "weekly_hours",
    "consecutive_shifts",
    "certification",
    "availability",
    "coverage",
    "fairness",
]
Severity = Literal["hard", "soft"]
GapReason = Literal["missing", "no_available_nurse", "no_certified_nurse"]


class Form(BaseModel):
    """Base for every form. An extra or misspelled field is an error, not ignored."""

    model_config = ConfigDict(extra="forbid")


# --- input files (JSON, one file per input type) ------------------------------------


class Nurse(Form):
    """One roster.json row."""

    nurse_id: str
    name: str
    unit: str
    certifications: List[str]
    hours_this_week: int


class DemandRow(Form):
    """One demand.json row. `status` is written by the orchestrator, never by an agent.

    `patient_count` and `nurses_needed` are empty (None) when status is "missing".
    `note` is required when status is not "ok".
    """

    unit: str
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    patient_count: Optional[int] = Field(default=None, ge=0)
    nurses_needed: Optional[int] = Field(default=None, ge=0)
    status: RowStatus
    note: str = ""

    @model_validator(mode="after")
    def _note_and_missing(self):
        if self.status != "ok" and not self.note:
            raise ValueError("note is required when status is not ok")
        if self.status == "missing" and (self.patient_count is not None or self.nurses_needed is not None):
            raise ValueError("patient_count and nurses_needed must be empty when status is missing")
        return self


class AvailabilityRow(Form):
    """One availability.json row: one nurse, one date, one shift.

    `available` and `reason` are empty (None) when status is "missing".
    `note` is required when status is not "ok".
    """

    nurse_id: str
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    available: Optional[bool] = None
    reason: Optional[AvailabilityReason] = None
    status: RowStatus
    note: str = ""

    @model_validator(mode="after")
    def _note_and_missing(self):
        if self.status != "ok" and not self.note:
            raise ValueError("note is required when status is not ok")
        if self.status == "missing" and (self.available is not None or self.reason is not None):
            raise ValueError("available and reason must be empty when status is missing")
        if self.status != "missing" and (self.available is None or self.reason is None):
            raise ValueError("available and reason are required unless status is missing")
        return self


class RulesConfig(Form):
    """rules.json. The limits check_rules uses."""

    min_rest_hours: int
    max_weekly_hours: int
    max_consecutive_shifts: int
    required_certifications_per_shift: List[str]
    ratio_patients_per_nurse: int
    max_fairness_gap: int


class Callout(Form):
    """One call-out. Phase 3 reads these (get_callouts)."""

    nurse_id: str
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    reported_at: str  # ISO date and time


# --- the draft (Scheduler to Rules Checker and back) --------------------------------


class Assignment(Form):
    """One nurse on one shift. A night shift ends the next morning (shift_end < shift_start)."""

    unit: str
    date: str  # YYYY-MM-DD, the day the shift starts
    shift: ShiftKind
    nurse_id: str
    shift_start: str  # HH:MM
    shift_end: str  # HH:MM


class OpenGap(Form):
    unit: str
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    nurses_needed: int
    nurses_assigned: int
    gap_reason: GapReason


class NeedsManualReview(Form):
    item_type: Literal["demand_day", "nurse"]
    id: str
    note: str


class Unfixable(Form):
    """A violation the Scheduler could not fix. The shift stays an open gap. Never invent a nurse."""

    rule: RuleName
    nurse_id: str = ""
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    reason: str  # one plain sentence


class Suggestion(Form):
    """Call-outs only: one replacement nurse for one shift."""

    date: str  # YYYY-MM-DD
    shift: ShiftKind
    nurse_id: str  # the replacement
    reason: str  # one plain sentence


class Draft(Form):
    """One version of the weekly schedule. check_rules reads only `assignments`."""

    case_id: str
    snapshot_id: str
    version: Literal[1, 2, 3]
    assignments: List[Assignment]
    open_gaps: List[OpenGap] = Field(default_factory=list)
    needs_manual_review: List[NeedsManualReview] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    unfixable: List[Unfixable] = Field(default_factory=list)
    suggestions: List[Suggestion] = Field(default_factory=list)


# --- check_rules and Rules Checker to Scheduler -------------------------------------


class Violation(Form):
    """One rule a draft breaks. `nurse_id` is empty for coverage.

    `found` and `limit` are plain text, such as "8 hours of rest" and "10 hours of rest".
    `fix_hint` is added later by the Rules Checker agent, so check_rules leaves it empty.
    """

    rule: RuleName
    severity: Severity
    nurse_id: str = ""
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    found: str
    limit: str
    fix_hint: str = ""


class SoftTradeoff(Form):
    """A soft result (such as fairness). It goes to the approval view and never fails a draft."""

    rule: RuleName
    nurse_id: str = ""
    date: str  # YYYY-MM-DD
    shift: ShiftKind
    note: str


class CheckRulesResult(Form):
    """What check_rules returns. It echoes case_id and version so a stale result is rejected."""

    case_id: str
    version: Literal[1, 2, 3]
    passed: bool
    violations: List[Violation] = Field(default_factory=list)
    soft_tradeoffs: List[SoftTradeoff] = Field(default_factory=list)

    @model_validator(mode="after")
    def _passed_matches_hard_violations(self):
        has_hard = any(v.severity == "hard" for v in self.violations)
        if self.passed and has_hard:
            raise ValueError("a draft with hard violations cannot pass")
        if not self.passed and not has_hard:
            raise ValueError("a draft with no hard violations must pass")
        return self
