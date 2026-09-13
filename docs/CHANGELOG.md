# Changelog

Kept from Phase 1 onward. Format is loose - what changed and why, newest first.

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
