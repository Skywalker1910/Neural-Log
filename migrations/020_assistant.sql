-- The assistant: what it said, what it cost, and what it wants to change.
--
-- Four tables, and the interesting one is the last.
--
-- ## Why conversations live in the database
--
-- The obvious place is the Flask session, which is a signed cookie and caps out
-- around 4 KB. A check-in conversation is an order of magnitude past that before
-- the tool calls are counted. So it goes in SQLite, which also means a check-in
-- survives closing the tab halfway through - the thing people actually do.

CREATE TABLE IF NOT EXISTS ai_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- 'today' is the guided daily check-in; 'general' is free-form chat. The
    -- distinction matters because a check-in is *about* a date and is resumed,
    -- while a general thread is not.
    kind TEXT NOT NULL DEFAULT 'general',
    -- Only set for kind='today'. The day being discussed, which is not always
    -- the day it is being discussed on - people log last night at 1am.
    subject_date TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_conversations_user
    ON ai_conversations (user_id, kind, subject_date);


CREATE TABLE IF NOT EXISTS ai_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    -- JSON rather than text. A turn is not always a string: it may be tool calls,
    -- tool results, or an image the user photographed. Storing the provider's own
    -- shape means replaying a conversation is a read rather than a translation.
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
    ON ai_messages (conversation_id, id);


-- ## Usage, logged per request rather than per conversation
--
-- Two jobs, and they pull in different directions. The spend cap has to be
-- enforced *before* a request, from data that is exact and local - the provider's
-- own usage API lags by minutes to hours and reports the whole organisation. The
-- cost report wants dollars, which depend on prices this table should not pretend
-- to know.
--
-- So: tokens are recorded because they are a fact, and the dollar figure is an
-- estimate computed from configurable rates. The estimate is what the cap
-- enforces and what the admin page shows, clearly labelled. The provider's own
-- billing remains the authority on what was actually charged.
CREATE TABLE IF NOT EXISTS ai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    -- Which part of the app spent this: 'chat', 'today', 'label'. Without it the
    -- bill is one number and there is no way to learn that label scanning is
    -- ninety percent of it.
    feature TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- The cap query is "what has this user spent this month", so the index has to
-- carry the date or every check runs a scan that grows with history.
CREATE INDEX IF NOT EXISTS idx_ai_usage_user_time
    ON ai_usage (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_feature_time
    ON ai_usage (feature, created_at);


-- ## Proposals: the table that makes the assistant safe to give write access
--
-- The assistant never writes to the app. It writes *here*, and a person presses
-- Save.
--
-- That is not caution for its own sake. Logging a workout is not like opening a
-- page: `recompute_after_change` runs, attribute scores move, XP is awarded, a
-- streak extends, the leaderboard reorders. A misheard "forty-five minutes"
-- silently becomes part of the trend the whole app exists to show you, and
-- nothing about the resulting chart looks wrong.
--
-- So a turn's write-intent accumulates into `actions` as JSON and stops. The
-- client renders it, the person edits the numbers and confirms, and only then
-- does anything execute.
--
-- `actions` is stored as proposed, never overwritten by what comes back on
-- confirmation. The apply path takes the edited copy and checks it against this
-- one: same action types, same order, same count - only values may differ. That
-- is what stops an edited payload from turning "log a 300 kcal breakfast" into
-- "delete every workout", which a client the user does not fully control could
-- otherwise ask for.
CREATE TABLE IF NOT EXISTS ai_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER REFERENCES ai_conversations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    actions TEXT NOT NULL,
    -- 'pending' -> 'applied' | 'discarded' | 'superseded'. Superseded is what
    -- happens when the conversation carries on and proposes again before the
    -- earlier card was answered; without it, two Save buttons are live at once
    -- and pressing the older one logs a thing the user already talked past.
    status TEXT NOT NULL DEFAULT 'pending',
    -- What actually happened, written on apply: ids created, errors hit. A
    -- proposal that half-applied has to be legible afterwards.
    result TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_proposals_pending
    ON ai_proposals (user_id, status, created_at);
