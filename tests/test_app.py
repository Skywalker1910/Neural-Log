"""Smoke tests for the core auth / activity / checklist flows.

These don't aim for full coverage - they exist to catch regressions in the
paths that matter most (a broken login or a broken checklist save ruins the
app for everyone using it). Each test gets a fresh temp SQLite DB and a fresh
`artifacts/` directory so tests never touch real project data.
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


def test_register_creates_first_user_as_admin(client):
    resp = register(client)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["is_admin"] is True  # first registered user is auto-promoted


def test_login_accepts_correct_and_rejects_wrong_password(client):
    register(client)
    client.get("/logout")

    good = login(client)
    assert good.status_code == 200
    assert good.get_json()["success"] is True

    bad = login(client, password="wrong-password")
    assert bad.status_code == 401
    assert bad.get_json()["success"] is False


def test_current_user_requires_login(client):
    resp = client.get("/api/current-user")
    # login_required redirects anonymous requests to the login page
    assert resp.status_code == 302


def test_current_user_reports_selected_path_after_registration(client):
    register(client)
    resp = client.get("/api/current-user")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["username"] == "alice"
    assert data["selected_path"] == "Batman Path"


def test_activity_create_list_delete_roundtrip(client):
    register(client)

    created = client.post(
        "/api/activities",
        json={
            "date": "2026-01-01",
            "activity_name": "Exercise",
            "description": "Ran 5k",
            "duration": 30,
            "progress_score": 8,
            "notes": "Felt great",
        },
    )
    assert created.status_code == 201
    activity_id = created.get_json()["id"]

    listed = client.get("/api/activities").get_json()
    assert any(a["id"] == activity_id for a in listed)

    deleted = client.delete(f"/api/activities/{activity_id}")
    assert deleted.status_code == 200

    listed_after = client.get("/api/activities").get_json()
    assert all(a["id"] != activity_id for a in listed_after)


def test_daily_checklist_submission_persists_completion_percent(client, app_module):
    """Regression test: mirrors the exact payload static/js/app.js posts from
    handleDailyChecklistSubmit(), including `completion_percent` - the field
    that used to throw a ReferenceError client-side before it was computed
    locally (see docs/CHANGELOG.md)."""
    register(client)

    resp = client.post(
        "/api/activities",
        json={
            "date": "2026-01-01",
            "activity_name": "Daily Checklist",
            "description": "1/2 completed",
            "duration": 0,
            "progress_score": 6,
            "notes": "",
            "checklist_data": {
                "date": "2026-01-01",
                "checklist": {"custom_0": "Yes"},
                "custom_responses": {"Did you work out today?": "Yes"},
                "selected_path_id": "batman-path",
                "selected_path_name": "Batman Path",
                "completion_percent": 50,
                "notes": "",
            },
        },
    )
    assert resp.status_code == 201

    checklist_file = app_module.get_checklist_file_path("alice")
    assert checklist_file.exists()
    saved_line = checklist_file.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert '"completion_percent": 50' in saved_line


def test_paths_endpoint_lists_default_paths_for_new_user(client):
    register(client)
    resp = client.get("/api/paths")
    assert resp.status_code == 200
    data = resp.get_json()
    path_names = {path["name"] for path in data["paths"]}
    assert path_names == {"Batman Path", "Thor Path", "Captain America Path", "Ironman Path"}
