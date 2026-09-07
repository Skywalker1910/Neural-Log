# Roadmap

Neural-Log started as a simple activity log and is becoming something closer to a
game: complete your daily checklist, earn XP, level up, keep your streak alive,
compare progress with a small group of friends. This tracks where that's headed,
in order.

## Status

| Phase | What | Status |
|-------|------|--------|
| 1 | Foundation - bug fixes, config hardening, docs, smoke tests | ✅ Done |
| 2 | Gamification system - XP, levels, streaks, badges, leaderboard | ✅ Done |
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

## Phase 2 - Gamification system (done)

The core hook of the app: turned "did I do my checklist today" into a game.

- **XP & levels** - each checklist item has a weight (1-5); completing it awards
  `weight * 10` XP. A level curve (`50 * (level-1)^2` cumulative) means early levels
  come fast, later ones take sustained consistency.
- **Streak multiplier** - `current_streak` (from `/api/stats`) now also scales that
  day's XP: +2%/day, capped at +50%. Missing a day only resets the streak - no XP or
  level penalty.
- **Badges** - 8 code-defined achievements (first log, 7/30-day streaks, 100 days,
  custom Path created, a perfect day, levels 5 and 10), tracked per-user in
  `user_badges` and evaluated on every checklist submission.
- **Two leaderboards** - overall (all-time XP) and monthly (resets each calendar
  month), both visible to the whole friend group.
- Full spec: [GAMIFICATION.md](GAMIFICATION.md). Data model: new `daily_xp` and
  `user_badges` SQL tables (see
  [ARCHITECTURE.md](ARCHITECTURE.md#why-two-storage-systems) for why this is SQL and
  not JSON, unlike the Paths system).

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
