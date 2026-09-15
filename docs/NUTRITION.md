# Nutrition and Lifestyle

What you ate, how you slept, how much you moved and drank. R4 turns the rest of
the day into data the way [TRAINING.md](TRAINING.md) did for the gym — and it is
what finally gives Recovery something real to measure.

## Motivation

After R3 the app could tell you a great deal about two hours in a gym and
essentially nothing about the other twenty-two. Recovery had been `unobserved`
since R2 because nothing fed it, and Discipline rested entirely on a checklist
you graded yourself.

The tricky part is not the tracking. It is deciding what deserves to move a
score. Half of what this workspace collects is self-reported feeling, and the
project's whole scoring doctrine says a number the app cannot verify does not get
to reach the top of the scale — so the interesting design work here is the line
between *behaviour* and *feeling*.

## What is scored, and what is not

| Recorded | Feeds | Why |
|---|---|---|
| Sleep duration | Recovery | Measured behaviour, and the strongest signal R4 adds |
| Sleep schedule consistency | Discipline | Going to bed at a similar hour is something you control |
| Steps | Stamina | Measured quantity; blends with logged cardio |
| Water and calorie adherence | Discipline | Hitting a target you set is adherence |
| Mood, stress, energy | **nothing** | Feelings, not behaviour |
| Sleep quality | **nothing** | Same |
| Body weight, body fat, waist | **nothing** | Outcomes, not actions |

Scoring a feeling would be dishonest in the same way an unevidenced "I trained"
is, and worse: it would pay you to report feeling good. They are charted instead,
so you can see what correlates with what, which is the useful thing about them
anyway.

Protein feeds **Discipline**, never Strength. Eating protein is not training.

## The food library

233 curated foods in `data/foods.json`, synced into the `foods` table on startup
by `scoring/foodlib.py` — the same arrangement as the exercise library, for the
same reasons.

Everything is stored **per 100 grams**. That is how nutrition data is published,
and more importantly it is the only basis on which recipes compose: a dish is the
weighted sum of its ingredients, which only works if everything shares a unit.
Serving sizes ("1 medium banana", 120g) are a display convenience on top so
nobody has to weigh a banana; grams remain what is stored.

Coverage is deliberately home-cooking-shaped: staples, whole ingredients, and
common dishes, including Indian staples. It has no branded supermarket products.
That is the trade made when choosing a curated file over an external API — no
network dependency on every search, no rate limits, no third-party service to be
down in production, and nothing extra to provision on AWS. Custom foods and
recipes cover the gap.

Alcohol is the one place calories do not reconcile with 4/4/9: ethanol carries
7 kcal/g and is not a macronutrient. The library test exempts wine and spirits
rather than treating it as an error.

## Recipes

The library alone cannot describe what you actually cook. A recipe fixes that:
name the dish, pick the ingredients that went in, and it becomes one entry in the
food picker.

Three decisions:

**A recipe *is* a food.** Saving one writes a row in `foods` with
`source = 'recipe'`, so logging a dish and logging a plain ingredient are the
same operation everywhere downstream. The ingredient breakdown lives in
`recipes` / `recipe_ingredients` for later editing.

**The macros are always derived, never typed.** Correcting an ingredient corrects
every meal already logged with the dish, and the endpoint rescores history when
you save.

**Cooked weight is stored separately from the raw sum.** Rice roughly triples, a
sauce reduces, roasting drives off water. Dividing by the raw ingredient total
when a dish lost a third of its mass would understate its density by a third and
quietly under-report every meal made from it. Leave it blank and the raw sum is
used, which is right for anything assembled rather than cooked.

## Energy balance

TDEE is estimated with Mifflin-St Jeor times an activity multiplier, adjusted by
your goal. Body weight comes from `body_measurements`, which R3 already fills —
a second copy on the profile would drift from the first.

`resolve_targets()` returns a `sources` map saying whether each number was **set**
by you, **estimated** from your profile, or **unknown**. The UI renders estimates
with an asterisk and a caveat, because Mifflin-St Jeor carries roughly 10% error
and activity multipliers considerably more.

When the inputs are missing, `tdee()` returns `None` rather than falling back to
defaults. An app that invented a TDEE would then show you a confident surplus or
deficit against a number it made up — the same failure the attribute statuses
exist to prevent.

`user_profile` lands here rather than in R9 as [DATA-MODEL.md](DATA-MODEL.md)
originally planned, because R4 cannot show energy balance without it. R9 expands
the table rather than creating it.

## Sleep

**Entries are keyed to the date you woke up.** A night spans two calendar dates,
and keying it to the bedtime would file a 01:00 bedtime under the previous day and
make every late night look like a missing night. Waking is the unambiguous end of
the event.

**Duration is a band, not a threshold.** Below target, credit falls off
proportionally. At target and for two hours beyond, full credit. Past that it
tapers toward a floor of 0.6 — eleven hours is not better recovery than eight,
but the evidence that it is actively bad is weak enough that it should not crater
the score either.

**Consistency uses a circular spread.** This is the one piece of arithmetic here
that is easy to get badly wrong. As raw minutes past midnight, bedtimes of 23:50
and 00:10 are 1430 and 10 — a 23-hour gap by plain standard deviation. The most
disciplined possible sleeper would have scored the worst possible consistency. So
the times are rotated around their own circular mean before the spread is taken.

The tolerance is 90 minutes, deliberately forgiving: a weekend lie-in should cost
something, not everything.

## Data model

| Table | Grain | Notes |
|---|---|---|
| `foods` | one food | Library (`user_id IS NULL`), custom, or recipe-produced |
| `recipes` | one dish | Cooked weight stored separately from the raw sum |
| `recipe_ingredients` | one ingredient | Ordered by `position` |
| `food_entries` | **one thing eaten at one meal** | The grain of the workspace |
| `sleep_entries` | one night | Keyed to the wake date; unique per date |
| `lifestyle_days` | one day | Water, steps, sunlight, mood, stress, energy, journal |
| `user_profile` | one user | The minimum needed for a TDEE |

`food_entries` does **not** denormalise macros. They are always the food's
per-100g values times grams, computed on read, so correcting a food's data
corrects every meal that used it instead of leaving a trail of rows frozen at the
wrong numbers.

`lifestyle_days` is one row per user per day rather than a metric-per-row table:
these are always read together for a single date, always upserted together by one
form, and a tall table would turn every dashboard read into a pivot.

## API

| Method | Route | Purpose |
|---|---|---|
| GET POST | `/api/foods` | Library + your own, filtered by `q`, `category`, `source` |
| GET POST | `/api/recipes` | List; build a dish |
| GET PUT DELETE | `/api/recipes/<id>` | Load; rebuild (rescores history); archive |
| GET | `/api/nutrition/<date>` | A day's meals, totals and targets in one response |
| POST | `/api/nutrition/<date>/entries` | Log something |
| PUT DELETE | `/api/nutrition/entries/<id>` | Correct or remove it |
| GET POST | `/api/sleep` | Recent nights; upsert one |
| GET | `/api/lifestyle` | The dashboard |
| GET PUT | `/api/lifestyle/<date>` | One day, merged field by field |
| GET PUT | `/api/profile` | Profile and resolved targets |

Everything lives in `nutrition_api.py` as a blueprint, with the auth helper,
database helper and the recompute function injected at registration so the module
never imports `app`.

A `PUT /api/lifestyle/<date>` **merges** rather than replaces. The water tracker
and the mood scale are separate controls on the same row, and a replacing write
would mean tapping "+250 ml" wiped the mood you recorded an hour earlier.

## A bug worth remembering

Verification screenshots taken at 20:02 in UTC−5 showed an empty day the API
definitely had data for. The cause was `new Date().toISOString().slice(0, 10)` —
the obvious way to get today's date, and wrong: it is UTC, so west of UTC it rolls
over to tomorrow every evening.

`Today.tsx` had already solved this in R2 with a local-date helper and a comment
explaining why; R3 and R4 then each wrote the UTC version again. All four now use
one shared helper in `frontend/src/lib/date.ts`, so there is nowhere left for it
to come back. Timestamps are a different question — an instant in time is
correctly stored as UTC.
