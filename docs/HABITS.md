# Habits and Goals

R6 did two things: it moved the Paths system out of JSON files and into SQL as
habits, and it built goals on top of them.

## Motivation

Paths are the oldest thing in this app. Four themed daily checklists, stored as
per-user JSON files in `artifacts/paths/`, loaded and rewritten on nearly every
request. They work — they are the one feature used every single day — but a JSON
blob has no rows to group by, so it cannot answer the questions that make a habit
tracker worth having:

- How often do I actually do this one?
- Is it due today, or is today a rest day for it?
- What is the streak for this habit alone, not the whole checklist?

Goals then needed somewhere to stand. A goal that cannot point at the behaviour
underneath it is just a note, and the app already has notes.

## The conversion was a move, not a rewrite

`load_user_paths()` returns byte-for-byte the payload it always did:

```
{'paths': [{'id', 'name', 'is_default', 'checklist_items': [...]}],
 'selected_path_id': ...}
```

Twelve call sites across `app.py`, the Jinja templates, `static/js/app.js` and
the SPA's Today page consume that shape. Changing the storage underneath without
changing the shape is what let the daily checklist keep working while it moved.

The proof this worked is not a new test — it is that the **245 tests that existed
before the migration passed against the new storage without modification**.

### The string ids are load-bearing

A path id (`batman-path`) and an item id (a uuid) are already referenced by
`daily_log.path_id`, `users.selected_path`, and every client. They are carried
across as `slug` rather than replaced with integers. Verified against the real
database: 40 of 40 item ids on the live account survived with nothing missing.

### The import is lazy and runs once

The first time a user's paths are loaded after the migration, their JSON file is
read, written into SQL, and the fact recorded in `habit_imports`.

That marker matters more than it looks. Without it, a later edit that removed a
path would be silently undone on the next load by re-importing the original file.
Registration also seeds habits immediately, so a new account is never in the state
where per-habit features read as empty.

The legacy JSON files are left on disk rather than deleted, so a bad import can be
diagnosed against the original.

## Two records, on purpose

`habit_completions` does **not** replace `daily_log.payload_json`, and the
difference is deliberate:

| | `daily_log.payload_json` | `habit_completions` |
|---|---|---|
| What it is | A snapshot of the items as they were that day | One row per habit per day |
| Authority for | Scoring | Streaks, adherence, "12 of the last 14" |
| Why | Makes "retune the weights and rescore everything" safe | A JSON blob cannot be grouped by |

Both are written by the same save, in the same transaction, so they cannot drift.
A test asserts they agree.

This is not the "second copy that can drift" the project otherwise avoids: the
snapshot is a point-in-time record by design, which is exactly why it exists.

### What does not get a completion row

Rating items. Rating your day is self-reflection, not a habit you complete; it
has weight 0, it is excluded from XP, it is already stored as
`daily_log.self_rating`, and a streak of "rated my day" would mean nothing.

## Schedules

The genuinely new capability. Every migrated path item became `daily`, because
that is what a path item has always been.

| Type | Due when |
|---|---|
| `daily` | Every day |
| `weekdays` | Monday to Friday |
| `days` | The weekdays listed in `schedule_days` (Monday = 0) |
| `times-per-week` | Always offerable — see below |

`times-per-week` always answers "yes" to *is it due today*, and that is not a
cop-out. It has no particular day, so the question has no honest answer beyond
"you could do it today". Whether you are **behind** on it is a weekly question,
and `weekly_progress()` answers that against a Monday-to-date week.

An unknown schedule type or junk weekday indices are dropped rather than stored,
so a malformed request cannot leave a habit permanently undue.

## Streaks

Two states have to be told apart, and conflating them is the easy mistake:

- **Nothing logged today** — you have not got to it yet. At 09:00 that is the
  normal state, so yesterday is allowed to carry the streak. A counter that reset
  overnight would report a lost streak every single morning.
- **Logged today as "No"** — you answered, and the answer was that you did not do
  it. That breaks the streak today.

## Goals

### Nothing here feeds an attribute

A goal is an intention plus a number you type in. Ticking a milestone is a claim
with nothing behind it, and scoring claims would pay you to declare progress
rather than make it.

This is enforced structurally: `goals_api.py` is the only workspace blueprint
with **no recompute function injected**, and a test asserts that declaring a goal
achieved, completing every milestone and closing a task moves no score at all.

What *is* evidenced is the habits underneath a goal, and those already feed
Discipline through the checklist producer.

### Progress has a source

Most evidenced first, and the UI always says which:

| Source | Where the number comes from |
|---|---|
| `habits` | Linked habits' real completions |
| `milestones` | How many you ticked — self-reported, but at least discrete |
| `metric` | A number you maintain by hand |
| `none` | Nothing to measure |

Linked habits deliberately outrank a typed-in metric. A goal claiming 10 of 10
sessions while the habit behind it was never completed reads 0%, and a test pins
that.

`none` returns `null` rather than 0%. Plenty of real goals ("get better at saying
no") have no number, and inventing 0% would read as failure when the honest
answer is that there is nothing to measure.

**Adherence divides by days elapsed**, not by days the habit was due. Scaling by
the schedule would let a once-a-fortnight habit read as perfect adherence while
the goal went nowhere.

### Abandoned is a status, not a deletion

Goals you gave up on are the most informative ones in hindsight. Quietly removing
them would leave a history in which you only ever succeeded.

Reaching `achieved` stamps the date once and keeps it — re-opening and
re-achieving should not rewrite when you first got there.

## Tasks

Deliberately thin: no projects, subtasks or dependencies. Tasks exist so a goal
can carry the concrete next actions that move it, not to become a task manager.

## Data model

| Table | Was | Notes |
|---|---|---|
| `habit_groups` | A Path | `slug` is the old string id |
| `habits` | A checklist item | `slug` is the old uuid; schedules are new |
| `habit_completions` | — | One habit, one day, one answer |
| `habit_imports` | — | Records that a user's JSON was imported |
| `goals` | — | Category, deadline, status, optional metric |
| `goal_milestones` | — | `completed_on` is a date, not a flag |
| `goal_habits` | — | Join table: a habit can serve several goals |
| `tasks` | — | Optional `goal_id` |

Deleting a path, a habit or a goal **archives** it. Completions and milestones
point at them, and deleting would silently rewrite history.

## API

The legacy `/api/paths` surface is unchanged and still serves three clients. The
new endpoints are separate on purpose — bolting schedule editing onto a
compatibility view would drag it somewhere it was never designed to go.

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/habits` | Stats for the selected path; `?all=1` for every path |
| GET | `/api/habits/due` | What is expected on a date, plus weekly counts |
| PUT | `/api/habits/<id>` | Schedule, name, weight |
| GET POST | `/api/goals` | List; create |
| GET PUT DELETE | `/api/goals/<id>` | Load; update; archive |
| POST | `/api/goals/<id>/milestones` | Add one |
| PUT DELETE | `/api/milestones/<id>` | Tick, rename, remove |
| GET POST | `/api/tasks` | List; create |
| PUT DELETE | `/api/tasks/<id>` | Update; archive |
| GET | `/api/goals/summary` | The dashboard, composed |

`/api/habits` is scoped to the path you are following by default. The four stock
paths share most of their items, so the unscoped list shows "What time did you
wake up?" four times — which reads as a bug rather than as four paths you are not
currently on.

## Operational note

This migration writes to a database that holds real daily logs. A backup was
taken before running it (`neural_log.db.pre-r6-*.bak`, gitignored). The existing
`*.db` ignore rule did not cover `.bak`, which is now fixed — a database backup
must never end up in version control.
