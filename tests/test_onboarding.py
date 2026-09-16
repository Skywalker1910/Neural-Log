"""Tests for the R9 onboarding flow.

Two things are being pinned here. The obvious one is that answers save and
resume. The important one is the boundary: onboarding sets *targets*, and targets
are denominators the scoring engine measures against - but it must never write an
attribute score, because a questionnaire answer is a claim and the engine already
has rules about claims.
"""
import sqlite3

import pytest

from conftest import register


@pytest.fixture()
def hero(client):
    register(client, username="hero")
    return client


def _state(client):
    resp = client.get("/api/onboarding")
    assert resp.status_code == 200
    return resp.get_json()


def _save(client, answers=None, **kwargs):
    payload = {"answers": answers or {}}
    payload.update(kwargs)
    return client.put("/api/onboarding", json=payload)


# --- the shape ---------------------------------------------------------------

def test_requires_login(client):
    assert client.get("/api/onboarding").status_code == 302


def test_a_new_account_is_prompted(hero):
    state = _state(hero)
    assert state["completed"] is False
    assert state["dismissed"] is False
    assert state["should_prompt"] is True
    assert state["step"] == 0


def test_the_steps_are_declared_by_the_server(hero):
    """So the API and the UI cannot disagree about how many there are. The
    client renders these; it does not define them."""
    steps = _state(hero)["steps"]
    assert len(steps) == 7
    assert [step["key"] for step in steps] == [
        "profile", "activity", "body_goal", "sleep", "learning", "survey", "baselines"]
    assert all(step["title"] and step["blurb"] for step in steps)


def test_state_works_for_an_account_with_no_profile_row(hero):
    """user_profile is created lazily, so the flow's first read is very often
    against a row that does not exist. It must answer, not 500."""
    state = _state(hero)
    assert state["answers"]["height_cm"] is None
    assert state["baselines"]["bmi"] is None
    assert set(state["baselines"]["missing"]) == {"height", "weight", "birth year"}


# --- saving ------------------------------------------------------------------

def test_a_step_saves_only_its_own_fields(hero):
    _save(hero, {"birth_year": 1990, "sex": "male", "height_cm": 180}, step=1)

    state = _state(hero)
    assert state["answers"]["birth_year"] == 1990
    assert state["answers"]["height_cm"] == 180
    assert state["step"] == 1

    # A later step's field is untouched. target_bedtime rather than
    # weekly_study_minutes, because that one carries a schema DEFAULT of 300 from
    # 005 - creating the row populates it, which is existing behaviour and not
    # this step writing it.
    assert state["answers"]["target_bedtime"] is None


def test_progress_survives_leaving_and_coming_back(hero):
    _save(hero, {"birth_year": 1990}, step=1)
    _save(hero, {"activity_level": "active"}, step=2)

    state = _state(hero)
    assert state["step"] == 2
    assert state["answers"]["birth_year"] == 1990
    assert state["answers"]["activity_level"] == "active"


def test_weight_is_stored_as_a_measurement_not_a_profile_field(hero, app_module):
    """Weight changes weekly; the profile is for things that do not. It also has
    to land in the same table the Training workspace reads."""
    _save(hero, {"weight_kg": 78.5})

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT metric, value, unit FROM body_measurements WHERE metric = 'weight'"
    ).fetchone()
    conn.close()

    assert (row["value"], row["unit"]) == (78.5, "kg")
    assert _state(hero)["answers"]["weight_kg"] == 78.5


def test_correcting_a_typo_does_not_create_a_second_weigh_in(hero, app_module):
    """Two saves in one session are one correction, not a two-day streak."""
    _save(hero, {"weight_kg": 87.5})
    _save(hero, {"weight_kg": 78.5})

    conn = sqlite3.connect(app_module.DATABASE)
    count = conn.execute(
        "SELECT COUNT(*) FROM body_measurements WHERE metric = 'weight'").fetchone()[0]
    conn.close()
    assert count == 1
    assert _state(hero)["answers"]["weight_kg"] == 78.5


def test_the_survey_step_shows_rather_than_asks(hero):
    """It used to be "Choose your Path", and choosing one quietly chose which of
    your attributes could be measured at all. Everyone answers the same survey
    now, so the step has nothing to write - it shows what you will be asked."""
    state = _state(hero)
    survey = state["survey"]
    step = next(s for s in state["steps"] if s["key"] == "survey")

    assert step["fields"] == [], "the step writes nothing"
    assert len(survey) == 10
    assert all(question["is_core"] for question in survey)


def test_finishing_never_writes_a_path(hero, app_module):
    """users.selected_path is vestigial. Nothing in the flow should touch it."""
    _save(hero, {"birth_year": 1990}, complete=True)

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT selected_path FROM users WHERE username = 'hero'").fetchone()
    conn.close()
    assert row["selected_path"] is None


# --- validation --------------------------------------------------------------

def test_a_closed_set_rejects_an_unrecognised_value(hero):
    """resolve_targets silently falls back to 'moderate' for an unknown activity
    level, so a typo would quietly become a 1.55 multiplier on someone's calorie
    target with nothing on screen to say so."""
    resp = _save(hero, {"activity_level": "extremely-sporty"})
    assert resp.status_code == 400
    assert "activity_level" in resp.get_json()["fields"]


def test_an_impossible_number_is_rejected(hero):
    resp = _save(hero, {"height_cm": 8000})
    assert resp.status_code == 400
    assert "height_cm" in resp.get_json()["fields"]


def test_a_rejected_step_saves_nothing_from_that_step(hero):
    """All-or-nothing per step, so a half-written profile cannot result from one
    bad field."""
    resp = _save(hero, {"birth_year": 1990, "height_cm": 8000})
    assert resp.status_code == 400
    assert _state(hero)["answers"]["birth_year"] is None


def test_a_malformed_time_is_rejected(hero):
    assert _save(hero, {"target_bedtime": "half past ten"}).status_code == 400
    assert _save(hero, {"target_bedtime": "25:00"}).status_code == 400
    assert _save(hero, {"target_bedtime": "23:30"}).status_code == 200


def test_clearing_a_field_is_allowed(hero):
    _save(hero, {"height_cm": 180})
    _save(hero, {"height_cm": None})
    assert _state(hero)["answers"]["height_cm"] is None


# --- baselines ---------------------------------------------------------------

def test_baselines_compute_once_the_inputs_exist(hero):
    _save(hero, {"birth_year": 1990, "sex": "male", "height_cm": 180})
    _save(hero, {"weight_kg": 80})

    baselines = _state(hero)["baselines"]
    assert baselines["bmi"] == pytest.approx(24.7, abs=0.1)
    assert baselines["bmr"] > 1000
    assert baselines["tdee"] > baselines["bmr"]
    assert baselines["missing"] == []


def test_baselines_say_what_is_missing_rather_than_guessing(hero):
    """Three dashes and no reason is worse than no baselines at all."""
    _save(hero, {"birth_year": 1990, "sex": "male"})

    baselines = _state(hero)["baselines"]
    assert baselines["bmi"] is None
    assert baselines["tdee"] is None
    assert set(baselines["missing"]) == {"height", "weight"}


def test_bmi_carries_no_category(hero):
    """BMI cannot see muscle, and the standard bands would tell a lifter at 15%
    body fat they are overweight. The number is observable; a verdict is not."""
    _save(hero, {"birth_year": 1990, "sex": "male", "height_cm": 180})
    _save(hero, {"weight_kg": 80})

    baselines = _state(hero)["baselines"]
    assert "category" not in baselines
    assert "band" not in baselines


# --- the boundary that matters -----------------------------------------------

def test_answers_change_targets(hero):
    """Targets are what the engine measures against, so this is the mechanism by
    which the questionnaire legitimately affects scoring."""
    before = _state(hero)["targets"]["calories"]
    assert before is None  # nothing known yet

    _save(hero, {"birth_year": 1990, "sex": "male", "height_cm": 180})
    _save(hero, {"weight_kg": 80, "goal": "cut"})

    after = _state(hero)["targets"]
    assert after["calories"] > 0
    assert after["sources"]["calories"] == "estimated"


def test_onboarding_never_writes_an_attribute_score(hero, app_module):
    """The line this phase must not cross. A questionnaire answer is a claim, and
    the engine caps claims at half the range and reports 'calibrating' until
    three days of real history exist. Seeding Strength at signup would walk past
    both rules and hand someone a character sheet they had not earned."""
    _save(hero, {"birth_year": 1990, "sex": "male", "height_cm": 180})
    _save(hero, {"weight_kg": 80, "goal": "cut"})
    _save(hero, {"activity_level": "very-active"})
    _save(hero, {"weekly_study_minutes": 600})
    _save(hero, complete=True)

    attributes = hero.get("/api/attributes").get_json()["attributes"]
    scored = [a for a in attributes if a.get("score") is not None]
    assert scored == [], f"onboarding invented scores for {[a['attribute'] for a in scored]}"


def test_a_completed_profile_does_not_fake_history(hero):
    """Finishing the questionnaire is not a logged day."""
    _save(hero, {"birth_year": 1990, "sex": "male", "height_cm": 180}, complete=True)
    home = hero.get("/api/home").get_json()
    assert home["days_logged"] == 0
    assert home["daily_score"] is None


# --- finishing and dismissing ------------------------------------------------

def test_completing_stops_the_prompt(hero):
    _save(hero, {"birth_year": 1990}, complete=True)

    state = _state(hero)
    assert state["completed"] is True
    assert state["completed_at"]
    assert state["should_prompt"] is False


def test_dismissing_stops_the_prompt_without_completing(hero):
    hero.post("/api/onboarding/dismiss")

    state = _state(hero)
    assert state["dismissed"] is True
    assert state["completed"] is False
    assert state["should_prompt"] is False


def test_a_dismissal_is_permanent_across_requests(hero):
    """A prompt that comes back after being declined is not a prompt."""
    hero.post("/api/onboarding/dismiss")
    _state(hero)
    assert _state(hero)["should_prompt"] is False


def test_reopening_after_a_dismissal_works(hero):
    """Profile's "finish setup" has to work for someone who changed their mind."""
    hero.post("/api/onboarding/dismiss")
    hero.post("/api/onboarding/reopen")
    assert _state(hero)["should_prompt"] is True


def test_dismissing_works_without_a_profile_row(hero, app_module):
    """The most common case - somebody declines before answering anything, so
    there is no row to update."""
    assert hero.post("/api/onboarding/dismiss").status_code == 200

    conn = sqlite3.connect(app_module.DATABASE)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT activity_level, goal FROM user_profile").fetchone()
    conn.close()
    # NOT NULL columns with schema defaults still have to be supplied on create.
    assert row["activity_level"] == "moderate"
    assert row["goal"] == "maintain"


# --- existing accounts -------------------------------------------------------

def test_an_existing_partial_profile_is_prefilled_rather_than_reset(hero):
    """Both live accounts are in this state: a profile half-built by the
    Nutrition page. That is the case onboarding exists to finish, so it prompts
    them and shows what they already have."""
    hero.put("/api/profile", json={"height_cm": 178, "sex": "male", "goal": "cut"})

    state = _state(hero)
    assert state["should_prompt"] is True
    assert state["answers"]["height_cm"] == 178
    assert state["answers"]["goal"] == "cut"


def test_finishing_does_not_discard_targets_set_by_hand(hero):
    """Someone who set a calorie target on the Nutrition page has chosen it. The
    questionnaire estimates; it does not overrule."""
    hero.put("/api/profile", json={"calorie_target": 2200})
    _save(hero, {"birth_year": 1990, "sex": "male", "height_cm": 180})
    _save(hero, {"weight_kg": 80, "goal": "cut"}, complete=True)

    targets = _state(hero)["targets"]
    assert targets["calories"] == 2200
    assert targets["sources"]["calories"] == "set"
