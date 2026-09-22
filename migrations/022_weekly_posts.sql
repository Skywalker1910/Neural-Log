CREATE TABLE IF NOT EXISTS weekly_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_at TEXT NOT NULL DEFAULT (datetime('now')),
    generated_at TEXT,
    snapshot TEXT,
    report TEXT,
    model TEXT,
    UNIQUE(user_id, week_end)
);
