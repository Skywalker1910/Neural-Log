# Data Model

## Motivation

The redesign needs roughly 27 entities - workouts, sets, food entries, learning
sessions, sleep, habits, goals, attribute scores. The app got here with five tables
created by `CREATE TABLE IF NOT EXISTS` inside `init_db()`, plus a couple of ad-hoc
`ALTER TABLE` checks. That approach has no record of what's been applied, no way to
express a change that isn't idempotent, and no ordering.

So before adding entities, we added a migration mechanism. This document covers that
mechanism and maps every planned entity to its owning phase - so each phase creates
only the tables it actually uses, and nobody has to guess whether something exists.

## Migrations

Numbered SQL files, applied in filename order, recorded in a ledger table:

```
migrations/
  001_baseline.sql      <- the five tables as they stood before the redesign
  002_....sql           <- added by the phase that needs it
```

```
init_db()
  |
  |-- run_migrations(conn)
  |     |-- CREATE TABLE IF NOT EXISTS schema_migrations (version, applied_at)
  |     |-- SELECT applied versions
  |     |-- for each migrations/*.sql not yet applied:
  |     |       executescript(file) ; INSERT INTO schema_migrations ; COMMIT
  |
  '-- legacy column backfill (see below)
```

Deliberately small: no ORM, no Alembic. It keeps the raw-`sqlite3` approach the app
already uses, and the same numbered-file pattern ports to Postgres/RDS later.

**Two things worth knowing before you add a migration:**

1. `MIGRATIONS_DIR` resolves from `__file__`, not the working directory. The test
   suite `chdir`s into a tmp directory (`tests/conftest.py`), and the server isn't
   always started from the project root. A cwd-relative path breaks both.
2. `001_baseline.sql` uses `IF NOT EXISTS` throughout, so it is a no-op against
   every database that already exists and a full build against a fresh one. Later
   migrations don't need that hedge - they run exactly once.

The legacy column backfill (`selected_path`, `custom_path_items`) stays as a
conditional Python step in `init_db()` rather than a migration file, because SQLite
has no `ADD COLUMN IF NOT EXISTS` and those columns may or may not exist on
databases predating the Paths feature.

## What exists today

| Table | Holds |
|---|---|
| `users` | Account, password hash, admin flag, selected path |
| `activities` | One row per logged activity, including daily checklist submissions |
| `milestones` | Snapshots at 10/25/45/70/100 days |
| `daily_xp` | One row per user per day - source of truth for XP and leaderboards |
| `user_badges` | Which badges each user unlocked, and when |
| `schema_migrations` | Migration ledger |

Plus two filesystem stores, which predate the SQL tables and are unchanged so far:
`artifacts/paths/<username>.json` (checklist templates) and
`artifacts/checklists/<username>.jsonl` (submissions). See
[ARCHITECTURE.md](ARCHITECTURE.md) for why that split exists.

## Planned entities

Each phase creates its own tables. Nothing here is built ahead of the phase that
uses it - an empty table is a liability, not a head start.

| Entity | Status | Phase |
|---|---|---|
| `UserProfile` | New - age, sex, height, activity level, targets | **4** (R9 expands it) |
| `UserPreferences` | New - targets, reminder settings | 9 |
| `DailyLog` | New - the per-day record a calendar cell maps to | 2 |
| `AttributeScore` | New - time-series of the eight attribute scores | 2 |
| `DailyScore` | New - daily performance and discipline scores | 2 |
| `habit_groups`, `habits`, `habit_completions` | **Absorbed the Paths JSON system** | 6 (done) |
| `goals`, `goal_milestones`, `goal_habits` | New | 6 (done) |
| `tasks` | New | 6 (done) |
| `Workout`, `WorkoutSession` | New | 3 |
| `Exercise`, `ExerciseSet` | New - library + per-set logging | 3 |
| `BodyMeasurement` | New | 3 |
| `Food`, `FoodEntry` | New - library + per-meal logging | 4 |
| `Recipe`, `RecipeIngredient` | New - a cooked dish, reusable as a food | 4 |
| `SleepEntry` | New - keyed to the WAKE date | 4 |
| `LifestyleDay` | New - one row per day, not metric-per-row | 4 |
| `LearningArea`, `LearningTopic`, `LearningSession` | New | 5 |
| `Achievement`, `UserAchievement` | Partly exists - `user_badges` is the seed | 7 |
| `XPTransaction` | Extends `daily_xp` - per-action XP ledger, auditable | 7 |
| `UserLevel` | Derived, not stored - level is a pure function of total XP | - |
| `Streak` | Derived from `DailyLog` - not a stored counter that can drift | - |
| `Notification` | New - models only; no delivery infrastructure yet | 10 |

### Two deliberate non-tables

`UserLevel` and `Streak` are computed, not stored. A stored streak counter is a
value that can disagree with the log it summarises; deriving it from `DailyLog`
means it can't. The same already applies to levels, which `calculate_level()`
derives from total XP.

### The Paths system's fate

**Done in R6.** Paths became `habit_groups` + `habits` + `habit_completions`.

The conversion kept `load_user_paths()`'s payload identical so the Jinja app, the
legacy JS and the SPA all kept working, and carried the existing string ids across
as `slug` so `daily_log.path_id` and `users.selected_path` were never orphaned.

The import is lazy and per-user, recorded in `habit_imports` so it runs exactly
once - without that marker, removing a path would be undone on the next load by
re-importing the original file. Completions are backfilled from `daily_log`'s
snapshots rather than the JSONL files, matched by name.

The JSON files are left on disk rather than deleted. See [HABITS.md](HABITS.md).

## Time-series

The app has to answer "what was my discipline score six months ago" and "how much
stronger am I than in March". That rules out tables that only hold current values.

`AttributeScore`, `DailyScore`, `BodyMeasurement`, `SleepEntry` and
`LifestyleDay` are all written per-day - one row per user per day, so history is
the default rather than something that has to be reconstructed.

`DailyNutrition` was planned as a per-day totals table and deliberately not
built. Totals are summed from `food_entries` on read instead, so correcting a
food corrects every day that used it. A stored total would be a second copy that
could disagree with the entries it summarises - the same reasoning that keeps
`Streak` and `UserLevel` derived.
