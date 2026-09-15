# XP and achievements

The per-action XP ledger, what earns, what cannot be farmed, and how
achievements report progress. For attribute scoring — a different system with
different goals — see [SCORING.md](SCORING.md).

## Motivation

XP had only ever come from the daily checklist. R3 through R6 added training,
nutrition, lifestyle, learning, habits and goals, and **not one of them awarded
anything**. You could log a two-hour workout and a three-hour study session and
earn nothing unless you also ticked a checkbox — while the leaderboard ranked
your friends on exactly that number.

`daily_xp` could not be extended to fix it. One opaque total per day cannot say
where the XP came from, cannot be audited when a number looks wrong, and cannot
express "this was capped" or "this was a claim rather than evidence".

## The ledger

`xp_transactions` is one row per awarded action, and is the authority for total
XP. `daily_xp` is still written as a per-day rollup, because the leaderboard and
the legacy API read it — the same compatibility approach R6 used for Paths.

Each row records the reason, the base XP, the streak multiplier, whether a cap
reduced it, and whether it was **measured** or **claimed**.

### A day is rebuilt, not appended to

Every award path recomputes a whole `(user, date)` and replaces that day's rows.

This is not laziness — it is what makes the daily caps correct. A cap is a
statement about a day, and applying one while inserting rows one at a time means
each insert has to know what the rest of the day already holds. Rebuilding
sidesteps the whole class of bug, exactly as `recompute_scores` does for
attributes, and makes re-saving a workout idempotent for free.

Achievement awards are the exception: they are never rebuilt, because an unlock
is one-off and a rebuild that dropped it would un-pay it.

## The two rules the rates serve

### Evidence beats a claim

Logging real sets pays full. Ticking "I trained" on a day you also logged pays
**40%** (`EVIDENCE_DISCOUNT`), because the sets are already being paid for that
behaviour and paying twice is what would make claiming as good as doing.

Not zero: filling in the checklist is still the daily ritual the whole app is
built around, and zeroing it would punish people for doing it.

This is the same principle as the scoring engine's self-report ceiling, applied
to XP.

### Farming is pointless, not merely difficult

Every source has a **daily cap** and a **floor**:

| Source | Daily cap | Floor |
|---|---|---|
| Checklist | 150 | — |
| Training | 80 | at least one working set |
| Learning | 60 | 10 minutes |
| Nutrition | 40 | 3 logged items |
| Lifestyle | 40 | 2 hours of sleep |

Plus a whole-day ceiling of 300 before the streak multiplier. Twelve workouts in
a day earn one day's cap, and the ledger records `capped_from` so "you hit the
training cap" is visible rather than an unexplained number.

Achievement XP is deliberately uncapped — it is one-off by definition, and a cap
would mean unlocking two in a day silently discarded one.

## The level curve

`LEVEL_CURVE_FACTOR * (level - 1) ** LEVEL_CURVE_EXPONENT`, both in
`xp_config.py`. R7's brief asked for it to be tunable; the defaults reproduce the
original hard-coded `50 * (level - 1) ** 2` exactly, and a test pins that, so
nobody's level moved when it shipped.

## Achievements

### Why they are data, not lambdas

The Phase 2 badges were eight dicts each carrying a `check(ctx)` callable. That
decides earned-or-not and nothing else — in particular it cannot say **how close
you are**, because a lambda returning `False` tells you nothing about the
distance to `True`.

An unlock UI that cannot show progress is just a list of things you do not have.
So an achievement is now a **metric name and a threshold**. Earned is
`ctx[metric] >= threshold`, and progress falls out of the same two numbers for
free. Tiers become nearly free too: bronze, silver and gold versions of one idea
are the same metric at three thresholds.

23 achievements across six categories — consistency, training, nutrition,
lifestyle, learning, mastery.

### Metrics share the XP floors

A three-minute study session earns no XP, so it must not unlock "logged your
first study session" either. The context queries read the same constants from
`xp_config`, so the two systems cannot disagree about what counts as a session, a
night, or a workout.

This was a real bug: before it was fixed, a workout containing only a warm-up
unlocked "Rack Pulled" while earning nothing.

### Legacy codes are preserved

`user_badges` rows reference these codes. The original eight keep theirs exactly
— renaming one would silently un-earn it for everyone who had it.

## Historical data

Two separate operations, and the distinction matters.

**The backfill** runs automatically at startup. It writes historical `daily_xp`
rows into the ledger, because the ledger became authoritative and every day
earned before R7 would otherwise stop counting and everyone's level would drop.
Each historical day becomes one `checklist` entry, since that is honestly all the
old schema knew.

**The rebuild** is `scripts/rebuild_xp.py`, and is deliberately manual. Past
activity earning nothing while identical activity tomorrow earns 16 is unfair,
but paying history at today's rates moves levels and reorders the leaderboard.
That is a choice to make deliberately, not a migration side effect.

```bash
python scripts/rebuild_xp.py --all --dry-run
python scripts/rebuild_xp.py --all
```

It also evaluates achievements afterwards. It did not at first, and the result
was a catalogue showing "Logged your first workout" as locked, reading **"7 of
1"** — the progress was right and the unlock had simply never been triggered,
because unlocking happens on the write paths and a rebuild is not one.

## Bugs worth remembering

**The rollup fed itself.** `_write_rollup` wrote the day's full base into
`daily_xp.base_xp`, which `recompute_day` reads back when no checklist figure is
passed. A workout's XP was summed into the column, read back as a *checklist*
award on the next rebuild, and survived deleting the workout — reappearing
relabelled. `daily_xp.base_xp` keeps its pre-R7 meaning: the checklist's base,
not the day's.

**The leaderboard would have under-reported.** Badge XP is written after the day
has been rebuilt, so `daily_xp` was short by exactly the unlock. Ledger said 94,
rollup said 84. The rollup is now refreshed whenever something unlocks.

**Rebuilding history stamped today's streak on every past day.** A day earned
during a ten-day run should keep that multiplier.
`calculate_current_streak(conn, user_id, as_of=date)` takes the day being scored;
only the display call sites ask about today.
