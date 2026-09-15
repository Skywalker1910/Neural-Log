-- R6b: Goals, milestones and tasks.
--
-- WHY NONE OF THIS FEEDS AN ATTRIBUTE
-- -----------------------------------
-- A goal is an intention plus a number you type in. Ticking a milestone is a
-- claim with nothing behind it, and scoring claims is exactly what the rest of
-- this app refuses to do - it would pay you to declare progress rather than make
-- it.
--
-- What IS evidenced is the habits underneath a goal, and those already feed
-- Discipline through the checklist producer. So a goal linked to habits derives
-- its progress from their real completions, a goal without them carries a number
-- you maintain by hand, and `goal_progress.source` says which. Same honesty as
-- the TDEE estimate: compute it, and never let the UI present it as more than it
-- is.

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,

    title TEXT NOT NULL,
    description TEXT,

    -- Mirrors the workspaces so a goal can be coloured and filed alongside the
    -- thing it is about: fitness | learning | lifestyle | career | finance | other
    category TEXT NOT NULL DEFAULT 'other',
    accent TEXT NOT NULL DEFAULT 'goals',

    -- active | paused | achieved | abandoned
    --
    -- 'abandoned' is a deliberate first-class state rather than a deletion. Goals
    -- you gave up on are the most informative ones in hindsight, and quietly
    -- removing them would leave a history in which you only ever succeeded.
    status TEXT NOT NULL DEFAULT 'active',

    target_date TEXT,

    -- Measurable goals: "run 100 km", "read 12 books". All three are nullable,
    -- because plenty of real goals ("get better at saying no") have no number
    -- and forcing one would produce a fake it.
    metric_name TEXT,
    target_value REAL,
    current_value REAL NOT NULL DEFAULT 0,

    started_on TEXT,
    achieved_on TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_goals_user ON goals (user_id, archived, status);

CREATE TABLE IF NOT EXISTS goal_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,

    title TEXT NOT NULL,
    target_date TEXT,
    position INTEGER NOT NULL DEFAULT 0,

    -- NULL means not done. A date rather than a boolean, because "when did I
    -- pass this" is the question you ask later and a flag cannot answer it.
    completed_on TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (goal_id) REFERENCES goals (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_goal_milestones_goal
    ON goal_milestones (goal_id, position);

-- The link that makes a goal's progress evidenced rather than asserted.
--
-- A habit may serve several goals ("train 4x a week" feeds both a strength goal
-- and a consistency one), so this is a join table rather than a column.
CREATE TABLE IF NOT EXISTS goal_habits (
    goal_id INTEGER NOT NULL,
    habit_id INTEGER NOT NULL,
    PRIMARY KEY (goal_id, habit_id),
    FOREIGN KEY (goal_id) REFERENCES goals (id),
    FOREIGN KEY (habit_id) REFERENCES habits (id)
);

-- One-off things to do, as distinct from habits, which recur.
--
-- Kept deliberately thin: no projects, no subtasks, no dependencies. This exists
-- so a goal can carry the concrete next actions that move it, not to become a
-- task manager.
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    goal_id INTEGER,                      -- nullable: not every task serves a goal

    title TEXT NOT NULL,
    notes TEXT,
    due_date TEXT,
    priority INTEGER NOT NULL DEFAULT 2,  -- 1 high, 2 normal, 3 low

    completed_on TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (goal_id) REFERENCES goals (id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks (user_id, archived, completed_on);
CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks (goal_id);
