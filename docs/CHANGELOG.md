# Changelog

Kept from Phase 1 onward. Format is loose - what changed and why, newest first.

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
