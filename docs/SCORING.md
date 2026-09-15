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

Which attributes can reach `active` depends on what you actually log:

| Attribute | Evidenced by | Since |
|---|---|---|
| Discipline | Checklist, sleep schedule consistency, water and calorie adherence | R2, R4 |
| Strength | Logged sets | R3 |
| Stamina | Logged cardio, steps | R3, R4 |
| Agility | Logged mobility work | R3 |
| Recovery | Sleep duration | R4 |
| Consistency | Showing up to log at all (its own producer, below) | R2 |
| Knowledge | Checklist only until R5 adds study sessions | R2 |
| Focus | Checklist only | R2 |

`locked` is now empty: every attribute has a data source. It is kept as a
mechanism for any attribute added before the phase that feeds it, because
reporting such an attribute as `unobserved` would read as "your Path is missing
something" rather than "this does not exist yet".

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

## Measured signals

From R3 onward the engine stopped running on self-report alone. Each workspace
adds a *producer* in `scoring/producers.py` that turns its own rows into the same
`{date: {attribute: (ratio, weight)}}` shape, and the scoring core never learns
what a workout or a meal is.

| Producer | Feeds | Shape |
|---|---|---|
| `training_ratios` | Strength, Stamina, Agility | Trailing 7-day window vs a weekly target |
| `sleep_ratios` | Recovery, Discipline | Per night; consistency over 14 nights |
| `steps_ratios` | Stamina | Trailing 7-day window |
| `adherence_ratios` | Discipline | Per day, against your own targets |

**Why sleep is per-night and steps are windowed.** Training and steps use a
window because a rest day is not a failure. Sleep is the opposite: you cannot
bank it, and a night you did not get is a real gap in recovery on that day.

**Overlapping producers are averaged, not overwritten.** Two now feed Discipline
and two feed Stamina. `merge_measured()` combines them by weight and keeps the
total, so an attribute evidenced by two independent measurements outweighs one
evidenced by a single measurement. A plain dict update would have let whichever
producer ran last silently win.

## The self-report ceiling

Where an attribute *can* be measured and you only ticked a box, the score is
capped at `self_report_ceiling` (0.5). The top of the scale is reserved for
evidence, because the app cannot tell a hard session from a claim about one.

`MEASURABLE_ATTRIBUTES` is Strength, Stamina, Agility and Recovery. Two
deliberate exclusions:

- **Discipline is not capped**, despite gaining measured signals in R4. The daily
  checklist is already direct evidence of discipline, so sleep consistency and
  adherence are *additional* evidence rather than the only possible evidence.
  Capping it would punish someone for not using a workspace.
- **Knowledge and Focus are not capped** because nothing measures them yet.

The ceiling is 0.5 rather than something higher for a reason that is arithmetic,
not taste. With `measured_weight` 3, an unevidenced claim worth C is only beaten
by real logging once that logging reaches `(4C - 1) / 3` of the target: 67% at
C=0.75, but 33% at C=0.5. A ceiling of 0.75 meant honestly logging a light week
scored *lower* than claiming a perfect one and logging nothing. An app that
punishes honest logging is worse than one that does not measure at all, and a
test asserts the incentive points the right way for both training and sleep.

## What is deliberately never scored

Mood, stress, energy, sleep quality and body measurements are recorded and
charted but never feed an attribute.

The first four are self-reported *feelings* rather than behaviour. Scoring them
would be dishonest in the same way an unevidenced "I trained" is, and worse: it
would pay you to report feeling good. Body weight is a measurement, but it is an
outcome rather than an action, and rewarding it would reward the wrong thing.

Protein intake feeds Discipline, as adherence to a target you set - never
Strength. Eating protein is not training.

## Extending it

`scoring/engine.py` is pure functions over plain dicts - no database, no Flask,
no import of `app`. A future phase adds a producer that emits the same shape from
its own data, registers it in `store.recompute_scores`, and the aggregation,
statuses, confidence and radar need no changes.

Two things a new producer must get right, because both have already been got
wrong here:

1. **Include your dates in `all_dates`.** A day whose only entry is a meal still
   has to appear in the series, or it silently vanishes from every score.
2. **Say nothing before your first observation.** Back-filling zeroes invents a
   history of not doing the thing, and the EWMA then carries that invented past
   forward for a fortnight.
