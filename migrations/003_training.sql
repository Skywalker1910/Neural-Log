-- R3: the Training workspace.
--
-- This is the first phase whose data is MEASURED rather than self-reported. A
-- checkbox says "I trained"; a set says 80kg x 8. That distinction is the whole
-- reason the scoring engine uses an opportunity denominator - see docs/SCORING.md
-- - so these tables are what finally give Strength and Stamina a real basis and
-- unlock Agility.

-- The exercise library. Rows with user_id IS NULL are the shipped library and are
-- shared by everyone; rows with a user_id are that person's own additions.
CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                      -- NULL = shipped library exercise
    slug TEXT NOT NULL,
    name TEXT NOT NULL,

    -- chest, back, shoulders, biceps, triceps, quads, hamstrings, glutes,
    -- calves, core, forearms, full-body, cardio
    primary_muscle TEXT NOT NULL,
    secondary_muscles TEXT,               -- JSON array; small and read whole
    equipment TEXT,                       -- barbell, dumbbell, machine, cable, bodyweight, kettlebell, band, none
    category TEXT NOT NULL DEFAULT 'strength',   -- strength | cardio | mobility
    difficulty TEXT,                      -- beginner | intermediate | advanced
    is_compound INTEGER NOT NULL DEFAULT 0,
    instructions TEXT,                    -- JSON array of short steps

    -- Demo animations are designed for but deliberately not shipped: no
    -- copyrighted media. A later phase fills this in (Lottie/SVG/WebM) without
    -- a migration.
    media_url TEXT,

    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Library slugs are globally unique; a user's own slugs only have to be unique to
-- them. Two partial indexes rather than UNIQUE(user_id, slug), because SQLite
-- treats NULLs as distinct and would happily allow duplicate library rows.
CREATE UNIQUE INDEX IF NOT EXISTS idx_exercises_library_slug
    ON exercises (slug) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_exercises_user_slug
    ON exercises (user_id, slug) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_exercises_muscle ON exercises (primary_muscle);

-- A named workout template: "Push A", "Upper Body", "Leg Day".
CREATE TABLE IF NOT EXISTS routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    split_type TEXT,                      -- push-pull-legs | upper-lower | full-body | custom
    notes TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Exercises in a routine, in order, with their targets.
CREATE TABLE IF NOT EXISTS routine_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL,
    exercise_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    target_sets INTEGER,
    target_reps INTEGER,
    notes TEXT,
    FOREIGN KEY (routine_id) REFERENCES routines (id),
    FOREIGN KEY (exercise_id) REFERENCES exercises (id)
);

CREATE INDEX IF NOT EXISTS idx_routine_exercises_routine
    ON routine_exercises (routine_id, position);

-- One performed workout. routine_id is nullable: plenty of sessions are improvised,
-- and a routine deleted later must not erase the history of having trained.
CREATE TABLE IF NOT EXISTS workout_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    routine_id INTEGER,
    name TEXT,
    notes TEXT,

    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    duration_seconds INTEGER,

    -- Denormalised session totals. Recomputed on write rather than summed over
    -- exercise_sets on every dashboard render.
    total_volume REAL NOT NULL DEFAULT 0,
    total_sets INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (routine_id) REFERENCES routines (id)
);

-- Deliberately NOT UNIQUE(user_id, date): two sessions in a day is normal
-- (a morning lift and an evening run), unlike the daily checklist.
CREATE INDEX IF NOT EXISTS idx_workout_sessions_user_date
    ON workout_sessions (user_id, date);

-- One logged set. The grain of the whole feature.
CREATE TABLE IF NOT EXISTS exercise_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    exercise_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    weight REAL,
    -- Stored per set rather than per user: someone who switches preference must
    -- not have their history silently reinterpreted, and plates are kg in one
    -- gym and lb in another.
    weight_unit TEXT NOT NULL DEFAULT 'kg',
    reps INTEGER,

    -- Cardio and mobility sets have duration and distance instead of load.
    duration_seconds INTEGER,
    distance REAL,
    distance_unit TEXT,

    rpe REAL,                             -- rate of perceived exertion, 1-10
    is_warmup INTEGER NOT NULL DEFAULT 0, -- excluded from volume and PRs
    completed INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (session_id) REFERENCES workout_sessions (id),
    FOREIGN KEY (exercise_id) REFERENCES exercises (id)
);

CREATE INDEX IF NOT EXISTS idx_exercise_sets_session
    ON exercise_sets (session_id, position);
-- Drives "previous performance" hints and personal records, both of which ask
-- "this exercise, this user, most recent first".
CREATE INDEX IF NOT EXISTS idx_exercise_sets_exercise
    ON exercise_sets (exercise_id, id);

-- Body metrics, long rather than wide so a new measurement is a row, not a
-- migration - the same reasoning as attribute_scores.
CREATE TABLE IF NOT EXISTS body_measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    metric TEXT NOT NULL,                 -- weight | body_fat | waist | chest | arms | thighs | ...
    value REAL NOT NULL,
    unit TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date, metric),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_body_measurements_user_metric
    ON body_measurements (user_id, metric, date);
