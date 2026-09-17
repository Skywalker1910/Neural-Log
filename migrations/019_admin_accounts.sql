-- Administrators need a reversible way to stop an account from using the app.
--
-- Deleting an account removes its history permanently. Suspending it is the
-- safer first response when someone loses a device, leaves a shared instance,
-- or simply needs their access paused. The application checks this field on
-- every authenticated request, so an already-open session stops working too.
ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_users_active_created
    ON users (is_active, created_at);
