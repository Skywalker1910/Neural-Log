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
| R2 | Home + Today - attributes, radar, daily score, streaks | Not started |
| - | **AWS deployment** - deploy once R2 makes the app worth using | Not started |
| R3 | Training - routines, exercise library, set logging, analytics | Not started |
| R4 | Nutrition + Lifestyle - macros, hydration, sleep, mood | Not started |
| R5 | Learning - subjects, sessions, knowledge analytics | Not started |
| R6 | Goals + Habits - milestones, routines, streak sources | Not started |
| R7 | Gamification depth - achievements, XP ledger, attributes | Not started |
| R8 | Analytics - long-range trends, calendar, comparisons | Not started |
| R9 | Onboarding - profile, baselines, BMR/TDEE, goal setup | Not started |
| R10 | Polish - responsive, animation, a11y, performance | Not started |

AWS sits after R2 deliberately: deploying before the redesign means configuring a
deployment for a stack that's about to be replaced, and waiting until R10 means
nobody else can use the app for months. After R2 there's something worth logging
into every day, and the deployment shape (static bundle + Flask API) is settled.

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
- Flip `/` from the Jinja app to the SPA; port login and admin.

## R3 - Training

Routines and splits, an exercise library organised by muscle group, set-by-set
logging with previous-performance hints and a rest timer, personal records,
progressive overload and volume analytics, body measurements. Exercise demo
animations are designed for from the start (component boundary ready) but not
shipped - no copyrighted media.

## R4 - Nutrition and Lifestyle

Calories, macros, fibre, hydration; energy balance against an estimated TDEE with
estimates clearly labelled as estimates. Sleep gets first-class treatment - duration,
schedule consistency, and a direct contribution to Discipline and Recovery. Steps,
sunlight, mood, stress, journal.

## R5 - Learning

Areas, topics and skills; tracked study sessions with focus and difficulty ratings;
study-time and topic-distribution analytics; weekly study goals; learning streaks.

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

## Beyond

Architected for, not built now: wearables (Apple Health, Health Connect, Garmin),
smart scales, calendar integration, nutrition APIs and barcode scanning, AI-generated
training and learning plans, and natural-language logging ("studied ML for 90 minutes
and did a chest workout"). The constraint these place on today's decisions is simply
that structured logs must stay structured - no free-text soup where an entity belongs.

An iOS client remains the long-term goal; the R1 split into a JSON API plus a
separate frontend is the groundwork that makes it possible.
