-- Retire the hero Paths; one shared daily survey instead.
--
-- Four Paths - Batman, Thor, Captain America, Ironman - each with ten items,
-- heavily overlapping. Picking one at signup decided which questions you were
-- asked forever, and that had two consequences nobody chose:
--
--   1. It quietly decided your SCORES. The opportunity denominator comes from
--      the items in your Path, so an Ironman never had a Stamina denominator
--      from the checklist and a Thor never had a Knowledge one. The leaderboard
--      then ranked those people against each other as if the numbers meant the
--      same thing. They did not.
--   2. It fragmented the habit history. Each account carried 40 habit rows
--      across 4 groups, of which 30 were never answered - habits_api.py's own
--      docstring complains that the unscoped list repeats "What time did you
--      wake up?" once per path.
--
-- One survey for everyone fixes both. Completion percentages become comparable,
-- and every attribute has the same denominator for every person.
--
-- ## The model
--
-- A core question belongs to nobody, so `habits.user_id` is now NULL for it.
-- A personal extra belongs to one person and keeps their id. `habit_completions`
-- already carries `user_id` alongside `habit_id`, so it distinguishes who
-- answered a shared question without any change.
--
-- SQLite cannot drop a NOT NULL in place, hence the table rebuild below. The
-- ledger guarantees this file runs exactly once.
--
-- ## What happens to history
--
-- Nothing. The old Path habits are ARCHIVED, not deleted: `habit_completions`
-- references them, and `daily_log.payload_json` already snapshots the questions
-- each day actually asked. Past days keep being scored against the survey that
-- applied then, which is the only honest option - rescoring them against
-- questions nobody was asked would be inventing answers.

-- --- rebuild habits with a nullable owner -----------------------------------

CREATE TABLE habits_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- NULL means this is a core question, shared by everyone and owned by
    -- nobody. A personal extra carries its owner's id.
    user_id INTEGER,

    -- Groups were the Path mechanism. Kept nullable so the existing rows can
    -- carry theirs (they are archived, but their history reads better with the
    -- group name intact); core questions and new personal extras have none.
    group_id INTEGER,

    is_core INTEGER NOT NULL DEFAULT 0,

    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'yes-no',
    icon TEXT NOT NULL DEFAULT 'default',
    weight INTEGER NOT NULL DEFAULT 1,
    options TEXT,
    sub_response TEXT,

    -- Explicit {attribute: share}, the scoring resolver's tier 1. The stock
    -- Paths relied on tier 2 and 3 - an icon vocabulary, then keyword matching
    -- on the question text - which meant rewording a question could silently
    -- change which attribute it fed. A curated shared survey should say what it
    -- means instead of hoping the words match.
    attributes TEXT,

    schedule_type TEXT NOT NULL DEFAULT 'daily',
    schedule_days TEXT,
    target_per_week INTEGER,

    position INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (group_id) REFERENCES habit_groups (id)
);

INSERT INTO habits_new (
    id, user_id, group_id, is_core, slug, name, type, icon, weight, options,
    sub_response, attributes, schedule_type, schedule_days, target_per_week,
    position, archived, created_at
)
SELECT
    id, user_id, group_id, 0, slug, name, type, icon, weight, options,
    sub_response, NULL, schedule_type, schedule_days, target_per_week,
    position,
    -- Every Path item retires here. Their completions and their names survive
    -- for the habit history; they simply stop being asked.
    1,
    created_at
FROM habits;

DROP TABLE habits;
ALTER TABLE habits_new RENAME TO habits;

CREATE INDEX IF NOT EXISTS idx_habits_user ON habits (user_id, archived);
CREATE INDEX IF NOT EXISTS idx_habits_core ON habits (is_core, archived, position);

-- The Path groups go the same way: kept for the archived items to point at,
-- deselected so nothing treats one as current.
UPDATE habit_groups SET is_selected = 0, archived = 1;

-- --- the shared survey ------------------------------------------------------
--
-- Ten questions, nine of them scored. Two principles decided the set:
--
--   Ask about what the app cannot observe for itself, and keep every attribute
--   fed for somebody who only ever uses the checklist. That second half is why
--   "did you train today?" survives even though the Training workspace measures
--   sets directly - someone who never opens Training would otherwise have no
--   Strength signal at all, while for someone who does log sets the claim is
--   already capped at half the range (self_report_ceiling) and outweighed 3:1 by
--   the measured signal. It costs nothing and it covers the casual case.
--
-- Weights total 15, and that number is not arbitrary: XP_PER_WEIGHT_POINT is 10
-- and DAILY_SOURCE_CAPS['checklist'] is 150, so a perfect day earns exactly the
-- cap. The stock Paths totalled 15 too - the cap was tuned to them - and going
-- over silently throws the excess away. An earlier draft of this survey totalled
-- 17 and quietly lost 20 XP off every perfect day.
--
-- The rating is weight 0 and is never scored: extract_signals skips rating items
-- outright, because paying you to rate your own day would pay you to rate it
-- highly.

INSERT INTO habits (user_id, group_id, is_core, slug, name, type, icon, weight, options, attributes, position, archived)
VALUES
  (NULL, NULL, 1, 'core-wake-time', 'What time did you wake up?', 'time', 'sun', 1,
   '["05:00 - 05:30 AM","05:30 - 06:30 AM","06:30 - 07:30 AM","After 07:30 AM"]',
   '{"Discipline": 1.0}', 0, 0),

  (NULL, NULL, 1, 'core-training', 'Did you train today? (strength, sport, or hard effort)', 'yes-no', 'workout', 3,
   NULL, '{"Strength": 0.6, "Stamina": 0.4}', 1, 0),

  -- Agility's only route in from the checklist. Without it the attribute depends
  -- entirely on logging mobility exercises in the Training workspace.
  (NULL, NULL, 1, 'core-mobility', 'Did you stretch or do mobility work?', 'yes-no', 'workout', 1,
   NULL, '{"Agility": 0.6, "Recovery": 0.4}', 2, 0),

  (NULL, NULL, 1, 'core-study', 'Did you study or practise a skill for at least 30 minutes?', 'yes-no', 'code', 3,
   NULL, '{"Knowledge": 0.7, "Focus": 0.3}', 3, 0),

  (NULL, NULL, 1, 'core-priority', 'Did you finish your most important task today?', 'yes-no', 'default', 3,
   NULL, '{"Discipline": 0.6, "Focus": 0.4}', 4, 0),

  (NULL, NULL, 1, 'core-nutrition', 'Did you eat in a way that supports your goal?', 'yes-no', 'breakfast', 1,
   NULL, '{"Recovery": 1.0}', 5, 0),

  (NULL, NULL, 1, 'core-wind-down', 'Did you wind down properly before bed?', 'yes-no', 'sleep', 1,
   NULL, '{"Recovery": 0.7, "Discipline": 0.3}', 6, 0),

  -- No attributes, deliberately. It matters enough to ask and it counts toward
  -- the day, and there is no attribute it honestly feeds - so it feeds none
  -- rather than being dropped into Discipline for tidiness.
  (NULL, NULL, 1, 'core-connection', 'Did you spend meaningful time with someone?', 'yes-no', 'default', 1,
   NULL, '{}', 7, 0),

  (NULL, NULL, 1, 'core-reflect', 'Did you reflect on today or plan tomorrow?', 'yes-no', 'default', 1,
   NULL, '{"Discipline": 0.6, "Focus": 0.4}', 8, 0),

  (NULL, NULL, 1, 'core-rating', 'Rate your day (1-5)', 'rating', 'default', 0,
   NULL, '{}', 9, 0);
