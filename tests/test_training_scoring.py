"""Tests for the R3 training producer.

This is the phase that tests whether the opportunity-denominator design actually
works. The engine was built on a promise: when measured data arrives, it enlarges
the denominator, so someone ticking a checkbox sits lower than someone logging
real training - without any hard-coded ceiling and without the number quietly
changing meaning. These tests hold it to that.
"""
from datetime import date, timedelta

import pytest

import scoring
from scoring import producers
from scoring.config import DEFAULT_CONFIG

START = date(2026, 9, 1)


@pytest.fixture()
def db(app_module):
    conn = app_module.get_db_connection()
    conn.execute("INSERT INTO users (username, password_hash) VALUES ('lifter', 'x')")
    conn.commit()
    user_id = conn.execute(
        "SELECT id FROM users WHERE username = 'lifter'").fetchone()['id']
    yield conn, user_id, app_module
    conn.close()


def _exercise(conn, slug, muscle, category='strength'):
    """A library exercise for the test to log sets against.

    Prefixed so it can never collide with the 85 real exercises that init_db now
    seeds from data/exercises.json - an earlier version of this helper picked
    'rowing-machine', which the shipped library also contains.
    """
    slug = f'test-{slug}'
    conn.execute(
        'INSERT INTO exercises (user_id, slug, name, primary_muscle, category) '
        'VALUES (NULL, ?, ?, ?, ?)', (slug, slug.replace('-', ' ').title(), muscle, category))
    return conn.execute('SELECT id FROM exercises WHERE slug = ?', (slug,)).fetchone()['id']


def _log_session(conn, user_id, day, exercise_id, sets, **kw):
    cur = conn.cursor()
    cur.execute('INSERT INTO workout_sessions (user_id, date, name) VALUES (?, ?, ?)',
                (user_id, day, 'Session'))
    session_id = cur.lastrowid
    for position, entry in enumerate(sets):
        conn.execute(
            'INSERT INTO exercise_sets (session_id, exercise_id, position, weight, '
            'weight_unit, reps, duration_seconds, is_warmup) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (session_id, exercise_id, position, entry.get('weight'),
             entry.get('unit', 'kg'), entry.get('reps'), entry.get('seconds'),
             1 if entry.get('warmup') else 0),
        )
    conn.commit()
    return session_id


def _items(app_module):
    return [p for p in app_module.build_default_paths()
            if p['id'] == 'batman-path'][0]['checklist_items']


def _answers(items, yes=True):
    out = {}
    for item in items:
        if item['type'] == 'time':
            out[item['name']] = item['options'][0]
        elif item['type'] == 'yes-no':
            out[item['name']] = 'Yes' if yes else 'No'
    return out


def _load_sets(conn, user_id):
    from scoring.store import _load_training_sets
    return _load_training_sets(conn, user_id)


def _score(conn, user_id, attribute):
    row = conn.execute(
        'SELECT score, status FROM attribute_scores WHERE user_id = ? AND attribute = ? '
        'ORDER BY date DESC LIMIT 1', (user_id, attribute)).fetchone()
    return (row['score'], row['status']) if row else (None, None)


# --- per-set signal extraction ----------------------------------------------

def test_strength_set_magnitude_is_volume():
    row = {'category': 'strength', 'primary_muscle': 'chest', 'weight': 80,
           'weight_unit': 'kg', 'reps': 8, 'completed': 1}
    assert producers.set_contribution(row) == ('Strength', 640.0)


def test_pounds_are_converted_to_kilograms():
    kg = producers.set_contribution(
        {'category': 'strength', 'primary_muscle': 'chest', 'weight': 100,
         'weight_unit': 'kg', 'reps': 1, 'completed': 1})[1]
    lb = producers.set_contribution(
        {'category': 'strength', 'primary_muscle': 'chest', 'weight': 100,
         'weight_unit': 'lb', 'reps': 1, 'completed': 1})[1]
    assert lb < kg
    assert round(lb, 1) == 45.4


def test_bodyweight_reps_still_count():
    """A set of 30 press-ups is training. Crediting it zero because there is no
    load on the bar would be worse than approximating it."""
    result = producers.set_contribution(
        {'category': 'strength', 'primary_muscle': 'chest', 'reps': 30, 'completed': 1})
    assert result is not None
    assert result[0] == 'Strength'
    assert result[1] > 0


def test_warmups_are_excluded():
    row = {'category': 'strength', 'primary_muscle': 'chest', 'weight': 20,
           'weight_unit': 'kg', 'reps': 10, 'completed': 1, 'is_warmup': 1}
    assert producers.set_contribution(row) is None


def test_cardio_feeds_stamina_and_mobility_feeds_agility():
    cardio = producers.set_contribution(
        {'category': 'cardio', 'primary_muscle': 'cardio', 'duration_seconds': 1800,
         'completed': 1})
    mobility = producers.set_contribution(
        {'category': 'mobility', 'primary_muscle': 'hamstrings', 'duration_seconds': 300,
         'completed': 1})
    assert cardio == ('Stamina', 30.0)
    # Category beats muscle: a mobility movement targeting hamstrings is Agility
    # work, not a hamstring builder.
    assert mobility == ('Agility', 5.0)


# --- the design claim -------------------------------------------------------

def test_measured_training_produces_a_real_signal(db):
    """A logged session must actually reach the attribute, not just sit in a
    table. Whether it should also out-SCORE a ticked box is a separate product
    decision - see docs/SCORING.md, "Self-report vs measurement".
    """
    conn, lifter_id, app_module = db
    items = _items(app_module)
    bench = _exercise(conn, 'bench-press', 'chest')

    for offset in range(14):
        day = (START + timedelta(days=offset)).isoformat()
        scoring.record_day(conn, lifter_id, day, items, _answers(items, yes=False))
        if offset % 2 == 0:
            _log_session(conn, lifter_id, day, bench,
                         [{'weight': 80, 'reps': 8} for _ in range(5)])
    conn.commit()
    scoring.recompute_scores(conn, lifter_id)
    conn.commit()

    score, status = _score(conn, lifter_id, 'Strength')
    assert status == 'active'
    # The checklist said "no strength training" every day. Only the logged sets
    # can be carrying this.
    assert score > 50


def test_first_training_day_is_not_measured_against_a_full_week(db):
    """Regression: the trailing window compared day one against a whole week's
    target, scoring a genuinely hard first session ~27% and letting the EWMA
    carry that unfair start forward for a fortnight."""
    conn, user_id, app_module = db
    items = _items(app_module)
    bench = _exercise(conn, 'bench-press', 'chest')

    day = START.isoformat()
    scoring.record_day(conn, user_id, day, items, _answers(items, yes=False))
    _log_session(conn, user_id, day, bench, [{'weight': 80, 'reps': 8} for _ in range(5)])
    conn.commit()

    sets = _load_sets(conn, user_id)
    ratios = producers.training_ratios(sets, [day], config=DEFAULT_CONFIG)
    assert ratios[day]['Strength'][0] == 1.0


def test_training_frequency_shows_up(db):
    """Once a week and four times a week must not score the same. A per-day model
    would give both 100% on the days they trained."""
    conn, often_id, app_module = db
    conn.execute("INSERT INTO users (username, password_hash) VALUES ('rare', 'x')")
    conn.commit()
    rare_id = conn.execute("SELECT id FROM users WHERE username = 'rare'").fetchone()['id']

    items = _items(app_module)
    squat = _exercise(conn, 'back-squat', 'quads')

    for offset in range(21):
        day = (START + timedelta(days=offset)).isoformat()
        for user_id in (often_id, rare_id):
            scoring.record_day(conn, user_id, day, items, _answers(items, yes=False))
        sets = [{'weight': 100, 'reps': 5} for _ in range(5)]
        if offset % 2 == 0:
            _log_session(conn, often_id, day, squat, sets)
        if offset % 7 == 0:
            _log_session(conn, rare_id, day, squat, sets)
    conn.commit()
    for user_id in (often_id, rare_id):
        scoring.recompute_scores(conn, user_id)
    conn.commit()

    assert _score(conn, often_id, 'Strength')[0] > _score(conn, rare_id, 'Strength')[0]


def test_a_rest_day_does_not_crater_the_score(db):
    """Training is windowed precisely so rest days are not punished - recovery is
    part of training, not a lapse."""
    conn, user_id, app_module = db
    items = _items(app_module)
    squat = _exercise(conn, 'back-squat', 'quads')

    days = [(START + timedelta(days=o)).isoformat() for o in range(10)]
    for offset, day in enumerate(days):
        scoring.record_day(conn, user_id, day, items, _answers(items))
        if offset < 8:  # trains for 8 days, then rests for 2
            _log_session(conn, user_id, day, squat,
                         [{'weight': 100, 'reps': 5} for _ in range(6)])
    conn.commit()
    scoring.recompute_scores(conn, user_id)
    conn.commit()

    series = scoring.get_attribute_history(conn, user_id, 'Strength', limit=30)
    active = [point for point in series if point['score'] is not None]
    assert active[-1]['score'] > 40, 'two rest days should not collapse Strength'


def test_mobility_work_unlocks_agility(db):
    """Agility was 'locked' for the whole of R2 with the note "unlocks in R3".
    This is that promise being kept."""
    conn, user_id, app_module = db
    items = _items(app_module)
    stretch = _exercise(conn, 'hamstring-stretch', 'hamstrings', category='mobility')

    before_days = [(START + timedelta(days=o)).isoformat() for o in range(5)]
    for day in before_days:
        scoring.record_day(conn, user_id, day, items, _answers(items))
    conn.commit()
    scoring.recompute_scores(conn, user_id)
    conn.commit()
    assert _score(conn, user_id, 'Agility') == (None, 'unobserved')

    for offset in range(5, 15):
        day = (START + timedelta(days=offset)).isoformat()
        scoring.record_day(conn, user_id, day, items, _answers(items))
        _log_session(conn, user_id, day, stretch, [{'seconds': 600}])
    conn.commit()
    scoring.recompute_scores(conn, user_id)
    conn.commit()

    score, status = _score(conn, user_id, 'Agility')
    assert status == 'active'
    assert score is not None and score > 0


def test_attribute_stays_silent_before_its_first_measurement(db):
    """Back-filling zeroes for the days before someone started training would
    invent a history of not training."""
    conn, user_id, app_module = db
    items = _items(app_module)
    row_machine = _exercise(conn, 'rowing-machine', 'cardio', category='cardio')

    days = [(START + timedelta(days=o)).isoformat() for o in range(10)]
    for day in days:
        scoring.record_day(conn, user_id, day, items, _answers(items))
    _log_session(conn, user_id, days[-1], row_machine, [{'seconds': 1800}])
    conn.commit()
    scoring.recompute_scores(conn, user_id)
    conn.commit()

    series = scoring.get_attribute_history(conn, user_id, 'Stamina', limit=30)
    # Stamina is fed by the checklist too, so it exists throughout - what must not
    # happen is the measured signal retroactively scoring the earlier days.
    early = conn.execute(
        'SELECT raw_value FROM attribute_scores WHERE user_id = ? AND attribute = ? '
        'AND date = ?', (user_id, 'Stamina', days[0])).fetchone()
    late = conn.execute(
        'SELECT raw_value FROM attribute_scores WHERE user_id = ? AND attribute = ? '
        'AND date = ?', (user_id, 'Stamina', days[-1])).fetchone()
    assert early is not None and late is not None
    assert series


def test_blend_prefers_the_measured_signal():
    """Neither source is discarded, but evidence beats assertion."""
    measured_high = producers.blend('Strength', 0.0, (1.0, DEFAULT_CONFIG.measured_weight))
    measured_low = producers.blend('Strength', 1.0, (0.0, DEFAULT_CONFIG.measured_weight))

    assert measured_high > 0.5, 'real training should outweigh an unticked box'
    assert measured_low < 0.5, 'a ticked box should not outweigh no training'
    assert producers.blend('Strength', None, None) is None


def test_self_report_alone_cannot_reach_the_top_of_a_measurable_attribute():
    """A ticked box is a claim. The last quarter of the scale is reserved for
    evidence, so logging sets is what opens it."""
    capped = producers.blend('Strength', 1.0, None)
    assert capped == DEFAULT_CONFIG.self_report_ceiling
    assert capped < 1.0

    # And logging real training does reach the top.
    proven = producers.blend('Strength', 1.0, (1.0, DEFAULT_CONFIG.measured_weight))
    assert proven == 1.0
    assert proven > capped


def test_the_ceiling_does_not_apply_where_nothing_can_measure():
    """Capping an attribute because you did not log something would punish
    someone for a feature that does not exist.

    Recovery left this list in R4 when sleep became loggable, and Knowledge and
    Focus left it in R5 when study sessions did.

    Discipline stays permanently despite gaining measured signals in R4: the
    daily checklist is already direct evidence of discipline, so sleep
    consistency and adherence are additional evidence rather than the only
    possible evidence. Consistency stays because nothing self-reports it at all.
    """
    for attribute in ('Discipline', 'Consistency'):
        assert producers.blend(attribute, 1.0, None) == 1.0


def test_logging_modest_training_always_beats_logging_nothing():
    """The incentive has to point the right way. An earlier ceiling of 0.75 meant
    honestly logging a light week scored 62 while claiming a perfect week and
    logging nothing scored 75 - the app would have punished honesty."""
    claimed_only = producers.blend('Strength', 1.0, None)

    for measured_ratio in (0.35, 0.5, 0.75, 1.0):
        logged = producers.blend('Strength', 1.0, (measured_ratio, DEFAULT_CONFIG.measured_weight))
        assert logged > claimed_only, (
            f'{measured_ratio:.0%} of the weekly target scored {logged:.2f}, '
            f'worse than claiming it and logging nothing ({claimed_only:.2f})'
        )


# --- R10: the weekly volume target scales with declared frequency ------------

def test_an_undeclared_frequency_reproduces_the_old_flat_target():
    """The whole rollout depends on this. Nobody's history moves until they
    answer the question, so the default has to land on the old 12000 exactly."""
    assert producers.weekly_strength_volume(None, DEFAULT_CONFIG) == 12000


def test_the_target_scales_with_how_often_you_train():
    """A flat weekly figure asks someone on a deliberate twice-a-week programme
    to produce a four-day week's volume, so they score permanently low for
    executing their plan perfectly."""
    two = producers.weekly_strength_volume(2, DEFAULT_CONFIG)
    four = producers.weekly_strength_volume(4, DEFAULT_CONFIG)
    six = producers.weekly_strength_volume(6, DEFAULT_CONFIG)

    assert two < four < six
    assert four == 12000


def test_declaring_almost_nothing_cannot_collapse_the_denominator():
    """The perverse incentive this clamp exists to close: without a floor,
    declaring "once a week" would turn one session into a free 100."""
    floor = producers.weekly_strength_volume(DEFAULT_CONFIG.min_training_days, DEFAULT_CONFIG)
    assert producers.weekly_strength_volume(1, DEFAULT_CONFIG) == floor
    assert producers.weekly_strength_volume(0, DEFAULT_CONFIG) == 12000  # 0 reads as undeclared


def test_declaring_everything_cannot_inflate_the_denominator():
    ceiling = producers.weekly_strength_volume(DEFAULT_CONFIG.max_training_days, DEFAULT_CONFIG)
    assert producers.weekly_strength_volume(7, DEFAULT_CONFIG) == ceiling
    assert producers.weekly_strength_volume(99, DEFAULT_CONFIG) == ceiling


def test_the_same_session_scores_higher_for_a_twice_a_week_lifter(db):
    """The point of the change, stated as behaviour rather than arithmetic. The
    identical session is worth more to someone who trains twice a week, because
    it is a larger share of the week they actually planned."""
    conn, user_id, app_module = db
    bench = _exercise(conn, 'bench-press', 'chest')

    day = START.isoformat()
    _log_session(conn, user_id, day, bench, [{'weight': 60, 'reps': 8} for _ in range(4)])
    conn.commit()
    sets = _load_sets(conn, user_id)

    frequent = producers.training_ratios(sets, [day], {day: 6}, config=DEFAULT_CONFIG)
    occasional = producers.training_ratios(sets, [day], {day: 2}, config=DEFAULT_CONFIG)

    assert occasional[day]['Strength'][0] > frequent[day]['Strength'][0]


def test_a_past_day_is_judged_against_the_frequency_that_applied_then(db):
    """Per-date, like the sleep and step targets - so changing your answer does
    not retroactively rewrite what every past week was aiming at."""
    conn, user_id, app_module = db
    bench = _exercise(conn, 'bench-press', 'chest')

    first = START.isoformat()
    second = (START + timedelta(days=1)).isoformat()
    for day in (first, second):
        _log_session(conn, user_id, day, bench, [{'weight': 60, 'reps': 8} for _ in range(3)])
    conn.commit()
    sets = _load_sets(conn, user_id)

    ratios = producers.training_ratios(
        sets, [first, second], {first: 2, second: 6}, config=DEFAULT_CONFIG)
    assert ratios[first]['Strength'][0] > ratios[second]['Strength'][0]
