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

def test_the_core_survey_is_one_shared_set_not_a_copy_each(user, app_module):
    """The point of the model. Forty habit rows per account became one set owned
    by nobody, which is what makes completion percentages comparable between
    people in the first place."""
    conn = _conn(app_module)
    core = conn.execute(
        "SELECT COUNT(*) AS n FROM habits WHERE is_core = 1 AND archived = 0"
    ).fetchone()["n"]
    owned_core = conn.execute(
        "SELECT COUNT(*) AS n FROM habits WHERE is_core = 1 AND user_id IS NOT NULL"
    ).fetchone()["n"]
    conn.close()

    assert core == 10
    assert owned_core == 0, "a core question belongs to nobody"


def test_a_personal_question_is_yours_alone(user, client, app_module):
    """Everyone shares the core set; anything added on top is private."""
    added = user.post("/api/survey/questions",
                      json={"name": "Did you practise guitar?"}).get_json()
    assert added["is_core"] is False

    mine = [q["name"] for q in user.get("/api/survey").get_json()["questions"]]
    assert "Did you practise guitar?" in mine

    user.get("/logout")
    register(client, username="someone-else")
    theirs = client.get("/api/survey").get_json()["questions"]

    assert "Did you practise guitar?" not in [q["name"] for q in theirs]
    # ...but the shared half is identical.
    assert len([q for q in theirs if q["is_core"]]) == 10


def test_two_people_answering_a_shared_question_do_not_collide(user, client, app_module):
    """Before migration 012 the completions index was unique on (habit_id, date),
    which was fine when every habit belonged to one account. A shared question
    made that a contested slot: whoever answered first owned the day, and the
    next person's answer overwrote theirs."""
    day = TODAY.isoformat()
    core = [q for q in user.get("/api/survey").get_json()["questions"]
            if q["is_core"] and q["type"] == "yes-no"][0]

    _submit(user, day, {core["name"]: "Yes"})
    user.get("/logout")

    register(client, username="someone-else")
    _submit(client, day, {core["name"]: "No"})

    conn = _conn(app_module)
    rows = conn.execute(
        "SELECT c.user_id, c.response FROM habit_completions c "
        "JOIN habits h ON h.id = c.habit_id "
        "WHERE h.slug = ? AND c.date = ? ORDER BY c.user_id",
        (core["id"], day),
    ).fetchall()
    conn.close()

    assert len(rows) == 2, "each person keeps their own answer"
    assert [row["response"] for row in rows] == ["Yes", "No"]
