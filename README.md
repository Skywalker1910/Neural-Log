# Neural Log

A personal activity tracker for training, nutrition, learning, habits, and long-term progress. Neural Log combines structured daily logs with an RPG-style attribute system, an auditable XP ledger, and analytics across each workspace.

## Motivation

I built Neural Log to keep workouts, meals, study sessions, and daily habits in one place. The goal is to see whether I am becoming more consistent over time, with enough detail to understand what is changing.

The scoring system follows that goal. Logged sets, study time, sleep, and completed habits provide evidence for progress. Mood and self-ratings remain useful context without becoming points to optimize.

## What it does today

- **Daily tracking** - shared survey, personal questions, schedules, completion history, and streaks.
- **Training** - exercise library, routines, set logging, records, and volume trends.
- **Nutrition and lifestyle** - foods, recipes, flexible measures, meals, sleep, hydration, steps, mood, and energy.
- **Learning and goals** - study areas, timed sessions, milestones, tasks, and linked habits.
- **Progression** - eight attributes, XP transactions, levels, achievements, and privacy-aware leaderboards.
- **Analytics** - comparisons, calendar heatmaps, and honest handling of unobserved days.
- **Classic tools** - administration and Excel export remain available at `/classic`.

## Architecture

Flask serves the React frontend and JSON API from one origin. SQLite is the authoritative store. Docker Compose runs Flask/Gunicorn and Caddy on AWS Lightsail; the database is mounted outside the application container. Full details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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
   `http://localhost:5000` - configure `ADMIN_USERNAME` for a deliberate admin.

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
├── templates/              # Jinja templates for the /classic surfaces
├── static/{css,js,images}/ # classic frontend + generated icon set (images/icons/)
├── artifacts/              # per-user Paths + checklist submissions (JSON/JSONL),
│                           # plus the source art scripts/build_icons.py reads from
├── scripts/
│   ├── build_icons.py      # dev-time icon generation
│   ├── check_migrations.py # fresh-database migration verification
│   ├── backup.sh           # verified SQLite backups
│   └── restore.sh          # database restore tool
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
    ├── SECURITY.md         # what had to be true before the app was public
    ├── DEPLOYMENT.md       # where it runs, what it costs, and why
    ├── ROADMAP.md          # the ten redesign phases, in order
    └── CHANGELOG.md        # what changed, newest first
```

## Roadmap

The core workspaces are built and the application is running on AWS Lightsail. The next work is release automation, off-instance backups, operational monitoring, and retiring the remaining classic administration surfaces. See [docs/ROADMAP.md](docs/ROADMAP.md).

## License

MIT License - personal project, feel free to use and adapt for your own tracking.
