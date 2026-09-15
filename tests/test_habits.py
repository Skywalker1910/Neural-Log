"""Tests for the Paths-to-Habits migration and the habit schedules.

The stakes here are different from the other phases. Paths are the oldest thing
in the app and the only feature used every single day, and they are consumed by
the Jinja app, static/js/app.js and the SPA's Today page. The conversion is a
storage move that must not change a single byte of the payload those three see -
so most of these tests are about things NOT changing.
"""
import json
import sqlite3
from datetime import date, timedelta

import pytest

import habits
from conftest import register

TODAY = date.today()


@pytest.fixture()
def user(client, app_module):
    register(client, username="pathwalker")
    return client


def _conn(app_module):
    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _user_id(app_module, username="pathwalker"):
    conn = _conn(app_module)
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row["id"]


# --- the payload has not changed --------------------------------------------

def test_paths_payload_keeps_its_exact_shape(user):
    """Twelve call sites consume this. Any drift breaks the daily checklist."""
    payload = user.get("/api/paths").get_json()

    assert payload["success"] is True
    assert isinstance(payload["paths"], list) and payload["paths"]
    assert payload["selected_path_id"]

    path = payload["paths"][0]
    assert set(path) >= {"id", "name", "is_default", "checklist_items"}

    item = path["checklist_items"][0]
    assert set(item) >= {"id", "name", "type", "icon", "weight"}


def test_stock_path_ids_and_item_ids_survive_the_move(user, app_module):
    """daily_log.path_id, users.selected_path and every client already reference
    these strings. Replacing them with integers would orphan all of it."""
    payload = user.get("/api/paths").get_json()
    ids = {path["id"] for path in payload["paths"]}
    assert "batman-path" in ids

    conn = _conn(app_module)
    slugs = {row["slug"] for row in conn.execute("SELECT slug FROM habit_groups")}
    conn.close()
    assert "batman-path" in slugs


def test_checklist_items_endpoint_still_serves_the_selected_path(user):
    items = user.get("/api/checklist-items").get_json()["items"]
    assert items
    assert all("name" in item and "type" in item for item in items)


def test_weights_and_icons_survive(user):
    """The shipped weights are what make XP unequal across items - losing them
    in the move would silently flatten scoring."""
    items = user.get("/api/checklist-items").get_json()["items"]
    weights = {item["weight"] for item in items}
    icons = {item["icon"] for item in items}

    assert weights != {1}, "every item came back weight 1 - the weights were lost"
    assert icons != {"default"}, "every item came back on the default icon"


# --- the import ---------------------------------------------------------------

def test_import_happens_once_and_is_recorded(user, app_module):
    conn = _conn(app_module)
    row = conn.execute("SELECT * FROM habit_imports").fetchone()
    conn.close()

    assert row is not None
    assert row["habits_imported"] > 0


def test_a_removed_path_stays_removed(user, app_module):
    """The bug this guards against: re-importing the JSON on every load would
    silently undo any edit the user made."""
    payload = user.get("/api/paths").get_json()
    victim = next(p for p in payload["paths"] if p["id"] != payload["selected_path_id"])

    assert user.delete(f"/api/paths/{victim['id']}").status_code == 200

    after = user.get("/api/paths").get_json()
    assert victim["id"] not in {p["id"] for p in after["paths"]}

    # And still gone on a fresh load, which is where a re-import would show up.
    again = user.get("/api/paths").get_json()
    assert victim["id"] not in {p["id"] for p in again["paths"]}


def test_deleting_a_path_archives_rather_than_deletes(user, app_module):
    payload = user.get("/api/paths").get_json()
    victim = next(p for p in payload["paths"] if p["id"] != payload["selected_path_id"])
    user.delete(f"/api/paths/{victim['id']}")

    conn = _conn(app_module)
    row = conn.execute("SELECT archived FROM habit_groups WHERE slug = ?",
                       (victim["id"],)).fetchone()
    conn.close()
    assert row is not None, "the group was deleted - completions would be orphaned"
    assert row["archived"] == 1


def test_sql_is_the_live_source_not_the_json_file(user, app_module):
    """After the import, the JSON file must stop being read. Editing SQL directly
    and seeing it through the API is the proof."""
    user_id = _user_id(app_module)

    conn = _conn(app_module)
    conn.execute(
        "UPDATE habits SET name = 'Renamed in SQL' WHERE user_id = ? "
        "AND id = (SELECT MIN(id) FROM habits WHERE user_id = ?)",
        (user_id, user_id),
    )
    conn.commit()
    conn.close()

    names = [
        item["name"]
        for path in user.get("/api/paths").get_json()["paths"]
        for item in path["checklist_items"]
    ]
    assert "Renamed in SQL" in names


# --- editing paths ------------------------------------------------------------

def test_creating_a_custom_path_persists(user, app_module):
    response = user.post("/api/paths", json={
        "name": "My Path",
        "checklist_items": [
            {"name": "Did the thing", "type": "yes-no", "icon": "code", "weight": 2},
        ],
    })
    assert response.status_code == 201

    payload = user.get("/api/paths").get_json()
    mine = next(p for p in payload["paths"] if p["name"] == "My Path")
    assert mine["is_default"] is False
    assert mine["checklist_items"][0]["name"] == "Did the thing"
    assert mine["checklist_items"][0]["weight"] == 2


def test_editing_checklist_items_persists(user):
    user.put("/api/checklist-items", json={
        "items": [{"name": "Only item", "type": "yes-no", "icon": "sun", "weight": 3}],
    })
    items = user.get("/api/checklist-items").get_json()["items"]
    assert [item["name"] for item in items] == ["Only item"]


def test_selecting_a_path_sticks(user):
    payload = user.get("/api/paths").get_json()
    target = next(p for p in payload["paths"] if p["id"] != payload["selected_path_id"])

    response = user.put("/api/paths/selected", json={"path_id": target["id"]})
    assert response.status_code == 200

    assert user.get("/api/paths").get_json()["selected_path_id"] == target["id"]


# --- completions ---------------------------------------------------------------

def _submit(client, day, answers):
    return client.put(f"/api/days/{day}", json={"responses": answers})


def test_submitting_a_day_records_per_habit_completions(user, app_module):
    items = user.get("/api/checklist-items").get_json()["items"]
    yes_no = [item for item in items if item["type"] == "yes-no"][:3]
    _submit(user, TODAY.isoformat(), {item["name"]: "Yes" for item in yes_no})

    conn = _conn(app_module)
    rows = conn.execute(
        "SELECT h.name, c.response, c.credit FROM habit_completions c "
        "JOIN habits h ON h.id = c.habit_id WHERE c.date = ?",
        (TODAY.isoformat(),),
    ).fetchall()
    conn.close()

    assert len(rows) >= 3
    answered = {row["name"]: row for row in rows}
    for item in yes_no:
        assert answered[item["name"]]["credit"] == 1.0


def test_resubmitting_a_day_corrects_rather_than_duplicates(user, app_module):
    items = user.get("/api/checklist-items").get_json()["items"]
    first = next(item for item in items if item["type"] == "yes-no")

    _submit(user, TODAY.isoformat(), {first["name"]: "Yes"})
    _submit(user, TODAY.isoformat(), {first["name"]: "No"})

    conn = _conn(app_module)
    rows = conn.execute(
        "SELECT c.credit FROM habit_completions c JOIN habits h ON h.id = c.habit_id "
        "WHERE c.date = ? AND h.name = ?",
        (TODAY.isoformat(), first["name"]),
    ).fetchall()
    conn.close()

    assert len(rows) == 1, "a second submission should correct, not append"
    assert rows[0]["credit"] == 0.0


def test_completions_and_the_daily_log_agree(user, app_module):
    """They are written in one transaction precisely so they cannot drift."""
    items = user.get("/api/checklist-items").get_json()["items"]
    yes_no = [item for item in items if item["type"] == "yes-no"][:2]
    _submit(user, TODAY.isoformat(), {item["name"]: "Yes" for item in yes_no})

    conn = _conn(app_module)
    payload = json.loads(conn.execute(
        "SELECT payload_json FROM daily_log WHERE date = ?", (TODAY.isoformat(),)
    ).fetchone()["payload_json"])
    completions = {
        row["name"]: row["credit"] for row in conn.execute(
            "SELECT h.name, c.credit FROM habit_completions c "
            "JOIN habits h ON h.id = c.habit_id WHERE c.date = ?",
            (TODAY.isoformat(),))
    }
    conn.close()

    for item in payload["items"]:
        if item["name"] in completions:
            assert completions[item["name"]] == pytest.approx(item["credit"])


def test_a_rating_item_gets_no_completion_row(user, app_module):
    """Rating your day is self-reflection, not a habit you complete. It has
    weight 0, it is excluded from XP, and it is already stored as
    daily_log.self_rating - a streak of "rated my day" would mean nothing."""
    items = user.get("/api/checklist-items").get_json()["items"]
    rating = next((item for item in items if item["type"] == "rating"), None)
    assert rating is not None, "the stock path should still carry a rating item"

    answers = {item["name"]: "Yes" for item in items if item["type"] == "yes-no"}
    answers[rating["name"]] = "4"
    _submit(user, TODAY.isoformat(), answers)

    conn = _conn(app_module)
    row = conn.execute(
        "SELECT 1 FROM habit_completions c JOIN habits h ON h.id = c.habit_id "
        "WHERE h.name = ?", (rating["name"],)).fetchone()
    conn.close()
    assert row is None


def test_backfill_rebuilds_completions_from_existing_history(user, app_module):
    """The data-preserving half of the migration.

    Someone who already had months of checklist history must not lose it when
    storage moves. The live database happened to have an empty daily_log when
    this shipped, so this is the only thing exercising that path.
    """
    items = user.get("/api/checklist-items").get_json()["items"]
    tracked = [item for item in items if item["type"] == "yes-no"][:2]

    for offset in range(3):
        _submit(user, (TODAY - timedelta(days=offset)).isoformat(),
                {item["name"]: "Yes" for item in tracked})

    user_id = _user_id(app_module)
    conn = _conn(app_module)

    # Wipe the index and rebuild it from the daily_log snapshots alone.
    conn.execute("DELETE FROM habit_completions WHERE user_id = ?", (user_id,))
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM habit_completions WHERE user_id = ?",
        (user_id,)).fetchone()["n"] == 0

    written = habits.backfill_completions(conn, user_id)
    conn.commit()

    rebuilt = conn.execute(
        "SELECT h.name, c.date, c.credit FROM habit_completions c "
        "JOIN habits h ON h.id = c.habit_id WHERE c.user_id = ?", (user_id,)
    ).fetchall()
    conn.close()

    assert written > 0
    assert len(rebuilt) >= len(tracked) * 3
    assert all(row["credit"] == 1.0 for row in rebuilt
               if row["name"] in {item["name"] for item in tracked})


def test_backfill_is_idempotent(user, app_module):
    items = user.get("/api/checklist-items").get_json()["items"]
    tracked = next(item for item in items if item["type"] == "yes-no")
    _submit(user, TODAY.isoformat(), {tracked["name"]: "Yes"})

    user_id = _user_id(app_module)
    conn = _conn(app_module)
    habits.backfill_completions(conn, user_id)
    habits.backfill_completions(conn, user_id)
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM habit_completions WHERE user_id = ? AND date = ?",
        (user_id, TODAY.isoformat())).fetchone()["n"]
    conn.close()

    # One row per habit per day however many times it runs.
    assert count == len([i for i in items if i["type"] != "rating"])


# --- schedules ----------------------------------------------------------------

def test_a_daily_habit_is_always_due():
    assert habits.is_due({"schedule_type": "daily"}, TODAY)


def test_weekday_habits_skip_the_weekend():
    monday = date(2026, 9, 14)
    saturday = date(2026, 9, 19)
    assert habits.is_due({"schedule_type": "weekdays"}, monday)
    assert not habits.is_due({"schedule_type": "weekdays"}, saturday)


def test_specific_days_are_honoured():
    monday = date(2026, 9, 14)
    wednesday = date(2026, 9, 16)
    habit = {"schedule_type": "days", "schedule_days": [0, 4]}  # Monday and Friday
    assert habits.is_due(habit, monday)
    assert not habits.is_due(habit, wednesday)


def test_schedule_days_survive_being_stored_as_json():
    habit = {"schedule_type": "days", "schedule_days": "[0, 4]"}
    assert habits.is_due(habit, date(2026, 9, 14))


def test_times_per_week_is_always_offerable():
    """It has no particular day, so "is it due today" has no honest answer beyond
    "you could". Whether you are behind is a weekly question."""
    habit = {"schedule_type": "times-per-week", "target_per_week": 3}
    assert habits.is_due(habit, date(2026, 9, 19))


def test_an_unknown_schedule_falls_back_to_daily():
    assert habits.is_due({"schedule_type": "lunar"}, TODAY)


# --- stats ---------------------------------------------------------------------

def test_habit_stats_report_streaks(user, app_module):
    items = user.get("/api/checklist-items").get_json()["items"]
    tracked = next(item for item in items if item["type"] == "yes-no")

    for offset in range(3):
        day = (TODAY - timedelta(days=offset)).isoformat()
        _submit(user, day, {tracked["name"]: "Yes"})

    conn = _conn(app_module)
    stats = habits.habit_stats(conn, _user_id(app_module), on_date=TODAY)
    conn.close()

    entry = next(row for row in stats if row["name"] == tracked["name"])
    assert entry["streak"] == 3
    assert entry["done"] == 3


def test_a_streak_survives_not_having_logged_yet_today(user, app_module):
    items = user.get("/api/checklist-items").get_json()["items"]
    tracked = next(item for item in items if item["type"] == "yes-no")

    for offset in range(1, 4):
        _submit(user, (TODAY - timedelta(days=offset)).isoformat(),
                {tracked["name"]: "Yes"})

    conn = _conn(app_module)
    stats = habits.habit_stats(conn, _user_id(app_module), on_date=TODAY)
    conn.close()

    entry = next(row for row in stats if row["name"] == tracked["name"])
    assert entry["streak"] == 3


def test_saying_no_does_not_extend_a_streak(user, app_module):
    items = user.get("/api/checklist-items").get_json()["items"]
    tracked = next(item for item in items if item["type"] == "yes-no")

    _submit(user, (TODAY - timedelta(days=1)).isoformat(), {tracked["name"]: "Yes"})
    _submit(user, TODAY.isoformat(), {tracked["name"]: "No"})

    conn = _conn(app_module)
    stats = habits.habit_stats(conn, _user_id(app_module), on_date=TODAY)
    conn.close()

    entry = next(row for row in stats if row["name"] == tracked["name"])
    assert entry["streak"] == 0, "a logged 'No' is a miss, not a completion"


# --- isolation -----------------------------------------------------------------

def test_habits_are_scoped_to_their_owner(user, client, app_module):
    user.get("/logout")
    register(client, username="someone-else")

    mine = _user_id(app_module, "someone-else")
    conn = _conn(app_module)
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM habits WHERE user_id != ?", (mine,)).fetchone()
    theirs = conn.execute(
        "SELECT COUNT(*) AS n FROM habits WHERE user_id = ?", (mine,)).fetchone()
    conn.close()

    assert rows["n"] > 0 and theirs["n"] > 0
    assert client.get("/api/paths").get_json()["paths"]
