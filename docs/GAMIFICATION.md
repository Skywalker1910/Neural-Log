# Gamification System

The spec behind Phase 2: how a completed checklist turns into XP, levels, streaks,
and badges. Written down here so the rules are a deliberate design, not just
whatever the code happens to do - see `app.py`'s "Gamification" section for the
implementation.

## XP

Every checklist item (except rating-type ones - see below) has a **weight**,
1-5, set per item in the Path editor. Completing an item on a given day awards
`weight * 10` XP. What counts as "completed":

| Item type | Completed when... |
|-----------|--------------------|
| `yes-no`  | the answer starts with "Yes" |
| `time` / `text` / other | any non-empty answer was given |
| `rating`  | never - excluded from scoring entirely (it's self-reflection, not a task) |

The four default Paths ship with 3 "heavier" items (weight 3 - workouts, deep
study/practice, project work) and the rest at weight 1 (habits, reflection,
planning) - a fully-completed default-Path day is 150 base XP before the streak
multiplier. Custom Paths and per-item weights are fully user-editable.

## Streak multiplier

XP scales with your current day streak: **+2% per consecutive day, capped at
+50%** (reached at a 25-day streak). A day's `total_xp = round(base_xp * (1 +
multiplier))`. Missing a day resets the streak counter to 0 for the *next*
day's multiplier - there's no additional XP or level penalty for breaking a
streak (a deliberate choice: the goal is to keep people coming back, not punish
an off day).

Resubmitting/editing a day's checklist recalculates that day's XP from
scratch (`daily_xp` is keyed `UNIQUE(user_id, date)`) rather than stacking.

## Levels

`xp_for_level(n) = 50 * (n - 1)^2` - cumulative XP required to *reach* level
`n`. Level 1 is the start (0 XP). Early levels come quickly, later ones need
sustained consistency:

| Level | Cumulative XP required |
|-------|------------------------|
| 1     | 0   |
| 2     | 50  |
| 3     | 200 |
| 4     | 450 |
| 5     | 800 |
| 10    | 4050 |

(Tunable - `XP_PER_WEIGHT_POINT` and the `50 * n^2` curve in `app.py` are
constants, not load-bearing elsewhere, if the pacing needs adjusting once real
usage data comes in.)

## Badges

Code-defined (like the default Paths), evaluated after every checklist
submission; which ones a user has unlocked lives in `user_badges`.

| Badge | Unlocks when |
|-------|--------------|
| First Steps | Logged your first day |
| One Week Strong | 7-day streak |
| Consistency Master | 30-day streak |
| Century Club | 100 days logged |
| Path Finder | Created a custom Path |
| Perfectionist | A single day at 100% completion |
| Leveling Up | Reached level 5 |
| Double Digits | Reached level 10 |

## Leaderboards

Two, both ranked by total XP (ties broken alphabetically):

- **Overall** - all-time XP across every user.
- **Monthly** - XP from `daily_xp` rows dated in the current calendar month
  only, so it resets each month and doesn't let early adopters permanently
  dominate.

Both are visible to everyone in the group - appropriate for a small, known
set of friends (~10 people), not something that would scale as-is to a public
leaderboard.
