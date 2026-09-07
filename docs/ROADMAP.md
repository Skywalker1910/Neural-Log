# Roadmap

Neural-Log started as a simple activity log and is becoming something closer to a
game: complete your daily checklist, earn XP, level up, keep your streak alive,
compare progress with a small group of friends. This tracks where that's headed,
in order.

## Status

| Phase | What | Status |
|-------|------|--------|
| 1 | Foundation - bug fixes, config hardening, docs, smoke tests | ✅ Done |
| 2 | Gamification system - XP, levels, streaks, badges, leaderboard | 🔲 Not started |
| 3 | AWS deployment | 🔲 Not started |
| 4 | iOS app | 🔲 Not started |

## Phase 1 - Foundation (done)

Made the existing app correct and configurable before building on top of it:

- Fixed the wizard's `completionPercent` bug (checklist submission was throwing
  client-side and silently failing to record completion %).
- Removed duplicate `#checklistWizard` legacy markup left over from before the
  dynamic wizard existed.
- Moved `SECRET_KEY`, debug mode, and the DB path out of hardcoded source and into
  environment variables (`.env`, see `.env.example`) - required groundwork for any
  real deployment.
- Added a small `pytest` smoke suite covering auth, activities, and the checklist
  submission path.
- Wrote this documentation set.

## Phase 2 - Gamification system

The core hook of the app: turn "did I do my checklist today" into a game.

Rough shape (to be nailed down in its own design pass, not decided yet):

- **XP & levels** - points per completed checklist item, weighted (e.g. workout >
  did-you-hydrate), with a level curve so early levels come fast and later ones take
  sustained consistency.
- **Streaks** - already have day-over-day streak calculation in `/api/stats`; extend
  it into a scored mechanic (streak multipliers, streak-loss handling that doesn't
  feel punishing enough to make people quit).
- **Badges / achievements** - milestone-based (first 7-day streak, 100 days logged,
  first custom Path created, etc.).
- **Leaderboard** - since this launches with a known group of 5-10 friends, a simple
  ranked view (XP, current streak, or both) rather than a public/global one.
- Needs a real data model decision: new SQL tables (`xp_events`, `badges`,
  `user_badges`) most likely, since this data is exactly the kind of aggregate/queried
  data SQLite is already used for elsewhere (see
  [ARCHITECTURE.md](ARCHITECTURE.md#why-two-storage-systems)).

## Phase 3 - AWS deployment

Not started - to be worked through together rather than pre-decided, since this is
new territory. Rough shape of the decision:

- **Compute**: simplest option first - a single EC2 instance (or Elastic Beanstalk)
  running Gunicorn behind Nginx. Containerizing (ECS/Fargate) is a reasonable later
  step once the deployment story is well understood, not a Phase 3 requirement.
- **Database**: staying on SQLite for now per the current user count; revisit RDS/
  Postgres if/when concurrent writes or backups become a real concern.
- **Storage**: the `artifacts/` JSON files need a persistent volume (EBS) or, later,
  S3 - plain "ephemeral instance disk" won't survive a redeploy.
- **Secrets**: `SECRET_KEY` etc. move from `.env` to AWS Secrets Manager or
  SSM Parameter Store rather than living on the instance as a file.
- **HTTPS/domain**: needed before sharing the URL with friends outside a VPN/local
  network.

## Phase 4 - iOS app

Later. The current server-rendered HTML approach won't serve a native client -
this phase likely starts with carving out a clean, versioned JSON API
(`/api/v1/...`) that both the web app and iOS app consume, rather than the current
routes that mix HTML rendering and JSON endpoints in the same file.
