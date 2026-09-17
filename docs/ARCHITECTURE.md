# Architecture

This describes the system as it exists today. See [ROADMAP.md](ROADMAP.md) for where
it's headed.

## Overview

Flask serves the React SPA at `/`, the JSON API, and the original server-rendered
Jinja dashboard at `/classic`. The classic dashboard remains for administration
and Excel export while the SPA owns the daily product experience.

```
Browser
  |
  |-- /            --> React SPA from frontend/dist
  |-- /classic     --> Jinja templates + static/js/app.js
  |-- /api/*       --> JSON, session-cookie authenticated
  v
Flask app (app.py)
  |
  |-- sqlite3 -------------> neural_log.db  (users, activities, milestones,
  |                                          daily_xp, user_badges, schema_migrations)
  |
  '-- filesystem (JSON) ---> artifacts/paths/<username>.json       (checklist templates)
                              artifacts/checklists/<username>.jsonl (daily submissions)
```

In development the SPA runs on Vite's own server (`:5173`) and proxies `/api`,
`/static` and `/login` to Flask (`:5000`), so the browser sees a single origin and
the existing session cookie works without CORS or any change to auth. In production
Flask serves the built bundle from `frontend/dist`.

## Schema migrations

Numbered SQL files under `migrations/`, applied once each and recorded in a
`schema_migrations` ledger by `run_migrations()` in `app.py`. This replaced the
ad-hoc `CREATE TABLE IF NOT EXISTS` block that `init_db()` used to be. Full
rationale, plus the map of planned entities to phases:
[DATA-MODEL.md](DATA-MODEL.md).

## Why two storage systems

Relational data (users, activities, milestones) lives in SQLite because it's queried,
joined, and aggregated (stats, streaks, admin dashboards). The per-user checklist
system - "Paths" - is structured, user-editable JSON (arbitrary item lists, custom
sub-questions) that's read/written as a whole document far more often than it's
queried piecemeal, so it's stored as flat JSON keyed by username under `artifacts/`.

This is a pragmatic split, not a textbook one - the trade-off is real:

- **Upside**: no schema migration needed every time the checklist item shape changes;
  a user's whole Path system is one readable file.
- **Downside**: no transactions across the two stores, and renaming a user means
  manually renaming files (`update_user_profile()` in `app.py`) rather than a single
  `UPDATE` statement. At this user count (~10) that's an acceptable trade. It's called
  out in the roadmap as something to revisit if the app grows.

## Request flow

1. `login_required` / `admin_required` decorators (`app.py`) gate every route via
   Flask's signed session cookie (`session['user_id']`, `session['is_admin']`).
2. The first account ever registered is auto-promoted to admin (`register()`).
3. Passwords are hashed with `werkzeug.security` - never stored or logged in plaintext.
4. Admin routes re-check `is_admin` from the database on every request rather than
   trusting the session value, so a stale/forged client-side flag can't grant access.

## The Paths system

A "Path" is a named list of daily checklist items (yes/no, rating, time-range, free
text, each with an optional follow-up sub-question). Four defaults ship in
`DEFAULT_PATH_LIBRARY` (Batman / Thor / Captain America / Ironman - see `app.py`);
users can also create, rename, reorder, and delete their own. `load_user_paths()`
lazily creates a user's `artifacts/paths/<username>.json` on first access and migrates
legacy `selected_path` string values into the newer path-id based format.

## Gamification

XP, levels, streak multipliers, and badges are computed from `daily_xp` and
`user_badges` (SQL, since it's aggregate/queried data - see above) whenever a daily
checklist is submitted. Full scoring spec: [GAMIFICATION.md](GAMIFICATION.md).

## Frontend: the redesign (`frontend/`)

React 19 + Vite + TypeScript, strict mode. Routed with react-router, data via
TanStack Query, styled with Tailwind v4 driven by the token layer in
`src/index.css`. Full component and token reference:
[DESIGN-SYSTEM.md](DESIGN-SYSTEM.md).

```
frontend/src/
  api/         client.ts (fetch wrapper), queries.ts (hooks), types.ts
  components/  ui/ (primitives) charts/ (lazy Recharts) layout/ (shell)
  pages/       one per workspace; placeholders until their phase lands
  navigation.ts  the ten sections, their icons and accents - single source
```

Two things that bite if you don't know them: Tailwind only sees class names that
appear as literal strings (hence the accent maps in `navigation.ts`), and charts
must be imported from `components/charts` so Recharts stays in its own lazy chunk.

## Frontend: the classic app (being retired)

Still serving `/` until the SPA replaces it workspace by workspace.

- `templates/index.html` - stats cards, the step-by-step checklist wizard,
  path/profile modals, a Chart.js progress chart.
- `static/js/app.js` - wizard engine, Paths CRUD, checklist submission, stats.
- `static/css/style.css` - one hand-written stylesheet shared by all three Jinja
  pages.

## Icons

Two sources with a clear split - Lucide SVG for UI chrome in the SPA, and the
hand-made PNG artwork for achievements and attributes.

`static/images/icons/` holds the circular-badge-ready PNGs generated from the source
art in `artifacts/` by `scripts/build_icons.py` (Pillow, dev-time only - not a
runtime dependency). Every default-Path checklist item carries an `icon` key
(`ICON_KEYS` in `app.py`). Re-run the script after adding or replacing anything in
`artifacts/`.

## Known rough edges (tracked, not yet fixed)

- **Personal data in the repo.** `artifacts/paths/AdityaMore.json` and
  `artifacts/checklist_items/AdityaMore.json` are tracked in git from before the
  project had a rule about it. Daily submissions (`artifacts/checklists/`) are now
  gitignored, but those two files are still committed. If this repo is public or
  shared, `git rm --cached` them (the local files stay put) - and remember that
  removing them from the current tree doesn't remove them from history.

- `artifacts/checklist_items/` is orphaned - current code reads from
  `artifacts/paths/` and `artifacts/checklists/` only. Left in place rather than
  deleted since it's real (if stale) user data; worth a manual cleanup pass.
- Three `.venv*` folders exist locally from earlier experimentation - harmless
  (gitignored) but worth pruning to just one when convenient.
- Account recovery, MFA, and an administrative audit log are not built yet.
