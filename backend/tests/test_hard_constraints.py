"""Tests for the first ShiftCore CP-SAT hard constraints."""

import unittest
from dataclasses import replace
from datetime import date

from app.solver.roster_model import solve_roster
from app.solver.sample_data import (
    GroupShiftLimit,
    RosterInput,
    Shift,
    WorkLimits,
    build_demo_input,
)


class HardConstraintTests(unittest.TestCase):
    def test_demo_roster_covers_each_shift_and_respects_unavailability(self) -> None:
        roster_input = build_demo_input()

        result = solve_roster(roster_input)

        self.assertEqual(result.status, "OPTIMAL")
        assignments = set(result.assignments)
        self.assertTrue(assignments.isdisjoint(roster_input.unavailable))

        for day in roster_input.days:
            for shift in roster_input.shifts:
                assigned_count = sum(
                    (employee, day, shift.code) in assignments
                    for employee in roster_input.employees
                )
                self.assertGreaterEqual(assigned_count, shift.required_staff)

    def test_missing_required_skill_makes_roster_infeasible(self) -> None:
        roster_input = RosterInput(
            employees=("Asha", "Ben"),
            days=(date(2026, 11, 23),),
            shifts=(
                Shift(
                    "night",
                    1,
                    {"machine_operator": 1},
                    start_minute=22 * 60,
                    end_minute=6 * 60,
                    work_minutes=8 * 60,
                ),
            ),
            employee_skills={"Asha": frozenset(), "Ben": frozenset()},
            work_limits={
                "Asha": WorkLimits(8 * 60, 45 * 60, 12 * 60),
                "Ben": WorkLimits(8 * 60, 45 * 60, 12 * 60),
            },
        )

        result = solve_roster(roster_input)

        self.assertEqual(result.status, "INFEASIBLE")

    def test_insufficient_rest_between_night_and_morning_is_infeasible(self) -> None:
        roster_input = RosterInput(
            employees=("Asha",),
            days=(date(2026, 11, 23), date(2026, 11, 24)),
            shifts=(
                Shift(
                    "morning",
                    0,
                    start_minute=8 * 60,
                    end_minute=16 * 60,
                    work_minutes=8 * 60,
                ),
                Shift(
                    "night",
                    0,
                    start_minute=22 * 60,
                    end_minute=6 * 60,
                    work_minutes=8 * 60,
                ),
            ),
            unavailable=frozenset(
                {
                    ("Asha", date(2026, 11, 23), "morning"),
                    ("Asha", date(2026, 11, 24), "night"),
                }
            ),
            locked_assignments=frozenset({
                ("Asha", date(2026, 11, 23), "night"),
                ("Asha", date(2026, 11, 24), "morning"),
            }),
            minimum_rest_minutes=11 * 60,
            work_limits={"Asha": WorkLimits(16 * 60, 45 * 60, 12 * 60)},
        )

        result = solve_roster(roster_input)

        self.assertEqual(result.status, "INFEASIBLE")
        # Two hours is the exact gap, so relaxing only rest makes it feasible.
        self.assertEqual(solve_roster(replace(roster_input, minimum_rest_minutes=120)).status, "OPTIMAL")

    def test_weekly_work_exceeding_overtime_limit_is_infeasible(self) -> None:
        roster_input = RosterInput(
            employees=("Asha",),
            days=(
                date(2026, 11, 23),
                date(2026, 11, 24),
                date(2026, 11, 25),
                date(2026, 11, 26),
                date(2026, 11, 27),
                date(2026, 11, 28),
                date(2026, 11, 29),
            ),
            shifts=(
                Shift(
                    "day",
                    1,
                    start_minute=8 * 60,
                    end_minute=16 * 60,
                    work_minutes=8 * 60,
                ),
            ),
            work_limits={
                "Asha": WorkLimits(
                    maximum_daily_minutes=8 * 60,
                    normal_weekly_minutes=45 * 60,
                    maximum_weekly_overtime_minutes=10 * 60,
                    minimum_rest_days_per_week=0,
                )
            },
        )

        result = solve_roster(roster_input)

        # Seven 8-hour shifts are 56 hours, above this employee's 55-hour cap.
        self.assertEqual(result.status, "INFEASIBLE")
        at_boundary = replace(roster_input, work_limits={
            "Asha": replace(roster_input.work_limits["Asha"], maximum_weekly_overtime_minutes=11 * 60)
        })
        self.assertEqual(solve_roster(at_boundary).status, "OPTIMAL")

    def test_single_shift_exceeding_daily_limit_is_infeasible(self) -> None:
        roster_input = RosterInput(
            employees=("Asha",),
            days=(date(2026, 11, 23),),
            shifts=(
                Shift(
                    "long_day",
                    1,
                    start_minute=8 * 60,
                    end_minute=18 * 60,
                    work_minutes=10 * 60,
                ),
            ),
            work_limits={"Asha": WorkLimits(8 * 60, 45 * 60, 12 * 60)},
        )

        result = solve_roster(roster_input)

        self.assertEqual(result.status, "INFEASIBLE")

    def test_no_full_rest_day_in_a_week_is_infeasible(self) -> None:
        roster_input = RosterInput(
            employees=("Asha",),
            days=(
                date(2026, 11, 23),
                date(2026, 11, 24),
                date(2026, 11, 25),
                date(2026, 11, 26),
                date(2026, 11, 27),
                date(2026, 11, 28),
                date(2026, 11, 29),
            ),
            shifts=(
                Shift(
                    "day",
                    1,
                    start_minute=8 * 60,
                    end_minute=16 * 60,
                    work_minutes=8 * 60,
                ),
            ),
            work_limits={
                "Asha": WorkLimits(
                    maximum_daily_minutes=8 * 60,
                    normal_weekly_minutes=45 * 60,
                    maximum_weekly_overtime_minutes=12 * 60,
                    minimum_rest_days_per_week=1,
                )
            },
        )

        result = solve_roster(roster_input)

        self.assertEqual(result.status, "INFEASIBLE")

    def test_group_specific_night_limit_is_enforced(self) -> None:
        roster_input = RosterInput(
            employees=("Asha",),
            days=(date(2026, 11, 23), date(2026, 11, 24)),
            shifts=(
                Shift(
                    "night",
                    1,
                    start_minute=22 * 60,
                    end_minute=6 * 60,
                    work_minutes=8 * 60,
                ),
            ),
            work_limits={"Asha": WorkLimits(8 * 60, 45 * 60, 12 * 60)},
            employee_groups={"Asha": frozenset({"night_restricted"})},
            group_shift_limits=(
                GroupShiftLimit("night_restricted", "night", maximum_assignments=1),
            ),
        )

        result = solve_roster(roster_input)

        self.assertEqual(result.status, "INFEASIBLE")

    def test_locked_assignment_is_preserved(self) -> None:
        roster_input = RosterInput(
            employees=("Asha", "Ben"),
            days=(date(2026, 11, 23),),
            shifts=(
                Shift(
                    "day",
                    1,
                    start_minute=8 * 60,
                    end_minute=16 * 60,
                    work_minutes=8 * 60,
                ),
            ),
            work_limits={
                "Asha": WorkLimits(8 * 60, 45 * 60, 12 * 60),
                "Ben": WorkLimits(8 * 60, 45 * 60, 12 * 60),
            },
            locked_assignments=frozenset({("Ben", date(2026, 11, 23), "day")}),
        )

        result = solve_roster(roster_input)

        self.assertEqual(result.status, "OPTIMAL")
        self.assertIn(("Ben", date(2026, 11, 23), "day"), result.assignments)

    def test_shift_with_no_work_duration_is_rejected(self) -> None:
        roster_input = RosterInput(
            employees=("Asha",),
            days=(date(2026, 11, 23),),
            shifts=(Shift("day", 1, start_minute=8 * 60, end_minute=16 * 60),),
            work_limits={"Asha": WorkLimits(8 * 60, 45 * 60, 12 * 60)},
        )

        with self.assertRaisesRegex(ValueError, "Work minutes must be an integer"):
            solve_roster(roster_input)


if __name__ == "__main__":
    unittest.main()
