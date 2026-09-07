# Changelog

Kept from Phase 1 onward. Format is loose - what changed and why, newest first.

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
