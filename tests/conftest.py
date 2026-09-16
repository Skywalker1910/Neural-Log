"""Shared pytest fixtures/helpers for the test suite.

Fixtures here (app_module, client) are auto-discovered by pytest for every test
module in this directory. The register()/login() helpers are plain functions -
import them explicitly where needed.
"""
import sys

import pytest


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    """Import a fresh copy of the Flask app pointed at an isolated temp DB."""
    db_path = tmp_path / "test_neural_log.db"
    monkeypatch.setenv("DATABASE", str(db_path))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FLASK_DEBUG", "0")

    # app.py writes artifacts/{paths,checklists}/*.json(l) relative to the cwd -
    # run inside tmp_path so tests never touch the real artifacts/ directory.
    monkeypatch.chdir(tmp_path)

    sys.modules.pop("app", None)
    import app as imported_app

    imported_app.init_db()
    imported_app.app.config.update(TESTING=True)
    yield imported_app
    sys.modules.pop("app", None)


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


def register(client, username="alice", password="password123", **extra):
    payload = {"username": username, "password": password}
    payload.update(extra)
    return client.post("/register", json=payload)


def survey_items(client):
    """The questions this account is asked, through the compatibility view.

    Migration 011 replaced the four hero Paths with one shared survey, so the
    paths payload now holds exactly one entry and there is no id to look it up
    by - which is why so many tests used to say `p['id'] == 'batman-path'`.
    """
    paths = client.get("/api/paths").get_json()["paths"]
    return paths[0]["checklist_items"] if paths else []


def core_survey(app_module):
    """The shared survey straight from the database.

    For tests that call the scoring engine directly rather than over HTTP.
    user_id=None returns the core set alone.
    """
    import habits

    conn = app_module.get_db_connection()
    try:
        return habits.load_survey(conn, None)
    finally:
        conn.close()


def login(client, username="alice", password="password123"):
    return client.post("/login", json={"username": username, "password": password})
