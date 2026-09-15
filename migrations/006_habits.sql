-- R6a: the Paths system becomes Habits.
--
-- Paths are the oldest thing in this app and the only one still living outside
-- SQL: per-user JSON files in artifacts/paths/, loaded and rewritten on nearly
-- every request. They work, but they cannot answer the questions R6 is for -
-- "how often do I actually do this one", "is this due today", "show me a streak
-- for this habit alone" - because a JSON blob has no rows to group by.
--
-- The conversion is deliberately a MOVE, not a rewrite. These tables are shaped
-- so that load_user_paths() can return the exact same payload it always has,
-- which is what keeps the Jinja app at / and the SPA's Today page working
-- untouched while the storage underneath changes.
--
-- The string ids are the load-bearing part. A path's id ('batman-path') and an
-- item's id (a uuid) are already referenced by daily_log.path_id, by
-- users.selected_path, and by the client. They are carried across verbatim as
-- `slug` rather than replaced with integers, so nothing that points at them
-- breaks.

-- What a Path becomes.
CREATE TABLE IF NOT EXISTS habit_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,

    -- The path id as the rest of the app already knows it: 'batman-path',
    -- 'custom-a1b2c3d4'. Returned to clients as `id`.
    slug TEXT NOT NULL,
    name TEXT NOT NULL,

    -- A stock path from DEFAULT_PATH_LIBRARY rather than one the user built.
    is_default INTEGER NOT NULL DEFAULT 0,
    -- Exactly one group per user is selected; enforced in code, not by a
    -- constraint, because SQLite cannot express "at most one true per user".
    is_selected INTEGER NOT NULL DEFAULT 0,

    position INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_habit_groups_user_slug
    ON habit_groups (user_id, slug);

-- What a checklist item becomes.
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,

    -- The item's existing uuid, carried across. Returned to clients as `id`.
    slug TEXT NOT NULL,
    name TEXT NOT NULL,

    -- yes-no | time | rating | text. Unchanged from the JSON.
    type TEXT NOT NULL DEFAULT 'yes-no',
    icon TEXT NOT NULL DEFAULT 'default',
    weight INTEGER NOT NULL DEFAULT 1,
    options TEXT,                         -- JSON array, for ordinal types
    sub_response TEXT,                    -- JSON object

    -- The genuinely new part. Every migrated path item becomes 'daily', because
    -- that is what a path item has always been - the schedule is capability the
    -- old system never had, not a reinterpretation of existing data.
    --
    --   daily           every day
    --   weekdays        Monday to Friday
    --   days            specific weekdays, listed in schedule_days
    --   times-per-week  any N days, counted across the week
    schedule_type TEXT NOT NULL DEFAULT 'daily',
    schedule_days TEXT,                   -- JSON array of 0-6, Monday = 0
    target_per_week INTEGER,

    position INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (group_id) REFERENCES habit_groups (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_habits_group_slug ON habits (group_id, slug);
CREATE INDEX IF NOT EXISTS idx_habits_user ON habits (user_id, archived);

-- One habit, one day, one answer.
--
-- This does NOT replace daily_log.payload_json, and the difference matters.
-- payload_json is a SNAPSHOT of the items as they were on that date, which is
-- what makes "retune the weights and rescore everything" safe and what keeps
-- scoring independent of the live habit list. This table is the queryable
-- per-habit record that a JSON blob cannot serve: streaks, adherence, "12 of the
-- last 14 days". Both are written by the same save, in the same transaction.
CREATE TABLE IF NOT EXISTS habit_completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    habit_id INTEGER NOT NULL,
    date TEXT NOT NULL,

    response TEXT,                        -- the raw answer, as given
    -- 0.0-1.0, graded for ordinal types - the same credit the scoring engine
    -- computed, stored so adherence queries do not have to re-derive it.
    credit REAL NOT NULL DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (habit_id) REFERENCES habits (id)
);

-- One answer per habit per day: logging the same day twice is a correction.
CREATE UNIQUE INDEX IF NOT EXISTS idx_habit_completions_habit_date
    ON habit_completions (habit_id, date);
CREATE INDEX IF NOT EXISTS idx_habit_completions_user_date
    ON habit_completions (user_id, date);

-- Records that a user's JSON path file has been imported, so the import runs
-- once per user and never silently re-imports over later edits.
CREATE TABLE IF NOT EXISTS habit_imports (
    user_id INTEGER PRIMARY KEY,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT,
    groups_imported INTEGER NOT NULL DEFAULT 0,
    habits_imported INTEGER NOT NULL DEFAULT 0,
    completions_backfilled INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
