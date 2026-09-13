-- Baseline: the schema as it stood at the end of the gamification phase, before
-- the product redesign. Written with IF NOT EXISTS so it is a no-op against
-- databases that already contain these tables (every existing install) while
-- still building a fresh database from scratch.
--
-- Everything after this point gets its own numbered file. Each phase of the
-- redesign adds the tables it actually uses - see docs/DATA-MODEL.md.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    is_admin INTEGER DEFAULT 0,
    selected_path TEXT DEFAULT 'Batman Path',
    custom_path_items TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    activity_name TEXT NOT NULL,
    description TEXT,
    duration INTEGER,
    progress_score INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    milestone_day INTEGER NOT NULL,
    insights TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- One row per user per day a checklist was submitted - the source of truth for
-- XP/levels/leaderboards. UNIQUE(user_id, date) lets resubmitting today's
-- checklist recalculate in place instead of double-counting (see award_daily_xp).
CREATE TABLE IF NOT EXISTS daily_xp (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    base_xp INTEGER NOT NULL,
    streak_multiplier_pct INTEGER NOT NULL,
    total_xp INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Which badges (see BADGE_DEFINITIONS) each user has unlocked, and when.
CREATE TABLE IF NOT EXISTS user_badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    badge_code TEXT NOT NULL,
    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, badge_code),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_activities_user_date ON activities (user_id, date);
CREATE INDEX IF NOT EXISTS idx_daily_xp_user_date ON daily_xp (user_id, date);
