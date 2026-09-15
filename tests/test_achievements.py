"""Tests for the R7 achievement catalogue.

The catalogue stopped being eight dicts carrying check() lambdas and became data:
a metric name and a threshold. That change exists so a locked achievement can say
"18 of 30 nights" instead of sitting greyed out, and these check that the
progress it reports is real rather than decorative.
"""
import sqlite3

import pytest

import achievements
from conftest import register

TODAY_CODES = {entry["code"] for entry in achievements.CATALOGUE}


@pytest.fixture()
def hero(client):
    register(client, username="hero")
    return client


def _summary(client):
    return client.get("/api/gamification/summary").get_json()


def _badge(client, code):
    return next(b for b in _summary(client)["badges"] if b["code"] == code)


# --- the catalogue -----------------------------------------------------------

def test_the_legacy_eight_keep_their_codes():
    """user_badges rows reference these. Renaming one silently un-earns it for
    everyone who had it."""
    legacy = {"first-log", "week-streak", "month-streak", "century",
              "custom-path", "perfect-day", "level-5", "level-10"}
    assert legacy <= TODAY_CODES


def test_every_achievement_has_a_metric_and_threshold():
    """An entry without both cannot report progress, which is the whole reason
    the catalogue stopped being lambdas."""
    for entry in achievements.CATALOGUE:
        assert entry.get("metric"), f'{entry["code"]} has no metric'
        assert entry.get("threshold"), f'{entry["code"]} has no threshold'
        assert entry["category"] in achievements.CATEGORIES
        assert entry["tier"] in (achievements.BRONZE, achievements.SILVER, achievements.GOLD)


def test_codes_are_unique():
    codes = [entry["code"] for entry in achievements.CATALOGUE]
    assert len(codes) == len(set(codes))


def test_every_metric_exists_in_the_context(hero, app_module):
    """A typo in a metric name would make an achievement permanently unreachable
    while looking perfectly fine on screen."""
    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    user_id = conn.execute("SELECT id FROM users WHERE username = 'hero'").fetchone()["id"]
    ctx = app_module.achievement_context(conn, user_id)
    conn.close()

    for entry in achievements.CATALOGUE:
        assert entry["metric"] in ctx, (
            f'{entry["code"]} reads "{entry["metric"]}", which the context never sets'
        )


def test_the_catalogue_is_synced_into_the_database(hero, app_module):
    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    stored = {row["code"] for row in conn.execute("SELECT code FROM achievements")}
    conn.close()
    assert TODAY_CODES <= stored


def test_syncing_twice_changes_nothing(hero, app_module):
    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    achievements.sync_catalogue(conn)
    added, updated = achievements.sync_catalogue(conn)
    conn.close()
    assert (added, updated) == (0, 0)


# --- progress ----------------------------------------------------------------

def test_a_locked_achievement_reports_how_close_you_are(hero):
    """The point of the rewrite. "18 of 30" beats a grey box."""
    for _ in range(3):
        hero.post("/api/learning/sessions", json={
            "date": "2026-09-10", "duration_minutes": 60, "started_at": "09:00"})

    badge = _badge(hero, "study-10h")  # 600 minutes
    assert badge["earned"] is False
    assert badge["current"] == 180
    assert badge["threshold"] == 600
    assert badge["progress"] == pytest.approx(0.3, abs=0.01)


def test_progress_never_exceeds_one(hero):
    hero.post("/api/learning/sessions", json={
        "date": "2026-09-10", "duration_minutes": 700, "started_at": "09:00"})
    assert _badge(hero, "study-10h")["progress"] <= 1.0


def test_an_earned_achievement_reads_as_complete(hero):
    hero.post("/api/learning/sessions", json={
        "date": "2026-09-10", "duration_minutes": 30, "started_at": "09:00"})
    badge = _badge(hero, "first-study")
    assert badge["earned"] is True
    assert badge["progress"] == 1.0


def test_untouched_workspaces_report_zero_not_missing(hero):
    """A brand-new account should see every achievement with honest progress,
    not a partial list."""
    badges = _summary(hero)["badges"]
    assert {b["code"] for b in badges} == TODAY_CODES

    # Not all zero: everyone starts at level 1, so "reach level 5" is already
    # one fifth done. Progress being non-zero out of the gate is correct.
    untouched = [b for b in badges if b["code"].startswith(("first-", "study-", "nights-"))]
    assert all(b["progress"] == 0 for b in untouched if not b["earned"])
    assert all(0 <= b["progress"] <= 1 for b in badges)


# --- unlocking ---------------------------------------------------------------

def test_workspace_achievements_unlock_from_workspace_activity(hero):
    """Before R7 nothing outside the checklist could unlock anything."""
    assert _badge(hero, "first-workout")["earned"] is False

    exercises = hero.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])
    workout = hero.post("/api/workouts",
                        json={"date": "2026-09-10", "name": "Push"}).get_json()
    hero.put(f"/api/workouts/{workout['id']}", json={"sets": [
        {"exercise_id": bench["id"], "weight": 80, "reps": 8}]})

    # R7: unlocking no longer waits for a checklist submission. Logging the
    # workout is itself enough for the app to notice.
    assert _badge(hero, "first-workout")["earned"] is True


def test_unlocking_pays_xp_through_the_ledger(hero, app_module):
    items = hero.get("/api/checklist-items").get_json()["items"]
    hero.put("/api/days/2026-09-10", json={
        "responses": {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT source_key, xp FROM xp_transactions WHERE source = 'badge'")]
    conn.close()

    assert rows, "unlocking an achievement should write to the ledger"
    assert all(r["xp"] > 0 for r in rows)
    assert any(r["source_key"] == "badge:first-log" for r in rows)


def test_an_achievement_pays_only_once(hero, app_module):
    items = hero.get("/api/checklist-items").get_json()["items"]
    answers = {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}

    hero.put("/api/days/2026-09-10", json={"responses": answers})
    hero.put("/api/days/2026-09-10", json={"responses": answers})
    hero.put("/api/days/2026-09-10", json={"responses": answers})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM xp_transactions "
        "WHERE source = 'badge' AND source_key = 'badge:first-log'").fetchone()["n"]
    conn.close()
    assert count == 1


def test_badge_xp_survives_a_day_rebuild(hero, app_module):
    """Achievement awards are never rebuilt - they are one-off, and a rebuild
    that dropped them would un-pay an unlock."""
    items = hero.get("/api/checklist-items").get_json()["items"]
    hero.put("/api/days/2026-09-10", json={
        "responses": {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    user_id = conn.execute("SELECT id FROM users WHERE username = 'hero'").fetchone()["id"]

    before = conn.execute(
        "SELECT COALESCE(SUM(xp), 0) AS n FROM xp_transactions "
        "WHERE user_id = ? AND source = 'badge'", (user_id,)).fetchone()["n"]

    app_module.recompute_xp_day(conn, user_id, "2026-09-10")
    conn.commit()

    after = conn.execute(
        "SELECT COALESCE(SUM(xp), 0) AS n FROM xp_transactions "
        "WHERE user_id = ? AND source = 'badge'", (user_id,)).fetchone()["n"]
    conn.close()

    assert before > 0
    assert after == before


# --- categories and tiers ----------------------------------------------------

def test_every_category_has_at_least_one_achievement():
    """A category with nothing in it is an empty tab in the UI."""
    used = {entry["category"] for entry in achievements.CATALOGUE}
    assert used == set(achievements.CATEGORIES)


def test_the_summary_exposes_category_and_tier(hero):
    badge = _badge(hero, "first-workout")
    assert badge["category"] == "training"
    assert badge["tier"] in ("bronze", "silver", "gold")
    assert badge["xp_reward"] > 0


def test_tiers_of_one_idea_escalate():
    """Bronze/silver/gold on the same metric should be increasing thresholds,
    or the tiers are decoration."""
    by_metric = {}
    for entry in achievements.CATALOGUE:
        by_metric.setdefault(entry["metric"], []).append(entry)

    order = {achievements.BRONZE: 0, achievements.SILVER: 1, achievements.GOLD: 2}
    for metric, entries in by_metric.items():
        if len(entries) < 2:
            continue
        ranked = sorted(entries, key=lambda e: order[e["tier"]])
        thresholds = [e["threshold"] for e in ranked]
        assert thresholds == sorted(thresholds), (
            f'{metric}: tiers do not escalate - {[(e["tier"], e["threshold"]) for e in ranked]}'
        )
