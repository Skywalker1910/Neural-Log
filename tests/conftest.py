"""Shared pytest fixtures/helpers for the test suite.

Fixtures here (app_module, client) are auto-discovered by pytest for every test
module in this directory. The register()/login() helpers are plain functions -
import them explicitly where needed.
"""
import shutil
import sys

import pytest


@pytest.fixture(scope="session")
def database_template(tmp_path_factory):
    """One fully migrated, fully seeded database, built once for the whole run.

    Every test gets its own database, and it used to build each one from nothing:
    fifteen migrations, then seeding 136 exercises, 233 foods and 23 achievements.
    That is 0.73s of setup per test, and with 400-odd tests it was the suite -
    roughly five minutes of the six spent creating databases rather than testing
    anything.

    Copying a prepared file instead costs 0.03s. Same schema, same seed data, same
    isolation - the copy is a separate file, so a test can still do anything it
    likes to it.
    """
    build = tmp_path_factory.mktemp("db-template")
    template = build / "template.db"

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE", str(template))
        patch.setenv("SECRET_KEY", "test-secret-key")
        patch.setenv("FLASK_DEBUG", "0")
        patch.chdir(build)

        # Importing app runs init_db() at module scope, which is what builds it.
        sys.modules.pop("app", None)
        import app  # noqa: F401
        sys.modules.pop("app", None)

    return template


@pytest.fixture()
def app_module(tmp_path, monkeypatch, database_template):
    """Import a fresh copy of the Flask app pointed at an isolated temp DB."""
    db_path = tmp_path / "test_neural_log.db"
    shutil.copyfile(database_template, db_path)

    monkeypatch.setenv("DATABASE", str(db_path))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FLASK_DEBUG", "0")

    # app.py writes artifacts/{paths,checklists}/*.json(l) relative to the cwd -
    # run inside tmp_path so tests never touch the real artifacts/ directory.
    monkeypatch.chdir(tmp_path)

    # The module still re-imports per test, because DATABASE is read at import
    # time and that is what points this copy of the app at this test's file.
    # init_db() runs again on the way in and finds everything already applied,
    # which is the cheap path and also proves the ledger is honest.
    sys.modules.pop("app", None)
    import app as imported_app

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
