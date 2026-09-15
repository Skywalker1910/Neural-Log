# Analytics

Long-range trends across every workspace: period filters, period-over-period
comparison, an adherence heatmap, and attribute movement. For how attributes
themselves are derived, see [SCORING.md](SCORING.md); for XP, see [XP.md](XP.md).

## Motivation

Every other workspace answers *what did I do today*. This one answers *am I
getting better* — and that question is much easier to answer dishonestly.

The failure mode is specific and it is not subtle. Take a month where sleep was
logged on nine nights. Sum those nine durations, divide by thirty, and the
dashboard reports an average of two hours and twenty minutes — a number that
describes nothing that happened. Do the same with calories and it says you ate
630 kcal a day. Every one of those figures is arithmetically correct and every
one of them is a lie, because the twenty-one unlogged days were counted as
zeroes rather than as absences.

So the whole design is organised around one distinction: **a day with no record
is unobserved, not zero.**

## The three rules

### Unobserved is not zero

Days with no record carry `null`, all the way from SQL to the chart. They are
excluded from averages, and `TrendChart` passes `connectNulls={false}` so the
line *gaps* rather than being drawn through them.

A gap is honest — it says "we don't know". A point on the floor is a claim that
you ate nothing, slept nothing, and studied nothing that day.

Every metric therefore ships `observed_days` next to `days`, and the UI prints
it under the figure. "7h 50m" is a different claim from "7h 50m, averaged over 9
of 30 days", and only the second one can be checked.

### A comparison needs something to compare against

The previous window is the equal-length window immediately before this one, so
"last 30 days" is always measured against the 30 before it.

When that window holds **no** observations, `delta` is `null` rather than a
percentage, and the UI renders no arrow at all — not a grey one, not "0%". An
arrow pointing up would turn *"I started logging sleep this month"* into a claim
that you are sleeping more.

`MetricCard` suppresses its `deltaLabel` along with the delta for the same
reason: "vs previous" sitting beside nothing reads as a comparison that came out
flat, rather than one that could not be made.

### Sums and averages are not interchangeable

Training volume **sums** — two sessions in a week is more work than one. Sleep
**averages** — nine hours across two nights is not better than eight across
seven.

Each metric declares which it is, and the UI renders what it is told rather than
inferring from the unit. Guessing is how a week of sleep becomes 56 hours.

## Metrics

| Metric | Source | Aggregate |
|---|---|---|
| Daily score | `daily_scores` ⨝ `daily_log` | average |
| Discipline | `daily_scores` | average |
| XP earned | `daily_xp` | sum |
| Training volume | `workout_sessions` | sum |
| Working sets | `workout_sessions` | sum |
| Study time | `learning_sessions` | sum |
| Sleep | `sleep_entries` | average |
| Calories | `food_entries` ⨝ `foods` | average |
| Protein | `food_entries` ⨝ `foods` | average |
| Steps | `lifestyle_days` | average |
| Hydration | `lifestyle_days` | average |

Grouping happens in SQL, not Python. Several of these tables hold many rows per
day — 41 sets across 9 sessions, 90 food entries across 10 days — and pulling
them back to sum them in the API would make the endpoint scale with how much you
log rather than with the length of the window being charted.

One response, not eleven requests: `QueryBoundary` wraps a single query, so
eleven calls would mean eleven skeletons and eleven independent error states on
one screen. Same reasoning as `/api/home`.

### Why daily score joins through daily_log

The scoring engine writes `daily_score = 0` for every day the checklist was not
submitted. On that table a zero therefore means *no answer* and also means
*answered No to everything*, and the column cannot tell them apart.

This was a real bug, found in live data rather than in review: a user who had
logged two days — scoring 100 and 95 — was being told their 30-day average was
**13.0**, because thirteen unlogged days were averaged in as zeroes.

`daily_log` can tell them apart, because a row exists there only for a day that
was actually submitted. The metric joins through it, and the average now reads
97.5 across 2 observed days.

Home's 14-day trend had the same phantom zeros, and was fixed in the same way:
`scoring.store.get_daily_scores()` now reads the score through that join and
returns `daily_score = None` plus a `logged` flag. Home is its only caller.

The chart keeps those days as null points rather than dropping them. Filtering
them out would close the gap and pack the logged days together, drawing a
continuous fortnight out of two days - the same lie as plotting zeros, told by
omission instead. Its subtitle now reads "2 of 14 days logged".

## Periods

`7`, `30`, `90`, `365`, `all`. An unknown period is a 400 rather than a silent
fallback to 30 days — a typo should not come back looking like data.

**All time** means *your* all time: it starts at the earliest date you have any
record on, across every workspace. Anchoring it to account creation would pad the
chart with empty months before you started, and a fixed number of days would
silently truncate someone with two years of history. It is capped at
`MAX_ALL_DAYS` (730) because a chart with four years of daily points is
unreadable and the query cost grows without buying an answer.

## The adherence heatmap

One square per day, coloured by how much of that day's Path was completed.

**Adherence rather than XP.** XP is capped and multiplied, so a perfect day
inside a ten-day streak outscores an identical day on day one — the grid would
get brighter toward the right for reasons that have nothing to do with how those
days went. Completion means the same thing on every square.

Five bands rather than a continuous gradient: nobody can read 63% out of a shade,
and the extra resolution renders as noise at 14px per square.

Columns are weeks and rows are weekdays — the GitHub arrangement, which works
because a year fits in 53 columns where 53 rows would not fit on a screen. The
first column is padded so every row is genuinely the same weekday; without that
the grid still renders, but diagonally, and "I never log on Sundays" becomes
unreadable.

Clicking a square opens that day at `/today?date=…`. Today reads its date from
the URL for this reason, which also makes a particular day shareable and lets it
survive a refresh.

It is a CSS grid of `div`s, not Recharts — Recharts has no heatmap, and pulling
300kB in to draw coloured rectangles would be absurd.

## Sparse series need dots

A line is drawn *between* points, so with `connectNulls={false}` a single
observed day surrounded by unlogged ones has nothing to connect to and renders as
literally nothing - the chart looks empty while holding real data.

`TrendChart` therefore draws dots when a series has 12 or fewer observations, and
drops them above that: on a dense series the dots crowd into a thick band and the
trend gets harder to read, which is the problem they were added to solve,
inverted.

## Bugs worth remembering

**An unlogged square has to be visible.** The empty state was first drawn in
`surface-card`, which is the card's own background — so the grid rendered as two
green dots floating in a void, with no sense of the days around them. Empty days
are the context that makes the filled ones mean something.

**`min-width: auto`, for the fourth time.** The Analytics page scrolled sideways
at 390px. `Card` already carried `min-w-0` from the interface pass, but a
`Reveal` sits between `Card` and the grid, and *it* was the grid item inheriting
`min-width: auto`. `min-w-0` now lives in `Reveal` too.

`PageHeader`'s action slot had a related problem: `shrink-0` is right — a pair of
buttons should not be squeezed to fit a long title — but on its own it also lets
the actions grow past the viewport, and any `flex-wrap` inside them never fires
because the container is never the thing under pressure. It now carries
`max-w-full` alongside.
