# ShiftCore
**A Constraint-Based Shift Scheduling and Roster Repair System with Sri Lankan Labour Rule Compliance**

## Tech Stack
- **Backend:** Python 3, FastAPI, SQLAlchemy, Alembic, PostgreSQL
- **Solver:** Google OR-Tools CP-SAT
- **Frontend:** React, TypeScript, Vite

## Team & Sprint 1 Leadership
- **Scrum Master (Sprint 1):** Isiwara
- **UI/UX Lead:** Keshan

## Run the solver example

From `backend`, create a virtual environment and install the declared dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.solver.solve_demo
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Hard-constraint input conventions

`RosterInput.days` contains consecutive, ordered `datetime.date` objects. For
example, use `date(2026, 11, 23)` in place of a weekday label. The default workweek
begins on Monday. Set `week_start_weekday` to another weekday when required.

Shift times and durations use integer minutes. An end time earlier than the start
crosses midnight. Equal start and end times are rejected. Supply unpaid breaks as
ordered `(start_offset, end_offset)` pairs measured from shift start. `work_minutes`
must equal the elapsed shift time minus those breaks. Work is counted on each
calendar date where it occurs, including overnight shifts crossing week or month
boundaries.

Use `coverage[(date, shift_code)]` to replace both staffing and skill requirements
for a specific dated shift. Entries without an override use the shift defaults.
One employee can count toward multiple skill minima when they hold those skills.

Supply complete `previous_assignments` for relevant rest windows, weeks, months,
and group-limit periods. The model treats an empty history as a declaration of no
previous work. Historical assignments use the supplied shift definitions, so
their times and breaks must match those definitions. Future roster runs must
include the preceding published assignments as history.

Working-time limits are configurable inputs. Daily overtime is work above
`normal_daily_minutes` when that optional threshold is supplied. Weekly overtime
adds excess regular time above `normal_weekly_minutes`, avoiding double counting
of daily overtime. Weekly excess is attributed in chronological order. Optional
monthly overtime caps sum this overtime by calendar month. The rule-pack owner
must confirm that this accounting convention matches each applicable policy.

Weekly rest currently requires full midnight-to-midnight days free of all shift
occupancy in rolling seven-day windows. Overnight work prevents its ending date
from counting as a full day off. Half-day and conditional holiday entitlements
still require policy-specific modeling. Demo thresholds are illustrative inputs.

Group shift limits support roster, calendar-week and calendar-month periods,
effective dates, and named consent requirements. Record `rule_pack_version` on
each input. The result carries that version and daily overtime totals for roster
dates. Overnight overtime on the following date is included in constraints and
will appear in that date's roster result when it is scheduled.

`solve_roster` defaults to a 120-second solver search limit. Model construction
adds to total wall time. `UNKNOWN` means the search stopped without a roster or
proof of infeasibility. The result preserves that status for callers.

## Database migrations

Set `DATABASE_URL` in the process environment before running Alembic from
`backend`. Application models must inherit from `app.core.database.Base` and be
imported by `app.models` so Alembic can discover their tables. The current checkout
contains the metadata bootstrap. Table definitions and migration revisions remain
part of the database implementation.
