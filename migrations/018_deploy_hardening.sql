-- What the database has to know before the app is reachable from the internet.
--
-- Two things, both of which only matter once strangers can reach the login page.
--
-- ## Failed logins have to be remembered somewhere durable
--
-- Rate limiting needs to count attempts, and an in-process counter is the
-- obvious cheap answer right up until the app runs under gunicorn with four
-- workers - then there are four counters, each one letting through the full
-- quota, and the limit is silently four times what it says. A table is shared by
-- every worker, survives a restart, and at this volume costs nothing.
--
-- Only failures are recorded. A successful login clears the row set, so the
-- table holds "attempts since the last time this actually worked" rather than a
-- login history - which is both the number the limiter wants and less to leak.
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Stored as typed, not resolved to a user id. Guesses at usernames that do
    -- not exist are exactly the traffic worth counting, and resolving first
    -- would drop them.
    username TEXT NOT NULL,
    ip TEXT NOT NULL,
    attempted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Both lookups are "how many in the last N minutes", so both need the timestamp
-- in the index rather than a scan-and-filter.
CREATE INDEX IF NOT EXISTS idx_login_attempts_username
    ON login_attempts (username, attempted_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip
    ON login_attempts (ip, attempted_at);

-- ## The leaderboard needs a way out
--
-- It lists every registered account's name, XP and current streak, to every
-- other account, with no way to decline. Among friends who opted into a shared
-- tracker that is the feature. It is still not something anyone agreed to, and
-- "you can leave the app" is not consent.
--
-- Opting out removes the row entirely rather than anonymising it. A blanked-out
-- entry sitting between two named ones at 2-5 users is not anonymous - everyone
-- can name the person by elimination.
ALTER TABLE users ADD COLUMN leaderboard_opt_out INTEGER NOT NULL DEFAULT 0;
