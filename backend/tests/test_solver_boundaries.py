"""Regression cases for dates, historical work, overtime and malformed input."""

from dataclasses import replace
from datetime import date, timedelta
import unittest
from unittest.mock import patch

from app.solver.roster_model import solve_roster
from app.solver.sample_data import (
    CoverageRequirement, GroupShiftLimit, RosterInput, Shift, WorkLimits,
)


MONDAY = date(2026, 11, 23)


def example(days: int = 1) -> RosterInput:
    """An uncongested example whose optional rules can be enabled independently."""

    return RosterInput(
        employees=("Asha",),
        days=tuple(MONDAY + timedelta(days=i) for i in range(days)),
        shifts=(Shift("day", 1, start_minute=480, end_minute=960, work_minutes=480),),
        minimum_rest_minutes=0,
        work_limits={"Asha": WorkLimits(1440, 10080, 10080, 0)},
    )


class SolverBoundaryTests(unittest.TestCase):
    def test_bad_inputs_are_rejected_before_solving(self) -> None:
        base = example()
        shift = base.shifts[0]
        limits = base.work_limits["Asha"]
        invalid = (
            replace(base, employees=("Asha", "Asha")),
            replace(base, days=("Monday",)),
            replace(base, days=(MONDAY, MONDAY + timedelta(days=2))),
            replace(base, shifts=(replace(shift, required_skills={"operator": -1}),)),
            replace(base, shifts=(replace(shift, required_staff=1.5),)),
            replace(base, shifts=(replace(shift, end_minute=481),)),
            replace(base, shifts=(replace(shift, end_minute=480),)),
            replace(base, shifts=(replace(shift, breaks=((60, 120), (90, 150))),)),
            replace(base, work_limits={"Asha": replace(limits, minimum_rest_days_per_week=1.5)}),
            replace(base, employee_groups={"Ashaa": frozenset({"restricted"})}),
            replace(base, employee_skills={"Asha": "operator"}),
            replace(base, work_limits={}),
            replace(base, group_shift_limits=(GroupShiftLimit("unknown", "day", 0),)),
            replace(base, previous_assignments=frozenset({("Asha", MONDAY, "day")})),
            replace(base, coverage={(MONDAY, "unknown"): CoverageRequirement(1)}),
            replace(base, week_start_weekday=7),
        )
        for index, data in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises(ValueError):
                solve_roster(data)

    def test_date_specific_headcount_and_skill_coverage(self) -> None:
        data = replace(
            example(2), employees=("Asha", "Ben"),
            work_limits={e: WorkLimits(1440, 10080, 10080, 0) for e in ("Asha", "Ben")},
            employee_skills={"Ben": frozenset({"operator"})},
            coverage={(MONDAY, "day"): CoverageRequirement(2, {"operator": 1})},
            unavailable=frozenset({("Ben", MONDAY + timedelta(days=1), "day")}),
        )
        result = solve_roster(data)
        self.assertEqual(result.status, "OPTIMAL")
        self.assertEqual(set(result.assignments), {
            ("Asha", MONDAY, "day"), ("Ben", MONDAY, "day"),
            ("Asha", MONDAY + timedelta(days=1), "day"),
        })

    def test_history_blocks_insufficient_rest_at_roster_start(self) -> None:
        data = replace(
            example(), minimum_rest_minutes=660,
            shifts=example().shifts + (Shift("night", 0, start_minute=1320, end_minute=360, work_minutes=480),),
            previous_assignments=frozenset({("Asha", MONDAY - timedelta(days=1), "night")}),
        )
        self.assertEqual(solve_roster(data).status, "INFEASIBLE")
        self.assertEqual(solve_roster(replace(data, minimum_rest_minutes=120)).status, "OPTIMAL")

    def test_history_counts_toward_weekly_hours(self) -> None:
        data = replace(
            example(), days=(MONDAY + timedelta(days=4),),
            previous_assignments=frozenset({("Asha", MONDAY, "day")}),
            work_limits={"Asha": WorkLimits(480, 480, 0, 0)},
        )
        self.assertEqual(solve_roster(data).status, "INFEASIBLE")
        self.assertEqual(solve_roster(replace(data, work_limits={"Asha": WorkLimits(480, 480, 480, 0)})).status, "OPTIMAL")

    def test_workweek_boundary_is_configurable(self) -> None:
        sunday = MONDAY + timedelta(days=6)
        data = replace(example(2), days=(sunday, sunday + timedelta(days=1)),
                       work_limits={"Asha": WorkLimits(480, 480, 0, 0)})
        self.assertEqual(solve_roster(data).status, "OPTIMAL")
        self.assertEqual(solve_roster(replace(data, week_start_weekday=6)).status, "INFEASIBLE")

    def test_previous_work_counts_in_rest_window_at_roster_start(self) -> None:
        data = replace(
            example(),
            previous_assignments=frozenset(
                ("Asha", MONDAY - timedelta(days=i), "day") for i in range(1, 7)
            ),
            work_limits={"Asha": WorkLimits(1440, 10080, 10080, 1)},
        )
        self.assertEqual(solve_roster(data).status, "INFEASIBLE")
        relaxed = replace(data, work_limits={"Asha": WorkLimits(1440, 10080, 10080, 0)})
        self.assertEqual(solve_roster(relaxed).status, "OPTIMAL")

    def test_result_records_the_input_rule_pack_version(self) -> None:
        data = replace(example(), rule_pack_version="synthetic-rules-v2")
        self.assertEqual(solve_roster(data).rule_pack_version, "synthetic-rules-v2")

    def test_overnight_minutes_split_across_calendar_weeks(self) -> None:
        sunday = MONDAY + timedelta(days=6)
        data = replace(
            example(), days=(sunday,),
            shifts=(Shift("night", 1, start_minute=1320, end_minute=360, work_minutes=480),),
            work_limits={"Asha": WorkLimits(480, 120, 180, 0)},
        )
        self.assertEqual(solve_roster(data).status, "INFEASIBLE")
        self.assertEqual(solve_roster(replace(data, work_limits={"Asha": WorkLimits(480, 120, 240, 0)})).status, "OPTIMAL")

    def test_overnight_shift_prevents_false_full_rest_day(self) -> None:
        data = replace(
            example(7),
            shifts=(Shift("night", 0, start_minute=1320, end_minute=360, work_minutes=480),),
            locked_assignments=frozenset(("Asha", d, "night") for d in example(6).days),
            work_limits={"Asha": WorkLimits(1440, 10080, 10080, 1)},
        )
        self.assertEqual(solve_roster(data).status, "INFEASIBLE")
        # Removing Saturday night leaves Sunday completely free.
        relaxed = replace(data, locked_assignments=frozenset(
            a for a in data.locked_assignments if a[1] != MONDAY + timedelta(days=5)
        ))
        self.assertEqual(solve_roster(relaxed).status, "OPTIMAL")

    def test_daily_and_weekly_overtime_do_not_double_count(self) -> None:
        data = replace(
            example(3), shifts=(Shift("long", 1, start_minute=480, end_minute=1080, work_minutes=600),),
            work_limits={"Asha": WorkLimits(600, 1200, 600, 0, normal_daily_minutes=480)},
        )
        result = solve_roster(data)
        self.assertEqual(result.status, "OPTIMAL")
        self.assertEqual([minutes for _, _, minutes in result.overtime_minutes], [120, 120, 360])
        self.assertEqual(solve_roster(replace(data, work_limits={
            "Asha": replace(data.work_limits["Asha"], maximum_weekly_overtime_minutes=599)
        })).status, "INFEASIBLE")

    def test_monthly_overtime_includes_prior_work(self) -> None:
        data = replace(
            example(), days=(date(2026, 11, 30),),
            shifts=(Shift("long", 1, start_minute=480, end_minute=1080, work_minutes=600),),
            previous_assignments=frozenset({("Asha", date(2026, 11, 29), "long")}),
            work_limits={"Asha": WorkLimits(600, 10080, 10080, 0, 480, 180)},
        )
        self.assertEqual(solve_roster(data).status, "INFEASIBLE")
        self.assertEqual(solve_roster(replace(data, work_limits={
            "Asha": replace(data.work_limits["Asha"], maximum_monthly_overtime_minutes=240)
        })).status, "OPTIMAL")

    def test_overtime_resets_at_calendar_month_boundary(self) -> None:
        data = replace(
            example(2), days=(date(2026, 11, 30), date(2026, 12, 1)),
            shifts=(Shift("long", 1, start_minute=480, end_minute=1080, work_minutes=600),),
            work_limits={"Asha": WorkLimits(600, 10080, 10080, 0, 480, 120)},
        )
        self.assertEqual(solve_roster(data).status, "OPTIMAL")

    def test_breaks_are_allocated_to_the_date_they_occur(self) -> None:
        data = replace(
            example(), shifts=(Shift("night", 1, start_minute=1320, end_minute=360,
                                     work_minutes=450, breaks=((60, 90),)),),
            work_limits={"Asha": WorkLimits(1440, 0, 1440, 0)},
        )
        result = solve_roster(data)
        self.assertEqual(result.status, "OPTIMAL")
        self.assertEqual(result.overtime_minutes, (("Asha", MONDAY, 90),))

    def test_group_week_limit_counts_history_and_resets_next_week(self) -> None:
        data = replace(
            example(), days=(MONDAY + timedelta(days=1),),
            employee_groups={"Asha": frozenset({"restricted"})},
            group_shift_limits=(GroupShiftLimit("restricted", "day", 1, period="week"),),
            previous_assignments=frozenset({("Asha", MONDAY, "day")}),
        )
        self.assertEqual(solve_roster(data).status, "INFEASIBLE")
        self.assertEqual(solve_roster(replace(data, days=(MONDAY + timedelta(days=7),))).status, "OPTIMAL")

    def test_group_consent_and_effective_dates(self) -> None:
        data = replace(
            example(), employee_groups={"Asha": frozenset({"restricted"})},
            group_shift_limits=(GroupShiftLimit("restricted", "day", 1, required_consent="night_work"),),
        )
        self.assertEqual(solve_roster(data).status, "INFEASIBLE")
        self.assertEqual(solve_roster(replace(data, employee_consents={"Asha": frozenset({"night_work"})})).status, "OPTIMAL")
        expired = replace(data.group_shift_limits[0], effective_until=MONDAY - timedelta(days=1))
        self.assertEqual(solve_roster(replace(data, group_shift_limits=(expired,))).status, "OPTIMAL")

    def test_lock_and_unavailability_conflict_is_infeasible(self) -> None:
        key = ("Asha", MONDAY, "day")
        data = replace(example(), unavailable=frozenset({key}), locked_assignments=frozenset({key}))
        self.assertEqual(solve_roster(data).status, "INFEASIBLE")

    def test_time_limit_and_unknown_status(self) -> None:
        for limit in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                solve_roster(example(), max_time_seconds=limit)
        from ortools.sat.python import cp_model
        with patch.object(cp_model.CpSolver, "solve", autospec=True, return_value=cp_model.UNKNOWN) as solve:
            result = solve_roster(example(), max_time_seconds=0.25)
            solver = solve.call_args.args[0]
            self.assertEqual(solver.parameters.max_time_in_seconds, 0.25)
            self.assertEqual(result.status, "UNKNOWN")
            self.assertEqual(result.assignments, ())


if __name__ == "__main__":
    unittest.main()
