# Learning

Areas, topics and tracked study sessions — and the phase that finally gives
Knowledge and Focus something real to measure.

## Motivation

Knowledge and Focus ran on checklist data alone from R2 to R4. A ticked "studied
today" box cannot tell twenty minutes of skimming from a three-hour deep session,
and it certainly cannot tell whether that time was spent in one stretch or in
twelve interruptions.

The second question turns out to be the interesting one, and it is what makes
Focus a genuinely different attribute from Knowledge rather than a second name
for the same number.

## What is scored, and what is not

| Recorded | Feeds | Why |
|---|---|---|
| Study minutes | Knowledge | Measured behaviour, over a trailing window |
| Uninterrupted block length | Focus | Deep work is observable in the shape of the time |
| Focus rating (1-5) | **nothing** | A feeling; scoring it pays you to rate yourself a five |
| Difficulty (1-5) | **nothing** | Same |

The original brief asked for the Focus attribute to come from the self-reported
focus rating. R4 had already established why that is wrong — the same reasoning
that keeps mood and sleep quality out of the scoring — so the rating is recorded
and charted, and a test asserts it never reaches the producer.

## Depth: why a duration-weighted mean

Focus asks how deep the work was, which is a question about the *shape* of study
time. Three obvious statistics are all wrong:

| Statistic | Why not |
|---|---|
| Total minutes | That is Knowledge again; it says nothing about depth |
| Longest block | One good session hides a week of fragmented ones |
| Plain mean block | A stray five-minute session drags a great day down |

The last is the subtle one. Two hours of deep work followed by a five-minute
glance at something scores 62 on a plain mean — *worse* than the two-hour block
on its own. That is backwards.

So blocks are averaged weighted by their own length:

```
depth = sum(d²) / sum(d)
```

which answers "for a randomly chosen minute of study, how long was the block it
belonged to?" — exactly what Focus is asking. A short session can then only
dilute the result in proportion to how little of your time it was.

| Day | Depth |
|---|---|
| One 120-minute block | 120 |
| 120 minutes + a 5-minute glance | 115 |
| Four 30-minute blocks | 30 |
| Eight 15-minute blocks | 15 |

The result is scored against `focus_target_block_minutes` (50), so a typical block
at or beyond fifty minutes reads as 100%.

## Blocks

A *block* is not the same thing as a session. Two sessions less than fifteen
minutes apart are one block that happened to be logged twice — getting up for
coffee does not end deep work, and counting it as two short sessions would score
an honest three-hour stretch worse than it deserves.

Three details that matter:

- **Sessions without clock times cannot be joined to anything**, so each stands
  alone. This is why the logger asks for start and end times even though
  duration alone is accepted.
- **Blocks are pooled per day**, so they cannot span midnight and join last
  night's late session to this morning's early one.
- **Overlapping sessions do not double-count** — the block is the union, not the
  sum.

Below `focus_min_window_minutes` (30) of study in the window, Focus stays silent
rather than reporting a number derived from a single short session.

## Knowledge

Study minutes against a weekly target, over a trailing seven-day window — the
same shape training uses, and for the same reason: a day off is not a failure,
and someone who studies hard twice a week would otherwise score 100 on those days
and be invisible on the other five.

The target is pro-rated by how much of the window actually has history, so a
genuine two-hour session on your first day is not measured against a full week.

The weekly target lives on `user_profile.weekly_study_minutes` alongside the
other targets. Areas may carry their own `weekly_target_minutes`, which the UI
shows but the scorer does not yet use — per-area scoring would need a per-area
attribute, and there is no such thing.

## Data model

| Table | Grain | Notes |
|---|---|---|
| `learning_areas` | one domain | Carries a design-system accent name |
| `learning_topics` | one subject | `area_id` nullable — unfiled work still counts |
| `learning_sessions` | **one study session** | The grain of the workspace |

Deliberately shallow: area then topic, and no deeper. A bigger tree is a thing to
maintain rather than a thing that helps you study.

`learning_sessions` has no unique constraint on `(user_id, date)` — several
sessions a day is the normal case, and it is precisely the shape this workspace
exists to measure.

Areas and topics **archive rather than delete**: their sessions are history, and
unfiling them would lose which area the work belonged to.

## Streaks

Consecutive days with at least one session, derived rather than stored — the same
rule `Streak` and `UserLevel` follow in [DATA-MODEL.md](DATA-MODEL.md).

A streak counts as unbroken if you studied *yesterday*, even with nothing logged
today. At 09:00 you have not studied today yet, and a counter that reset overnight
would tell you you had lost a three-week streak every single morning.

## The timer

The session logger's timer is driven by a start **timestamp** held in
`localStorage`, not by a ticking counter. Both halves matter:

- Browsers throttle timers in background tabs, and studying is precisely the
  activity during which you switch away from this tab for an hour.
- Comparing against a stored start means the elapsed time is right the moment you
  look back at it, and survives a reload.

Stopping the timer fills in the date, start and end times, and duration, and
leaves them editable — the timer is a convenience for producing an accurate
record, not a separate kind of entry.

## API

| Method | Route | Purpose |
|---|---|---|
| GET POST | `/api/learning/areas` | List with rollups; create |
| PUT DELETE | `/api/learning/areas/<id>` | Update; archive |
| GET POST | `/api/learning/topics` | List with rollups; create |
| PUT DELETE | `/api/learning/topics/<id>` | Update; archive |
| GET POST | `/api/learning/sessions` | Recent; log one |
| PUT DELETE | `/api/learning/sessions/<id>` | Correct; remove |
| GET | `/api/learning` | The dashboard, composed |

Everything lives in `learning_api.py` as a blueprint, with the auth helper,
database helper and recompute function injected at registration so the module
never imports `app`.

The dashboard reports block depth by calling the *same producer the scorer uses*
rather than recomputing it. Two definitions of "how deep was your work" would
eventually disagree.

## Two bugs worth remembering

**The study-time chart lied by omission.** `/api/learning` returns only days that
have sessions, so plotting it directly drew a straight line from one study day to
the next and a rest day looked like continuity. The client now fills the gaps with
zero — but only between the first and last logged day, because extending the fill
backwards would invent a history of not studying before you started.

**A topic row broke the page on a phone.** Grid items default to
`min-width: auto`, so the row refused to shrink below its three buttons plus the
topic name and pushed the whole document into horizontal scroll. `min-w-0` on the
row and `shrink-0` on the buttons fixed it. A DOM probe comparing
`documentElement.scrollWidth` against `clientWidth` found it in seconds and is
worth reaching for on any new page.
