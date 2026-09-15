-- R7a: a per-action XP ledger.
--
-- THE PROBLEM THIS FIXES
-- ---------------------
-- XP has only ever come from the daily checklist. R3 through R6 added training,
-- nutrition, lifestyle, learning, habits and goals, and not one of them awards
-- anything. You can log a two-hour workout and a three-hour study session and
-- earn nothing unless you also tick a checkbox - and the leaderboard ranks your
-- friends on that number.
--
-- `daily_xp` cannot be extended to fix it, because it stores one opaque total
-- per day. It cannot say where the XP came from, cannot be audited when a number
-- looks wrong, and cannot express "this was capped" or "this was a claim rather
-- than evidence".
--
-- WHAT REPLACES IT
-- ----------------
-- One row per awarded action. `daily_xp` is kept and still written as a rollup,
-- because the leaderboard and the existing API read it - the same compatibility
-- approach R6 used for Paths.
--
-- The ledger is REBUILT PER DAY rather than appended to. Recomputing a whole
-- (user, date) is what makes daily caps correct: a cap is a statement about a
-- day, and you cannot apply one correctly while inserting rows one at a time
-- without knowing what else that day already holds.

CREATE TABLE IF NOT EXISTS xp_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,

    -- checklist | training | nutrition | lifestyle | learning | badge
    source TEXT NOT NULL,

    -- Identifies the thing that earned it, so a rebuild replaces rather than
    -- duplicates: 'checklist', 'workout:12', 'session:34', 'sleep', 'badge:streak-7'.
    -- Unique per user per day.
    source_key TEXT NOT NULL,

    -- Shown to the user. The ledger is only worth having if it can answer
    -- "why did I get 18 XP for that".
    reason TEXT NOT NULL,

    base_xp INTEGER NOT NULL,

    -- What the streak multiplier added, recorded rather than folded in, so the
    -- base is still visible after the fact.
    multiplier_pct INTEGER NOT NULL DEFAULT 0,
    xp INTEGER NOT NULL,

    -- Set when a daily cap reduced this row, holding what it would otherwise
    -- have been. Being able to see "you hit the training cap" is the difference
    -- between a rule and an unexplained number.
    capped_from INTEGER,

    -- 'measured' for a logged set, meal, night or study session; 'claimed' for a
    -- ticked checklist box. Recorded because the two are not worth the same, and
    -- because a total should be able to show how much of it was evidenced.
    evidence TEXT NOT NULL DEFAULT 'measured',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_xp_transactions_key
    ON xp_transactions (user_id, date, source_key);
CREATE INDEX IF NOT EXISTS idx_xp_transactions_user_date
    ON xp_transactions (user_id, date);
CREATE INDEX IF NOT EXISTS idx_xp_transactions_source
    ON xp_transactions (user_id, source);

-- Achievements, replacing the hard-coded BADGE_DEFINITIONS list.
--
-- In a table rather than in Python because R7 adds categories and tiers, and a
-- list that the UI has to group, filter and show progress against is data, not
-- code. The evaluation rules stay in Python - what is stored is the catalogue.
CREATE TABLE IF NOT EXISTS achievements (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,

    -- consistency | training | nutrition | lifestyle | learning | mastery
    category TEXT NOT NULL DEFAULT 'consistency',

    -- bronze | silver | gold. Tiers exist so a category can have a visible
    -- progression rather than a flat list of unrelated one-offs.
    tier TEXT NOT NULL DEFAULT 'bronze',

    -- XP granted on unlock, written into the ledger like anything else.
    xp_reward INTEGER NOT NULL DEFAULT 0,

    -- The threshold its rule compares against, so tiers of one achievement can
    -- share a rule and differ only by number.
    threshold INTEGER,

    icon TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_achievements_category
    ON achievements (category, position);
