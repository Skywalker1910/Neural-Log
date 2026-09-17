"""Smoke tests for the core auth / activity / checklist flows.

These don't aim for full coverage - they exist to catch regressions in the
paths that matter most (a broken login or a broken checklist save ruins the
app for everyone using it). Fixtures (app_module, client) come from conftest.py.
"""
from conftest import core_survey, register, login


def test_register_creates_first_user_as_admin(client):
    resp = register(client)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["is_admin"] is True  # first registered user is auto-promoted


def test_login_accepts_correct_and_rejects_wrong_password(client):
    register(client)
    client.post("/logout")

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


def test_current_user_reports_the_account_after_registration(client):
    """selected_path used to be here and used to be a real choice. Migration 011
    retired the four hero Paths for one shared survey, so the field survives only
    as the synthetic name three clients still read."""
    register(client)
    resp = client.get("/api/current-user")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["username"] == "alice"
    assert data["selected_path"] == "Daily survey"


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


def test_classic_page_renders_for_logged_in_user(client):
    """Catches template errors in index.html (Jinja syntax, broken tags, etc.).

    R8 moved this off / - the SPA is the app now - but the classic dashboard is
    still the only home of the Excel export, so it keeps its own address and
    keeps being checked."""
    register(client)
    resp = client.get("/classic")
    assert resp.status_code == 200
    assert b"checklistWizard" in resp.data


def test_paths_endpoint_returns_the_one_shared_survey(client):
    """Four hero Paths became one shared survey. The endpoint keeps its shape
    because the Jinja app, static/js/app.js and the SPA all read it, and all
    three only ever used it to find the list of questions."""
    register(client)
    resp = client.get("/api/paths")
    assert resp.status_code == 200
    data = resp.get_json()

    assert [path["name"] for path in data["paths"]] == ["Daily survey"]
    assert data["selected_path_id"] == "daily-survey"
    assert len(data["paths"][0]["checklist_items"]) == 10


def test_every_survey_question_has_a_valid_icon_key(app_module):
    """Every shared question must reference an icon the resolver knows - see
    ICON_KEYS, and ICON_ATTRIBUTES in scoring/config.py, which reads the same
    vocabulary to decide what an item feeds."""
    for item in core_survey(app_module):
        assert item["icon"] in app_module.ICON_KEYS, item["name"]


def test_every_survey_question_states_the_attributes_it_feeds(app_module):
    """The shared survey uses the resolver's explicit tier rather than leaving it
    to keyword matching, so rewording a question cannot silently change which
    attribute it feeds. An empty dict is a real answer - "this feeds none".
    """
    inferred_ok = {"core-connection", "core-rating"}  # both feed nothing, by design
    for item in core_survey(app_module):
        if item["id"] in inferred_ok:
            continue
        assert item.get("attributes"), item["name"]


def test_deleting_a_user_removes_all_their_data(client, app_module):
    """Deleting an account must not leave the person's data behind - neither the
    per-user SQL rows nor their Path/submission files on disk. Nothing cascades:
    SQLite foreign keys are not enabled, so every table is deleted explicitly."""
    import scoring

    register(client)  # first user -> admin, stays logged in as the deleter

    conn = app_module.get_db_connection()
    conn.execute("INSERT INTO users (username, password_hash) VALUES ('victim', 'x')")
    conn.commit()
    victim = conn.execute(
        "SELECT id FROM users WHERE username = 'victim'").fetchone()["id"]

    items = core_survey(app_module)
    answers = {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}

    conn.execute("INSERT INTO activities (user_id, date, activity_name) "
                 "VALUES (?, '2026-09-01', 'Daily Checklist')", (victim,))
    conn.execute("INSERT INTO daily_xp (user_id, date, base_xp, "
                 "streak_multiplier_pct, total_xp) VALUES (?, '2026-09-01', 10, 0, 10)",
                 (victim,))
    conn.execute("INSERT INTO user_badges (user_id, badge_code) VALUES (?, 'first-log')",
                 (victim,))
    scoring.record_day(conn, victim, "2026-09-01", items, answers)
    conn.commit()
    scoring.recompute_scores(conn, victim)
    conn.commit()

    paths_file = app_module.get_user_paths_file_path("victim")
    paths_file.write_text("{}", encoding="utf-8")
    conn.close()

    assert client.delete(f"/api/admin/users/{victim}").status_code == 200

    conn = app_module.get_db_connection()
    for table in ("activities", "milestones", "daily_xp", "user_badges",
                  "daily_log", "attribute_scores", "daily_scores"):
        remaining = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?", (victim,)
        ).fetchone()["n"]
        assert remaining == 0, f"{table} still holds rows for the deleted user"
    assert conn.execute("SELECT COUNT(*) AS n FROM users WHERE id = ?",
                        (victim,)).fetchone()["n"] == 0
    conn.close()

    assert not paths_file.exists(), "the deleted user's Path file is still on disk"


def test_admin_can_suspend_and_resume_an_account(client):
    register(client, username="alice")
    client.post("/logout")
    register(client, username="bob")
    client.post("/logout")
    login(client, username="alice")

    users = client.get("/api/admin/users").get_json()
    bob = next(user for user in users if user["username"] == "bob")
    assert bob["is_active"] is True

    suspended = client.post(f"/api/admin/users/{bob['id']}/toggle-active")
    assert suspended.status_code == 200
    assert suspended.get_json()["is_active"] is False

    client.post("/logout")
    assert login(client, username="bob").status_code == 401

    login(client, username="alice")
    resumed = client.post(f"/api/admin/users/{bob['id']}/toggle-active")
    assert resumed.status_code == 200
    assert resumed.get_json()["is_active"] is True

    client.post("/logout")
    assert login(client, username="bob").status_code == 200


def test_admin_overview_reports_account_and_workspace_state(client):
    register(client)

    overview = client.get("/api/admin/stats")

    assert overview.status_code == 200
    payload = overview.get_json()
    assert payload["accounts"] == {
        "total": 1,
        "active": 1,
        "admins": 1,
        "active_this_week": 0,
    }
    assert payload["database_integrity"] == "ok"
    assert set(payload["features"]) == {"workouts", "meals", "learning_sessions", "goals", "habits"}


def test_admin_route_serves_the_spa_for_an_admin(client):
    register(client)

    response = client.get("/admin")

    assert response.status_code == 200
    assert (
        b'<div id="root"></div>' in response.data
        or b"The app hasn't been built yet" in response.data
    )
