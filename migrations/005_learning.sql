-- R5: the Learning workspace.
--
-- Knowledge and Focus have run on checklist data alone since R2 - a ticked
-- "studied today" box, which cannot tell twenty minutes of skimming from a
-- three-hour deep session. This gives both of them measured behaviour:
--
--   study minutes            -> Knowledge, over a trailing window
--   uninterrupted block size -> Focus
--
-- The second one is the interesting decision. Focus is derived from how study
-- time is SHAPED, not from a self-reported "how focused did you feel" rating -
-- one two-hour block is deeper work than four half-hour ones for the same total,
-- and that is observable. The rating is still recorded, and still never scored,
-- for the same reason mood is not: it would pay you to rate yourself a five.

-- A domain you are learning. Deliberately shallow - area then topic - because a
-- deeper tree is a thing to maintain rather than a thing that helps you study.
CREATE TABLE IF NOT EXISTS learning_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,

    -- One of the design system's accent names, so the UI colours an area
    -- consistently everywhere without inventing a second palette.
    accent TEXT NOT NULL DEFAULT 'learning',
    notes TEXT,

    -- Per-area weekly target in minutes. NULL means "no target of its own" and
    -- the profile-wide weekly study target applies instead.
    weekly_target_minutes INTEGER,

    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_learning_areas_user ON learning_areas (user_id, archived);

-- What you actually sit down and study.
CREATE TABLE IF NOT EXISTS learning_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    area_id INTEGER,                      -- nullable: a topic can be unfiled
    name TEXT NOT NULL,
    notes TEXT,

    -- active | paused | done. A finished topic stays in the database because its
    -- sessions are history; it just stops cluttering the picker.
    status TEXT NOT NULL DEFAULT 'active',

    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (area_id) REFERENCES learning_areas (id)
);

CREATE INDEX IF NOT EXISTS idx_learning_topics_user ON learning_topics (user_id, archived);
CREATE INDEX IF NOT EXISTS idx_learning_topics_area ON learning_topics (area_id);

-- One study session. The grain of the whole workspace, the way exercise_sets is
-- for Training and food_entries is for Nutrition.
CREATE TABLE IF NOT EXISTS learning_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    topic_id INTEGER,                     -- nullable: studying something unfiled still counts

    -- HH:MM local. Optional, but when present they are what lets two sessions
    -- fifteen minutes apart be recognised as one interrupted block rather than
    -- two short ones - which is the difference between an honest Focus score and
    -- a punitive one.
    started_at TEXT,
    ended_at TEXT,

    duration_minutes INTEGER NOT NULL,

    -- 1-5, self-reported. Recorded and charted, never scored.
    focus_rating INTEGER,
    difficulty INTEGER,

    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (topic_id) REFERENCES learning_topics (id)
);

-- Deliberately NOT unique per (user, date): several sessions a day is the normal
-- case, and it is precisely the shape this workspace is trying to measure.
CREATE INDEX IF NOT EXISTS idx_learning_sessions_user_date
    ON learning_sessions (user_id, date);
CREATE INDEX IF NOT EXISTS idx_learning_sessions_topic
    ON learning_sessions (topic_id);

-- The weekly study target lives with the other targets rather than in a table of
-- its own. SQLite has no ADD COLUMN IF NOT EXISTS, but the migration ledger
-- guarantees this file runs exactly once, so a plain ALTER is safe here.
ALTER TABLE user_profile ADD COLUMN weekly_study_minutes INTEGER DEFAULT 300;
