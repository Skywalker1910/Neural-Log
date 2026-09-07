# Architecture

This describes the system as it exists today (Phase 1). See [ROADMAP.md](ROADMAP.md)
for where it's headed.

## Overview

Neural-Log is a single-process Flask app. There's no build step and no frontend
framework - server-rendered Jinja templates, plain JS, plain CSS. That's a deliberate
choice for a project used by ~10 people: less moving parts, easier to reason about,
easier to deploy.

```
Browser
  |
  | HTTP (session cookie)
  v
Flask app (app.py)
  |
  |-- sqlite3 -------------> neural_log.db  (users, activities, milestones,
  |                                          daily_xp, user_badges)
  |
  '-- filesystem (JSON) ---> artifacts/paths/<username>.json       (checklist templates)
                              artifacts/checklists/<username>.jsonl (daily submissions)
```

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

## Frontend

- `templates/index.html` - the main dashboard: stats cards, the step-by-step wizard
  (one checklist item per screen, keyboard navigable), path/profile management modals,
  a Chart.js progress chart.
- `static/js/app.js` - all client logic: wizard step engine, Paths CRUD, checklist
  submission, stats/chart loading, Excel export trigger.
- `static/css/style.css` - a single hand-written stylesheet (CSS custom properties for
  theming, no framework/preprocessor) - shared by all three pages (`index.html`,
  `login.html`, `admin.html` all link it; none carry their own inline `<style>`).

## Icons

`static/images/icons/` holds a small set of circular-badge-ready PNGs generated from
the source art in `artifacts/` by `scripts/build_icons.py` (Pillow, dev-time only -
not a runtime dependency). Every default-Path checklist item carries an `icon` key
(`ICON_KEYS` in `app.py`, validated in `normalize_checklist_items`); custom items get
an icon-picker in the UI instead of free text. Re-run the script after adding or
replacing anything in `artifacts/`.

## Known rough edges (tracked, not yet fixed)

- `artifacts/checklist_items/` is orphaned - current code reads from
  `artifacts/paths/` and `artifacts/checklists/` only. Left in place rather than
  deleted since it's real (if stale) user data; worth a manual cleanup pass.
- Three `.venv*` folders exist locally from earlier experimentation - harmless
  (gitignored) but worth pruning to just one when convenient.
- No CSRF protection and no login rate limiting yet - acceptable for a trusted
  ~10-person group behind no public listing, but must land before the app is
  reachable by a wider audience.
