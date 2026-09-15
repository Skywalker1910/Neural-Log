# Changelog

Kept from Phase 1 onward. Format is loose - what changed and why, newest first.

## R8 - Analytics

Long-range trends across every workspace. Full write-up in
[ANALYTICS.md](ANALYTICS.md).

- **Eleven metrics, one response**, spanning discipline, XP, training, learning,
  nutrition, sleep and lifestyle - with period filters from 7 days to all time,
  and every window compared against the equal-length window before it.
- **Unobserved is not zero.** A day with no record carries `null` from SQL to the
  chart; averages divide by observed days, the trend line gaps rather than being
  drawn through the absence, and every figure prints the denominator it was
  computed with ("averaged over 9 of 30 days").
- **No comparison without something to compare against.** An empty previous
  window produces no delta and no arrow, rather than "+100%".
- **An adherence heatmap**, one square per day, coloured by Path completion
  rather than XP - XP is capped and multiplied, so it would brighten toward the
  right for reasons unrelated to the days themselves. Clicking a square opens
  that day, so Today now reads its date from the URL.
- **Attribute movement**: the radar's existing previous-period overlay, filled
  with where each attribute stood when the window opened.
- **Excel export** surfaced on the page, pointing at the endpoint the classic
  dashboard already used.

It caught a real bug in live data. The engine writes `daily_score = 0` for every
day the checklist was not submitted, so on that table a zero means "no answer"
and also means "answered No to everything". A user who had logged two days -
scoring 100 and 95 - was being told their 30-day average was **13.0**. The metric
now joins through `daily_log`, which only has a row for a day actually submitted,
and reads 97.5 across 2 observed days.

Two shared primitives gained `min-w-0` (`Reveal`) and `max-w-full`
(`PageHeader`'s action slot) - the `min-width: auto` trap, fourth occurrence.

## Interface pass - design language and the cutover

Six phases of redesign were unreachable in normal use. `/login` redirects to `/`,
which served the classic Jinja dashboard, so signing in always landed there - the
new workspaces were only visible to someone who typed `/app` by hand. Reported as
"I don't see the workout library, nutrition option etc", which was accurate.

- **`/` now serves the SPA.** The classic dashboard moves to `/classic`, `/app`
  redirects so existing bookmarks work, and a root catch-all serves the shell for
  client-side routes - a refresh on `/training/session/12` no longer 404s. Unknown
  paths under `/api`, `/static` and `/assets` 404 instead, decided before the auth
  check so a mistyped API path doesn't answer 302-to-login.
- **The design tokens were retuned to Apple's design language** - true black
  ground, frosted translucent chrome with `saturate(180%)`, a tighter bimodal type
  scale, larger radii, pill buttons, one easing curve. Done at the token layer, so
  all ten workspaces inherited it at once. The category accents were left alone:
  they are data identity, not chrome.
- **The custom PNG artwork is gone**, replaced by Lucide everywhere. It was line
  art drawn for a light ground and needed a pale disc behind every glyph to be
  visible, which rendered a checklist as a column of white circles. `ItemIcon`
  replaces `ArtworkBadge`, takes an accent colour, and infers a glyph from the
  question text when the server's icon key is `default` - otherwise four stock
  items drew the same placeholder.
- **A new sign-in page** in the same language, self-contained rather than pulling
  in the classic light stylesheet.
- **Three horizontal-overflow bugs at 390px**, all the `min-width: auto` trap:
  a `DataTable` inside a `Card`, the Training routine rows, and the Today summary
  card. `min-w-0` now lives in `Card` itself, since this was its third occurrence.

## R7 - Gamification depth

XP had only ever come from the daily checklist. Four phases of workspaces awarded
nothing, and the leaderboard ranked people on box-ticking. Full write-up in
[XP.md](XP.md).

- **A per-action XP ledger** (`xp_transactions`) replaces day-granularity XP as
  the authority. `daily_xp` is kept as a rollup because the leaderboard reads it.
  Each row records the reason, the multiplier, whether a cap reduced it, and
  whether it was measured or claimed.
- **Every workspace earns.** Training, learning, nutrition and lifestyle all pay,
  sized by what is actually in them.
- **Evidence beats a claim.** Ticking "I trained" on a day you also logged pays
  40%, because the sets are already being paid for that behaviour. Not zero - the
  checklist is still the daily ritual.
- **Caps and floors.** Per-source daily caps, a whole-day ceiling, and floors so
  a three-minute study session or a warm-up-only workout earns nothing.
  `capped_from` is recorded, so hitting a cap is visible rather than unexplained.
- **A configurable level curve**, defaults reproducing the old hard-coded one
  exactly - a test pins that so nobody's level moved.
- **23 achievements across six categories**, up from 8, covering the workspaces
  that had nothing. They became data - a metric and a threshold - rather than
  lambdas, which is what lets a locked one report "8 of 10".
- **The Achievements page**: category filters, tier styling, progress on every
  locked achievement, an XP breakdown by source, the evidenced-vs-claimed split,
  and the ledger itself with reasons and caps.
- **Unlocking no longer waits for a checklist submission.** Logging your first
  workout unlocks it there and then.

### Bugs found

- **The rollup fed itself.** `_write_rollup` wrote the day's full base into
  `daily_xp.base_xp`, which `recompute_day` reads back as the CHECKLIST base. A
  workout's XP was read back as a checklist award on the next rebuild and
  survived deleting the workout, reappearing relabelled.
- **The leaderboard would have under-reported.** Badge XP is written after the
  day is rebuilt, so `daily_xp` was short by exactly the unlock - ledger 94,
  rollup 84.
- **Rebuilding history stamped today's streak on every past day.** Found by a
  user coming out 1 XP lighter than they went in, because their streak had since
  lapsed. `calculate_current_streak` now takes an `as_of` date.
- **Achievement metrics disagreed with the XP floors.** A warm-up-only workout
  unlocked "Rack Pulled" while earning nothing. Both now read `xp_config`.
- **The rebuild script did not unlock anything.** Seven logged workouts with
  "Logged your first workout" still locked, reading "7 of 1" - progress was
  right, and unlocking simply never ran because it happens on write paths.

### Also

`docs/CI.md` corrected: required approvals were dropped from 1 to 0. They never
protected against outsiders - only write access does - so on a one-maintainer
repo the rule gated nobody but the maintainer, who cannot approve their own PR.
Everything else stayed, including the force-push block.

## R6 - Goals and Habits

The Paths JSON system moved into SQL, and goals were built on top. Full write-up
in [HABITS.md](HABITS.md).

### R6a - the migration

The riskiest change so far: Paths are the one feature used every single day, and
three different clients consume them.

- **It was a move, not a rewrite.** `load_user_paths()` returns byte-for-byte the
  payload it always did, so the Jinja app at `/`, `static/js/app.js` and the SPA's
  Today page all kept working untouched. The 245 tests predating the migration
  passed against the new storage without modification.
- **The string ids were carried across**, not replaced with integers -
  `daily_log.path_id`, `users.selected_path` and every client already reference
  them. Verified on the real database: 40 of 40 item ids survived.
- **The import is lazy, per-user and recorded** in `habit_imports`. Without that
  marker, a later edit removing a path would be silently undone on the next load.
- **`habit_completions` does not replace `daily_log.payload_json`.** The snapshot
  stays the authority for scoring - it is what makes rescoring safe - and the new
  table is the queryable index a JSON blob cannot be. Written in one transaction.
- **Schedules**: daily, weekdays, specific days, N times a week. Every migrated
  item became `daily`, which is what a path item has always been.
- **Per-habit streaks and adherence**, which is what the conversion was for.

Two bugs the new tests caught:

- A freshly registered account had no habits at all until it happened to hit a
  path endpoint. Registration now seeds them.
- The streak counter treated a logged "No" the same as "nothing logged yet". The
  first is a miss and breaks the streak; the second is just 09:00.

### R6b - goals, milestones, tasks

- **Nothing here feeds an attribute**, enforced structurally: `goals_api.py` is
  the only workspace blueprint with no recompute function injected, and a test
  asserts that declaring a goal achieved and completing every milestone moves no
  score. A goal is an intention plus a number you type in.
- **Progress has a source** - habits, milestones, metric or none - and the UI
  always shows which. Linked habits outrank a typed-in metric, so a goal claiming
  10 of 10 sessions while the habit behind it was never done reads 0%.
- **`none` returns null, not 0%.** Plenty of real goals have no number, and 0%
  would read as failure where the honest answer is "nothing to measure".
- **Abandoned is a status, not a deletion.** Goals you gave up on are the most
  informative in hindsight.
- Adherence divides by days elapsed rather than days the habit was due, so a
  once-a-fortnight habit cannot read as perfect while the goal goes nowhere.
- Tasks are deliberately thin - no projects, subtasks or dependencies.

### Caught in verification

- **`/api/habits` returned 40 habits**, because the four stock paths share most of
  their items and the list showed "What time did you wake up?" four times. It is
  now scoped to the path you are following, with `?all=1` for everything.
- **The goal cards broke the page on a phone.** Grid items default to
  `min-width: auto`, so a card would not shrink below its header and pushed the
  document into horizontal scroll - the same trap R5 hit with topic rows. The DOM
  probe that found it is worth reaching for on every new page.

### Operational

A database backup was taken before the migration. The existing `*.db` ignore rule
did not cover `.bak`, so it was briefly staged for commit; `.gitignore` now covers
database backups.

## R5 - Learning

Knowledge and Focus stopped running on checklist data alone. Full write-up in
[LEARNING.md](LEARNING.md).

- **Three tables** (`migrations/005_learning.sql`) - areas, topics and sessions,
  plus `weekly_study_minutes` on `user_profile`. Deliberately shallow: a deeper
  tree is a thing to maintain rather than a thing that helps you study.
- **`producers.learning_ratios()`** - study minutes feed Knowledge over a trailing
  window; block depth feeds Focus.
- **`learning_api.py`** - areas, topics, sessions and a composed dashboard.
- **Learning workspace** - a persistent session timer, manual logging, weekly
  goal, study-time trend, topic distribution, streak and block depth.

### The Focus signal

The brief asked for Focus to come from a self-reported focus rating. R4 had
already established why that is wrong, so Focus is derived from the *shape* of
study time instead - one two-hour block is deeper work than four half-hour ones
for the same total, and that is observable. The rating is recorded and charted,
and a test asserts it never reaches the producer.

Depth is a **duration-weighted mean block length**, `sum(d^2)/sum(d)`. The three
obvious statistics are all wrong: total minutes is Knowledge again, longest block
lets one good session hide a fragmented week, and a plain mean lets a stray
five-minute session drag a great day down - 120 minutes plus a 5-minute glance
scores 62, worse than the 120 alone. Weighting by duration asks "for a randomly
chosen minute of study, how long was the block it belonged to".

Sessions less than 15 minutes apart merge into one block; blocks are pooled per
day so they cannot span midnight; overlapping sessions do not double-count.

Knowledge and Focus join `MEASURABLE_ATTRIBUTES`. Only Discipline and Consistency
remain outside it now - the checklist is already direct evidence of discipline,
and nothing self-reports consistency at all.

### Bugs found in verification

- **The study-time chart lied by omission.** The endpoint returns only days with
  sessions, so the line ran straight from one study day to the next and a rest day
  read as continuity. Gaps are now filled with zero - but only between the first
  and last logged day, since extending the fill backwards would invent a history
  of not studying before you started.
- **A topic row broke the page on a phone.** Grid items default to
  `min-width: auto`, so the row refused to shrink below its three buttons and
  pushed the whole document into horizontal scroll. A DOM probe comparing
  `scrollWidth` against `clientWidth` located it immediately, and the same probe
  cleared Home, Today, Training, Nutrition and Lifestyle.
- **A ref was read during render** in the session timer. The ref was redundant -
  the effect already depends on the stored value and can close over it.
- **The "not scored" badge wrapped onto two lines** here and on Lifestyle.

### Streaks

Consecutive days studied, derived rather than stored. A streak counts as unbroken
if you studied yesterday even with nothing logged today - at 09:00 you have not
studied yet, and a counter that reset overnight would report a lost streak every
single morning.

## R4 - Nutrition and Lifestyle

Recovery stopped being `unobserved`, and `locked` is now empty: every attribute
has a data source. Full write-up in [NUTRITION.md](NUTRITION.md).

- **Seven tables** (`migrations/004_nutrition_lifestyle.sql`) at the grain of one
  thing eaten at one meal. `food_entries` deliberately does not denormalise
  macros - they are the food's per-100g values times grams, computed on read, so
  correcting a food corrects every meal that used it.
- **233-food curated library** in `data/foods.json`, per 100g because that is the
  only basis on which recipes compose. Chosen over an external API: no network
  dependency on every search, no rate limits, nothing extra to provision on AWS.
- **Recipes.** Describe a cooked dish, pick the ingredients, and it becomes one
  entry in the food picker. A recipe *is* a food (`source = 'recipe'`), so logging
  a dish and logging an ingredient are the same operation downstream. Macros are
  always derived, and editing a dish rescores every meal already logged with it.
- **Cooked weight is stored separately from the raw ingredient sum**, because rice
  absorbs water and roasting drives it off. Dividing by the raw total for a dish
  that lost a third of its mass would under-report every portion of it.
- **Sleep, hydration, steps, sunlight, mood, stress, energy, journal.**
- **Energy balance** against a Mifflin-St Jeor TDEE, with a `sources` map marking
  every number as set / estimated / unknown, and `tdee()` returning None rather
  than guessing.
- **`user_profile` arrived in R4 rather than R9**, since energy balance cannot
  exist without it. R9 expands the table rather than creating it.

### Scoring

Four new measured signals: sleep duration to Recovery, sleep schedule consistency
to Discipline, steps to Stamina, water and calorie adherence to Discipline.

- **Recovery joined `MEASURABLE_ATTRIBUTES`; Discipline deliberately did not.**
  Sleep is now loggable, so an unevidenced Recovery claim gets the 0.5 ceiling.
  But the checklist is already direct evidence of discipline, so sleep consistency
  and adherence are additional evidence rather than the only possible evidence -
  capping it would punish someone for not using a workspace.
- **Sleep is scored per night while steps use a trailing window.** Not an
  inconsistency: a rest day is not a failure, but a night you did not get is a
  real gap in recovery on that day. You cannot bank sleep.
- **Sleep consistency uses a circular spread.** As raw minutes past midnight,
  bedtimes of 23:50 and 00:10 look 23 hours apart, so the most disciplined
  possible sleeper would have scored the worst possible consistency.
- **Calories are scored two-sided.** A one-sided "more is better" reading would
  call a 4,000 kcal day against a 2,000 target perfect adherence.
- **`merge_measured()`** averages by weight where producers overlap. Two now feed
  Discipline and two feed Stamina; a plain dict update would have let whichever
  ran last silently win.
- **Mood, stress, energy and sleep quality are never scored.** They are
  self-reported feelings, and an app that scored them would be paying you to
  report feeling good.

### Bugs found and fixed

- **"Today" was UTC, not local.** `new Date().toISOString().slice(0, 10)` is the
  obvious way to get today's date and it is wrong: west of UTC it rolls over to
  tomorrow in the evening. At 20:02 in UTC-5 the Nutrition page asked for
  2026-09-15 and showed an empty day the API had 2,152 kcal of data for. Training
  had it too, where it would have dated a new workout tomorrow. `Today.tsx` had
  already solved this in R2 with a comment explaining why, and R3 and R4 each
  wrote the UTC version again - so all four now share one helper in
  `frontend/src/lib/date.ts`.
- **`entry_macros()` was handed a `sqlite3.Row`**, which has no `.get()`, so every
  request for a day with a logged meal raised AttributeError.
- **A partial profile PUT hit NOT NULL constraints.** "Just set my calorie target"
  merged `activity_level` and `goal` to None, which failed for any user without a
  profile row - i.e. on everyone's first edit.
- **`TrendChart` drew a 1-5 mood rating on an axis up to 8**, which makes a good
  week look like a mediocre one. It now takes an optional fixed `domain`.

## R3 - Training

The first feature that feeds the attribute engine measured data instead of
self-report. Full write-up in [TRAINING.md](TRAINING.md).

- **Six new tables** (`migrations/003_training.sql`) at the grain of the
  individual set. `workout_sessions` deliberately has no `UNIQUE(user_id, date)` -
  a morning lift and an evening run are two sessions. The exercise library uses
  two *partial* unique indexes, because SQLite treats `NULL`s as distinct and a
  plain `UNIQUE(user_id, slug)` would allow ten copies of every shared exercise.
- **85-exercise library** in `data/exercises.json`, synced on startup. Exercises
  removed from the file are archived, never deleted - someone may have logged sets
  against them.
- **`scoring/producers.py`**, the seam that turns sets into the same
  `(attribute, ratio)` shape the checklist produces. Agility is no longer `locked`:
  mobility work feeds it.
- **Routines** - named, ordered plans with target sets and reps. Starting one
  inherits its name and pre-fills the session. The plan is never persisted as
  training data; only what you actually lift is saved, and so only that is scored.
- **Training UI** - dashboard (volume trend, muscle balance, records, sessions,
  measurements), focused set logging, library picker, rest timer.

### Scoring problems found and fixed

- **The app paid you to lie.** With self-report capped at 0.75, ticking the
  "Workout" checkbox scored 75 while honestly logging a light week scored 62. The
  breakeven is `(4C−1)/3` - 67% of target at C=0.75, 33% at C=0.5. The ceiling is
  now 0.5 for measurable attributes only, and a test asserts every level of real
  training beats claiming it.
- **Starting was punished.** The first training day was measured against a full
  week's target, scoring a genuine session at 27%. The target is now pro-rated by
  the observed window.
- **Deleting all workouts left Strength at 100.** `recompute_scores()` returned
  early with no source data, orphaning the derived rows. `_prune_orphaned_scores()`
  removes rows whose source is gone.
- **Consistency scored a 5-day lapse as 100%.** The window was anchored to the
  last log rather than to today, so stopping looked identical to never starting.

### Training UI defects caught in verification

- **`StatCard` truncated its own value.** The hint was `shrink-0` while the value
  was allowed to truncate - exactly backwards - so a 16,710kg total rendered as
  "1".
- **Four-figure chart values rendered as "000"**, overflowing the axis gutter.
  `TrendChart` now compacts at 1,000 (`4.5k`) and the tooltip shows the full
  number.
- **The logging form remounted its inputs on every render.** Server sets were
  remapped through a key-minting function outside `useMemo`, so React saw fresh
  keys each pass and would have dropped focus mid-typing.
- **"Last time" quoted the session back at you.** Reopening a saved workout showed
  its own sets as previous performance, and its own lifts as the all-time best.
  `/api/exercises/<id>/history` now takes `?exclude_session=<id>`.
- **Routine-seeded sessions would have saved blank sets.** Planned rows counted
  toward "working sets" before anything was typed, and would have persisted as
  real logged sets on finish.

### Tooling

- `scripts/shoot.mjs` gained `SHOOT_EVAL`, which runs a snippet in the page before
  capture - modals, drawers and timers only exist after a click, so there was no
  URL that rendered them. It reports exceptions, which immediately caught a
  malformed snippet that had been silently producing empty screenshots.

## R2 prerequisites - scoring integrity fixes

Found while mapping the codebase for R2's attribute engine. All three are bugs in
already-shipped behaviour that would have poisoned any score derived from it.

- **Completion was measured wrong.** The client computes `completion_percent` as
  *answered* / total, and the wizard refuses to advance without an answer - so it
  reported 100% for a day answered entirely "No". The `perfect-day` badge keyed off
  it, so it fired on days that were nothing of the sort (the live account holds one
  such badge, earned on a 53%-complete day). Completion is now computed server-side
  in `compute_completion_percent()` from `_item_is_completed` and item weights; the
  client's number is ignored for scoring.
- **Stock Paths never received the shipped weights and icons.** A per-user path file
  is written once and never re-seeded from `DEFAULT_PATH_LIBRARY`, so accounts
  created before weights/icons existed kept `weight=1, icon='default'` on every
  item - flattening XP (a weight-3 item scored like a weight-1 one) and showing the
  same fallback artwork on every wizard step. `repair_default_path_items()` now
  re-attaches them on load, matching by exact item name and only touching items that
  still look untouched, so deliberate user edits to a stock Path survive.
- **Migrations never ran under gunicorn.** `init_db()` was called only under
  `if __name__ == '__main__'`, so a WSGI-served deployment would start against an
  unmigrated database. It now runs at import time (it is idempotent).
- **`pytest` did not work as documented.** Bare `pytest` failed with 32
  `ModuleNotFoundError` - only `python -m pytest` worked, because it puts the cwd on
  `sys.path`. Added `pytest.ini` with `pythonpath = .` so the documented command is
  the working one.

## Redesign R1 - Foundation

First phase of the product redesign (see [ROADMAP.md](ROADMAP.md)). Builds the
foundation the remaining nine phases sit on, without breaking the running app.

- **Frontend stack**: React 19 + Vite + TypeScript SPA in `frontend/`, served by
  Flask at `/app`. The classic Jinja app keeps serving `/` until R2 flips it. In
  dev, Vite proxies `/api` to Flask so the existing session cookie works unchanged -
  no CORS, no auth rewrite.
- **Design system**: dark charcoal token set (surfaces, ink, one brand accent, six
  category accents), Inter self-hosted, a six-step type scale with tabular numerals.
  Replaces the light theme from the previous visual pass. See
  [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md).
- **App shell**: collapsible sidebar on desktop, thumb-reachable bottom tab bar plus
  overflow sheet on mobile, ten routed sections with honest "arrives in phase N"
  placeholders.
- **Component library**: Card, MetricCard, StatCard, ProgressCard, ProgressRing,
  AttributeBadge, ArtworkBadge, Button, Badge, EmptyState, Skeleton, Modal,
  ConfirmationDialog, DataTable, QueryBoundary, plus lazy-loaded radar and trend
  charts. Browsable at `/app/_design`.
- **Data layer**: typed fetch client + TanStack Query. `QueryBoundary` makes
  loading/error/empty/retry structural rather than per-component. The client detects
  Flask's *redirect*-to-login (rather than a 401) and bounces to sign-in properly.
- **Migrations**: numbered SQL files + a `schema_migrations` ledger replace the
  ad-hoc `CREATE TABLE IF NOT EXISTS` block. Resolves `migrations/` from `__file__`,
  not cwd - the test suite chdirs, so a cwd-relative path would break everything.
  See [DATA-MODEL.md](DATA-MODEL.md).
- **Icons**: Lucide for UI chrome; the custom PNG artwork kept for achievements and
  attributes, now on a light disc since near-black line art disappears on a dark UI.
- **Performance**: Recharts (~300kB) split into its own lazy chunk - main bundle
  dropped from 716kB to 316kB.
- **Tooling**: `scripts/shoot.mjs` captures authenticated SPA screenshots over the
  DevTools Protocol (injects the session cookie, which plain headless `--screenshot`
  cannot).
- Tests: 16 -> 22, covering the migration ledger, idempotency, data preservation,
  and the SPA mount point.

## Visual redesign - light theme & icon system

Not one of the numbered roadmap phases - a UI pass that cuts across all of them.

- **Theme**: replaced the "Batman Dark Noir" look (animated conic-gradient spinning
  button borders, neon text-shadow glows, heavy colored box-shadows, dark gradient
  header) with a light, minimal theme - flat cards, a single restrained red accent,
  soft 1-2px shadows, no glow/animation effects.
- **Consolidation**: `login.html` had its own full inline `<style>` block (a second,
  slightly different copy of the theme) and never linked `style.css`; `admin.html`
  linked it but also carried its own inline `<style>` block. Both are gone now - one
  shared stylesheet, one set of tokens.
- **Icon system**: wired the custom-generated artwork in `artifacts/` in as real
  per-item icons instead of sitting unused on disk. `scripts/build_icons.py`
  (Pillow, dev-time only) auto-detects each source image's subject and crops a
  square around it, producing the 256x256 set in `static/images/icons/`. Every
  default-Path checklist item now carries a matching `icon` key (`ICON_KEYS` in
  `app.py`); custom items get an icon-picker (a grid of the same images) instead of
  a free-text emoji field. Rendered as small circular badges (`.icon-badge`/
  `.icon-badge-sm`) in the wizard, the header (replacing the 👤︎/🛡 emoji), the
  admin users table, and the custom-item list/preview.
- **Fix**: found while touching this code - `renderCustomItems()` (a dead leftover
  from an earlier "inline checklist form" implementation, targeting a
  `#customItemsContainer` that no longer exists in the DOM) was still being called
  from the real add/edit/delete custom-item paths and threw a `TypeError` every
  time, silently preventing the modal from closing and the visible list from
  refreshing after adding, editing, or deleting a custom item. Removed the dead
  function (and `removeCustomItem()`/`generateCustomItemInput()`/
  `toggleCustomSubResponse()`/`selectCustomRating()`, only ever called from it) and
  fixed the three call sites to refresh via the real `displayCustomItems()`.
- **Fix**: `.step-icon img { transform: scale(4) }` - a hack that blew up a 50px
  image 4x, presumably compensating for undersized source art - removed now that
  icons are generated at a proper resolution.

## Phase 2 - Gamification system

- **Add**: `daily_xp` and `user_badges` SQLite tables (`init_db()`), created
  alongside the existing ones.
- **Add**: per-item `weight` (1-5) on Path checklist items (`normalize_checklist_items`,
  Path editor UI); default Paths tuned with heavier weights on
  workout/study/deep-work items. See `docs/GAMIFICATION.md` for the full scoring spec.
- **Add**: `calculate_daily_xp()`, `compute_level()`, `award_daily_xp()`, and
  `evaluate_badges()` in `app.py` - the scoring engine, hooked into the existing
  `/api/activities` "Daily Checklist" submission path.
- **Refactor**: pulled the streak-counting loop out of `/api/stats` into a shared
  `calculate_current_streak()`, since the XP engine needed the same logic.
- **Add**: `GET /api/gamification/summary` (XP/level/streak/badges) and
  `GET /api/leaderboard/<overall|monthly>` endpoints.
- **Add**: a Level/XP banner, Badges modal, and Leaderboard modal on the main
  dashboard (`templates/index.html`, `static/js/app.js`, `static/css/style.css`); a
  "badge unlocked" toast on checklist submission.
- **Add**: `tests/test_gamification.py` covering XP weighting, level thresholds, the
  streak multiplier, same-day resubmission (no double-counting), badge unlocks, and
  both leaderboards. Shared test fixtures moved to `tests/conftest.py`.

## Phase 1 - Foundation

- **Fix**: `handleDailyChecklistSubmit()` in `static/js/app.js` referenced
  `completionPercent`, a variable only ever declared inside an unrelated function
  (`populateWizardFromActivity()`). Submitting the daily checklist threw a
  `ReferenceError` client-side. Now computed locally from the answered/total custom
  item counts, same formula as before.
- **Fix**: `templates/index.html` had two elements with `id="checklistWizard"` - a
  dead static block of hardcoded checklist markup (wake time / coffee / breakfast /
  exercise / lunch / dinner radios) left over from before the dynamic wizard was
  introduced, and the real container the wizard populates. `getElementById` only
  ever found the first (dead) one. Removed the legacy block, along with the
  now-unused `toggleSubOptions()` / `getRadioValue()` helpers that only served it.
- **Change**: `SECRET_KEY`, Flask debug mode, and the SQLite DB path now come from
  environment variables (`python-dotenv` + `.env`) instead of being hardcoded in
  `app.py`. See `.env.example`.
- **Add**: `pytest` smoke tests (`tests/test_app.py`) covering registration/login,
  activity CRUD, the daily checklist submission path, and the paths API.
- **Add**: `gunicorn` to `requirements.txt` in preparation for Phase 3 (AWS).
- **Add**: this `docs/` set (`ARCHITECTURE.md`, `ROADMAP.md`, `CHANGELOG.md`) and a
  rewritten root `README.md`.
