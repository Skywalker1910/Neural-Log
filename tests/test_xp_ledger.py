"""Tests for the R7 XP ledger.

Two things are being protected here:

  1. Every workspace earns XP now. Before R7 only the checklist did, so a
     two-hour workout and a three-hour study session were worth nothing and the
     leaderboard ranked people on box-ticking.
  2. Farming is pointless. Caps and floors mean you cannot grind XP out of
     trivial repeated actions, and a fabricated number cannot out-earn a real one
     because the cap lands first.
"""
from datetime import date, timedelta

import pytest

import xp
import xp_config as cfg
from conftest import register

TODAY = date.today()


@pytest.fixture()
def player(client):
    register(client, username="player")
    return client


def _iso(offset=0):
    return (TODAY - timedelta(days=offset)).isoformat()


def _ledger(client, source=None):
    rows = client.get("/api/gamification/ledger").get_json()["entries"]
    return [r for r in rows if source is None or r["source"] == source]


def _total(client):
    return client.get("/api/gamification/summary").get_json()["total_xp"]


def _source_xp(client, source):
    """XP from one source. Preferred over the grand total wherever a test is
    about whether a particular kind of action earned, because unlocking an
    achievement also moves the total and would mask the answer."""
    return sum(e["xp"] for e in _ledger(client, source))


# --- the level curve ---------------------------------------------------------

def test_the_level_curve_is_unchanged_by_becoming_configurable():
    """R7 made the curve tunable. The defaults must reproduce the old hard-coded
    50 * (level - 1) ** 2 exactly, or everyone's level silently moves."""
    for level in range(1, 12):
        assert xp.xp_for_level(level) == 50 * ((level - 1) ** 2)


def test_level_one_starts_at_zero():
    assert xp.compute_level(0)[0] == 1


# --- every workspace earns ---------------------------------------------------

def test_a_workout_earns_xp_on_its_own(player):
    """The headline gap R7 closes: before this, logging a session earned nothing
    unless you also ticked a checkbox."""
    exercises = player.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])

    before = _total(player)
    workout = player.post("/api/workouts",
                          json={"date": _iso(), "name": "Push"}).get_json()
    player.put(f"/api/workouts/{workout['id']}", json={"sets": [
        {"exercise_id": bench["id"], "weight": 80, "reps": 8} for _ in range(4)
    ]})

    assert _total(player) > before
    assert _ledger(player, "training"), "no training entry in the ledger"


def test_a_study_session_earns_xp(player):
    before = _total(player)
    player.post("/api/learning/sessions", json={
        "date": _iso(), "duration_minutes": 60, "started_at": "09:00",
    })
    assert _total(player) > before
    assert _ledger(player, "learning")


def test_sleep_and_steps_earn_xp(player):
    before = _total(player)
    player.post("/api/sleep", json={"date": _iso(), "duration_minutes": 480})
    player.put(f"/api/lifestyle/{_iso()}", json={"steps": 12000, "water_ml": 3000})

    assert _total(player) > before
    reasons = [e["reason"] for e in _ledger(player, "lifestyle")]
    assert any("night" in r for r in reasons)
    assert any("step" in r for r in reasons)


def test_the_ledger_says_why(player):
    """A ledger is only worth having if it can answer "why did I get that"."""
    player.post("/api/learning/sessions", json={
        "date": _iso(), "duration_minutes": 60, "started_at": "09:00"})
    entry = _ledger(player, "learning")[0]

    assert entry["reason"]
    assert entry["xp"] > 0
    assert entry["source_key"].startswith("session:")


# --- thresholds --------------------------------------------------------------

def test_a_trivial_study_session_earns_nothing(player):
    """Three minutes is opening a book and closing it."""
    player.post("/api/learning/sessions", json={
        "date": _iso(), "duration_minutes": 3, "started_at": "09:00"})
    assert _source_xp(player, "learning") == 0

    # Nor should it unlock the achievement. The floor has to mean the same thing
    # to both systems, or one of them is lying about what counts as study.
    badges = player.get("/api/gamification/summary").get_json()["badges"]
    assert next(b for b in badges if b["code"] == "first-study")["earned"] is False


def test_an_empty_workout_earns_nothing(player):
    """Guards the "start a workout, never fill it in, collect XP" path."""
    before = _total(player)
    player.post("/api/workouts", json={"date": _iso(), "name": "Ghost"})
    assert _total(player) == before


def test_warmups_do_not_earn(player):
    exercises = player.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])

    workout = player.post("/api/workouts",
                          json={"date": _iso(), "name": "Warmup only"}).get_json()
    player.put(f"/api/workouts/{workout['id']}", json={"sets": [
        {"exercise_id": bench["id"], "weight": 40, "reps": 5, "is_warmup": True},
    ]})
    assert _source_xp(player, "training") == 0


def test_a_two_hour_night_is_not_a_night(player):
    player.post("/api/sleep", json={"date": _iso(), "duration_minutes": 60})
    assert _source_xp(player, "lifestyle") == 0

    # And it should not unlock "logged your first night" either - the achievement
    # metric respects the same floor, or the two would disagree about what counts
    # as a night.
    badges = player.get("/api/gamification/summary").get_json()["badges"]
    assert next(b for b in badges if b["code"] == "first-night")["earned"] is False


# --- caps --------------------------------------------------------------------

def test_a_source_cannot_exceed_its_daily_cap(player):
    """Twenty workouts in a day is not twenty workouts' worth of XP."""
    exercises = player.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])

    for i in range(12):
        workout = player.post("/api/workouts",
                              json={"date": _iso(), "name": f"S{i}"}).get_json()
        player.put(f"/api/workouts/{workout['id']}", json={"sets": [
            {"exercise_id": bench["id"], "weight": 80, "reps": 8} for _ in range(6)
        ]})

    training_xp = sum(e["xp"] for e in _ledger(player, "training"))
    assert training_xp <= cfg.DAILY_SOURCE_CAPS["training"], (
        f"training earned {training_xp}, above the "
        f"{cfg.DAILY_SOURCE_CAPS['training']} cap"
    )


def test_hitting_a_cap_is_recorded_not_hidden(player):
    """"You hit the training cap" is the difference between a rule and an
    unexplained number."""
    exercises = player.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])

    for i in range(12):
        workout = player.post("/api/workouts",
                              json={"date": _iso(), "name": f"S{i}"}).get_json()
        player.put(f"/api/workouts/{workout['id']}", json={"sets": [
            {"exercise_id": bench["id"], "weight": 80, "reps": 8} for _ in range(6)
        ]})

    assert any(e["capped_from"] for e in _ledger(player, "training")), (
        "a capped award should record what it would have been"
    )


def test_a_whole_day_is_capped_too(player):
    exercises = player.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])

    for i in range(8):
        workout = player.post("/api/workouts",
                              json={"date": _iso(), "name": f"S{i}"}).get_json()
        player.put(f"/api/workouts/{workout['id']}", json={"sets": [
            {"exercise_id": bench["id"], "weight": 80, "reps": 8} for _ in range(8)
        ]})
    for i in range(8):
        player.post("/api/learning/sessions", json={
            "date": _iso(), "duration_minutes": 120, "started_at": f"{6 + i:02d}:00"})
    player.post("/api/sleep", json={"date": _iso(), "duration_minutes": 480})
    player.put(f"/api/lifestyle/{_iso()}", json={"steps": 20000, "water_ml": 4000})

    day_xp = sum(e["xp"] for e in _ledger(player) if e["date"] == _iso())
    # The streak multiplier applies on top of the cap, so allow for it.
    ceiling = cfg.DAILY_TOTAL_CAP * (1 + cfg.STREAK_MULTIPLIER_CAP_PCT / 100)
    assert day_xp <= ceiling, f"one day produced {day_xp}, above the ceiling"


# --- evidence beats a claim --------------------------------------------------

def test_ticking_a_box_you_also_logged_does_not_pay_twice(player):
    """The rule that makes honest logging worth more than claiming."""
    items = player.get("/api/checklist-items").get_json()["items"]
    answers = {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}

    # A day with only the checklist.
    player.put(f"/api/days/{_iso(1)}", json={"responses": answers})
    claim_only = [e for e in _ledger(player, "checklist") if e["date"] == _iso(1)][0]

    # The same checklist, on a day that also has real logged training.
    exercises = player.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])
    workout = player.post("/api/workouts",
                          json={"date": _iso(), "name": "Push"}).get_json()
    player.put(f"/api/workouts/{workout['id']}", json={"sets": [
        {"exercise_id": bench["id"], "weight": 80, "reps": 8} for _ in range(4)
    ]})
    player.put(f"/api/days/{_iso()}", json={"responses": answers})

    evidenced = [e for e in _ledger(player, "checklist") if e["date"] == _iso()][0]

    assert evidenced["base_xp"] < claim_only["base_xp"], (
        "a claim alongside evidence should not pay the same as a claim alone"
    )
    assert evidenced["base_xp"] > 0, "it should be discounted, not removed"


def test_the_checklist_is_marked_as_a_claim(player):
    items = player.get("/api/checklist-items").get_json()["items"]
    player.put(f"/api/days/{_iso()}", json={
        "responses": {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}})

    assert _ledger(player, "checklist")[0]["evidence"] == "claimed"


def test_logged_work_is_marked_as_measured(player):
    player.post("/api/learning/sessions", json={
        "date": _iso(), "duration_minutes": 60, "started_at": "09:00"})
    assert _ledger(player, "learning")[0]["evidence"] == "measured"


# --- idempotency -------------------------------------------------------------

def test_editing_a_workout_replaces_its_xp_rather_than_stacking(player):
    exercises = player.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])
    workout = player.post("/api/workouts",
                          json={"date": _iso(), "name": "Push"}).get_json()

    sets = [{"exercise_id": bench["id"], "weight": 80, "reps": 8} for _ in range(4)]
    player.put(f"/api/workouts/{workout['id']}", json={"sets": sets})
    first = _total(player)

    player.put(f"/api/workouts/{workout['id']}", json={"sets": sets})
    assert _total(player) == first, "re-saving the same workout doubled its XP"


def test_deleting_a_workout_removes_its_xp(player):
    exercises = player.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])

    before = _total(player)
    workout = player.post("/api/workouts",
                          json={"date": _iso(), "name": "Push"}).get_json()
    player.put(f"/api/workouts/{workout['id']}", json={"sets": [
        {"exercise_id": bench["id"], "weight": 80, "reps": 8} for _ in range(4)
    ]})
    assert _total(player) > before

    player.delete(f"/api/workouts/{workout['id']}")
    # Source-specific: the achievement the workout unlocked keeps its XP, because
    # an unlock is permanent. Only the training award is undone.
    assert _source_xp(player, "training") == 0


def test_rebuilding_a_day_twice_does_not_relabel_xp(player, app_module):
    """Regression: a workout's XP reappearing as checklist XP.

    daily_xp.base_xp means the CHECKLIST's base, and recompute_day reads it back
    when no checklist figure is passed. Writing the day's full base there instead
    created a loop - a workout's value was summed into the column, read back as a
    checklist award on the next rebuild, and survived deleting the workout.
    """
    import sqlite3
    player.post("/api/learning/sessions", json={
        "date": _iso(), "duration_minutes": 90, "started_at": "09:00"})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    user_id = conn.execute("SELECT id FROM users WHERE username = 'player'").fetchone()["id"]

    for _ in range(3):
        app_module.recompute_xp_day(conn, user_id, _iso())
        conn.commit()

    sources = [r["source"] for r in conn.execute(
        "SELECT source FROM xp_transactions WHERE user_id = ? AND date = ? "
        "AND source != 'badge'",
        (user_id, _iso()))]
    conn.close()

    assert sources == ["learning"], (
        f"repeated rebuilds invented sources: {sources}"
    )


def test_a_past_day_keeps_the_streak_it_was_earned_with(player, app_module):
    """Rebuilding history must not stamp today's streak onto every past day.

    A day earned during a ten-day run should keep that multiplier, and a day
    earned with no streak should not gain one retroactively. The bug this guards
    against showed up as a user losing XP during a historical rebuild, because
    their streak had since lapsed to zero.
    """
    import sqlite3
    items = player.get("/api/checklist-items").get_json()["items"]
    answers = {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}

    # Four consecutive days, so the last of them was earned on a 4-day streak.
    for offset in range(3, -1, -1):
        player.put(f"/api/days/{_iso(offset)}", json={"responses": answers})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    user_id = conn.execute("SELECT id FROM users WHERE username = 'player'").fetchone()["id"]

    # Filtered to the checklist row on purpose: achievement awards also land on
    # the day they unlock, and they carry no multiplier, so an unfiltered
    # fetchone() can pick up a badge row and read 0%.
    def multiplier(day):
        return conn.execute(
            "SELECT multiplier_pct FROM xp_transactions "
            "WHERE user_id = ? AND date = ? AND source = 'checklist'",
            (user_id, day)).fetchone()["multiplier_pct"]

    first_day = multiplier(_iso(3))
    last_day = multiplier(_iso(0))
    conn.close()

    assert last_day > first_day, (
        f"the fourth consecutive day ({last_day}%) should carry a bigger streak "
        f"multiplier than the first ({first_day}%)"
    )


def test_the_streak_can_be_asked_for_as_of_a_past_date(player, app_module):
    import sqlite3
    items = player.get("/api/checklist-items").get_json()["items"]
    answers = {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}
    for offset in range(3, -1, -1):
        player.put(f"/api/days/{_iso(offset)}", json={"responses": answers})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    user_id = conn.execute("SELECT id FROM users WHERE username = 'player'").fetchone()["id"]

    assert app_module.calculate_current_streak(conn, user_id, as_of=_iso(3)) == 1
    assert app_module.calculate_current_streak(conn, user_id, as_of=_iso(0)) == 4
    conn.close()


# --- the backfill ------------------------------------------------------------

def test_historical_xp_is_preserved(player, app_module):
    """R7 made the ledger authoritative. Without a backfill, every day earned
    before it would silently stop counting and everyone's level would drop."""
    import sqlite3
    items = player.get("/api/checklist-items").get_json()["items"]
    player.put(f"/api/days/{_iso(2)}", json={
        "responses": {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    user_id = conn.execute("SELECT id FROM users WHERE username = 'player'").fetchone()["id"]

    # Simulate a pre-R7 database: daily_xp populated, ledger empty.
    conn.execute('DELETE FROM xp_transactions WHERE user_id = ?', (user_id,))
    conn.commit()
    assert xp.total_xp(conn, user_id) == 0

    written = xp.backfill_from_daily_xp(conn)
    assert written >= 1

    rollup = conn.execute(
        'SELECT COALESCE(SUM(total_xp), 0) AS n FROM daily_xp WHERE user_id = ?',
        (user_id,)).fetchone()["n"]
    assert xp.total_xp(conn, user_id) == rollup
    conn.close()


def test_the_backfill_is_idempotent(player, app_module):
    import sqlite3
    items = player.get("/api/checklist-items").get_json()["items"]
    player.put(f"/api/days/{_iso(2)}", json={
        "responses": {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    user_id = conn.execute("SELECT id FROM users WHERE username = 'player'").fetchone()["id"]

    before = xp.total_xp(conn, user_id)
    xp.backfill_from_daily_xp(conn)
    xp.backfill_from_daily_xp(conn)
    assert xp.total_xp(conn, user_id) == before
    conn.close()


# --- the rollup stays in step -------------------------------------------------

def test_the_leaderboard_rollup_matches_the_ledger(player, app_module):
    """daily_xp is kept for the leaderboard. If the two drift, the leaderboard
    starts lying."""
    import sqlite3
    player.post("/api/learning/sessions", json={
        "date": _iso(), "duration_minutes": 90, "started_at": "09:00"})
    player.post("/api/sleep", json={"date": _iso(), "duration_minutes": 480})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    user_id = conn.execute("SELECT id FROM users WHERE username = 'player'").fetchone()["id"]

    ledger_total = conn.execute(
        'SELECT COALESCE(SUM(xp), 0) AS n FROM xp_transactions '
        'WHERE user_id = ? AND date = ?', (user_id, _iso())).fetchone()["n"]
    rollup = conn.execute(
        'SELECT COALESCE(total_xp, 0) AS n FROM daily_xp WHERE user_id = ? AND date = ?',
        (user_id, _iso())).fetchone()["n"]
    conn.close()

    assert ledger_total == rollup
