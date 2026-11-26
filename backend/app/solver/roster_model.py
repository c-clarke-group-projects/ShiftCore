"""CP-SAT model with dated coverage, calendar rest and working-time rules."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite

from ortools.sat.python import cp_model

from app.solver.sample_data import CoverageRequirement, RosterInput


AssignmentKey = tuple[str, date, str]
DAY_MINUTES = 1440


def shift_interval(day_index: int, start_minute: int, end_minute: int) -> tuple[int, int]:
    """Return absolute minutes, with an earlier end crossing midnight."""

    start = day_index * DAY_MINUTES + start_minute
    end = day_index * DAY_MINUTES + end_minute
    if end_minute < start_minute:
        end += DAY_MINUTES
    return start, end


def require_integer(name: str, value: int, minimum: int = 0, maximum: int | None = None) -> None:
    """Reject fractions and booleans before passing arithmetic to CP-SAT."""

    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")


def validate_roster_input(data: RosterInput) -> None:
    """Validate identities, calendar dates, durations and rule references."""

    for name, values in (
        ("Employee", data.employees),
        ("Shift", tuple(s.code for s in data.shifts)),
    ):
        if not values or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(f"{name} identifiers must be nonempty strings")
        if len(set(values)) != len(values):
            raise ValueError(f"{name} identifiers must be unique")
    if not data.days or any(type(d) is not date for d in data.days):
        raise ValueError("Roster days must be calendar date objects")
    if any(b != a + timedelta(days=1) for a, b in zip(data.days, data.days[1:])):
        raise ValueError("Roster dates must be consecutive and ordered")

    require_integer("Minimum rest minutes", data.minimum_rest_minutes)
    require_integer("Week start weekday", data.week_start_weekday, maximum=6)
    if not isinstance(data.rule_pack_version, str) or not data.rule_pack_version.strip():
        raise ValueError("A rule pack version is required")

    for shift in data.shifts:
        require_integer("Shift start minute", shift.start_minute, maximum=1439)
        require_integer("Shift end minute", shift.end_minute, maximum=1439)
        if shift.start_minute == shift.end_minute:
            raise ValueError("Shift start and end must differ")
        require_integer("Work minutes", shift.work_minutes, minimum=1)
        elapsed = (shift.end_minute - shift.start_minute) % DAY_MINUTES
        previous_end = 0
        for start, end in shift.breaks:
            require_integer("Break start", start, maximum=elapsed)
            require_integer("Break end", end, maximum=elapsed)
            if start < previous_end or end <= start:
                raise ValueError("Breaks must be ordered, positive and non-overlapping")
            previous_end = end
        if shift.work_minutes != elapsed - sum(b - a for a, b in shift.breaks):
            raise ValueError("Work minutes must equal elapsed shift time minus breaks")

    employees = set(data.employees)
    shifts = {s.code for s in data.shifts}
    for name, mapping in (
        ("work limits", data.work_limits), ("skills", data.employee_skills),
        ("groups", data.employee_groups), ("consents", data.employee_consents),
    ):
        if set(mapping) - employees:
            raise ValueError(f"Unknown employee in {name}")
    if set(data.work_limits) != employees:
        raise ValueError("Missing work limits for employees")
    for mapping in (data.employee_skills, data.employee_groups, data.employee_consents):
        for values in mapping.values():
            if not isinstance(values, (set, frozenset)) or any(
                not isinstance(v, str) or not v.strip() for v in values
            ):
                raise ValueError("Skills, groups and consents must be sets of nonempty names")

    for limits in data.work_limits.values():
        require_integer("Daily work limit", limits.maximum_daily_minutes)
        require_integer("Normal weekly minutes", limits.normal_weekly_minutes)
        require_integer("Weekly overtime limit", limits.maximum_weekly_overtime_minutes)
        require_integer("Weekly rest days", limits.minimum_rest_days_per_week, maximum=7)
        for name, value in (
            ("Normal daily minutes", limits.normal_daily_minutes),
            ("Monthly overtime limit", limits.maximum_monthly_overtime_minutes),
        ):
            if value is not None:
                require_integer(name, value)

    for employee, day, code in data.unavailable | data.locked_assignments | data.previous_assignments:
        if employee not in employees or type(day) is not date or code not in shifts:
            raise ValueError("Unknown employee, date or shift in assignment")
    for _, day, _ in data.unavailable | data.locked_assignments:
        if day not in data.days:
            raise ValueError("Unavailable and locked assignments must be inside the roster")
    if any(day >= data.days[0] for _, day, _ in data.previous_assignments):
        raise ValueError("Previous assignments must start before the roster")
    historical_days = [(e, d) for e, d, _ in data.previous_assignments]
    if len(set(historical_days)) != len(historical_days):
        raise ValueError("Previous assignments allow at most one shift start per employee per date")

    for day, code in data.coverage:
        if day not in data.days or code not in shifts:
            raise ValueError("Unknown date or shift in coverage")
    for requirement in list(data.shifts) + list(data.coverage.values()):
        require_integer("Required staff", requirement.required_staff)
        for skill, count in requirement.required_skills.items():
            if not isinstance(skill, str) or not skill.strip():
                raise ValueError("Required skills must have nonempty names")
            require_integer("Required skill count", count)

    known_groups = set().union(*data.employee_groups.values())
    for limit in data.group_shift_limits:
        if limit.shift_code not in shifts or limit.group not in known_groups:
            raise ValueError("Unknown shift or group in group limit")
        require_integer("Group assignment limit", limit.maximum_assignments)
        if limit.period not in ("roster", "week", "month"):
            raise ValueError("Group limit period must be roster, week or month")
        for bound in (limit.effective_from, limit.effective_until):
            if bound is not None and type(bound) is not date:
                raise ValueError("Rule effective dates must be calendar dates")
        if limit.effective_from and limit.effective_until and limit.effective_from > limit.effective_until:
            raise ValueError("Rule effective dates are reversed")
        if limit.required_consent is not None and (
            not isinstance(limit.required_consent, str) or not limit.required_consent.strip()
        ):
            raise ValueError("Required consent must have a nonempty name")


def week_start(day: date, weekday: int) -> date:
    return day - timedelta(days=(day.weekday() - weekday) % 7)


@dataclass(frozen=True)
class SolveResult:
    status: str
    assignments: tuple[AssignmentKey, ...]
    overtime_minutes: tuple[tuple[str, date, int], ...] = ()
    rule_pack_version: str = "demo"


def solve_roster(roster_input: RosterInput, max_time_seconds: float = 120) -> SolveResult:
    """Find a roster using full calendar rest days and calendar work totals.

    Overtime is daily excess plus weekly excess of remaining regular minutes.
    Weekly excess is attributed chronologically to the date it arises. Monthly
    caps sum that overtime by calendar month. Supply all relevant prior work,
    including work earlier in any intersecting week or capped month.
    """

    data = roster_input
    validate_roster_input(data)
    if isinstance(max_time_seconds, bool) or not isinstance(max_time_seconds, (int, float)):
        raise ValueError("Solver time limit must be a positive finite number")
    if not isfinite(max_time_seconds) or max_time_seconds <= 0:
        raise ValueError("Solver time limit must be a positive finite number")
    model = cp_model.CpModel()
    x = {
        (e, d, s.code): model.new_bool_var(f"assignment_{e}_{d}_{s.code}")
        for e in data.employees for d in data.days for s in data.shifts
    }
    for day in data.days:
        for shift in data.shifts:
            requirement = data.coverage.get(
                (day, shift.code), CoverageRequirement(shift.required_staff, shift.required_skills)
            )
            # H1 and H2 count total staff and holders of each required skill.
            model.add(sum(x[e, day, shift.code] for e in data.employees) >= requirement.required_staff)
            for skill, count in requirement.required_skills.items():
                model.add(sum(
                    x[e, day, shift.code] for e in data.employees
                    if skill in data.employee_skills.get(e, frozenset())
                ) >= count)
        for employee in data.employees:
            # H3 permits zero or one shift start per calendar date.
            model.add(sum(x[employee, day, s.code] for s in data.shifts) <= 1)

    # Build the timeline and forbidden pairs once for all employees.
    history_dates = {d for _, d, _ in data.previous_assignments}
    instances = []
    for day in sorted(set(data.days) | history_dates):
        for shift in data.shifts:
            start, end = shift_interval(day.toordinal(), shift.start_minute, shift.end_minute)
            instances.append((day, shift, start, end))
    instances.sort(key=lambda item: item[2])
    forbidden_pairs = []
    for index, first in enumerate(instances):
        for second in instances[index + 1:]:
            if second[2] - first[3] >= data.minimum_rest_minutes:
                break
            forbidden_pairs.append((first, second))

    start_context = min(
        data.days[0] - timedelta(days=6),
        week_start(data.days[0], data.week_start_weekday),
        data.days[0].replace(day=1),
        *history_dates,
    )
    end_context = data.days[-1] + timedelta(days=1)
    calendar_days = tuple(
        start_context + timedelta(days=i)
        for i in range((end_context - start_context).days + 1)
    )
    weeks = defaultdict(list)
    months = defaultdict(list)
    for day in calendar_days:
        weeks[week_start(day, data.week_start_weekday)].append(day)
        months[(day.year, day.month)].append(day)
    overtime = {}
    selected = dict(x)
    selected.update({key: 1 for key in data.previous_assignments})

    for employee in data.employees:
        limits = data.work_limits[employee]
        # H4 also sees historical assignments and overlapping shifts.
        for first, second in forbidden_pairs:
            first_value = selected.get((employee, first[0], first[1].code), 0)
            second_value = selected.get((employee, second[0], second[1].code), 0)
            model.add(first_value + second_value <= 1)

        work_terms = defaultdict(list)
        occupied_terms = defaultdict(list)
        for day, shift, start, end in instances:
            assignment = selected.get((employee, day, shift.code), 0)
            # Breaks remain occupied time for rest-day purposes.
            for ordinal in range(start // DAY_MINUTES, (end - 1) // DAY_MINUTES + 1):
                occupied_terms[date.fromordinal(ordinal)].append(assignment)
            cursor = 0
            elapsed = end - start
            for break_start, break_end in shift.breaks + ((elapsed, elapsed),):
                work_start, work_end = start + cursor, start + break_start
                for ordinal in range(work_start // DAY_MINUTES, (work_end - 1) // DAY_MINUTES + 1):
                    minutes = min(work_end, (ordinal + 1) * DAY_MINUTES) - max(work_start, ordinal * DAY_MINUTES)
                    work_terms[date.fromordinal(ordinal)].append(assignment * minutes)
                cursor = break_end

        regular = {}
        daily_overtime = {}
        free_days = {}
        for day in calendar_days:
            total = sum(work_terms[day])
            model.add(total <= limits.maximum_daily_minutes)
            daily_overtime[day] = model.new_int_var(0, DAY_MINUTES, f"daily_ot_{employee}_{day}")
            if limits.normal_daily_minutes is None:
                model.add(daily_overtime[day] == 0)
            else:
                model.add_max_equality(daily_overtime[day], [0, total - limits.normal_daily_minutes])
            regular[day] = total - daily_overtime[day]
            free_days[day] = model.new_bool_var(f"free_{employee}_{day}")
            model.add(sum(occupied_terms[day]) == 0).only_enforce_if(free_days[day])
            model.add(sum(occupied_terms[day]) >= 1).only_enforce_if(free_days[day].Not())

        # H5 counts overnight minutes on the date where work occurs.
        for week_days in weeks.values():
            cumulative_regular = 0
            previous_excess = 0
            for day in week_days:
                cumulative_regular += regular[day]
                excess = model.new_int_var(0, 7 * DAY_MINUTES, f"weekly_excess_{employee}_{day}")
                model.add_max_equality(excess, [0, cumulative_regular - limits.normal_weekly_minutes])
                overtime[employee, day] = model.new_int_var(0, DAY_MINUTES, f"overtime_{employee}_{day}")
                model.add(overtime[employee, day] == daily_overtime[day] + excess - previous_excess)
                previous_excess = excess
            model.add(sum(overtime[employee, d] for d in week_days) <= limits.maximum_weekly_overtime_minutes)
        if limits.maximum_monthly_overtime_minutes is not None:
            for month_days in months.values():
                model.add(
                    sum(overtime[employee, d] for d in month_days)
                    <= limits.maximum_monthly_overtime_minutes
                )

        # H6 requires full midnight-to-midnight days off in rolling windows.
        for window_end in data.days:
            window = tuple(window_end - timedelta(days=i) for i in range(7))
            model.add(sum(free_days[d] for d in window) >= limits.minimum_rest_days_per_week)

        # H8 supports roster, calendar-week and calendar-month shift counts.
        for limit in data.group_shift_limits:
            if limit.group not in data.employee_groups.get(employee, frozenset()):
                continue
            buckets = defaultdict(list)
            for day, shift, _, _ in instances:
                if shift.code != limit.shift_code:
                    continue
                if limit.effective_from is not None and day < limit.effective_from:
                    continue
                if limit.effective_until is not None and day > limit.effective_until:
                    continue
                if limit.period == "roster" and day not in data.days:
                    continue
                key = "roster"
                if limit.period == "week":
                    key = week_start(day, data.week_start_weekday)
                if limit.period == "month":
                    key = (day.year, day.month)
                assignment = selected.get((employee, day, shift.code), 0)
                buckets[key].append(assignment)
                consents = data.employee_consents.get(employee, frozenset())
                if limit.required_consent and limit.required_consent not in consents:
                    model.add(assignment == 0)
            for assignments in buckets.values():
                model.add(sum(assignments) <= limit.maximum_assignments)

    for assignment in data.unavailable:
        model.add(x[assignment] == 0)
    for assignment in data.locked_assignments:
        model.add(x[assignment] == 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    status = solver.solve(model)
    status_name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(status_name, (), rule_pack_version=data.rule_pack_version)
    return SolveResult(
        status=status_name,
        assignments=tuple(key for key, variable in x.items() if solver.value(variable)),
        overtime_minutes=tuple(
            (e, d, solver.value(variable)) for (e, d), variable in overtime.items() if d in data.days
        ),
        rule_pack_version=data.rule_pack_version,
    )
