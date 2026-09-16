# Training

The workout workspace: an exercise library, set-by-set logging, routines, and the
analytics built on top. This is also the first feature that feeds the attribute
engine with *measured* data rather than self-report - see
[SCORING.md](SCORING.md) for what that changes.

## Motivation

Before R3 the only thing Neural Log knew about your training was whether you had
ticked a checkbox labelled "Workout". That is enough to notice you showed up, and
nothing else. It cannot tell a 20-minute walk from a heavy squat session, cannot
notice you have not trained legs in a month, and cannot tell you what you lifted
last time - the single most useful thing a training app can put in front of you
mid-session.

R3 adds the grain that was missing: the individual set. Everything else here -
volume trends, muscle balance, personal records, the Strength and Stamina and
Agility scores - is derived from that one table.

## The data model

Six tables, created in `migrations/003_training.sql`.

| Table | Grain | Notes |
|---|---|---|
| `exercises` | one exercise | Shared library (`user_id IS NULL`) plus per-user custom entries |
| `routines` | one plan | Archived, never deleted |
| `routine_exercises` | one planned exercise | Ordered by `position`, with target sets/reps |
| `workout_sessions` | one performed session | `routine_id` nullable - most sessions are improvised |
| `exercise_sets` | **one set** | The grain of the whole feature |
| `body_measurements` | one metric on one day | Context only; deliberately not scored |

Three decisions worth recording:

**Sessions are not unique per day.** Unlike the daily checklist, there is no
`UNIQUE(user_id, date)` on `workout_sessions`. A morning lift and an evening run
are two sessions, and forcing them into one row would either lose data or require
merging logic that nothing asked for.

**The library uses partial unique indexes.** SQLite treats `NULL`s as distinct,
so a plain `UNIQUE(user_id, slug)` would happily allow ten rows of
`barbell-bench-press` in the shared library. Two partial indexes instead:

```sql
CREATE UNIQUE INDEX idx_exercises_library_slug ON exercises (slug) WHERE user_id IS NULL;
CREATE UNIQUE INDEX idx_exercises_user_slug ON exercises (user_id, slug) WHERE user_id IS NOT NULL;
```

**Routines are archived, not deleted.** `workout_sessions.routine_id` points at
them, and deleting a routine must not erase the history of having trained it.

## The exercise library

85 exercises ship in `data/exercises.json` - 63 strength, 11 cardio, 7 mobility,
57 of them beginner-accessible. Each carries a primary muscle, secondary muscles,
equipment, difficulty, whether it is compound, and short form cues.

`scoring/library.py` syncs the file into the database on startup and returns
`(added, updated, archived)`. An exercise removed from the file is **archived, not
deleted** - someone may have logged sets against it, and their history has to
survive a library edit.

No exercise demo animations or images ship: they would be copyrighted media. The
component boundary is ready for them if that ever changes.

## Logging a set

The logging screen is the part you use standing in a gym holding a phone, so it
optimises for that:

- **Previous performance in the header.** "Last time: 82.5×8, 82.5×7, 85×6 · best
  85kg×6", from `/api/exercises/<id>/history`.
- **The current session is excluded from its own history.** Pass
  `?exclude_session=<id>` - otherwise reopening a saved session quotes it back at
  you as "last time", and reports today's lift as your all-time best before you
  have beaten anything.
- **Two kinds of "best".** `heaviest_set` and `best_volume_set` are both returned,
  because 82.5kg × 6 and 80kg × 8 are each the better set depending on what you
  are asking, and conflating them under one label is misleading.
- **New sets inherit the previous set's load**, because most sets repeat the one
  before.
- **Warm-ups are marked, not hidden.** They are real work, but they are excluded
  from volume, from records and from the scoring signal - counting them would let
  a warm-up week outscore a working one.
- **A row you never typed into is not a set.** Routine-seeded sessions open with a
  row per planned set; empty rows are excluded from the counters and are never
  saved.

### The rest timer

Driven by a target timestamp, not by decrementing a counter on an interval.
Browsers throttle timers in background tabs and phones lock mid-set, so a counter
would drift or freeze. Comparing against a stored end-time means the timer is
correct the moment you look at it again, however long the tab was asleep.

## Routines

A routine is a plan: a named, ordered list of exercises with target sets and reps.
Starting a session from one inherits its name and pre-fills the exercises with
empty inputs.

The plan is never persisted as training data. Only what you actually lift is
saved, and so only that is scored - a routine you never performed contributes
nothing to any attribute.

Editing a routine replaces its exercise list wholesale rather than diffing
positions. A routine is a handful of rows the client always sends in full, and a
replace cannot leave the order half-applied.

## Analytics

`/api/training` composes the whole dashboard in one response, for the same reason
`/api/home` does: five queries would mean five independent loading states.

| Panel | Window | Measure |
|---|---|---|
| Volume trend | Last 30 training days | Volume per training day |
| Muscle balance | Last 30 days | **Working sets**, not volume |
| Personal records | All time | Heaviest working set per exercise |
| Recent sessions | Last 8 | Sets and volume |

Balance is measured in sets because a set of calf raises and a set of squats are
comparable as training stimulus in a way their kilogram totals are not. Ordering
a muscle-balance chart by volume would put squats at the top of every chart ever
drawn and say nothing.

Body measurements are recorded and shown but **not scored**. They are context for
the numbers above, not behaviour - and rewarding a bodyweight number would reward
the wrong thing.

## How training reaches the attributes

`scoring/producers.py` is the seam. It converts sets into the same
`(attribute, ratio)` shape the checklist produces, so the engine blends them
without knowing where either came from.

```
set_contribution(row)  ->  one set becomes (attribute, magnitude)
training_ratios(...)   ->  trailing window, pro-rated target
blend(...)             ->  measured + self-reported, weighted
```

Three rules matter:

1. **Measured data outweighs self-report** 3:1 (`measured_weight` /
   `self_report_weight`).
2. **Self-report alone is capped at 0.5** for Strength, Stamina and Agility. At
   the original 0.75 ceiling the app paid you to lie: ticking "Workout" scored 75,
   while honestly logging a light week scored 62. The breakeven is `(4C−1)/3` -
   67% of target at C=0.75, but 33% at C=0.5. A test asserts every level of real
   training beats claiming it.
3. **The first training day is pro-rated.** Measuring one day against a full
   week's target scored a genuine session at 27%, which reads as a punishment for
   starting. The target now scales to the observed window.
4. **The weekly volume target scales with how often you train** (R10). It used to
   be a flat 12,000 kg×reps for everyone, which asks someone on a deliberate
   twice-a-week programme to produce a four-day week's work - they then score
   permanently low for executing their plan perfectly. That is the engine
   measuring the *plan* rather than the adherence.

   The target is `per_session_strength_volume × training_days_per_week`, clamped
   to 2-6 days. Undeclared falls back to four days, which reproduces the old
   12,000 exactly, so **nobody's history moved when this shipped**.

   Part of the denominator therefore comes from something you declared, and that
   is not a departure: the opportunity denominator has always worked this way -
   your Path decides which attributes have a denominator at all, and you choose
   your Path. The clamp is what closes the obvious hole, because without a floor
   "I train once a week" would turn a single session into a free 100.

   Cardio and mobility stay absolute. They are weekly time budgets, not
   per-session work products - how many days you lift says nothing about how many
   minutes of cardio a week is a reasonable ask.

Mobility work is what unlocks Agility - it was `locked` before R3 because nothing
fed it.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/exercises` | Library, filterable by `q`, `category`, `muscle` |
| GET | `/api/exercises/<id>/history` | Previous performance; `?exclude_session=<id>` |
| GET POST | `/api/workouts` | List recent sessions; start one |
| GET PUT DELETE | `/api/workouts/<id>` | Load, save sets, remove |
| GET POST | `/api/routines` | List; create |
| GET PUT DELETE | `/api/routines/<id>` | Load; update; archive |
| GET | `/api/training` | The dashboard, composed |
| GET POST | `/api/measurements` | Body metrics; upserts per (date, metric) |

Everything lives in `training_api.py` as a blueprint. The auth decorator and
database helper are injected at registration rather than imported, so the module
never imports `app` - the test suite swaps modules per test, and importing `app`
there would bind to whichever copy loaded first.

## Deleting data

Deleting a session recomputes the attributes without it. This needed an explicit
fix: `recompute_scores()` returned early when a user had no training data left,
which orphaned the derived rows and left Strength frozen at its last value
forever. `_prune_orphaned_scores()` now removes derived rows whose source is gone.
