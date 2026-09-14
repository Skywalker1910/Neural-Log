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
    client.get('/logout')

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


def test_training_endpoints_require_login(client):
    for url in ('/api/exercises', '/api/workouts', '/api/training', '/api/measurements'):
        assert client.get(url).status_code == 302
