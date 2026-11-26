"""Run the smallest ShiftCore hard-constraint example from the command line."""

from app.solver.roster_model import solve_roster
from app.solver.sample_data import build_demo_input


def main() -> None:
    result = solve_roster(build_demo_input())
    print(f"Solver status: {result.status}")

    if result.status not in ("OPTIMAL", "FEASIBLE"):
        messages = {
            "INFEASIBLE": "The requirements cannot all be satisfied.",
            "UNKNOWN": "The run ended before finding a roster or proving infeasibility.",
            "MODEL_INVALID": "The solver model is invalid.",
        }
        print(messages.get(result.status, "The solver returned an unexpected status."))
        return

    print("Assignments:")
    for employee, day, shift_code in result.assignments:
        print(f"- {day}: {employee} works {shift_code}")


if __name__ == "__main__":
    main()
