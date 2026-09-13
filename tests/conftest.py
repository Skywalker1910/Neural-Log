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
    payload = {"username": username, "password": password, "selected_path": "Batman Path"}
    payload.update(extra)
    return client.post("/register", json=payload)


def login(client, username="alice", password="password123"):
    return client.post("/login", json={"username": username, "password": password})
