"""Tests for the R2 prerequisite fixes: server-side completion, and repairing
stock Paths whose items predate the shipped weights/icons.

Both guard against the same class of bug - scoring that trusts something it
shouldn't. See docs/CHANGELOG.md under "R2 prerequisites".
"""
from datetime import datetime

from conftest import register
from test_gamification import _answer_all, _submit_checklist


def _batman(app_module):
    return [p for p in app_module.build_default_paths() if p["id"] == "batman-path"][0]


# --- server-side completion -------------------------------------------------

def test_completion_counts_completed_not_merely_answered(app_module):
    """A day answered entirely "No" is 0% complete, even though every question
    was answered. The client reports answered/total and would say 100."""
    batman = _batman(app_module)
    all_no = _answer_all(batman, all_yes=False)
    # 'time' items have no "No" option, so the wake-up item still counts as done.
    assert app_module.compute_completion_percent(batman["checklist_items"], all_no) < 20


def test_completion_is_weight_based_not_item_count(app_module):
    """Completing one weight-3 item beats completing one weight-1 item."""
    batman = _batman(app_module)
    items = batman["checklist_items"]
    heavy = next(i for i in items if i.get("weight") == 3)
    light = next(i for i in items if i.get("weight") == 1 and i["type"] == "yes-no")

    heavy_only = app_module.compute_completion_percent(items, {heavy["name"]: "Yes"})
    light_only = app_module.compute_completion_percent(items, {light["name"]: "Yes"})
    assert heavy_only > light_only


def test_full_completion_is_100(app_module):
    batman = _batman(app_module)
    assert app_module.compute_completion_percent(
        batman["checklist_items"], _answer_all(batman, all_yes=True)
    ) == 100


def test_empty_path_does_not_divide_by_zero(app_module):
    assert app_module.compute_completion_percent([], {}) == 0


def test_perfect_day_badge_ignores_inflated_client_completion(client, app_module):
    """The regression this whole fix exists for: the client sends
    completion_percent=100 for a day answered "No" throughout, and the
    perfect-day badge must not fire on it."""
    register(client)
    batman = _batman(app_module)
    today = datetime.now().strftime("%Y-%m-%d")

    resp = _submit_checklist(
        client, today, batman, all_yes=False, completion_percent=100
    )
    earned = {b["code"] for b in resp.get_json()["newly_earned_badges"]}
    assert "perfect-day" not in earned
    assert "first-log" in earned  # the honest one still fires


def test_perfect_day_badge_still_awarded_when_genuinely_perfect(client, app_module):
    register(client)
    batman = _batman(app_module)
    today = datetime.now().strftime("%Y-%m-%d")

    resp = _submit_checklist(client, today, batman, all_yes=True)
    earned = {b["code"] for b in resp.get_json()["newly_earned_badges"]}
    assert "perfect-day" in earned


# --- stock-path repair ------------------------------------------------------

def test_repair_restores_shipped_weights_and_icons(app_module):
    """Simulates an account created before weights/icons existed: every item
    flattened to weight 1 / icon 'default'."""
    paths = app_module.build_default_paths()
    for path in paths:
        for item in path["checklist_items"]:
            item["weight"] = 1
            item["icon"] = "default"

    assert app_module.repair_default_path_items(paths) is True

    batman = [p for p in paths if p["id"] == "batman-path"][0]
    by_name = {i["name"]: i for i in batman["checklist_items"]}
    assert by_name["Did you complete strength training today?"]["weight"] == 3
    assert by_name["Did you complete strength training today?"]["icon"] == "workout"
    assert by_name["What time did you wake up?"]["icon"] == "sun"


def test_repair_leaves_user_customisation_alone(app_module):
    """A stock path the user has deliberately edited must not be reverted."""
    paths = app_module.build_default_paths()
    batman = [p for p in paths if p["id"] == "batman-path"][0]
    target = next(i for i in batman["checklist_items"] if i["weight"] == 3)
    target["weight"] = 5
    target["icon"] = "chess"

    app_module.repair_default_path_items(paths)

    assert target["weight"] == 5
    assert target["icon"] == "chess"


def test_repair_ignores_custom_paths(app_module):
    custom = [{
        "id": "custom-abc",
        "name": "My Path",
        "is_default": False,
        "checklist_items": [
            {"name": "Did you complete strength training today?", "type": "yes-no",
             "weight": 1, "icon": "default"}
        ],
    }]
    assert app_module.repair_default_path_items(custom) is False
    assert custom[0]["checklist_items"][0]["weight"] == 1


def test_repair_is_idempotent(app_module):
    paths = app_module.build_default_paths()
    for path in paths:
        for item in path["checklist_items"]:
            item["weight"] = 1
            item["icon"] = "default"

    assert app_module.repair_default_path_items(paths) is True
    assert app_module.repair_default_path_items(paths) is False
