"""Tests for the R2 read endpoints that Home and Today consume.

These stay deliberately thin - R2.5 rewrites the backend in TypeScript - so the
tests focus on the contracts the UI actually depends on rather than on exhaustive
shape validation.
"""
from datetime import date, timedelta

import pytest

from conftest import register

# The real current date, not a fixed one: /api/home computes "today" from the
# server clock, so a hardcoded date here passes only on the day it was written.
TODAY = date.today()


def _items(client):
    paths = client.get('/api/paths').get_json()
    return [p for p in paths['paths'] if p['id'] == 'batman-path'][0]['checklist_items']


def _submit(client, day, items, strong=True):
    responses = {}
    for index, item in enumerate(items):
        if item['type'] == 'time':
            responses[item['name']] = item['options'][0 if strong else 3]
        elif item['type'] == 'yes-no':
            responses[item['name']] = 'Yes' if (strong or index % 3 == 0) else 'No'
        elif item['type'] == 'rating':
            responses[item['name']] = '4'
    return client.post('/api/activities', json={
        'date': day, 'activity_name': 'Daily Checklist', 'description': '',
        'duration': 0, 'progress_score': 8, 'notes': '',
        'checklist_data': {
            'date': day, 'checklist': {}, 'custom_responses': responses,
            'selected_path_id': 'batman-path', 'selected_path_name': 'Batman Path',
            'completion_percent': 100, 'notes': '',
        },
    })


@pytest.fixture()
def logged_in(client):
    register(client)
    return client


def _seed(client, days):
    items = _items(client)
    for offset in range(days - 1, -1, -1):
        _submit(client, (TODAY - timedelta(days=offset)).isoformat(), items)
    return items


# --- the write path actually runs now ---------------------------------------

def test_submitting_a_checklist_populates_the_scoring_tables(logged_in, app_module):
    """app.py did not import scoring at all until R2 wired it in, so these
    tables stayed empty in production while passing every test."""
    _seed(logged_in, 1)

    conn = app_module.get_db_connection()
    for table in ('daily_log', 'attribute_scores', 'daily_scores'):
        count = conn.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n']
        assert count > 0, f'{table} was not written on submission'
    conn.close()


def test_resubmitting_a_day_does_not_duplicate_the_log(logged_in, app_module):
    items = _seed(logged_in, 1)
    _submit(logged_in, TODAY.isoformat(), items, strong=False)

    conn = app_module.get_db_connection()
    count = conn.execute('SELECT COUNT(*) AS n FROM daily_log').fetchone()['n']
    conn.close()
    assert count == 1


# --- GET /api/attributes ----------------------------------------------------

def test_attributes_always_returns_all_eight_in_axis_order(logged_in, app_module):
    """The radar needs every axis every time; an axis that appears and vanishes
    between renders is unreadable."""
    _seed(logged_in, 5)

    data = logged_in.get('/api/attributes').get_json()
    names = [a['attribute'] for a in data['attributes']]
    assert names == list(app_module.scoring.ATTRIBUTES)


def test_attributes_for_a_brand_new_user_are_honest_not_zero(logged_in):
    """Nothing logged yet: every attribute must report a status, and none may
    report a score of 0 - that would read as failure rather than no data."""
    data = logged_in.get('/api/attributes').get_json()
    for attribute in data['attributes']:
        assert attribute['score'] is None
        assert attribute['status'] in {'locked', 'unobserved', 'calibrating'}


def test_locked_attribute_names_the_phase_that_unlocks_it(logged_in):
    data = logged_in.get('/api/attributes').get_json()
    agility = next(a for a in data['attributes'] if a['attribute'] == 'Agility')
    assert agility['status'] == 'locked'
    assert agility['unlocks_in'] == 'R3'


def test_calibrating_attribute_reports_days_remaining(logged_in):
    _seed(logged_in, 1)
    data = logged_in.get('/api/attributes').get_json()
    calibrating = [a for a in data['attributes'] if a['status'] == 'calibrating']
    assert calibrating, 'one logged day should leave attributes calibrating'
    assert all(a.get('needs_days', 0) > 0 for a in calibrating)


def test_attributes_become_active_with_enough_history(logged_in):
    _seed(logged_in, 5)
    data = logged_in.get('/api/attributes').get_json()
    active = [a for a in data['attributes'] if a['status'] == 'active']
    assert len(active) >= 5
    assert all(isinstance(a['score'], int) for a in active)


# --- GET /api/days/<date> ---------------------------------------------------

def test_day_detail_returns_the_per_item_snapshot(logged_in):
    _seed(logged_in, 1)
    data = logged_in.get(f'/api/days/{TODAY.isoformat()}').get_json()

    assert data['logged'] is True
    assert data['completion_pct'] == 100
    assert data['self_rating'] == 4
    assert len(data['items']) > 0
    first = data['items'][0]
    assert {'name', 'type', 'icon', 'weight', 'response', 'credit'} <= set(first)


def test_unlogged_day_is_not_an_error(logged_in):
    """Most dates simply have not been logged; that is a normal answer, not a 404."""
    resp = logged_in.get('/api/days/2020-01-01')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['logged'] is False
    assert data['items'] == []


def test_day_detail_is_per_user(client, app_module):
    """One user must not be able to read another's day."""
    register(client, username='alice')
    _seed(client, 1)
    client.get('/logout')

    register(client, username='bob')
    data = client.get(f'/api/days/{TODAY.isoformat()}').get_json()
    assert data['logged'] is False


# --- GET /api/home ----------------------------------------------------------

def test_home_composes_everything_in_one_response(logged_in):
    """Composed server-side so the dashboard has one loading state rather than
    five independent skeletons."""
    _seed(logged_in, 5)
    data = logged_in.get('/api/home').get_json()

    assert {'level', 'total_xp', 'current_streak', 'daily_score', 'discipline_score',
            'today', 'attributes', 'trend', 'days_logged'} <= set(data)
    assert len(data['attributes']) == 8
    assert data['days_logged'] == 5
    assert len(data['trend']) == 5


def test_home_for_a_new_user_does_not_invent_numbers(logged_in):
    data = logged_in.get('/api/home').get_json()
    assert data['days_logged'] == 0
    assert data['daily_score'] is None
    assert data['discipline_score'] is None
    assert data['today']['logged'] is False
    assert all(a['score'] is None for a in data['attributes'])


def test_home_reports_todays_progress(logged_in):
    _seed(logged_in, 1)
    data = logged_in.get('/api/home').get_json()
    assert data['today']['logged'] is True
    assert data['today']['completion_pct'] == 100
    assert data['today']['items_completed'] == data['today']['items_total']


def test_r2_endpoints_require_login(client):
    for url in ('/api/home', '/api/attributes', '/api/days/2026-09-13'):
        assert client.get(url).status_code == 302


def test_spa_mount_point_tolerates_a_trailing_slash(logged_in):
    """/app/ is what a bookmark or a typed URL tends to look like. The <path:>
    converter does not match an empty string, so this 404'd until R2."""
    for url in ('/app', '/app/'):
        assert logged_in.get(url).status_code == 200, url


# --- PUT /api/days/<date> ---------------------------------------------------

def _answers_for(items, yes=True):
    out = {}
    for item in items:
        if item['type'] == 'time':
            out[item['name']] = item['options'][0 if yes else 3]
        elif item['type'] == 'yes-no':
            out[item['name']] = 'Yes' if yes else 'No'
        elif item['type'] == 'rating':
            out[item['name']] = '4'
    return out


def test_put_day_logs_and_scores_it(logged_in, app_module):
    items = _items(logged_in)
    resp = logged_in.put(f'/api/days/{TODAY.isoformat()}',
                         json={'responses': _answers_for(items), 'path_id': 'batman-path'})
    assert resp.status_code == 200
    assert resp.get_json()['completion_pct'] == 100

    conn = app_module.get_db_connection()
    for table in ('daily_log', 'attribute_scores', 'daily_scores'):
        assert conn.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n'] > 0
    conn.close()

    day = logged_in.get(f'/api/days/{TODAY.isoformat()}').get_json()
    assert day['logged'] is True
    assert day['items']


def test_put_day_updates_in_place_instead_of_appending(logged_in, app_module):
    """The legacy wizard appends an activities row per submission, so a corrected
    day is logged twice. This endpoint corrects the record instead."""
    items = _items(logged_in)
    url = f'/api/days/{TODAY.isoformat()}'
    logged_in.put(url, json={'responses': _answers_for(items, yes=True)})
    logged_in.put(url, json={'responses': _answers_for(items, yes=False)})

    conn = app_module.get_db_connection()
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM activities WHERE activity_name = 'Daily Checklist'"
    ).fetchone()['n']
    logs = conn.execute('SELECT COUNT(*) AS n FROM daily_log').fetchone()['n']
    conn.close()
    assert rows == 1
    assert logs == 1

    # The correction won, rather than the first answer sticking.
    assert logged_in.get(url).get_json()['completion_pct'] < 50


def test_put_day_scores_the_same_as_the_legacy_wizard(client, app_module):
    """Both writers must agree - a day logged in the SPA and the same day logged
    in the old wizard should not produce different XP."""
    register(client, username='viaput')
    items = _items(client)
    client.put(f'/api/days/{TODAY.isoformat()}',
               json={'responses': _answers_for(items), 'path_id': 'batman-path'})
    via_put = client.get('/api/gamification/summary').get_json()['total_xp']
    client.get('/logout')

    register(client, username='viapost')
    _submit(client, TODAY.isoformat(), _items(client))
    via_post = client.get('/api/gamification/summary').get_json()['total_xp']

    assert via_put == via_post


def test_put_day_rejects_a_bad_payload(logged_in):
    assert logged_in.put(f'/api/days/{TODAY.isoformat()}', json={}).status_code == 400
    assert logged_in.put(f'/api/days/{TODAY.isoformat()}',
                         json={'responses': 'nope'}).status_code == 400
    assert logged_in.put('/api/days/not-a-date', json={'responses': {}}).status_code == 400


def test_put_day_requires_login(client):
    assert client.put('/api/days/2026-09-14', json={'responses': {}}).status_code == 302
