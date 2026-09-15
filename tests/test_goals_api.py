"""Tests for Goals, milestones, tasks and the habit endpoints.

The theme: a goal is an intention, not evidence. These check that the app is
honest about where a progress number came from, and that nothing here quietly
moves an attribute score.
"""
from datetime import date, timedelta

import pytest

from conftest import register

TODAY = date.today()


@pytest.fixture()
def planner(client):
    register(client, username="planner")
    return client


def _iso(offset=0):
    return (TODAY + timedelta(days=offset)).isoformat()


def _goal(client, **overrides):
    body = {"title": "Run a half marathon", "category": "fitness"}
    body.update(overrides)
    return client.post("/api/goals", json=body).get_json()


def _first_habit(client):
    return client.get("/api/habits").get_json()["habits"][0]


# --- goals ------------------------------------------------------------------

def test_a_goal_round_trips(planner):
    goal = _goal(planner, description="Under two hours", target_date=_iso(90))

    assert goal["title"] == "Run a half marathon"
    assert goal["status"] == "active"
    assert goal["days_remaining"] == 90

    listed = planner.get("/api/goals").get_json()["goals"]
    assert len(listed) == 1


def test_an_unmeasurable_goal_reports_no_progress_rather_than_zero(planner):
    """Plenty of real goals have no number. Inventing 0% would read as failure
    when the honest answer is that there is nothing to measure."""
    goal = _goal(planner, title="Get better at saying no")
    assert goal["progress"]["percent"] is None
    assert goal["progress"]["source"] == "none"


def test_milestones_drive_progress_when_there_is_nothing_better(planner):
    goal = _goal(planner, milestones=["5k", "10k", "Half"])
    assert goal["progress"]["source"] == "milestones"
    assert goal["progress"]["percent"] == 0

    first = goal["milestones"][0]
    planner.put(f"/api/milestones/{first['id']}", json={"completed": True})

    updated = planner.get(f"/api/goals/{goal['id']}").get_json()
    assert updated["progress"]["percent"] == 33


def test_a_metric_goal_reports_its_own_number(planner):
    goal = _goal(planner, title="Read 12 books", metric_name="books",
                 target_value=12, current_value=3)
    assert goal["progress"]["source"] == "metric"
    assert goal["progress"]["percent"] == 25


def test_linked_habits_outrank_a_typed_number(planner):
    """The whole point of the linking. A goal backed by habits derives its
    progress from what you actually did, not from what you claimed."""
    habit = _first_habit(planner)
    goal = _goal(planner, metric_name="sessions", target_value=10,
                 current_value=10, habit_ids=[habit["id"]])

    assert goal["progress"]["source"] == "habits", (
        "a typed-in 10/10 should not outrank real completions"
    )
    assert goal["progress"]["percent"] == 0, "nothing has actually been done yet"
    assert goal["progress"]["linked_habits"][0]["habit_id"] == habit["id"]


def test_doing_the_linked_habit_moves_the_goal(planner):
    items = planner.get("/api/checklist-items").get_json()["items"]
    tracked = next(item for item in items if item["type"] == "yes-no")

    habits = planner.get("/api/habits").get_json()["habits"]
    habit = next(h for h in habits if h["name"] == tracked["name"])

    goal = _goal(planner, habit_ids=[habit["id"]], started_on=TODAY.isoformat())
    assert goal["progress"]["percent"] == 0

    planner.put(f"/api/days/{TODAY.isoformat()}", json={"responses": {tracked["name"]: "Yes"}})

    updated = planner.get(f"/api/goals/{goal['id']}").get_json()
    assert updated["progress"]["percent"] == 100
    assert updated["progress"]["linked_habits"][0]["done"] == 1


def test_achieving_a_goal_stamps_the_date_once(planner):
    goal = _goal(planner)
    planner.put(f"/api/goals/{goal['id']}", json={"status": "achieved"})
    first = planner.get(f"/api/goals/{goal['id']}").get_json()["achieved_on"]
    assert first == TODAY.isoformat()

    planner.put(f"/api/goals/{goal['id']}", json={"status": "active"})
    planner.put(f"/api/goals/{goal['id']}", json={"status": "achieved"})
    again = planner.get(f"/api/goals/{goal['id']}").get_json()["achieved_on"]
    assert again == first, "re-achieving should not rewrite when you first did it"


def test_abandoning_a_goal_keeps_it(planner):
    """Goals you gave up on are the most informative in hindsight. Quietly
    removing them would leave a history in which you only ever succeeded."""
    goal = _goal(planner)
    planner.put(f"/api/goals/{goal['id']}", json={"status": "abandoned"})

    listed = planner.get("/api/goals").get_json()["goals"]
    assert [g["status"] for g in listed] == ["abandoned"]


def test_deleting_a_goal_archives_it(planner):
    goal = _goal(planner, milestones=["One"])
    assert planner.delete(f"/api/goals/{goal['id']}").status_code == 200
    assert planner.get("/api/goals").get_json()["goals"] == []
    assert planner.get(f"/api/goals/{goal['id']}").status_code == 200


def test_goals_require_a_title(planner):
    assert planner.post("/api/goals", json={}).status_code == 400
    assert planner.post("/api/goals", json={"title": "   "}).status_code == 400


def test_goals_are_scoped_to_their_owner(planner, client):
    goal = _goal(planner)
    planner.get("/logout")

    register(client, username="someone-else")
    assert client.get("/api/goals").get_json()["goals"] == []
    assert client.get(f"/api/goals/{goal['id']}").status_code == 404
    assert client.put(f"/api/goals/{goal['id']}", json={"title": "mine"}).status_code == 404


def test_you_cannot_link_someone_elses_habit(planner, client):
    planner_habit = _first_habit(planner)
    planner.get("/logout")

    register(client, username="intruder")
    goal = client.post("/api/goals", json={
        "title": "Borrowed", "habit_ids": [planner_habit["id"]],
    }).get_json()

    assert goal["habit_ids"] == []
    assert goal["progress"]["source"] != "habits"


# --- tasks --------------------------------------------------------------------

def test_a_task_can_stand_alone_or_serve_a_goal(planner):
    goal = _goal(planner)
    planner.post("/api/tasks", json={"title": "Book the race"})
    planner.post("/api/tasks", json={"title": "Buy shoes", "goal_id": goal["id"]})

    tasks = planner.get("/api/tasks").get_json()["tasks"]
    assert len(tasks) == 2
    linked = next(t for t in tasks if t["title"] == "Buy shoes")
    assert linked["goal_title"] == goal["title"]

    detail = planner.get(f"/api/goals/{goal['id']}").get_json()
    assert [t["title"] for t in detail["tasks"]] == ["Buy shoes"]


def test_completing_a_task_records_when(planner):
    task = planner.post("/api/tasks", json={"title": "Book the race"}).get_json()
    planner.put(f"/api/tasks/{task['id']}", json={"completed": True})

    stored = next(t for t in planner.get("/api/tasks").get_json()["tasks"]
                  if t["id"] == task["id"])
    assert stored["completed_on"] == TODAY.isoformat()

    planner.put(f"/api/tasks/{task['id']}", json={"completed": False})
    stored = next(t for t in planner.get("/api/tasks").get_json()["tasks"]
                  if t["id"] == task["id"])
    assert stored["completed_on"] is None


def test_open_tasks_sort_before_completed_ones(planner):
    first = planner.post("/api/tasks", json={"title": "Done thing"}).get_json()
    planner.post("/api/tasks", json={"title": "Open thing"})
    planner.put(f"/api/tasks/{first['id']}", json={"completed": True})

    titles = [t["title"] for t in planner.get("/api/tasks").get_json()["tasks"]]
    assert titles.index("Open thing") < titles.index("Done thing")


def test_you_cannot_attach_a_task_to_someone_elses_goal(planner, client):
    goal = _goal(planner)
    planner.get("/logout")

    register(client, username="intruder")
    response = client.post("/api/tasks", json={"title": "Sneak", "goal_id": goal["id"]})
    assert response.status_code == 404


# --- the summary --------------------------------------------------------------

def test_summary_counts_overdue_and_due_soon(planner):
    _goal(planner, title="Late", target_date=_iso(-3))
    _goal(planner, title="Soon", target_date=_iso(3))
    _goal(planner, title="Later", target_date=_iso(60))

    totals = planner.get("/api/goals/summary").get_json()["totals"]
    assert totals["active"] == 3
    assert totals["overdue"] == 1
    assert totals["due_soon"] == 1


def test_summary_offers_the_habits_available_for_linking(planner):
    summary = planner.get("/api/goals/summary").get_json()
    assert summary["habits"], "a new account should have habits to link"
    assert all("name" in habit for habit in summary["habits"])


def test_summary_for_a_new_user_is_empty_not_broken(planner):
    summary = planner.get("/api/goals/summary").get_json()
    assert summary["goals"] == []
    assert summary["totals"]["active"] == 0


# --- nothing here is scored ----------------------------------------------------

def test_goals_never_move_an_attribute(planner):
    """The reason no recompute function is injected into goals_api."""
    before = planner.get("/api/attributes").get_json()["attributes"]

    goal = _goal(planner, milestones=["One", "Two"], metric_name="x",
                 target_value=10, current_value=10)
    for milestone in goal["milestones"]:
        planner.put(f"/api/milestones/{milestone['id']}", json={"completed": True})
    planner.put(f"/api/goals/{goal['id']}", json={"status": "achieved"})
    task = planner.post("/api/tasks", json={"title": "Anything"}).get_json()
    planner.put(f"/api/tasks/{task['id']}", json={"completed": True})

    after = planner.get("/api/attributes").get_json()["attributes"]
    assert after == before, "declaring a goal achieved must not score anything"


# --- habit endpoints ------------------------------------------------------------

def test_habits_endpoint_reports_stats(planner):
    habits = planner.get("/api/habits").get_json()["habits"]
    assert habits
    entry = habits[0]
    assert {"id", "name", "streak", "done", "schedule_type"} <= set(entry)
    assert entry["schedule_type"] == "daily", "migrated path items are daily"


def test_habits_are_scoped_to_the_path_you_are_following(planner):
    """The four stock paths share most of their items. Listing all of them shows
    "What time did you wake up?" four times, which reads as a bug."""
    scoped = planner.get("/api/habits").get_json()
    everything = planner.get("/api/habits?all=1").get_json()

    assert scoped["scope"] == "selected"
    assert everything["scope"] == "all"
    assert len(everything["habits"]) > len(scoped["habits"])

    names = [habit["name"] for habit in scoped["habits"]]
    assert len(names) == len(set(names)), f"duplicate habits in the scoped list: {names}"


def test_the_goal_link_picker_offers_no_duplicates(planner):
    habits = planner.get("/api/goals/summary").get_json()["habits"]
    names = [habit["name"] for habit in habits]
    assert names
    assert len(names) == len(set(names))


def test_a_habit_schedule_can_be_changed(planner):
    habit = _first_habit(planner)
    updated = planner.put(f"/api/habits/{habit['id']}", json={
        "schedule_type": "days", "schedule_days": [0, 2, 4],
    }).get_json()

    assert updated["schedule_type"] == "days"
    assert updated["schedule_days"] == "[0, 2, 4]"


def test_an_invalid_schedule_is_rejected_without_breaking_the_habit(planner):
    habit = _first_habit(planner)
    updated = planner.put(f"/api/habits/{habit['id']}", json={
        "schedule_type": "lunar", "schedule_days": [9, "x", 2],
    }).get_json()

    assert updated["schedule_type"] == "daily", "an unknown type should not stick"
    assert updated["schedule_days"] == "[2]", "junk weekdays should be dropped"


def test_switching_away_from_times_per_week_clears_the_target(planner):
    habit = _first_habit(planner)
    planner.put(f"/api/habits/{habit['id']}",
                json={"schedule_type": "times-per-week", "target_per_week": 3})
    updated = planner.put(f"/api/habits/{habit['id']}",
                          json={"schedule_type": "daily"}).get_json()
    assert updated["target_per_week"] is None


def test_due_reflects_the_schedule(planner):
    habit = _first_habit(planner)
    # Only Mondays.
    planner.put(f"/api/habits/{habit['id']}",
                json={"schedule_type": "days", "schedule_days": [0]})

    monday = "2026-09-14"
    tuesday = "2026-09-15"

    due_monday = planner.get(f"/api/habits/due?date={monday}").get_json()["habits"]
    due_tuesday = planner.get(f"/api/habits/due?date={tuesday}").get_json()["habits"]

    assert habit["id"] in {h["id"] for h in due_monday}
    assert habit["id"] not in {h["id"] for h in due_tuesday}


def test_due_rejects_a_malformed_date(planner):
    assert planner.get("/api/habits/due?date=not-a-date").status_code == 400


def test_habit_endpoints_require_login(client):
    for url in ("/api/habits", "/api/habits/due", "/api/goals", "/api/tasks",
                "/api/goals/summary"):
        assert client.get(url).status_code == 302
