"""Typed inputs for the roster model and a small illustrative data set."""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Shift:
    """One shift type that can be assigned on a roster date.

    ``required_skills`` maps a skill name to the number of assigned employees
    who must hold that skill. An empty mapping means no special skill is needed.
    """

    code: str
    required_staff: int
    required_skills: dict[str, int] = field(default_factory=dict)
    start_minute: int = 0
    end_minute: int = 0
    work_minutes: int = 0
    # Break offsets are minutes after shift start, e.g. ((240, 270),).
    breaks: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class WorkLimits:
    """Working-time limits for one employee from the active rule pack.

    All values use integer minutes. CP-SAT works with integers, while minutes
    avoid rounding problems that can arise from storing hours as decimals.
    """

    maximum_daily_minutes: int
    normal_weekly_minutes: int
    maximum_weekly_overtime_minutes: int
    minimum_rest_days_per_week: int = 1
    normal_daily_minutes: int | None = None
    maximum_monthly_overtime_minutes: int | None = None


@dataclass(frozen=True)
class GroupShiftLimit:
    """A maximum number of assignments per employee in a group to one shift.

    Counts apply over the named period and inclusive effective dates. A value
    of zero prohibits the shift. A named consent requirement blocks applicable
    assignments until that consent is recorded for the employee.
    """

    group: str
    shift_code: str
    maximum_assignments: int
    period: str = "roster"
    effective_from: date | None = None
    effective_until: date | None = None
    required_consent: str | None = None


@dataclass(frozen=True)
class CoverageRequirement:
    """Headcount and skill minima for one dated shift, replacing its defaults."""

    required_staff: int
    required_skills: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RosterInput:
    """Dated inputs and policies required by the hard-constraint model.

    An unavailable entry is an (employee, day, shift-code) combination that the
    solver must never assign. Days are consecutive calendar dates. Numeric
    defaults and the demonstration rule-pack version are illustrative.
    """

    employees: tuple[str, ...]
    days: tuple[date, ...]
    shifts: tuple[Shift, ...]
    employee_skills: dict[str, frozenset[str]] = field(default_factory=dict)
    unavailable: frozenset[tuple[str, date, str]] = frozenset()
    minimum_rest_minutes: int = 11 * 60
    work_limits: dict[str, WorkLimits] = field(default_factory=dict)
    employee_groups: dict[str, frozenset[str]] = field(default_factory=dict)
    group_shift_limits: tuple[GroupShiftLimit, ...] = ()
    locked_assignments: frozenset[tuple[str, date, str]] = frozenset()
    coverage: dict[tuple[date, str], CoverageRequirement] = field(default_factory=dict)
    # Supply complete relevant history. An empty set explicitly declares no
    # prior assignments. Historical shifts use the same shift definitions.
    previous_assignments: frozenset[tuple[str, date, str]] = frozenset()
    week_start_weekday: int = 0  # Monday=0, Sunday=6.
    employee_consents: dict[str, frozenset[str]] = field(default_factory=dict)
    rule_pack_version: str = "demo"


def build_demo_input() -> RosterInput:
    """Return a feasible two-day example with two employees and two shifts."""

    return RosterInput(
        employees=("Asha", "Ben"),
        days=(date(2026, 11, 23), date(2026, 11, 24)),
        shifts=(
            Shift(
                code="morning",
                required_staff=1,
                start_minute=6 * 60,
                end_minute=14 * 60,
                work_minutes=8 * 60,
            ),
            Shift(
                code="night",
                required_staff=1,
                required_skills={"machine_operator": 1},
                start_minute=22 * 60,
                end_minute=6 * 60,
                work_minutes=8 * 60,
            ),
        ),
        employee_skills={
            "Asha": frozenset({"machine_operator"}),
            "Ben": frozenset(),
        },
        unavailable=frozenset(
            {
                ("Ben", date(2026, 11, 23), "night"),
                ("Asha", date(2026, 11, 24), "morning"),
            }
        ),
        work_limits={
            "Asha": WorkLimits(8 * 60, 45 * 60, 12 * 60),
            "Ben": WorkLimits(8 * 60, 45 * 60, 12 * 60),
        },
    )
