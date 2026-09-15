"""Tests for the R8 analytics endpoint.

This is the one workspace that answers "am I getting better", and that question
is easy to answer dishonestly. Most of what follows pins the three rules that
stop it: an unlogged day is unobserved rather than zero, a comparison needs a
previous window with something in it, and sums are not averages.
"""
import pytest

from conftest import register

# A fixed window so the tests never depend on what today happens to be. END is
# the last day of the window; the 30-day period therefore opens on 2026-06-02.
END = "2026-07-01"
IN_WINDOW = "2026-06-20"
IN_PREVIOUS = "2026-05-20"


@pytest.fixture()
def hero(client):
    register(client, username="hero")
    return client


def _analytics(client, period="30", end=END):
    resp = client.get(f"/api/analytics?period={period}&end={end}")
    assert resp.status_code == 200
    return resp.get_json()


def _metric(payload, key):
    return next(m for m in payload["metrics"] if m["key"] == key)


def _log_study(client, date, minutes):
    return client.post("/api/learning/sessions", json={
        "date": date, "duration_minutes": minutes, "started_at": "09:00"})


def _log_sleep(client, date, minutes):
    return client.post("/api/sleep", json={
        "date": date, "duration_minutes": minutes, "bedtime": "23:00", "wake_time": "07:00"})


# --- the shape ---------------------------------------------------------------

def test_requires_login(client):
    assert client.get("/api/analytics").status_code == 302


def test_an_unknown_period_is_rejected(hero):
    """Silently falling back to 30 days would make a typo look like data."""
    assert hero.get("/api/analytics?period=fortnight").status_code == 400


@pytest.mark.parametrize("period,days", [("7", 7), ("30", 30), ("90", 90), ("365", 365)])
def test_each_period_spans_the_days_it_claims(hero, period, days):
    payload = _analytics(hero, period=period)
    assert payload["range"]["days"] == days
    assert payload["range"]["end"] == END
    assert len(payload["calendar"]) == days
    assert all(len(m["series"]) == days for m in payload["metrics"])


def test_the_comparison_window_sits_immediately_before_this_one(hero):
    payload = _analytics(hero, period="30")
    assert payload["range"]["start"] == "2026-06-02"
    assert payload["previous"]["end"] == "2026-06-01"
    assert payload["previous"]["start"] == "2026-05-03"
    assert payload["previous"]["days"] == payload["range"]["days"]


def test_every_metric_declares_how_it_aggregates(hero):
    """The UI renders the aggregate it is told. A metric that did not say would
    be rendered by guessing from the unit, which is how a week of sleep ends up
    summed into 56 hours."""
    for metric in _analytics(hero)["metrics"]:
        assert metric["aggregate"] in ("sum", "avg")
        assert metric["label"] and metric["accent"]
        assert metric["days"] == 30


# --- unobserved is not zero --------------------------------------------------

def test_a_day_with_no_record_is_null_not_zero(hero):
    """The whole doctrine in one assertion. A gap in the line is honest; a point
    on the floor is a claim that you ate nothing."""
    _log_study(hero, IN_WINDOW, 60)

    series = _metric(_analytics(hero), "study_minutes")["series"]
    logged = [point for point in series if point["date"] == IN_WINDOW]
    assert logged[0]["value"] == 60
    assert all(point["value"] is None for point in series if point["date"] != IN_WINDOW)


def test_an_average_divides_by_observed_days_not_calendar_days(hero):
    """Two nights of 8h across a 30-day window averages 8h, not 32 minutes."""
    _log_sleep(hero, "2026-06-20", 480)
    _log_sleep(hero, "2026-06-21", 480)

    sleep = _metric(_analytics(hero), "sleep_minutes")
    assert sleep["value"] == 480
    assert sleep["observed_days"] == 2
    assert sleep["days"] == 30


def test_observed_days_is_reported_so_an_average_can_be_read_honestly(hero):
    _log_sleep(hero, "2026-06-20", 480)
    sleep = _metric(_analytics(hero), "sleep_minutes")
    assert (sleep["observed_days"], sleep["days"]) == (1, 30)


def test_a_metric_with_no_data_reports_null_rather_than_zero(hero):
    """A brand-new account has not trained 0 kg - it has not trained."""
    volume = _metric(_analytics(hero), "training_volume")
    assert volume["value"] is None
    assert volume["observed_days"] == 0


def test_an_unsubmitted_day_does_not_drag_the_daily_score_average_down(hero):
    """Found in live data. The engine writes daily_score = 0 for every day the
    checklist was not submitted, so a user who logged twice - scoring 100 and 95 -
    had thirteen phantom zeros averaged in and was told 13.0.

    daily_scores cannot distinguish "no answer" from "answered No to everything";
    both store 0. A daily_log row can, because it only exists for a day that was
    actually submitted."""
    items = hero.get("/api/checklist-items").get_json()["items"]
    answers = {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}
    hero.put("/api/days/2026-06-20", json={"responses": answers})

    # Days that were never submitted, but which the engine still scored as 0
    # because a workout produced attribute signal.
    exercises = hero.get("/api/exercises").get_json()["exercises"]
    bench = next(e for e in exercises if "Bench" in e["name"])
    for date in ("2026-06-10", "2026-06-11", "2026-06-12"):
        workout = hero.post("/api/workouts", json={"date": date, "name": "Push"}).get_json()
        hero.put(f"/api/workouts/{workout['id']}",
                 json={"sets": [{"exercise_id": bench["id"], "weight": 80, "reps": 8}]})

    score = _metric(_analytics(hero), "daily_score")
    observed = [point for point in score["series"] if point["value"] is not None]

    assert len(observed) == 1, "only the submitted day is observed"
    assert observed[0]["date"] == "2026-06-20"
    # The exact figure depends on the stock Path's weights, so pin the property
    # that the bug broke: the average is the submitted day, undiluted.
    assert score["observed_days"] == 1
    assert score["value"] == observed[0]["value"] > 50


# --- sums and averages -------------------------------------------------------

def test_a_sum_metric_sums(hero):
    _log_study(hero, "2026-06-20", 60)
    _log_study(hero, "2026-06-21", 30)

    study = _metric(_analytics(hero), "study_minutes")
    assert study["aggregate"] == "sum"
    assert study["value"] == 90


def test_two_sessions_on_one_day_collapse_into_that_day(hero):
    """The series is one point per calendar day, whatever the row count."""
    _log_study(hero, IN_WINDOW, 45)
    _log_study(hero, IN_WINDOW, 15)

    study = _metric(_analytics(hero), "study_minutes")
    assert study["observed_days"] == 1
    assert study["value"] == 60


# --- comparison --------------------------------------------------------------

def test_no_previous_observations_means_no_delta(hero):
    """"Up 100%" against an empty window would turn "I started logging sleep"
    into a claim about sleeping more."""
    _log_sleep(hero, IN_WINDOW, 480)

    sleep = _metric(_analytics(hero), "sleep_minutes")
    assert sleep["previous"] is None
    assert sleep["delta"] is None
    assert sleep["delta_pct"] is None
    assert sleep["previous_observed_days"] == 0


def test_a_delta_is_reported_when_both_windows_have_data(hero):
    _log_study(hero, IN_PREVIOUS, 60)   # previous window
    _log_study(hero, IN_WINDOW, 90)     # current window

    study = _metric(_analytics(hero), "study_minutes")
    assert study["previous"] == 60
    assert study["value"] == 90
    assert study["delta"] == 30
    assert study["delta_pct"] == 50.0


def test_a_decline_is_reported_as_a_decline(hero):
    _log_study(hero, IN_PREVIOUS, 100)
    _log_study(hero, IN_WINDOW, 40)

    study = _metric(_analytics(hero), "study_minutes")
    assert study["delta"] == -60
    assert study["delta_pct"] == -60.0


def test_the_previous_window_does_not_leak_into_the_current_series(hero):
    """A boundary bug here would double-count the handover day and make every
    comparison flatter than it is."""
    _log_study(hero, IN_PREVIOUS, 60)

    study = _metric(_analytics(hero), "study_minutes")
    assert study["value"] is None
    assert all(point["value"] is None for point in study["series"])


def test_the_day_before_the_window_belongs_to_the_previous_period(hero):
    _log_study(hero, "2026-06-01", 25)   # previous window's last day
    _log_study(hero, "2026-06-02", 75)   # current window's first day

    study = _metric(_analytics(hero), "study_minutes")
    assert study["value"] == 75
    assert study["previous"] == 25


# --- calendar ----------------------------------------------------------------

def test_the_calendar_marks_unlogged_days_as_unlogged(hero):
    calendar = _analytics(hero)["calendar"]
    assert len(calendar) == 30
    assert all(cell["logged"] is False for cell in calendar)
    assert all(cell["completion_pct"] is None for cell in calendar)


def test_a_logged_day_carries_its_adherence(hero):
    items = hero.get("/api/checklist-items").get_json()["items"]
    hero.put(f"/api/days/{IN_WINDOW}", json={
        "responses": {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}})

    cell = next(c for c in _analytics(hero)["calendar"] if c["date"] == IN_WINDOW)
    assert cell["logged"] is True
    assert cell["completion_pct"] > 0
    assert cell["items_total"] > 0


def test_days_logged_counts_the_calendar(hero):
    items = hero.get("/api/checklist-items").get_json()["items"]
    answers = {i["name"]: "Yes" for i in items if i["type"] == "yes-no"}
    hero.put("/api/days/2026-06-20", json={"responses": answers})
    hero.put("/api/days/2026-06-21", json={"responses": answers})

    assert _analytics(hero)["days_logged"] == 2


# --- attributes --------------------------------------------------------------

def test_every_attribute_appears_with_a_comparison_point(hero):
    """All eight, every time. A radar whose axes come and go is unreadable."""
    attributes = _analytics(hero)["attributes"]
    assert len(attributes) == 8
    for entry in attributes:
        assert entry["attribute"]
        assert "score" in entry and "previous" in entry and "delta" in entry


def test_an_attribute_with_no_history_has_no_delta(hero):
    for entry in _analytics(hero)["attributes"]:
        assert entry["delta"] is None


# --- all time ----------------------------------------------------------------

def test_all_time_starts_at_the_first_logged_day(hero):
    """Not at account creation - that would pad the chart with empty months
    before they started."""
    _log_study(hero, "2026-06-10", 30)

    payload = _analytics(hero, period="all")
    assert payload["range"]["start"] == "2026-06-10"
    assert payload["range"]["end"] == END


def test_all_time_on_an_empty_account_does_not_explode(hero):
    payload = _analytics(hero, period="all")
    assert payload["range"]["days"] >= 1
    assert len(payload["calendar"]) == payload["range"]["days"]
