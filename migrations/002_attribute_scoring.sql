-- R2: storage for the attribute scoring engine (see docs/SCORING.md).
--
-- The seam between these three tables is RAW vs DERIVED, not "day" vs "score":
--
--   daily_log        immutable facts about one submission, including a snapshot
--                    of the checklist items AS THEY WERE that day
--   attribute_scores derived, rewritable, stamped with the engine version
--   daily_scores     derived, rewritable, stamped with the engine version
--
-- That split is what makes "recompute every score with new weights" safe: it
-- never touches the log. It also protects history - scoring currently reads the
-- user's LIVE path file, which app.py rewrites on every read and which has
-- already drifted once, so recomputing the past from live templates would
-- silently rewrite it.

-- One row per user per day. Resubmitting a day REPLACES its row (UNIQUE below
-- plus ON CONFLICT in the writer), mirroring daily_xp, so editing a day
-- recomputes in place instead of accumulating duplicates the way `activities`
-- does.
CREATE TABLE IF NOT EXISTS daily_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,

    -- 'checklist' today. 'seed' for demo data, 'backfill' for the one-time
    -- import of historical JSONL - kept distinct so demo data can never be
    -- mistaken for real behaviour.
    source TEXT NOT NULL DEFAULT 'checklist',

    -- Denormalised snapshot: which Path was used, by id and name. Deliberately
    -- NOT a foreign key - Paths live in per-user JSON files until R6, and a
    -- renamed or deleted Path must not orphan history.
    path_id TEXT,
    path_name TEXT,

    -- Server-computed, never the client's number (which counts answered rather
    -- than completed items and is therefore ~always 100).
    weight_total REAL NOT NULL DEFAULT 0,
    weight_earned REAL NOT NULL DEFAULT 0,
    completion_pct INTEGER NOT NULL DEFAULT 0,

    items_total INTEGER NOT NULL DEFAULT 0,
    items_completed INTEGER NOT NULL DEFAULT 0,

    -- The 1-5 self-rating item, kept as itself rather than folded into a score.
    self_rating INTEGER,
    notes TEXT,

    -- The activities row this came from, for cross-checking. Nullable because
    -- seeded and backfilled rows have no originating submission.
    activity_id INTEGER,

    -- Per-item snapshot: name, type, icon, weight, response, credit, and the
    -- attributes it fed, exactly as they were on this date. This is what makes
    -- the log independent of today's mutable Path definitions.
    payload_json TEXT,

    engine_version INTEGER NOT NULL DEFAULT 1,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(user_id, date),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- LONG, not wide: one row per attribute per day rather than eight columns.
-- Adding or removing an attribute is then a config change, not a migration, and
-- there is somewhere to put per-attribute confidence - which cold start makes
-- essential, since most attributes are unscored for the first few days.
CREATE TABLE IF NOT EXISTS attribute_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    attribute TEXT NOT NULL,

    -- That day's observed ratio (earned credit / available credit), before any
    -- rolling average. NULL when the attribute was not observable that day.
    raw_value REAL,

    -- The reportable 0-100 figure after the rolling average. NULL unless status
    -- is 'active' - an unobserved or calibrating attribute has no honest number,
    -- and storing 0 would make "no data" indistinguishable from "did nothing".
    score INTEGER,

    -- locked | unobserved | calibrating | active - see docs/SCORING.md
    status TEXT NOT NULL,

    confidence REAL NOT NULL DEFAULT 0,
    sample_days INTEGER NOT NULL DEFAULT 0,

    engine_version INTEGER NOT NULL DEFAULT 1,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(user_id, date, attribute),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- The composite day score and the discipline score, both derived.
CREATE TABLE IF NOT EXISTS daily_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,

    daily_score INTEGER,
    discipline_score INTEGER,
    completion_pct INTEGER NOT NULL DEFAULT 0,

    engine_version INTEGER NOT NULL DEFAULT 1,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(user_id, date),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_daily_log_user_date
    ON daily_log (user_id, date);

-- Ordered by attribute first: the common read is "this attribute's history for
-- the radar's 7/30/all-time ranges", not "everything about one day".
CREATE INDEX IF NOT EXISTS idx_attribute_scores_user_attr_date
    ON attribute_scores (user_id, attribute, date);

CREATE INDEX IF NOT EXISTS idx_daily_scores_user_date
    ON daily_scores (user_id, date);
