"""Tests for the R4 scoring producers and nutrition arithmetic.

The theme running through these: R4 adds four measured signals, and each one has
a way of being subtly wrong that a naive implementation would ship.
"""
from datetime import date, timedelta

from scoring import producers
from scoring.config import DEFAULT_CONFIG, MEASURABLE_ATTRIBUTES
from scoring import nutrition

TODAY = date.today()


def _iso(offset):
    return (TODAY - timedelta(days=offset)).isoformat()


# --- sleep duration ---------------------------------------------------------

def test_sleep_duration_scales_below_target_and_plateaus_above():
    assert producers.sleep_duration_ratio(480, 480) == 1.0
    assert producers.sleep_duration_ratio(360, 480) == 0.75
    # A little over target is not a failure.
    assert producers.sleep_duration_ratio(540, 480) == 1.0


def test_sleeping_far_too_long_tapers_but_does_not_crater():
    """Eleven hours is not better recovery than eight, but the evidence that it
    is actively bad is weak - it should cost something, not everything."""
    eleven = producers.sleep_duration_ratio(660, 480)
    fourteen = producers.sleep_duration_ratio(840, 480)

    assert eleven < 1.0
    assert fourteen < eleven
    assert fourteen >= DEFAULT_CONFIG.sleep_oversleep_floor


def test_a_missing_or_zero_night_is_silent_not_zero():
    assert producers.sleep_duration_ratio(None, 480) is None
    assert producers.sleep_duration_ratio(0, 480) is None


# --- sleep schedule consistency ---------------------------------------------

def test_bedtimes_either_side_of_midnight_are_consistent():
    """The bug this guards against is severe and easy to ship: as raw minutes,
    23:50 and 00:10 look 23 hours apart, so the most disciplined possible sleeper
    would score the worst possible consistency."""
    spread = producers._circular_spread([1430, 10, 1435, 5])
    assert spread < 20, f'midnight-straddling bedtimes read as {spread:.0f} min apart'


def test_a_genuinely_erratic_schedule_scores_badly():
    rows = [
        {'date': _iso(3), 'duration_minutes': 420, 'bedtime': '22:00', 'wake_time': '05:00'},
        {'date': _iso(2), 'duration_minutes': 420, 'bedtime': '02:00', 'wake_time': '09:00'},
        {'date': _iso(1), 'duration_minutes': 420, 'bedtime': '23:00', 'wake_time': '06:00'},
        {'date': _iso(0), 'duration_minutes': 420, 'bedtime': '03:30', 'wake_time': '10:30'},
    ]
    erratic = producers.sleep_ratios(rows, [_iso(0)])[_iso(0)]['Discipline'][0]

    steady = [
        {'date': _iso(i), 'duration_minutes': 450, 'bedtime': '23:00', 'wake_time': '06:30'}
        for i in range(4)
    ]
    fixed = producers.sleep_ratios(steady, [_iso(0)])[_iso(0)]['Discipline'][0]

    assert fixed > erratic
    assert fixed > 0.9
    assert erratic < 0.5


def test_consistency_stays_quiet_until_there_are_enough_nights():
    rows = [{'date': _iso(1), 'duration_minutes': 450, 'bedtime': '23:00', 'wake_time': '06:30'}]
    out = producers.sleep_ratios(rows, [_iso(1)])
    assert 'Recovery' in out[_iso(1)]
    assert 'Discipline' not in out[_iso(1)], 'one night is not a schedule'


def test_sleep_says_nothing_about_days_before_the_first_night():
    rows = [{'date': _iso(0), 'duration_minutes': 480}]
    out = producers.sleep_ratios(rows, [_iso(5), _iso(0)])
    assert _iso(5) not in out, 'back-filling zeroes would invent a history of not sleeping'


# --- steps ------------------------------------------------------------------

def test_steps_feed_stamina_over_a_window():
    rows = [{'date': _iso(i), 'steps': 10000} for i in range(7)]
    out = producers.steps_ratios(rows, [_iso(0)])
    assert out[_iso(0)]['Stamina'][0] == 1.0


def test_the_first_logged_day_is_not_measured_against_a_full_week():
    """Same ramp-up fairness R3 needed: a genuine 10,000-step day on day one
    should not score 18% because six days of nothing sit in the window."""
    out = producers.steps_ratios([{'date': _iso(0), 'steps': 10000}], [_iso(0)])
    assert out[_iso(0)]['Stamina'][0] == 1.0


# --- adherence --------------------------------------------------------------

def _targets(calories=2000, protein=150, water=2500):
    return {'calories': calories, 'protein_g': protein, 'water_ml': water}


def test_hitting_your_targets_scores_well():
    lifestyle = [{'date': _iso(0), 'water_ml': 2500}]
    totals = {_iso(0): {'calories': 2000, 'protein_g': 150}}
    out = producers.adherence_ratios(lifestyle, totals, {_iso(0): _targets()})
    assert out[_iso(0)]['Discipline'][0] == 1.0


def test_calories_are_scored_two_sided():
    """A one-sided "more is better" reading would call a 4,000 kcal day against a
    2,000 target perfect adherence."""
    lifestyle = [{'date': _iso(0), 'water_ml': 2500}]
    over = producers.adherence_ratios(
        lifestyle, {_iso(0): {'calories': 4000, 'protein_g': 150}},
        {_iso(0): _targets()})[_iso(0)]['Discipline'][0]
    on_target = producers.adherence_ratios(
        lifestyle, {_iso(0): {'calories': 2000, 'protein_g': 150}},
        {_iso(0): _targets()})[_iso(0)]['Discipline'][0]

    assert over < on_target


def test_being_slightly_off_target_still_counts_as_hitting_it():
    """Nutrition tracking is approximate; 2,050 against a 2,000 target is a hit
    by any honest reading."""
    lifestyle = [{'date': _iso(0), 'water_ml': 2500}]
    out = producers.adherence_ratios(
        lifestyle, {_iso(0): {'calories': 2050, 'protein_g': 150}},
        {_iso(0): _targets()})
    assert out[_iso(0)]['Discipline'][0] == 1.0


def test_adherence_feeds_discipline_and_never_strength():
    lifestyle = [{'date': _iso(0), 'water_ml': 3000}]
    totals = {_iso(0): {'calories': 2000, 'protein_g': 300}}
    out = producers.adherence_ratios(lifestyle, totals, {_iso(0): _targets()})
    assert set(out[_iso(0)]) == {'Discipline'}, 'eating protein is not training'


# --- merging ----------------------------------------------------------------

def test_two_producers_feeding_one_attribute_are_averaged_not_overwritten():
    """After R4, sleep consistency and nutrition adherence both speak to
    Discipline. A plain dict update would let whichever ran last silently win."""
    merged = producers.merge_measured(
        {_iso(0): {'Discipline': (1.0, 3.0)}},
        {_iso(0): {'Discipline': (0.0, 3.0)}},
    )
    ratio, weight = merged[_iso(0)]['Discipline']
    assert ratio == 0.5
    assert weight == 6.0, 'two independent measurements should outweigh one'


def test_merging_leaves_unrelated_attributes_alone():
    merged = producers.merge_measured(
        {_iso(0): {'Strength': (0.8, 3.0)}},
        {_iso(0): {'Recovery': (0.6, 3.0)}},
    )
    assert merged[_iso(0)]['Strength'] == (0.8, 3.0)
    assert merged[_iso(0)]['Recovery'] == (0.6, 3.0)


# --- the ceiling ------------------------------------------------------------

def test_recovery_became_measurable_in_r4():
    assert 'Recovery' in MEASURABLE_ATTRIBUTES
    assert producers.blend('Recovery', 1.0, None) == DEFAULT_CONFIG.self_report_ceiling


def test_discipline_deliberately_did_not_become_measurable():
    """The checklist is already direct evidence of discipline, so capping it
    would punish someone for not using the Lifestyle workspace."""
    assert 'Discipline' not in MEASURABLE_ATTRIBUTES
    assert producers.blend('Discipline', 1.0, None) == 1.0


def test_logging_real_sleep_always_beats_claiming_it():
    """The same incentive check R3 needed. Any honestly logged night has to beat
    ticking a "slept well" box and logging nothing."""
    claimed = producers.blend('Recovery', 1.0, None)
    for hours in (4, 5, 6, 7, 8):
        ratio = producers.sleep_duration_ratio(hours * 60, 480)
        logged = producers.blend('Recovery', 1.0, (ratio, DEFAULT_CONFIG.measured_weight))
        assert logged > claimed, (
            f'{hours}h of logged sleep scored {logged:.2f}, worse than claiming it '
            f'and logging nothing ({claimed:.2f})'
        )


# --- nutrition arithmetic ---------------------------------------------------

def test_tdee_is_none_when_it_cannot_be_estimated():
    """An app that invented a TDEE from defaults would then show a confident
    deficit against a number it made up."""
    assert nutrition.tdee(None, 180, 30, 'male') is None
    assert nutrition.tdee(80, None, 30, 'male') is None
    assert nutrition.tdee(80, 180, None, 'male') is None


def test_tdee_lands_in_a_sane_range():
    value = nutrition.tdee(80, 180, 30, 'male', 'moderate')
    assert 2500 < value < 3000


def test_activity_level_moves_tdee_in_the_right_direction():
    sedentary = nutrition.tdee(80, 180, 30, 'male', 'sedentary')
    active = nutrition.tdee(80, 180, 30, 'male', 'very-active')
    assert active > sedentary


def test_targets_record_whether_each_number_was_set_or_estimated():
    targets = nutrition.resolve_targets(
        {'birth_year': TODAY.year - 30, 'sex': 'male', 'height_cm': 180,
         'activity_level': 'moderate', 'goal': 'maintain'},
        80, TODAY,
    )
    assert targets['sources']['calories'] == 'estimated'
    assert targets['estimated_tdee'] is not None

    explicit = nutrition.resolve_targets({'calorie_target': 2200}, 80, TODAY)
    assert explicit['sources']['calories'] == 'set'
    assert explicit['calories'] == 2200


def test_targets_are_unknown_rather_than_guessed_without_a_profile():
    targets = nutrition.resolve_targets({}, None, TODAY)
    assert targets['calories'] is None
    assert targets['sources']['calories'] == 'unknown'
    # Targets that do not depend on body composition still have defaults.
    assert targets['water_ml'] == 2500
    assert targets['steps'] == 8000


def test_cutting_sets_a_lower_calorie_target_than_bulking():
    profile = {'birth_year': TODAY.year - 30, 'sex': 'female', 'height_cm': 165,
               'activity_level': 'moderate'}
    cut = nutrition.resolve_targets({**profile, 'goal': 'cut'}, 65, TODAY)
    bulk = nutrition.resolve_targets({**profile, 'goal': 'bulk'}, 65, TODAY)
    assert cut['calories'] < bulk['calories']
    assert cut['protein_g'] > bulk['protein_g'], 'protein protects lean mass on a deficit'


def test_macros_scale_with_grams():
    food = {'kcal_per_100g': 165, 'protein_per_100g': 31, 'carbs_per_100g': 0,
            'fat_per_100g': 3.6, 'fibre_per_100g': 0}
    macros = nutrition.entry_macros(food, 200)
    assert macros['calories'] == 330
    assert macros['protein_g'] == 62


def test_a_recipe_is_the_weighted_sum_of_its_ingredients():
    ingredients = [
        {'kcal_per_100g': 165, 'protein_per_100g': 31, 'carbs_per_100g': 0,
         'fat_per_100g': 3.6, 'fibre_per_100g': 0, 'grams': 200},
        {'kcal_per_100g': 130, 'protein_per_100g': 2.7, 'carbs_per_100g': 28,
         'fat_per_100g': 0.3, 'fibre_per_100g': 0.4, 'grams': 300},
    ]
    per_100 = nutrition.recipe_per_100g(ingredients)
    assert per_100['total_grams'] == 500
    # 330 + 390 kcal over 500g
    assert per_100['kcal_per_100g'] == 144.0


def test_cooked_weight_changes_a_recipes_density():
    """Rice absorbs water and roasting drives it off, so dividing by the raw sum
    when a dish lost a third of its mass would under-report every meal made from
    it."""
    ingredients = [
        {'kcal_per_100g': 200, 'protein_per_100g': 10, 'carbs_per_100g': 20,
         'fat_per_100g': 5, 'fibre_per_100g': 1, 'grams': 300},
    ]
    raw = nutrition.recipe_per_100g(ingredients)
    reduced = nutrition.recipe_per_100g(ingredients, total_grams=200)

    assert raw['kcal_per_100g'] == 200
    assert reduced['kcal_per_100g'] == 300
