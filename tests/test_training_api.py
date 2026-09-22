"""Tests for the Training workspace endpoints."""
from datetime import date, timedelta

import pytest

from conftest import register

TODAY = date.today()


@pytest.fixture()
def client_with_library(client):
    register(client, username='lifter')
    return client


def _exercise(client, name_contains='Barbell Bench'):
    exercises = client.get('/api/exercises').get_json()['exercises']
    return next(e for e in exercises if name_contains in e['name'])


def _log(client, day, exercise_id, sets, name='Session'):
    workout = client.post('/api/workouts', json={'date': day, 'name': name}).get_json()
    client.put(f"/api/workouts/{workout['id']}", json={'sets': sets})
    return workout['id']


# --- library ----------------------------------------------------------------

def test_library_is_available_immediately(client_with_library):
    """Seeded by init_db, so a brand-new account never opens an empty picker."""
    exercises = client_with_library.get('/api/exercises').get_json()['exercises']
    assert len(exercises) > 50
    assert all(e['is_custom'] is False for e in exercises)


def test_library_filters(client_with_library):
    chest = client_with_library.get('/api/exercises?muscle=chest').get_json()['exercises']
    assert chest and all(e['primary_muscle'] == 'chest' for e in chest)

    mobility = client_with_library.get(
        '/api/exercises?category=mobility').get_json()['exercises']
    assert mobility and all(e['category'] == 'mobility' for e in mobility)

    home = client_with_library.get(
        '/api/exercises?equipment=bodyweight').get_json()['exercises']
    assert home and all(e['equipment'] == 'bodyweight' for e in home)


def test_library_search(client_with_library):
    found = client_with_library.get('/api/exercises?q=squat').get_json()['exercises']
    assert found
    assert all('squat' in e['name'].lower() for e in found)


def test_archived_exercises_are_hidden(client_with_library, app_module):
    conn = app_module.get_db_connection()
    conn.execute("UPDATE exercises SET archived = 1 WHERE slug = 'push-up'")
    conn.commit()
    conn.close()

    names = [e['slug'] for e in
             client_with_library.get('/api/exercises').get_json()['exercises']]
    assert 'push-up' not in names


# --- logging ----------------------------------------------------------------

def test_log_a_session_and_read_it_back(client_with_library):
    bench = _exercise(client_with_library)
    workout_id = _log(client_with_library, TODAY.isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 80, 'reps': 8},
        {'exercise_id': bench['id'], 'weight': 80, 'reps': 7},
    ])

    detail = client_with_library.get(f'/api/workouts/{workout_id}').get_json()
    assert detail['total_sets'] == 2
    assert detail['total_volume'] == 80 * 8 + 80 * 7
    assert detail['sets'][0]['exercise_name'] == bench['name']


def test_warmups_are_excluded_from_volume(client_with_library):
    """A warm-up is real work but it is not the training signal, and counting it
    would inflate every session."""
    bench = _exercise(client_with_library)
    workout_id = _log(client_with_library, TODAY.isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 40, 'reps': 10, 'is_warmup': True},
        {'exercise_id': bench['id'], 'weight': 80, 'reps': 8},
    ])

    detail = client_with_library.get(f'/api/workouts/{workout_id}').get_json()
    assert detail['total_sets'] == 1
    assert detail['total_volume'] == 640


def test_updating_a_session_replaces_its_sets(client_with_library):
    """A partial save that left deleted sets behind would quietly inflate volume."""
    bench = _exercise(client_with_library)
    workout_id = _log(client_with_library, TODAY.isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 80, 'reps': 8},
        {'exercise_id': bench['id'], 'weight': 80, 'reps': 8},
        {'exercise_id': bench['id'], 'weight': 80, 'reps': 8},
    ])
    client_with_library.put(f'/api/workouts/{workout_id}', json={
        'sets': [{'exercise_id': bench['id'], 'weight': 80, 'reps': 8}]})

    detail = client_with_library.get(f'/api/workouts/{workout_id}').get_json()
    assert detail['total_sets'] == 1
    assert detail['total_volume'] == 640


def test_two_sessions_in_one_day_are_allowed(client_with_library):
    """A morning lift and an evening run is normal, unlike the daily checklist."""
    bench = _exercise(client_with_library)
    _log(client_with_library, TODAY.isoformat(), bench['id'],
         [{'exercise_id': bench['id'], 'weight': 80, 'reps': 5}], name='Morning')
    _log(client_with_library, TODAY.isoformat(), bench['id'],
         [{'exercise_id': bench['id'], 'weight': 60, 'reps': 10}], name='Evening')

    workouts = client_with_library.get('/api/workouts').get_json()['workouts']
    assert len(workouts) == 2


def test_deleting_a_session_rebuilds_the_scores(client_with_library, app_module):
    """The deleted session was feeding Strength; leaving the derived scores
    behind would credit training that no longer exists."""
    bench = _exercise(client_with_library)
    for offset in range(6):
        day = (TODAY - timedelta(days=offset)).isoformat()
        _log(client_with_library, day, bench['id'],
             [{'exercise_id': bench['id'], 'weight': 100, 'reps': 10} for _ in range(5)])

    conn = app_module.get_db_connection()
    before = conn.execute(
        "SELECT score FROM attribute_scores WHERE attribute = 'Strength' "
        'ORDER BY date DESC LIMIT 1').fetchone()['score']
    conn.close()

    workouts = client_with_library.get('/api/workouts').get_json()['workouts']
    for workout in workouts:
        client_with_library.delete(f"/api/workouts/{workout['id']}")

    conn = app_module.get_db_connection()
    after = conn.execute(
        "SELECT score FROM attribute_scores WHERE attribute = 'Strength' "
        'ORDER BY date DESC LIMIT 1').fetchone()
    conn.close()
    assert before is not None
    assert after is None or after['score'] != before


def test_workouts_are_per_user(client, app_module):
    register(client, username='alice')
    bench = _exercise(client)
    workout_id = _log(client, TODAY.isoformat(), bench['id'],
                      [{'exercise_id': bench['id'], 'weight': 80, 'reps': 8}])
    client.post('/logout')

    register(client, username='bob')
    assert client.get(f'/api/workouts/{workout_id}').status_code == 404
    assert client.get('/api/workouts').get_json()['workouts'] == []


# --- previous performance ---------------------------------------------------

def test_history_reports_both_kinds_of_record(client_with_library):
    """"Best" means two things in a gym: the heaviest lift and the biggest set.
    Reporting only one of them is misleading."""
    bench = _exercise(client_with_library)
    _log(client_with_library, (TODAY - timedelta(days=3)).isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 80, 'reps': 8},    # 640 volume
        {'exercise_id': bench['id'], 'weight': 82.5, 'reps': 6},  # heavier, 495
    ])

    history = client_with_library.get(
        f"/api/exercises/{bench['id']}/history").get_json()
    assert history['heaviest_set']['weight'] == 82.5
    assert history['best_volume_set']['weight'] == 80
    assert history['best_volume_set']['reps'] == 8


def test_history_surfaces_the_last_session(client_with_library):
    """"Last time: 80kg x 8" is what someone needs before picking today's weight."""
    bench = _exercise(client_with_library)
    _log(client_with_library, (TODAY - timedelta(days=7)).isoformat(), bench['id'],
         [{'exercise_id': bench['id'], 'weight': 70, 'reps': 8}])
    _log(client_with_library, (TODAY - timedelta(days=2)).isoformat(), bench['id'],
         [{'exercise_id': bench['id'], 'weight': 80, 'reps': 8}])

    history = client_with_library.get(
        f"/api/exercises/{bench['id']}/history").get_json()
    assert history['last_session_date'] == (TODAY - timedelta(days=2)).isoformat()
    assert len(history['last_session_sets']) == 1
    assert history['last_session_sets'][0]['weight'] == 80


def test_history_can_exclude_the_session_being_edited(client_with_library):
    """Reopening a saved session must not quote that session back as "last time".

    Without the exclusion the logging screen shows you the sets you are looking
    at, which is useless for deciding today's weight - and reports today's lift
    as the all-time best before you have beaten anything.
    """
    bench = _exercise(client_with_library)
    _log(client_with_library, (TODAY - timedelta(days=7)).isoformat(), bench['id'],
         [{'exercise_id': bench['id'], 'weight': 70, 'reps': 8}])
    current = _log(client_with_library, TODAY.isoformat(), bench['id'],
                   [{'exercise_id': bench['id'], 'weight': 80, 'reps': 8}])

    included = client_with_library.get(
        f"/api/exercises/{bench['id']}/history").get_json()
    assert included['last_session_date'] == TODAY.isoformat()
    assert included['heaviest_set']['weight'] == 80

    excluded = client_with_library.get(
        f"/api/exercises/{bench['id']}/history?exclude_session={current}").get_json()
    assert excluded['last_session_date'] == (TODAY - timedelta(days=7)).isoformat()
    assert excluded['last_session_sets'][0]['weight'] == 70
    assert excluded['heaviest_set']['weight'] == 70
    assert excluded['best_volume_set']['weight'] == 70


def test_history_for_a_never_performed_exercise_is_empty_not_an_error(client_with_library):
    squat = _exercise(client_with_library, 'Back Squat')
    history = client_with_library.get(f"/api/exercises/{squat['id']}/history").get_json()
    assert history['last_session_sets'] == []
    assert history['heaviest_set'] is None


# --- dashboard --------------------------------------------------------------

def test_training_summary_composes_the_dashboard(client_with_library):
    bench = _exercise(client_with_library)
    for offset in range(3):
        day = (TODAY - timedelta(days=offset)).isoformat()
        _log(client_with_library, day, bench['id'],
             [{'exercise_id': bench['id'], 'weight': 80, 'reps': 8}])

    summary = client_with_library.get('/api/training').get_json()
    assert summary['total_sessions'] == 3
    assert summary['total_volume'] == 640 * 3
    assert len(summary['recent']) == 3
    assert summary['by_muscle'][0]['muscle'] == 'chest'
    assert summary['records'][0]['exercise'] == bench['name']


def test_training_summary_for_a_new_user_is_empty_not_broken(client_with_library):
    summary = client_with_library.get('/api/training').get_json()
    assert summary['total_sessions'] == 0
    assert summary['recent'] == []
    assert summary['by_muscle'] == []


# --- measurements -----------------------------------------------------------

def test_measurements_upsert_by_date_and_metric(client_with_library):
    day = TODAY.isoformat()
    client_with_library.post('/api/measurements',
                             json={'date': day, 'metric': 'weight', 'value': 75.5, 'unit': 'kg'})
    client_with_library.post('/api/measurements',
                             json={'date': day, 'metric': 'weight', 'value': 75.1, 'unit': 'kg'})

    rows = client_with_library.get('/api/measurements?metric=weight').get_json()['measurements']
    assert len(rows) == 1, 'correcting a measurement should not create a second row'
    assert rows[0]['value'] == 75.1


def test_measurements_validate(client_with_library):
    assert client_with_library.post('/api/measurements', json={}).status_code == 400
    assert client_with_library.post(
        '/api/measurements', json={'metric': 'weight'}).status_code == 400


# --- routines ---------------------------------------------------------------

def _routine(client, name='Push day', exercises=None):
    return client.post('/api/routines', json={
        'name': name, 'split_type': 'push-pull-legs', 'exercises': exercises or [],
    }).get_json()


def test_routine_round_trips_with_its_exercises(client_with_library):
    bench = _exercise(client_with_library)
    press = _exercise(client_with_library, 'Barbell Overhead')

    created = _routine(client_with_library, exercises=[
        {'exercise_id': bench['id'], 'target_sets': 4, 'target_reps': 6},
        {'exercise_id': press['id'], 'target_sets': 3, 'target_reps': 8},
    ])

    assert created['name'] == 'Push day'
    assert [e['name'] for e in created['exercises']] == [bench['name'], press['name']]
    assert created['exercises'][0]['target_sets'] == 4

    listed = client_with_library.get('/api/routines').get_json()['routines']
    assert len(listed) == 1
    assert len(listed[0]['exercises']) == 2


def test_updating_a_routine_replaces_its_exercise_list(client_with_library):
    """Reordering or removing must not leave the old rows behind."""
    bench = _exercise(client_with_library)
    press = _exercise(client_with_library, 'Barbell Overhead')
    created = _routine(client_with_library, exercises=[
        {'exercise_id': bench['id'], 'target_sets': 4, 'target_reps': 6},
        {'exercise_id': press['id'], 'target_sets': 3, 'target_reps': 8},
    ])

    updated = client_with_library.put(f"/api/routines/{created['id']}", json={
        'name': 'Push day A',
        'exercises': [{'exercise_id': press['id'], 'target_sets': 5, 'target_reps': 5}],
    }).get_json()

    assert updated['name'] == 'Push day A'
    assert len(updated['exercises']) == 1
    assert updated['exercises'][0]['exercise_id'] == press['id']
    assert updated['exercises'][0]['target_sets'] == 5


def test_deleting_a_routine_keeps_the_sessions_trained_from_it(client_with_library):
    """A routine is archived, never deleted - history must survive it."""
    bench = _exercise(client_with_library)
    routine = _routine(client_with_library, exercises=[
        {'exercise_id': bench['id'], 'target_sets': 3, 'target_reps': 8}])

    workout = client_with_library.post(
        '/api/workouts', json={'date': TODAY.isoformat(), 'routine_id': routine['id']},
    ).get_json()
    client_with_library.put(f"/api/workouts/{workout['id']}", json={
        'sets': [{'exercise_id': bench['id'], 'weight': 80, 'reps': 8}]})

    assert client_with_library.delete(f"/api/routines/{routine['id']}").status_code == 200
    assert client_with_library.get('/api/routines').get_json()['routines'] == []

    sessions = client_with_library.get('/api/workouts').get_json()['workouts']
    assert len(sessions) == 1
    assert sessions[0]['total_sets'] == 1


def test_session_started_from_a_routine_inherits_its_name(client_with_library):
    routine = _routine(client_with_library, name='Leg day')
    workout = client_with_library.post(
        '/api/workouts', json={'date': TODAY.isoformat(), 'routine_id': routine['id']},
    ).get_json()

    assert workout['name'] == 'Leg day'
    assert workout['routine_id'] == routine['id']


def test_routines_are_scoped_to_their_owner(client_with_library, client):
    routine = _routine(client_with_library)
    client_with_library.post('/logout')

    register(client, username='someone-else')
    assert client.get('/api/routines').get_json()['routines'] == []
    assert client.get(f"/api/routines/{routine['id']}").status_code == 404
    assert client.put(f"/api/routines/{routine['id']}", json={'name': 'mine'}).status_code == 404


def test_routine_requires_a_name(client_with_library):
    assert client_with_library.post('/api/routines', json={}).status_code == 400
    assert client_with_library.post('/api/routines', json={'name': '  '}).status_code == 400


def test_training_endpoints_require_login(client):
    for url in ('/api/exercises', '/api/workouts', '/api/training', '/api/measurements',
                '/api/routines'):
        assert client.get(url).status_code == 302


# --- pounds -------------------------------------------------------------------
#
# `exercise_sets.weight_unit` has stored a unit per set since R3, but until the
# logging screen offered the toggle nothing could write anything but kilograms -
# so every read path that compared or summed raw numbers was correct by accident.
# These are the tests that stop being vacuous now that pounds can get in.

POUND = 0.45359237


def test_a_set_keeps_the_unit_it_was_lifted_in(client_with_library):
    bench = _exercise(client_with_library)
    workout_id = _log(client_with_library, TODAY.isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 135, 'reps': 8, 'weight_unit': 'lb'},
    ])

    detail = client_with_library.get(f'/api/workouts/{workout_id}').get_json()
    assert detail['sets'][0]['weight'] == 135, 'the number must not be converted on write'
    assert detail['sets'][0]['weight_unit'] == 'lb'


def test_an_odd_spelling_of_pounds_is_normalised_on_the_way_in(client_with_library):
    """So the read paths have two spellings to handle rather than every casing."""
    bench = _exercise(client_with_library)
    workout_id = _log(client_with_library, TODAY.isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 135, 'reps': 8, 'weight_unit': 'LBS'},
        {'exercise_id': bench['id'], 'weight': 60, 'reps': 8, 'weight_unit': 'nonsense'},
    ])

    sets = client_with_library.get(f'/api/workouts/{workout_id}').get_json()['sets']
    assert [s['weight_unit'] for s in sets] == ['lb', 'kg']


def test_a_pounds_session_is_totalled_in_kilograms(client_with_library):
    """The bug this whole module exists for: 2.2x inflation on the Training page
    and the Analytics chart, while the Strength attribute stayed correct."""
    bench = _exercise(client_with_library)
    workout_id = _log(client_with_library, TODAY.isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 135, 'reps': 8, 'weight_unit': 'lb'},
    ])

    detail = client_with_library.get(f'/api/workouts/{workout_id}').get_json()
    assert detail['total_volume'] == pytest.approx(135 * POUND * 8)
    assert detail['total_volume'] < 600, 'raw pounds would be 1080'


def test_the_heaviest_set_is_the_heaviest_not_the_biggest_number(client_with_library):
    """135 lb is 61 kg. Ranking on the raw column would call it a record."""
    bench = _exercise(client_with_library)
    _log(client_with_library, (TODAY - timedelta(days=3)).isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 100, 'reps': 5, 'weight_unit': 'kg'},
    ])
    _log(client_with_library, (TODAY - timedelta(days=1)).isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 135, 'reps': 5, 'weight_unit': 'lb'},
    ])

    history = client_with_library.get(
        f"/api/exercises/{bench['id']}/history").get_json()
    assert history['heaviest_set']['weight'] == 100
    assert history['heaviest_set']['weight_unit'] == 'kg'


def test_the_best_set_is_compared_in_kilograms_too(client_with_library):
    bench = _exercise(client_with_library)
    _log(client_with_library, (TODAY - timedelta(days=3)).isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 90, 'reps': 8, 'weight_unit': 'kg'},
    ])
    _log(client_with_library, (TODAY - timedelta(days=1)).isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 185, 'reps': 8, 'weight_unit': 'lb'},
    ])

    history = client_with_library.get(
        f"/api/exercises/{bench['id']}/history").get_json()
    assert history['best_volume_set']['weight'] == 90, '185 lb x 8 is 671 kg, not 1480'


def test_volume_per_muscle_group_is_totalled_in_kilograms(client_with_library):
    bench = _exercise(client_with_library)
    _log(client_with_library, TODAY.isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 100, 'reps': 10, 'weight_unit': 'lb'},
    ])

    overview = client_with_library.get('/api/training').get_json()
    chest = next(row for row in overview['by_muscle'] if row['muscle'] == 'chest')
    assert chest['volume'] == pytest.approx(100 * POUND * 10)


def test_records_rank_by_load_and_report_the_unit_lifted(client_with_library):
    bench = _exercise(client_with_library)
    squat = _exercise(client_with_library, 'Back Squat')
    _log(client_with_library, (TODAY - timedelta(days=2)).isoformat(), bench['id'], [
        {'exercise_id': bench['id'], 'weight': 225, 'reps': 3, 'weight_unit': 'lb'},
    ])
    _log(client_with_library, (TODAY - timedelta(days=1)).isoformat(), squat['id'], [
        {'exercise_id': squat['id'], 'weight': 140, 'reps': 3, 'weight_unit': 'kg'},
    ])

    records = client_with_library.get('/api/training').get_json()['records']
    # 225 lb is 102 kg, so the squat leads - by the raw number the bench would.
    assert [row['exercise'] for row in records][0] == squat['name']
    bench_row = next(row for row in records if row['exercise'] == bench['name'])
    assert (bench_row['weight'], bench_row['weight_unit']) == (225, 'lb')
    assert 'weight_kg' not in bench_row, 'the ranking key is not part of the contract'
