"""Tests for the R2 attribute scoring engine (scoring/).

The engine's whole claim is that it does not fabricate numbers, so most of these
assert on *status* (locked / unobserved / calibrating / active) as much as on
score. See docs/SCORING.md for the model.
"""
from datetime import date, timedelta

import pytest

from scoring import (
    ATTRIBUTES,
    DEFAULT_CONFIG,
    aggregate_attribute,
    score_day,
)
from scoring.engine import (
    consistency_from_log_dates,
    item_credit,
    resolve_item_attributes,
)

TODAY = date(2026, 9, 13)


def _dates(*offsets):
    return [(TODAY - timedelta(days=o)).isoformat() for o in offsets]


# --- item -> attribute resolution ------------------------------------------

def test_explicit_attributes_win_over_icon():
    item = {'name': 'anything', 'icon': 'workout', 'attributes': {'Knowledge': 1.0}}
    assert resolve_item_attributes(item) == {'Knowledge': 1.0}


def test_icon_wins_over_keyword():
    # Name says "read" (Knowledge) but the icon says workout.
    item = {'name': 'Did you read about training?', 'icon': 'workout'}
    assert set(resolve_item_attributes(item)) == {'Strength', 'Stamina'}


def test_keyword_fallback_for_default_icon():
    item = {'name': 'Did you do cardio today?', 'icon': 'default'}
    assert resolve_item_attributes(item) == {'Stamina': 1.0}


def test_unmatched_item_feeds_nothing():
    """An item we cannot classify must contribute to no attribute rather than
    being dumped into a catch-all, which would fabricate signal."""
    assert resolve_item_attributes({'name': 'Did you xyzzy?', 'icon': 'default'}) == {}


def test_explicit_attributes_reject_unknown_names():
    item = {'name': 'x', 'attributes': {'Knowledge': 1.0, 'Charisma': 1.0}}
    assert resolve_item_attributes(item) == {'Knowledge': 1.0}


# --- per-item credit --------------------------------------------------------

def test_yes_no_credit():
    item = {'type': 'yes-no'}
    assert item_credit(item, 'Yes') == 1.0
    assert item_credit(item, 'No') == 0.0
    assert item_credit(item, 'Yes (Gym, Run)') == 1.0  # sub-response form
    assert item_credit(item, None) == 0.0


def test_time_items_are_graded_not_binary():
    """The XP path treats any answer as complete; attributes must not, or waking
    at 05:00 and after 07:30 score identically."""
    item = {'type': 'time', 'options': ['05:00 - 05:30 AM', '05:30 - 06:30 AM',
                                        '06:30 - 07:30 AM', 'After 07:30 AM']}
    best = item_credit(item, '05:00 - 05:30 AM')
    worst = item_credit(item, 'After 07:30 AM')
    assert best == 1.0
    assert 0 < worst < best


def test_rating_items_never_earn_credit():
    assert item_credit({'type': 'rating'}, '5') == 0.0


# --- whole-day scoring ------------------------------------------------------

def _batman(app_module):
    return [p for p in app_module.build_default_paths()
            if p['id'] == 'batman-path'][0]['checklist_items']


def _answers(items, yes=True, wake=0):
    out = {}
    for i in items:
        if i['type'] == 'time':
            out[i['name']] = i['options'][wake]
        elif i['type'] == 'yes-no':
            out[i['name']] = 'Yes' if yes else 'No'
    return out


def test_perfect_day_scores_full_completion(app_module):
    items = _batman(app_module)
    assert score_day(items, _answers(items, yes=True, wake=0))['completion'] == 1.0


def test_late_wake_costs_discipline_but_not_knowledge(app_module):
    items = _batman(app_module)
    early = score_day(items, _answers(items, yes=True, wake=0))['attributes']
    late = score_day(items, _answers(items, yes=True, wake=3))['attributes']

    ratio = lambda a, key: a[key]['earned'] / a[key]['available']
    assert ratio(late, 'Discipline') < ratio(early, 'Discipline')
    assert ratio(late, 'Knowledge') == ratio(early, 'Knowledge') == 1.0


def test_attribute_with_no_feeding_item_is_absent_not_zero(app_module):
    """The opportunity denominator: Agility is not in the Batman path at all, so
    it must be missing from the result rather than present with earned=0."""
    items = _batman(app_module)
    attributes = score_day(items, _answers(items))['attributes']
    assert 'Agility' not in attributes
    assert 'Strength' in attributes


# --- aggregation and honesty gates ------------------------------------------

def test_locked_attribute_reports_the_phase_that_unlocks_it(monkeypatch):
    """No attribute is locked since R3 unlocked Agility, but the mechanism has
    to keep working - a future attribute added before the phase that feeds it
    must report 'locked', not 'unobserved' (which would read as "your Path is
    missing something" rather than "this does not exist yet").
    """
    from scoring import engine

    monkeypatch.setitem(engine.LOCKED_UNTIL, 'Stamina', 'R9')
    result = aggregate_attribute('Stamina', [1.0] * 30)
    assert result['status'] == 'locked'
    assert result['score'] is None
    assert result['unlocks_in'] == 'R9'


def test_no_attribute_is_locked_now_that_training_exists():
    """R3 added mobility work, the only thing Agility was waiting for."""
    from scoring import engine

    assert engine.LOCKED_UNTIL == {}


def test_unobserved_when_no_days_have_the_signal():
    result = aggregate_attribute('Strength', [])
    assert result['status'] == 'unobserved'
    assert result['score'] is None


def test_calibrating_below_minimum_history():
    result = aggregate_attribute('Knowledge', [1.0, 1.0])
    assert result['status'] == 'calibrating'
    assert result['score'] is None
    assert result['needs_days'] == DEFAULT_CONFIG.min_days_for_score - 2


def test_active_score_is_recency_weighted():
    """Recent behaviour should dominate: the same days in improving order must
    score higher than in declining order."""
    improving = aggregate_attribute('Knowledge', [0.0, 0.0, 0.5, 1.0, 1.0])
    declining = aggregate_attribute('Knowledge', [1.0, 1.0, 0.5, 0.0, 0.0])
    assert improving['score'] > declining['score']


def test_confidence_grows_with_history():
    short = aggregate_attribute('Knowledge', [1.0] * 4)
    long = aggregate_attribute('Knowledge', [1.0] * 20)
    assert short['confidence'] < long['confidence'] == 1.0


# --- consistency ------------------------------------------------------------

def test_consistency_perfect_when_logged_every_day():
    ratios = consistency_from_log_dates(_dates(*range(14)), 14, TODAY.isoformat())
    assert aggregate_attribute('Consistency', ratios)['score'] == 100


def test_consistency_reflects_a_lapse():
    """Logged four days then stopped five days ago - must not read as perfect."""
    ratios = consistency_from_log_dates(_dates(5, 6, 7, 8), 14, TODAY.isoformat())
    assert aggregate_attribute('Consistency', ratios)['score'] < 50


def test_one_missed_day_is_not_punished_harshly():
    """The brief asks for both: reflect a drop, but don't punish one missed day.
    Ten solid days with today missed should still read strong."""
    ratios = consistency_from_log_dates(_dates(*range(1, 11)), 14, TODAY.isoformat())
    assert aggregate_attribute('Consistency', ratios)['score'] > 75


def test_consistency_never_claims_more_history_than_exists():
    ratios = consistency_from_log_dates(_dates(0), 14, TODAY.isoformat())
    assert aggregate_attribute('Consistency', ratios)['sample_days'] == 1


def test_consistency_with_no_logs_is_unobserved():
    ratios = consistency_from_log_dates([], 14, TODAY.isoformat())
    assert aggregate_attribute('Consistency', ratios)['status'] == 'unobserved'


# --- config integrity -------------------------------------------------------

@pytest.mark.parametrize('attribute', ATTRIBUTES)
def test_every_attribute_has_a_defined_outcome(attribute):
    """No attribute may fall through the engine undefined - each must resolve to
    one of the four statuses even with no data."""
    result = aggregate_attribute(attribute, [])
    assert result['status'] in {'locked', 'unobserved', 'calibrating', 'active'}
