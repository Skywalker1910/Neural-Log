# Neural-Log

A daily-discipline tracker for a small group of friends, built around a simple bet:
if you make consistency visible - and eventually, game-like - you'll keep showing up.

## Motivation

I wanted a way to actually see whether I'm becoming more disciplined, not just feel
like I am. Wake time, workouts, meals, sleep, the one important task I said I'd do -
logged daily, cheaply (one wizard, a minute a day), so patterns show up over weeks
instead of staying a vague impression. The long-term intent is to make that logging
itself rewarding: XP, levels, streaks, badges, a small leaderboard among the friends
using it - see [docs/ROADMAP.md](docs/ROADMAP.md). This README covers what exists
today; the roadmap covers what's next.

## What it does today

- **Daily checklist wizard** - a themed set of daily questions ("Paths": Batman /
  Thor / Captain America / Ironman, or your own custom one), answered one at a time,
  keyboard-navigable.
- **Custom Paths** - create, rename, reorder, and delete your own checklist items and
  templates per user, each item weighted for XP.
- **Gamification** - XP and levels for completing your checklist, a streak
  multiplier, 8 badges, and overall + monthly leaderboards across the group. Full
  scoring spec: [docs/GAMIFICATION.md](docs/GAMIFICATION.md).
- **Accounts & admin** - session-based login; the first registered user becomes an
  admin who can view/manage every other user's account and activity.
- **Stats & streaks** - days logged, total activities, current streak, average
  progress score, a Chart.js progress chart.
- **Milestone insights** - a summary snapshot at 10/25/45/70/100 days logged.
- **Excel export** - all of your activity history, formatted, one click.
- **Custom icon set** - each checklist item shows a small circular badge icon,
  generated from the artwork in `artifacts/` (see `scripts/build_icons.py`).

## Architecture

Flask serves a JSON API plus two frontends: the React + TypeScript SPA at `/`,
which is the app, and the original server-rendered Jinja dashboard at `/classic`,
kept only for the few features not yet ported (Excel export, admin). SQLite holds
users/activities/XP; per-user checklist templates and daily submissions are
JSON/JSONL files under `artifacts/`. Full
write-up, including *why* it's split that way:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Setup

1. **Clone and enter the project directory.**
2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate      # Windows
   # source venv/bin/activate # macOS/Linux
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   npm --prefix frontend install
   ```
4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # then edit .env - at minimum, set a real SECRET_KEY:
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
5. **Build the frontend, then run it.** Flask serves the built SPA at `/`, so the
   build has to exist before the app has a UI:
   ```bash
   npm --prefix frontend run build
   python app.py
   ```
   `http://localhost:5000` - the first account you register becomes admin.

   While working on the frontend, run Vite instead for hot reload, with Flask
   still running in another terminal:
   ```bash
   npm --prefix frontend run dev
   ```
   `http://localhost:5173` - `/api`, `/login` and friends are proxied to Flask, so
   your session works normally.

   The classic dashboard at `/classic` needs no build - it is server-rendered.

### Running tests

```bash
pytest                              # backend
npm --prefix frontend run lint      # frontend lint
npm --prefix frontend run typecheck # frontend types
```

## Project structure

```
Neural-Log/
├── app.py                  # Flask app: routes, auth, DB + Paths persistence
├── requirements.txt
├── .env.example            # copy to .env - see Setup
├── frontend/               # React + Vite + TS SPA (the app, served at /)
├── migrations/             # numbered SQL migrations + schema_migrations ledger
├── templates/              # Jinja templates (classic app, being retired)
├── static/{css,js,images}/ # classic frontend + generated icon set (images/icons/)
├── artifacts/              # per-user Paths + checklist submissions (JSON/JSONL),
│                           # plus the source art scripts/build_icons.py reads from
├── scripts/
│   ├── build_icons.py      # (re)generates static/images/icons/ from artifacts/
│   └── shoot.mjs           # authenticated SPA screenshots via DevTools Protocol
├── tests/                  # pytest smoke tests
└── docs/
    ├── ARCHITECTURE.md     # how it's built, and why
    ├── DESIGN-SYSTEM.md    # tokens, typography, component inventory
    ├── DATA-MODEL.md       # migrations + planned entities, mapped to phases
    ├── GAMIFICATION.md     # XP/levels/streaks/badges scoring spec
    ├── SCORING.md          # how behaviour becomes the eight attributes
    ├── TRAINING.md         # exercise library, set logging, routines, analytics
    ├── NUTRITION.md        # food library, recipes, sleep, lifestyle, TDEE
    ├── LEARNING.md         # areas, topics, study sessions, block depth
    ├── HABITS.md           # the Paths-to-Habits migration, schedules, goals
    ├── XP.md               # the XP ledger, caps, and achievements
    ├── CI.md               # what runs on a PR, and what main enforces
    ├── DEPLOYMENT.md       # AWS plan and cost model
    ├── ROADMAP.md          # the ten redesign phases, in order
    └── CHANGELOG.md        # what changed, newest first
```

## Roadmap

Mid-redesign: turning the checklist app into a full personal-development platform -
ten workspaces, an RPG-style attribute system driven by real behaviour, and analytics
over it all. Foundation (R1), Home and Today (R2), Training (R3), Nutrition +
Lifestyle (R4), Learning (R5), Goals + Habits (R6) and Gamification depth (R7)
are done; Analytics (R8) is next. Deployment comes last, once the product is
complete - see [docs/ROADMAP.md](docs/ROADMAP.md).
See [docs/ROADMAP.md](docs/ROADMAP.md).

## License

MIT License - personal project, feel free to use and adapt for your own tracking.
