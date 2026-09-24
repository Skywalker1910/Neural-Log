-- Invite codes: admin-generated, single-use registration tokens.
-- Replaces the single REGISTRATION_CODE env var with per-code tracking.

CREATE TABLE IF NOT EXISTS invite_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    UNIQUE NOT NULL,
    label       TEXT,                              -- optional note, e.g. "for Alice"
    created_by  INTEGER NOT NULL,                  -- admin user_id
    used_by     INTEGER,                           -- user_id of the account that redeemed it
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at     TIMESTAMP,
    revoked     INTEGER DEFAULT 0,
    FOREIGN KEY (created_by) REFERENCES users (id),
    FOREIGN KEY (used_by)    REFERENCES users (id)
);
