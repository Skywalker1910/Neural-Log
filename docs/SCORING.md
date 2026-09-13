# Attribute scoring

How daily behaviour becomes the eight character attributes on the Home radar.
For the XP/level/badge rules, see [GAMIFICATION.md](GAMIFICATION.md) - that is a
separate, older system and this one does not replace it.

## Motivation

The product brief asks for RPG-style attributes, and it also says:

> Do NOT simply generate arbitrary scores. Design an extensible scoring engine
> where scores are derived from measurable user behavior.

Those two pull against each other at this stage of the project. The only
behavioural data Neural Log has today is a daily checklist - workouts, sleep,
meals and study sessions arrive in R3, R4 and R5. Deriving a *Stamina* number
from a yes/no checkbox, or an *Agility* number from nothing at all, is exactly
the arbitrary scoring the brief forbids.

So the engine is built to say "I don't know" out loud.

## The opportunity denominator

The core rule:

```
attribute score = earned credit / available credit
```

Available credit comes *only* from checklist items that actually feed that
attribute. An attribute nothing in your Path feeds has a denominator of zero, so
it is **unobserved** rather than 0/100.

This one decision does a lot of work:

- It is what makes it honest to show an attribute as locked instead of guessing.
- It removes the need for artificial score ceilings. When R3 adds measured
  workout data, those signals *enlarge Strength's denominator*, so someone who
  only ticks a checkbox naturally sits lower than someone who also logs real
  training - without a hard-coded cap, and without the number quietly changing
  meaning underneath the user.

## The four statuses

An attribute never silently becomes a number. It reports one of:

| Status | Meaning | Shows |
|---|---|---|
| `locked` | No data source exists yet | The phase that unlocks it (e.g. "R3") |
| `unobserved` | Nothing in your Path feeds it | A prompt to add a relevant item |
| `calibrating` | Observed, too little history | "needs N more days" |
| `active` | A real score | 0-100 plus a confidence |

Today, with only checklist data: Agility is `locked` (needs mobility work from
the Training phase). The rest depend on your Path - the stock Batman Path feeds
Discipline, Knowledge, Strength, Stamina, Recovery and Focus, and leaves Agility
unobserved. Consistency has its own producer (below).

## Resolving an item to attributes

Three tiers, most explicit first:

1. **Explicit override** - an `attributes` map on the item.
2. **Icon vocabulary** - the curated `ICON_KEYS` already attached to every item
   (`workout` feeds Strength 0.6 / Stamina 0.4, `code` feeds Knowledge 0.7 /
   Focus 0.3, and so on).
3. **Keyword match** on the item name, for items left on the default icon.

An item matching none of these feeds **nothing**. It is not swept into a
catch-all, because that would manufacture signal out of an unclassifiable item.

## Graded credit

XP treats any answer as complete (`_item_is_completed` in `app.py`). Attributes
do not, because "woke at 05:00" and "woke after 07:30" are not the same
behaviour:

| Item type | Credit |
|---|---|
| `yes-no` | 1.0 for yes, 0.0 for no |
| `time` | Graded down the option ladder: 1.0 / 0.8 / 0.55 / 0.3 |
| `text` | 1.0 if answered |
| `rating` | Never - self-reflection, not an action |

XP deliberately keeps its old binary behaviour so existing scores and tests stay
stable; only attributes use the graded scale.

## Time model

Scores are an exponentially weighted moving average with a **7-day half-life**,
not a flat window. The brief asks for two things that sound contradictory:

> avoid punishing one missed day too aggressively

> when consistency drops, the relevant metrics should reflect it

A half-life gives both. Measured on real numbers: ten solid days with today
missed still reads 86; four days logged and then five days of silence falls to
34.

Consistency is anchored to **today**, not to your last submission - otherwise
someone who logged four days and then vanished for a week would still read as
perfectly consistent, because the gap would be invisible.

## Configuration

Every constant lives in `scoring/config.py` - half-life, calibration thresholds,
the icon and keyword maps, graded credit ladders, daily-score weights. Nothing
outside that module hard-codes a scoring number, so tuning the product means
editing one file and bumping `ENGINE_VERSION`.

Derived scores are stamped with that version when persisted, so a recomputed row
can be told apart from an original and a weight change never silently rewrites
history.

## Extending it (R3 onwards)

`scoring/engine.py` is pure functions over plain dicts - no database, no Flask,
no import of `app`. A future phase adds a producer that emits the same
`{attribute: {available, earned}}` shape from its own data, and the aggregation,
statuses, confidence and radar need no changes.
