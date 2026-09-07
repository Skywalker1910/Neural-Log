"""Tests for the Phase 2 gamification system: XP scoring, levels, the streak
multiplier, badges, and the two leaderboards. See docs/GAMIFICATION.md for the
spec these implement.
"""
from datetime import datetime, timedelta

from conftest import register, login


def _answer_all(path, all_yes=True):
    """Build a custom_responses dict that answers every scorable item on a
    Path (skips rating items, same as the real wizard would for a "did
    everything" day)."""
    responses = {}
    for item in path["checklist_items"]:
        if item["type"] == "rating":
            continue
        if item["type"] == "time":
            responses[item["name"]] = item["options"][0]
        else:
            responses[item["name"]] = "Yes" if all_yes else "No"
    return responses


def _submit_checklist(client, date, path, all_yes=True, completion_percent=100):
    return client.post(
        "/api/activities",
        json={
            "date": date,
            "activity_name": "Daily Checklist",
            "description": "test day",
            "duration": 0,
            "progress_score": 10,
            "notes": "",
            "checklist_data": {
                "date": date,
                "checklist": {},
                "custom_responses": _answer_all(path, all_yes=all_yes),
                "selected_path_id": path["id"],
                "selected_path_name": path["name"],
                "completion_percent": completion_percent,
                "notes": "",
            },
        },
    )


def test_calculate_daily_xp_weights_completed_items_and_skips_rating(app_module):
    items = [
        {"name": "A", "type": "yes-no", "weight": 3},
        {"name": "B", "type": "yes-no", "weight": 1},
        {"name": "C", "type": "rating", "weight": 0},
        {"name": "D", "type": "time", "weight": 1},
    ]
    responses = {"A": "Yes", "B": "No", "C": "5", "D": "05:00 - 05:30 AM"}
    # A completed (weight 3), B answered "No" so not completed, C is a rating
    # (excluded regardless of weight), D is a completed time answer (weight 1)
    assert app_module.calculate_daily_xp(items, responses) == (3 + 1) * app_module.XP_PER_WEIGHT_POINT


def test_compute_level_thresholds(app_module):
    assert app_module.compute_level(0) == (1, 0, 50)
    assert app_module.compute_level(49) == (1, 49, 50)
    assert app_module.compute_level(50) == (2, 0, 150)
    assert app_module.compute_level(199) == (2, 149, 150)
    assert app_module.compute_level(200) == (3, 0, 250)


def test_daily_checklist_awards_weighted_xp_and_first_day_badges(client, app_module):
    register(client)
    batman_path = next(p for p in app_module.DEFAULT_PATH_LIBRARY if p["id"] == "batman-path")
    expected_base_xp = sum(
        item["weight"] for item in batman_path["checklist_items"] if item["type"] != "rating"
    ) * app_module.XP_PER_WEIGHT_POINT

    today = datetime.now().strftime("%Y-%m-%d")
    resp = _submit_checklist(client, today, batman_path)
    assert resp.status_code == 201

    newly_earned = {b["code"] for b in resp.get_json()["newly_earned_badges"]}
    assert "first-log" in newly_earned
    assert "perfect-day" in newly_earned

    # First day logged -> streak of 1 -> +2% multiplier
    expected_total_xp = round(expected_base_xp * 1.02)

    summary = client.get("/api/gamification/summary").get_json()
    assert summary["total_xp"] == expected_total_xp
    assert summary["current_streak"] == 1
    assert summary["streak_multiplier_pct"] == 2

    earned_codes = {b["code"] for b in summary["badges"] if b["earned"]}
    assert {"first-log", "perfect-day"}.issubset(earned_codes)


def test_resubmitting_same_day_recalculates_instead_of_stacking(client, app_module):
    register(client)
    batman_path = next(p for p in app_module.DEFAULT_PATH_LIBRARY if p["id"] == "batman-path")
    today = datetime.now().strftime("%Y-%m-%d")

    _submit_checklist(client, today, batman_path, all_yes=True)
    first_total = client.get("/api/gamification/summary").get_json()["total_xp"]

    # Resubmit the same day answering "No" to every yes/no item - should
    # replace the day's XP, not add to it. The wake-time item still counts
    # (it's a "time" item, always answered, no yes/no state), so the floor
    # is that item's weight, not zero.
    _submit_checklist(client, today, batman_path, all_yes=False, completion_percent=0)
    second_total = client.get("/api/gamification/summary").get_json()["total_xp"]

    time_only_base_xp = sum(
        item["weight"] for item in batman_path["checklist_items"] if item["type"] == "time"
    ) * app_module.XP_PER_WEIGHT_POINT

    assert first_total > round(time_only_base_xp * 1.02)
    assert second_total == round(time_only_base_xp * 1.02)


def test_seven_day_streak_unlocks_badge_and_scales_multiplier(client, app_module):
    register(client)
    batman_path = next(p for p in app_module.DEFAULT_PATH_LIBRARY if p["id"] == "batman-path")
    today = datetime.now().date()

    last_response = None
    for offset in range(6, -1, -1):  # oldest -> newest, ending today
        day = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        last_response = _submit_checklist(client, day, batman_path)

    newly_earned = {b["code"] for b in last_response.get_json()["newly_earned_badges"]}
    assert "week-streak" in newly_earned

    summary = client.get("/api/gamification/summary").get_json()
    assert summary["current_streak"] == 7
    assert summary["streak_multiplier_pct"] == 14  # 7 days * 2% per day


def test_leaderboard_overall_and_monthly_scoping(client, app_module):
    register(client, username="alice")
    register(client, username="bob")

    conn = app_module.get_db_connection()
    alice_id = conn.execute("SELECT id FROM users WHERE username = 'alice'").fetchone()["id"]
    bob_id = conn.execute("SELECT id FROM users WHERE username = 'bob'").fetchone()["id"]

    today = datetime.now().strftime("%Y-%m-%d")
    # Guaranteed to fall in the previous calendar month regardless of run date
    last_month_date = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")

    conn.executemany(
        "INSERT INTO daily_xp (user_id, date, base_xp, streak_multiplier_pct, total_xp) VALUES (?, ?, ?, ?, ?)",
        [
            (alice_id, today, 100, 0, 100),
            (bob_id, today, 50, 0, 50),
            (bob_id, last_month_date, 200, 0, 200),
        ],
    )
    conn.commit()
    conn.close()

    login(client, username="alice")

    monthly = client.get("/api/leaderboard/monthly").get_json()["entries"]
    assert [(e["username"], e["total_xp"]) for e in monthly] == [("alice", 100), ("bob", 50)]

    overall = client.get("/api/leaderboard/overall").get_json()["entries"]
    # bob: 50 (this month) + 200 (last month) = 250, ahead of alice's 100
    assert [(e["username"], e["total_xp"]) for e in overall] == [("bob", 250), ("alice", 100)]


def test_leaderboard_rejects_unknown_scope(client):
    register(client)
    resp = client.get("/api/leaderboard/yearly")
    assert resp.status_code == 400
