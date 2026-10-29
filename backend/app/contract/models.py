"""Phase 1 handoff forms.

Owner: Cheich (formats). **Kerrian Gordon signed off 2026-10-28** (field names and meanings match the PRD
sections she owns prompts/evals against). No form fields were changed in that sign-off.

Source of truth: the PRD (Google Doc), sections 3b "Handoff format", "Phase 1 input files",
"Draft format" and "Violation format". If this file and the PRD disagree, the PRD wins.
Field names match the PRD exactly (snake_case). Only the Phase 1 forms are here.
The case record and the snapshot are Phase 2 (`case_record.py`).

Dates and times are adjusted automatically when the meaning is unambiguous ("7:00" becomes "07:00",
"7pm" becomes "19:00", "2026-11-2" becomes "2026-11-02") and rejected otherwise ("25:99", "11/02/2026").
Counts and limits must be in range (no negative hours, no zero weekly limit).
"""

import re
from datetime import date as _date
from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

_TIME_24H = re.compile(r"(\d{1,2}):(\d{2})(?::00)?")
_TIME_12H = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)")
_DATE_YMD = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")


def _adjust_time(value):
    """Return HH:MM, adjusting only when the meaning is unambiguous. Anything else is an error.

    Adjusted: "7:00" -> "07:00", " 07:00 " -> "07:00", "07:00:00" -> "07:00",
    "7am" -> "07:00", "7:30 PM" -> "19:30", "12:00 AM" -> "00:00". Rejected: "25:99", "24:00",
    "07:00:30", "7", "".
    """
    if not isinstance(value, str):
        raise ValueError("time must be text like 07:00")
    text = value.strip().lower()
    m = _TIME_12H.fullmatch(text)
    if m:
        hour, minute, half = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if not 1 <= hour <= 12 or not 0 <= minute <= 59:
            raise ValueError(f"not a valid time: {value!r}")
        hour = (hour % 12) + (12 if half == "pm" else 0)
        return f"{hour:02d}:{minute:02d}"
    m = _TIME_24H.fullmatch(text)
    if m and int(m.group(1)) <= 23 and int(m.group(2)) <= 59:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    raise ValueError(f"not a valid time: {value!r} (use HH:MM, for example 07:00)")


def _adjust_date(value):
    """Return YYYY-MM-DD, adjusting only when the meaning is unambiguous. Anything else is an error.

    Adjusted: "2026-11-2" -> "2026-11-02", "2026/11/02" -> "2026-11-02".
    Rejected: "11/02/2026" (month first or day first? we do not guess), "2026-02-30", "tomorrow", "".
    """
    if not isinstance(value, str):
        raise ValueError("date must be text like 2026-11-02")
    m = _DATE_YMD.fullmatch(value.strip())
    if m:
        try:
            return _date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    raise ValueError(f"not a valid date: {value!r} (use YYYY-MM-DD, for example 2026-11-02)")


Day = Annotated[str, BeforeValidator(_adjust_date)]  # YYYY-MM-DD
Clock = Annotated[str, BeforeValidator(_adjust_time)]  # HH:MM

ShiftKind = Literal["day", "night"]
RowStatus = Literal["ok", "needs_review", "missing"]
AvailabilityReason = Literal["none", "approved_time_off", "call_out"]
RuleName = Literal[
    "one_shift_per_day",
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
    hours_this_week: int = Field(ge=0)


class DemandRow(Form):
    """One demand.json row. `status` is written by the orchestrator, never by an agent.

    `patient_count` and `nurses_needed` are empty (None) when status is "missing".
    `note` is required when status is not "ok".
    """

    unit: str
    date: Day
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
    date: Day
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


class ShiftTimes(Form):
    """When one kind of shift starts and ends. A night shift ends the next morning (end is before start)."""

    start: Clock
    end: Clock

    @model_validator(mode="after")
    def _not_zero_length(self):
        if self.start == self.end:
            raise ValueError("a shift cannot start and end at the same time")
        return self


def _standard_shift_times() -> Dict[str, "ShiftTimes"]:
    return {"day": ShiftTimes(start="07:00", end="19:00"), "night": ShiftTimes(start="19:00", end="07:00")}


class RulesConfig(Form):
    """rules.json. The limits check_rules uses.

    `shift_times` is the one source of truth for how long a shift is. A draft's own start and end
    times must match it exactly, so a draft cannot shrink its own hours. If a rules file does not
    list it, the standard 12-hour shifts are used (day 07:00 to 19:00, night 19:00 to 07:00).
    """

    min_rest_hours: int = Field(ge=0)
    max_weekly_hours: int = Field(gt=0)
    max_consecutive_shifts: int = Field(ge=1)
    required_certifications_per_shift: List[str]
    ratio_patients_per_nurse: int = Field(ge=1)
    max_fairness_gap: int = Field(ge=0)
    shift_times: Dict[ShiftKind, ShiftTimes] = Field(default_factory=_standard_shift_times)

    @model_validator(mode="after")
    def _both_shifts_defined(self):
        if set(self.shift_times) != {"day", "night"}:
            raise ValueError("shift_times must define exactly day and night")
        return self


class Callout(Form):
    """One call-out. Phase 3 reads these (get_callouts)."""

    nurse_id: str
    date: Day
    shift: ShiftKind
    reported_at: str  # ISO date and time


# --- the draft (Scheduler to Rules Checker and back) --------------------------------


class Assignment(Form):
    """One nurse on one shift. A night shift ends the next morning (shift_end < shift_start)."""

    unit: str
    date: Day  # the day the shift starts
    shift: ShiftKind
    nurse_id: str
    shift_start: Clock
    shift_end: Clock


class OpenGap(Form):
    unit: str
    date: Day
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
    date: Day
    shift: ShiftKind
    reason: str  # one plain sentence


class Suggestion(Form):
    """Call-outs only: one replacement nurse for one shift."""

    date: Day
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
    date: Day
    shift: ShiftKind
    found: str
    limit: str
    fix_hint: str = ""


class SoftTradeoff(Form):
    """A soft result (such as fairness). It goes to the approval view and never fails a draft."""

    rule: RuleName
    nurse_id: str = ""
    date: Day
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
