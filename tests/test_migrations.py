"""Tests for the schema migration runner and the SPA mount point.

The runner resolves migrations/ relative to app.py rather than the cwd - these
tests run inside a tmp directory (see conftest.py), so they'd fail outright if
that ever regressed to a cwd-relative path.
"""
from conftest import register

BASELINE_TABLES = ["users", "activities", "milestones", "daily_xp", "user_badges"]


def applied_versions(app_module):
    conn = app_module.get_db_connection()
    try:
        return [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
    finally:
        conn.close()


def test_migrations_record_and_create_baseline_schema(app_module):
    assert "001_baseline" in applied_versions(app_module)

    conn = app_module.get_db_connection()
    try:
        names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    finally:
        conn.close()

    for table in BASELINE_TABLES:
        assert table in names


def test_migrations_are_idempotent(app_module):
    """init_db() runs on every boot - a second pass must not re-apply anything."""
    before = applied_versions(app_module)

    app_module.init_db()
    app_module.init_db()

    assert applied_versions(app_module) == before


def test_migrations_preserve_existing_rows(app_module):
    """Re-running migrations against a populated database must not touch data."""
    client = app_module.app.test_client()
    register(client)

    app_module.init_db()

    conn = app_module.get_db_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    finally:
        conn.close()


def test_spa_route_requires_login(client):
    resp = client.get("/app")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_spa_route_serves_shell_for_logged_in_user(client):
    register(client)
    resp = client.get("/app")
    assert resp.status_code == 200
    # Either the built bundle or the "run npm build" helper page - both mean the
    # route resolved rather than 404ing.
    assert b"<!doctype html" in resp.data.lower()


def test_spa_client_routes_fall_through_to_the_shell(client):
    """Deep links like /app/training must serve the shell, not 404."""
    register(client)
    assert client.get("/app/training").status_code == 200
