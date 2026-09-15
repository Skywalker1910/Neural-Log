# Roadmap

Neural Log began as a daily checklist with XP attached. It's becoming a personal
operating system: track the things that actually move your life - training, food,
sleep, study, goals - and watch a character sheet built from your own behaviour
grow or shrink accordingly.

This tracks where that's headed, in order.

## Status

| Phase | What | Status |
|---|---|---|
| - | Foundation - bug fixes, config hardening, tests, docs | Done |
| - | Gamification - XP, levels, streaks, badges, leaderboards | Done |
| - | Visual pass - light theme, custom icon set | Superseded by R1 |
| R1 | Redesign foundation - toolchain, design system, shell, migrations | Done |
| R2 | Home + Today - attributes, radar, daily score, streaks | Done |
| R3 | Training - routines, exercise library, set logging, analytics | Done |
| R4 | Nutrition + Lifestyle - macros, hydration, sleep, mood | Done |
| R5 | Learning - subjects, sessions, knowledge analytics | Backend done, UI next |
| R6 | Goals + Habits - milestones, routines, streak sources | Not started |
| R7 | Gamification depth - achievements, XP ledger, attributes | Not started |
| R8 | Analytics - long-range trends, calendar, comparisons | Not started |
| R9 | Onboarding - profile, baselines, BMR/TDEE, goal setup | Not started |
| R10 | Polish - responsive, animation, a11y, performance | Not started |
| Ship | **Re-platform to Next.js + DynamoDB, then deploy to AWS** | Not started |

Shipping is last, and the re-platform goes with it. An earlier plan put both after
R2, reasoning that the data model needed to stop moving before the DynamoDB key
design could be done. That reasoning does not survive inspection: the data model
keeps moving all the way through R6 - R3 adds workouts, exercises and sets, R4 adds
nutrition and sleep, R5 adds learning sessions, R6 adds goals and habits. Porting
after R2 would mean revisiting the key design in every one of those phases.

So the app stays on Flask + SQLite for the whole build. That keeps feature velocity
high (no toolchain switch mid-stream, the Python test suite and scoring engine keep
working) and defers the port to the point where the schema is actually final. The
cost is rewriting the Flask endpoints in TypeScript at the end - mechanical work,
and far less of it than redesigning DynamoDB keys eight times.

The React components are unaffected either way: they carry over to Next.js close to
unchanged, so everything built in R2-R10 keeps its value.

## Done before the redesign

**Foundation.** Fixed the wizard's `completionPercent` crash, removed duplicate
`#checklistWizard` markup, moved `SECRET_KEY`/debug/DB path into environment
variables, added a pytest smoke suite.

**Gamification.** Weighted checklist items award `weight * 10` XP; a level curve of
`50 * (level-1)^2` cumulative; a streak multiplier of +2%/day capped at +50%; eight
badges; overall and monthly leaderboards. Full spec:
[GAMIFICATION.md](GAMIFICATION.md).

**Visual pass.** A light minimal theme and a custom icon set generated from hand-made
artwork. The theme was replaced by R1's dark design system; the artwork survives, now
reserved for achievements and attributes.

## R1 - Redesign foundation (done)

The old frontend was 1,791 lines of string-template DOM code in one classic script.
Ten workspaces built that way is how you get the dead-code bugs the foundation phase
had to clean up. R1 replaced the *frontend* stack without touching the backend's
working endpoints:

- **React + Vite + TypeScript** SPA in `frontend/`, served by Flask at `/app`. Flask
  becomes a JSON API - 22 of its 26 routes already were.
- **Design system** - dark charcoal tokens, Inter, a type scale, category accents.
  See [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md).
- **App shell** - sidebar on desktop, bottom tab bar on mobile, ten routed sections.
- **Component library** - cards, metrics, rings, tables, modals, empty states,
  skeletons, chart wrappers.
- **Data layer** - typed API client plus TanStack Query, so loading/error/empty/retry
  is structural rather than per-component.
- **Migrations** - numbered SQL files and a ledger table, replacing ad-hoc
  `CREATE TABLE IF NOT EXISTS`. See [DATA-MODEL.md](DATA-MODEL.md).

The classic Jinja app still serves `/`. R2 flips the default over.

## R2 - Home and Today

The phase that makes the redesign worth using.

- **Scoring engine** - a single configurable module deriving the eight attributes
  (Discipline, Knowledge, Strength, Stamina, Agility, Recovery, Consistency, Focus)
  and the daily/discipline scores from logged behaviour. Formulas live in one place
  with adjustable weights, and use rolling averages so one missed day doesn't crater
  a score.
- **Home** - level, XP, discipline score, streaks, the attribute radar, today's
  progress, weekly trends, active goals, recent achievements, quick actions.
- **Today** - the full day as sections and a timeline; complete, skip, reschedule.
- **Seed data** - realistic demo data behind an explicit demo mode, so dashboards can
  be developed and reviewed without waiting weeks for real history.

- **Motion system** - the animation layer every later phase builds on, added here
  rather than saved for R10 so eight phases of UI are not retrofitted at the end.
The flip of `/` from the Jinja app to the SPA was planned for this phase and has
been **moved** - see *Retiring the Jinja app* below. Today replaces the checklist
wizard, but the wizard is only part of what that page does.

The Flask endpoints are now load-bearing for the whole build rather than throwaway
(the port moved to the end), so they are built properly - just not elaborately.

## Retiring the Jinja app

`/` stays on the legacy Jinja dashboard until the SPA can actually replace it. The
checklist wizard is the obvious feature, and Today covers that - but the same page
also carries Path management, custom checklist items, profile and password, the
badges and leaderboard modals, milestone insights, and Excel export. Flipping after
R2 would have traded a complete app for a prettier one missing most of its surface.

Parity is reached phase by phase, not in one step:

| Legacy feature | Replaced in |
|---|---|
| Daily checklist wizard | R2 (done - Today) |
| Stats, streaks, progress chart | R2 (done - Home) |
| Path management, custom items | R6 - Goals and Habits |
| Badges, leaderboard | R7 - Gamification depth |
| Milestone insights, Excel export | R8 - Analytics |
| Profile, password, settings | R9 - Onboarding |
| Admin dashboard | Ship |

So the flip lands once R9 is done, and the Ship phase removes the Jinja templates
entirely. Until then both run side by side: `/` is the working app, `/app` is the
redesign, and they share one database, so anything logged in either shows in both.

## R3 - Training

Done. See [TRAINING.md](TRAINING.md) for the full write-up.

Shipped: an 85-exercise library synced from `data/exercises.json`, set-by-set
logging with previous-performance hints and a timestamp-driven rest timer,
routines with target sets and reps that pre-fill a session, volume and
muscle-balance analytics, personal records, and body measurements.

This is also the phase where the attribute engine stopped running on self-report
alone. `scoring/producers.py` turns logged sets into measured signals for
Strength, Stamina and Agility - and Agility stopped being `locked`, because
mobility work now feeds it. Two scoring problems surfaced and were fixed here: a
perverse incentive where ticking a checkbox outscored an honestly logged light
week, and a ramp-up penalty that scored a genuine first session at 27% by
measuring one day against a full week's target.

Exercise demo animations remain designed-for but unshipped - no copyrighted
media.

## R4 - Nutrition and Lifestyle

Done. See [NUTRITION.md](NUTRITION.md) for the full write-up.

Shipped: a 233-food curated library, per-meal logging with macros and fibre, a
recipe builder that turns a cooked dish into a reusable food, hydration and step
tracking, sleep with duration and schedule consistency, mood/stress/energy, a
journal, and energy balance against an estimated TDEE with every estimate labelled
as one.

Recovery stopped being `unobserved` - sleep duration finally gives it data - and
Discipline gained its first measured signals in sleep consistency and target
adherence. `locked` is now empty: every attribute has a source.

The line this phase had to draw is between behaviour and feeling. Mood, stress,
energy and sleep quality are recorded and charted but never scored, because an
app that scored them would be paying you to report feeling good.

`user_profile` landed here rather than in R9 as planned, because energy balance
cannot exist without it. R9 expands the table rather than creating it.

## R5 - Learning

Areas and topics, tracked study sessions, study-time and topic-distribution
analytics, weekly study goals, learning streaks.

**In progress.** The backend is done and committed; the UI is what remains.

Done:

- `migrations/005_learning.sql` - `learning_areas`, `learning_topics`,
  `learning_sessions`, plus `weekly_study_minutes` on `user_profile`.
- `producers.learning_ratios()` - study minutes feed Knowledge over a trailing
  window; block depth feeds Focus. Wired into `store.recompute_scores`.
- `learning_api.py` - areas, topics, sessions and the dashboard summary.
- 41 tests across `tests/test_learning_scoring.py` and `tests/test_learning_api.py`.

Still to do:

- Types and query hooks in `frontend/src/api/`.
- A Learning page: areas and topics, a session timer and manual logger,
  study-time trend, topic distribution, streak and depth.
- Route wiring in `App.tsx` (add `/learning` to the `BUILT` set).
- `docs/LEARNING.md`, changelog and README entries, verification screenshots.

### The two decisions this phase turned on

**Focus is measured from the shape of study time, not from a rating.** The
original brief asked for a self-reported focus rating, but R4 established that
scoring a feeling pays you to report feeling good. So Focus comes from
uninterrupted block length instead - one two-hour block is deeper work than four
half-hour ones for the same total, and that is observable. The rating is still
recorded and charted; a test asserts it never reaches the producer.

**Depth is a duration-weighted mean block length**, `sum(d^2)/sum(d)`. Total
minutes is just Knowledge again; longest block lets one good session hide a
fragmented week; a plain mean lets a stray five-minute session drag a great day
down. Weighting by duration asks "for a randomly chosen minute of study, how long
was the block it belonged to", which is the question Focus is actually asking.

Scope was held to the roadmap: no resource tracking (books, courses with progress)
and no spaced repetition. Both were considered and deliberately left out to keep
R5 the size of R3 and R4.

## R6 - Goals and Habits

Goals with milestones, categories, deadlines and linked habits. Reusable habits with
real schedules (daily, weekdays, N times per week, custom). This is where the Paths
JSON system converts into `Habit`/`HabitCompletion` - see
[DATA-MODEL.md](DATA-MODEL.md).

## R7 - Gamification depth

Achievement categories and unlock UI, an auditable per-action XP ledger
(`XPTransaction`) replacing day-granularity XP, a configurable level curve, and
anti-gaming rules so XP can't be farmed by trivial repeated actions.

## R8 - Analytics

Period filters from 7 days to all time, trend charts across every tracked dimension,
a calendar heatmap where each day is coloured by adherence and clicking a date opens
that day's log, and period-over-period comparison.

## R9 - Onboarding

The seven-step first-run flow: profile, fitness profile, goals, sleep schedule,
learning intent, goal selection, and computed baselines (BMI, BMR via Mifflin-St
Jeor, estimated TDEE). Behavioural scores start conservative and from questionnaire
answers - they are explicitly not derived from height and weight.

## R10 - Polish

Responsive review at every breakpoint, XP/level-up/achievement animations that
respect reduced motion, accessibility pass, loading and empty states everywhere,
performance work (pagination, lazy loading, bundle budget).

## Ship - Re-platform and deploy

The last phase. Port to the stack already running Tech-Portfolio in production -
**Next.js 16 App Router on AWS Amplify SSR, with DynamoDB and S3** - then deploy to
`neurallog.adityamore.dev`. See [DEPLOYMENT.md](DEPLOYMENT.md).

- Frontend: React 19 + Vite + TypeScript + Tailwind v4 -> Next.js App Router. The
  components, tokens and motion system carry over; routing and data fetching change.
- Backend: Flask route handlers -> Next.js route handlers. `scoring/engine.py` is pure
  functions over plain dicts with no database or framework imports, so it translates
  mechanically; the SQL layer and migrations are rewritten for DynamoDB.
- Storage: SQLite **and** the per-user `artifacts/` JSON files -> DynamoDB. Both have
  to go: every serverless platform has an ephemeral filesystem.
- Retires the legacy Jinja app, the `/app` mount point, and the unversioned Flask routes.
- The security prerequisites in [DEPLOYMENT.md](DEPLOYMENT.md) land here, before the
  app is reachable: no hard-coded secret fallback, closed registration, login rate
  limiting, CSRF, session cookie flags.
- Cost after this lands: ~$0/month within AWS's perpetual Always Free allowances.

## Beyond

Architected for, not built now: wearables (Apple Health, Health Connect, Garmin),
smart scales, calendar integration, nutrition APIs and barcode scanning, AI-generated
training and learning plans, and natural-language logging ("studied ML for 90 minutes
and did a chest workout"). The constraint these place on today's decisions is simply
that structured logs must stay structured - no free-text soup where an entity belongs.

A native iOS client is **not planned**. It was dropped once the cost was clear: the
Apple Developer Program is $99/year purely to distribute to a handful of friends, and
since iOS 16.4 a Home Screen web app can be installed and receive push notifications for
$0. A PWA covers what a habit tracker needs; the native-only features that would justify
the fee - HealthKit, widgets, Siri Shortcuts, background sync - are all in *Beyond*
rather than planned work. The clean API boundary is still worth keeping, because it is
what makes a PWA (or a later native client, if HealthKit ever becomes the point) possible.
