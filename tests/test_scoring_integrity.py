"""Tests for the R2 prerequisite fixes: server-side completion, and repairing
stock Paths whose items predate the shipped weights/icons.

Both guard against the same class of bug - scoring that trusts something it
shouldn't. See docs/CHANGELOG.md under "R2 prerequisites".
"""
from datetime import datetime

from conftest import core_survey, register
from test_gamification import _answer_all, _submit_checklist


def _batman(app_module):
    """The shared survey, wrapped as a path so the helpers below read the same.

    Named for the Path it replaced; every caller just wants a realistic set of
    checklist items.
    """
    return {"id": "daily-survey", "name": "Daily survey",
            "checklist_items": core_survey(app_module)}


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


# The stock-path repair tests lived here. repair_default_path_items() existed to
# restore shipped weights and icons onto the four hero Paths after a user had
# edited them, and both the function and the Paths are gone - the shared survey
# is a single set of rows that an admin edits deliberately, with nothing to
# drift back from.
