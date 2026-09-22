"""Logging a session with the detail a session actually has.

Two things are being fixed here and they are easy to conflate.

**Per-exercise numbers.** The card used to ask for "sets each", "reps each" and
"weight each" and flatten the lot into a sentence. Fine for a circuit that
genuinely is 3x10; wrong for every other session, because nobody benches and
curls the same load. The card either recorded a number false for most of the
exercises, or the person gave up and typed it out by hand.

**Pounds.** `exercise_sets.weight_unit` has existed since R3 and almost nothing
read it. `scoring/producers.py` converted, so the Strength attribute was right;
the two queries computing `workout_sessions.total_volume` did not, so a session
in pounds would have inflated the Training page and the Analytics chart by 2.2x
while the attribute stayed correct. Both plausible, silently disagreeing.
"""
import json

import assistant.cards as cards
import assistant.tools as tools
from conftest import register
from scoring.units import to_kg


def context(app_module, user_id=1, today='2026-09-22'):
    return tools.ToolContext(app_module.get_db_connection(), user_id, today=today)


def exercise(ctx, like='Bench'):
    return ctx.conn.execute(
        'SELECT id, name FROM exercises WHERE name LIKE ? LIMIT 1', (f'%{like}%',)
    ).fetchone()


def make_routine(ctx, name='Back & Biceps', muscles=('back', 'biceps')):
    cursor = ctx.conn.cursor()
    cursor.execute(
        "INSERT INTO routines (user_id, name, split_type) VALUES (?, ?, 'custom')",
        (ctx.user_id, name),
    )
    routine_id = cursor.lastrowid
    for position, muscle in enumerate(muscles):
        row = ctx.conn.execute(
            'SELECT id FROM exercises WHERE primary_muscle = ? LIMIT 1', (muscle,)
        ).fetchone()
        ctx.conn.execute(
            'INSERT INTO routine_exercises (routine_id, exercise_id, position, '
            'target_sets, target_reps) VALUES (?, ?, ?, ?, ?)',
            (routine_id, row['id'], position, 4, 8),
        )
    ctx.conn.commit()
    return routine_id


# --- the card ------------------------------------------------------------------

def test_a_routine_card_carries_every_exercise_with_its_own_numbers(app_module, client):
    """The fix, stated once. Six exercises, six sets of inputs."""
    register(client)
    ctx = context(app_module)
    routine_id = make_routine(ctx)

    card = cards._routine_exercise_card(ctx.conn, 1, f'i want to log routine #{routine_id} today')

    assert card['kind'] == 'workout_rows'
    assert len(card['rows']) == 2
    for row in card['rows']:
        assert {'exercise_id', 'name', 'sets', 'reps', 'weight'} <= set(row)


def test_a_routine_card_prefills_the_targets_and_pre_ticks_them(app_module, client):
    """They said they followed this routine, so the likely edit is removing one
    rather than adding six. The targets are a starting point, not the record."""
    register(client)
    ctx = context(app_module)
    routine_id = make_routine(ctx)

    card = cards._routine_exercise_card(ctx.conn, 1, f'routine #{routine_id}')

    assert all(row['selected'] is True for row in card['rows'])
    assert all(row['sets'] == 4 and row['reps'] == 8 for row in card['rows'])
    assert card['allow_add'] is True, 'nobody follows a routine exactly'


def test_a_muscle_card_pre_ticks_nothing(app_module, client):
    """A pre-ticked menu logs the menu."""
    register(client)
    ctx = context(app_module)

    card = cards._exercise_card(ctx.conn, 1, ['chest'])

    assert card['rows'] and all(row['selected'] is False for row in card['rows'])


def test_a_card_opens_in_the_unit_the_person_lifts_in(app_module, client):
    """Otherwise somebody who lifts in pounds picks 'lb' on every set forever,
    and eventually forgets once and records 225 kg on a bench press."""
    register(client)
    ctx = context(app_module)
    assert cards.preferred_unit(ctx.conn, 1) == 'kg'

    ctx.conn.execute('INSERT INTO user_profile (user_id, weight_unit) VALUES (1, ?)', ('lb',))
    ctx.conn.commit()

    assert cards.preferred_unit(ctx.conn, 1) == 'lb'
    assert cards._exercise_card(ctx.conn, 1, ['chest'])['weight_unit'] == 'lb'


def test_an_unknown_routine_produces_no_card(app_module, client):
    register(client)
    ctx = context(app_module)

    assert cards._routine_exercise_card(ctx.conn, 1, 'routine #9999') is None


def test_somebody_elses_routine_produces_no_card(app_module, client):
    """Ids are sequential integers and the message carrying one is user text."""
    register(client, username='owner')
    ctx = context(app_module)
    routine_id = make_routine(ctx)

    assert cards._routine_exercise_card(ctx.conn, 2, f'routine #{routine_id}') is None


# --- submitting it -------------------------------------------------------------

def submit(client, payload, message='Logged my session.'):
    return client.post('/api/assistant/chat',
                       json={'message': message, 'structured': payload})


def sse(response):
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith('data: ')]


def test_a_filled_card_queues_without_calling_the_model(client, app_module, monkeypatch):
    """The card already knows the exercise ids it looked up.

    Describing them to the model and reading them back costs two round trips and
    loses the ids, so it searches every name again and can pick the wrong Bench
    Press. This asserts the model is never reached.
    """
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)

    def explode():
        raise AssertionError('the model should not have been called')
    monkeypatch.setattr('assistant.agent.build_client', explode)

    events = sse(submit(client, {
        'type': 'workout', 'name': 'Push', 'weight_unit': 'kg',
        'exercises': [{'exercise_id': bench['id'], 'name': bench['name'],
                       'sets': 3, 'reps': 8, 'weight': 60}],
    }))

    done = next(e for e in events if e['type'] == 'done')
    assert done['queued'][0]['type'] == 'workout'
    assert len(done['queued'][0]['exercises'][0]['sets']) == 3


def test_a_filled_card_still_produces_a_proposal_rather_than_writing(client, app_module):
    """Not a second path into the database - the same tool, the same gate."""
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)

    events = sse(submit(client, {
        'type': 'workout', 'name': 'Push', 'weight_unit': 'kg',
        'exercises': [{'exercise_id': bench['id'], 'name': bench['name'],
                       'sets': 3, 'reps': 8, 'weight': 60}],
    }))

    assert any(e['type'] == 'proposal' for e in events)
    assert ctx.conn.execute('SELECT COUNT(*) AS n FROM workout_sessions').fetchone()['n'] == 0


def test_untouched_rows_are_dropped(client, app_module):
    """A row nobody filled in is not a claim that they did nothing with it."""
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)
    curl = exercise(ctx, 'Curl')

    events = sse(submit(client, {
        'type': 'workout', 'name': 'Push', 'weight_unit': 'kg',
        'exercises': [
            {'exercise_id': bench['id'], 'name': bench['name'], 'sets': 3, 'reps': 8, 'weight': 60},
            {'exercise_id': curl['id'], 'name': curl['name'], 'sets': None, 'reps': None, 'weight': None},
        ],
    }))

    done = next(e for e in events if e['type'] == 'done')
    assert len(done['queued'][0]['exercises']) == 1


def test_an_entirely_empty_card_says_so_rather_than_queueing_nothing(client, app_module):
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)

    events = sse(submit(client, {
        'type': 'workout', 'name': 'Push', 'weight_unit': 'kg',
        'exercises': [{'exercise_id': bench['id'], 'name': bench['name'],
                       'sets': None, 'reps': None, 'weight': None}],
    }))

    error = next(e for e in events if e['type'] == 'error')
    assert 'nothing to log' in error['message']


def test_a_card_for_somebody_elses_exercise_is_refused(client, app_module):
    register(client)

    events = sse(submit(client, {
        'type': 'workout', 'name': 'Push', 'weight_unit': 'kg',
        'exercises': [{'exercise_id': 999999, 'name': 'Invented', 'sets': 3,
                       'reps': 8, 'weight': 60}],
    }))

    assert any(e['type'] == 'error' for e in events)


# --- pounds --------------------------------------------------------------------

def test_a_set_is_stored_in_the_unit_it_was_entered_in(app_module, client):
    """Never converted on write. Somebody who switches gyms must not have last
    year's log reinterpreted - which is what the column was added for."""
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)

    tools.apply_action(ctx, {
        'type': 'workout', 'date': '2026-09-22', 'name': 'Push',
        'exercises': [{'exercise_id': bench['id'], 'name': bench['name'],
                       'sets': [{'reps': 8, 'weight': 135, 'weight_unit': 'lb',
                                 'duration_minutes': None}]}],
    })

    row = ctx.conn.execute('SELECT weight, weight_unit FROM exercise_sets').fetchone()
    assert row['weight'] == 135 and row['weight_unit'] == 'lb'


def test_volume_is_normalised_to_kilograms(app_module, client):
    """The bug this release exists to prevent.

    Both queries that compute total_volume summed `weight * reps` with no
    conversion. Nothing could enter pounds, so it never fired - and it would have
    fired the moment anything could, inflating the Training page and the
    Analytics chart by 2.2x while Strength stayed correct.
    """
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)

    tools.apply_action(ctx, {
        'type': 'workout', 'date': '2026-09-22', 'name': 'Push',
        'exercises': [{'exercise_id': bench['id'], 'name': bench['name'],
                       'sets': [{'reps': 10, 'weight': 100, 'weight_unit': 'lb',
                                 'duration_minutes': None}]}],
    })

    volume = ctx.conn.execute('SELECT total_volume FROM workout_sessions').fetchone()['total_volume']
    assert round(volume, 2) == round(to_kg(100, 'lb') * 10, 2)
    assert volume < 1000, 'pounds were summed as if they were kilograms'


def test_the_same_session_in_either_unit_scores_the_same(app_module, client):
    """100 lb x 10 and 45.359 kg x 10 are the same work and must read the same."""
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)

    def volume_for(weight, unit, date):
        tools.apply_action(ctx, {
            'type': 'workout', 'date': date, 'name': 'Push',
            'exercises': [{'exercise_id': bench['id'], 'name': bench['name'],
                           'sets': [{'reps': 10, 'weight': weight, 'weight_unit': unit,
                                     'duration_minutes': None}]}],
        })
        return ctx.conn.execute(
            'SELECT total_volume FROM workout_sessions WHERE date = ?', (date,)
        ).fetchone()['total_volume']

    in_pounds = volume_for(100, 'lb', '2026-09-22')
    in_kilos = volume_for(to_kg(100, 'lb'), 'kg', '2026-09-23')

    assert round(in_pounds, 3) == round(in_kilos, 3)


def test_an_implausible_load_is_refused_in_either_unit(app_module, client):
    """600 lb would sail past a bare `weight <= 600` check, so the ceiling is
    applied in kilograms whatever was typed."""
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)

    # 1500 lb is about 680 kg - past the ceiling, but under it as a bare number.
    try:
        tools.propose_workout(ctx, date='2026-09-22', name='Push', exercises=[{
            'exercise_id': bench['id'], 'name': bench['name'],
            'sets': [{'reps': 1, 'weight': 1500, 'weight_unit': 'lb',
                      'duration_minutes': None}],
        }])
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'plausible' in str(error)


def test_an_unknown_unit_is_refused(app_module, client):
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)

    try:
        tools.propose_workout(ctx, date='2026-09-22', name='Push', exercises=[{
            'exercise_id': bench['id'], 'name': bench['name'],
            'sets': [{'reps': 8, 'weight': 60, 'weight_unit': 'stone',
                      'duration_minutes': None}],
        }])
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'kg or lb' in str(error)


def test_a_proposal_queued_before_this_change_still_applies(app_module, client):
    """`weight_kg` was the old field name. A pending proposal from before the
    rename is somebody's Save button, and it should not 400."""
    register(client)
    ctx = context(app_module)
    bench = exercise(ctx)

    note = tools.apply_action(ctx, {
        'type': 'workout', 'date': '2026-09-22', 'name': 'Push',
        'exercises': [{'exercise_id': bench['id'], 'name': bench['name'],
                       'sets': [{'reps': 8, 'weight_kg': 60, 'duration_minutes': None}]}],
    })

    assert '1 sets' in note
    assert ctx.conn.execute('SELECT weight FROM exercise_sets').fetchone()['weight'] == 60
