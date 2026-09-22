"""Tests for the weekly personal feed and journal drafting endpoint."""
from conftest import register


END = '2026-09-20'


def _food(client, name_contains='Chicken Breast, cooked'):
    foods = client.get('/api/foods').get_json()['foods']
    return next(food for food in foods if name_contains in food['name'])


def test_weekly_feed_is_a_seven_day_honest_summary(client):
    register(client, username='reader')
    chicken = _food(client)
    client.post('/api/nutrition/2026-09-18/entries', json={
        'food_id': chicken['id'], 'grams': 200, 'meal': 'lunch',
    })
    client.post('/api/sleep', json={
        'date': '2026-09-18', 'duration_minutes': 480,
    })
    client.put('/api/lifestyle/2026-09-18', json={
        'steps': 7500, 'water_ml': 2200, 'mood': 4,
    })
    client.post('/api/learning/sessions', json={
        'date': '2026-09-18', 'duration_minutes': 45, 'started_at': '09:00',
    })

    response = client.get(f'/api/feed/weekly?end={END}')
    assert response.status_code == 200
    payload = response.get_json()

    assert payload['range'] == {'start': '2026-09-14', 'end': END}
    assert len(payload['days']) == 7
    logged = next(day for day in payload['days'] if day['date'] == '2026-09-18')
    unlogged = next(day for day in payload['days'] if day['date'] == '2026-09-17')
    assert logged['calories'] == 330
    assert logged['protein_g'] == 62
    assert logged['sleep_minutes'] == 480
    assert logged['steps'] == 7500
    assert payload['totals']['study_minutes'] == 45
    assert unlogged['calories'] is None
    assert unlogged['sleep_minutes'] is None


def test_journal_draft_never_calls_an_unconfigured_assistant(client, monkeypatch):
    register(client, username='journal-reader')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)

    response = client.post('/api/journal/summary', json={'date': END})

    assert response.status_code == 503
    assert 'not configured' in response.get_json()['error'].lower()


def test_feed_endpoints_require_login(client):
    assert client.get('/api/feed/weekly').status_code == 302
    assert client.post('/api/journal/summary', json={'date': END}).status_code == 302
