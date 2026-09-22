import json
from types import SimpleNamespace

import pytest

from assistant import agent, config, usage
from conftest import register


END = '2026-09-20'
REPORT = {
    'title': 'A rhythm worth keeping', 'summary': 'Your recorded week has a starting point.',
    'strengths': [{'title': 'Showing up', 'body': 'You recorded a night of sleep.'}],
    'opportunities': [{'title': 'Complete the picture', 'body': 'More observations would help.'}],
    'next_steps': [{'title': 'Log a night', 'body': 'Add your next sleep entry.', 'workspace': 'lifestyle'}],
    'coverage_note': 'Missing days are unknown.',
}


class Provider:
    def __init__(self, text=None, status='completed'):
        self.text = json.dumps(REPORT) if text is None else text
        self.status = status
        self.requests = []
        self.responses = self

    def with_options(self, **options):
        assert options['timeout'] < 30
        assert options['max_retries'] == 0
        return self

    def create(self, **request):
        self.requests.append(request)
        if isinstance(self.text, Exception):
            raise self.text
        return SimpleNamespace(output_text=self.text, status=self.status, usage=None)


@pytest.fixture
def reader(client, monkeypatch):
    register(client, username='reader')
    monkeypatch.setattr(config, 'is_configured', lambda: True)
    client.post('/api/sleep', json={'date': '2026-09-18', 'duration_minutes': 480})
    return client


def provider(monkeypatch, **options):
    fake = Provider(**options)
    monkeypatch.setattr(agent, 'build_client', lambda: fake)
    return fake


def test_post_uses_structured_ai_and_saves_the_evidence(reader, app_module, monkeypatch):
    fake = provider(monkeypatch)
    reader.put('/api/lifestyle/2026-09-18', json={'journal': 'PRIVATE JOURNAL', 'steps': 1200})
    reader.post('/api/sleep', json={'date': '2026-09-11', 'duration_minutes': 420})
    response = reader.post('/api/feed/posts', json={'end': END})
    assert response.status_code == 201
    post = response.get_json()
    assert post['report'] == REPORT
    assert len(post['snapshot']['days']) == 7
    assert post['snapshot']['previous_days'][4]['sleep_minutes'] == 420
    request = fake.requests[0]
    assert request['text']['format']['strict'] is True
    assert request['store'] is False
    assert 'PRIVATE JOURNAL' not in request['input']
    assert 'previous_days' in request['input']
    conn = app_module.get_db_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM ai_usage WHERE feature = 'weekly_feed' AND ok = 1").fetchone()[0] == 1
    finally:
        conn.close()


def test_revisiting_post_reuses_saved_review_and_snapshot(reader, monkeypatch):
    fake = provider(monkeypatch)
    first = reader.post('/api/feed/posts', json={'end': END}).get_json()
    reader.post('/api/sleep', json={'date': '2026-09-18', 'duration_minutes': 500})
    again = reader.post('/api/feed/posts', json={'end': END})
    assert again.status_code == 200
    assert again.get_json() == first
    assert len(fake.requests) == 1
    assert reader.get('/api/feed/posts').get_json()['posts'] == [first]


def test_explicit_refresh_updates_same_post(reader, monkeypatch):
    fake = provider(monkeypatch)
    first = reader.post('/api/feed/posts', json={'end': END}).get_json()
    reader.post('/api/sleep', json={'date': '2026-09-18', 'duration_minutes': 500})
    updated = reader.post('/api/feed/posts', json={'end': END, 'refresh': True}).get_json()
    assert updated['id'] == first['id']
    assert updated['snapshot']['days'][4]['sleep_minutes'] == 500
    assert len(fake.requests) == 2


def test_failed_refresh_preserves_existing_post(reader, monkeypatch):
    provider(monkeypatch)
    first = reader.post('/api/feed/posts', json={'end': END}).get_json()
    provider(monkeypatch, text=RuntimeError('provider credentials must stay private'))
    failed = reader.post('/api/feed/posts', json={'end': END, 'refresh': True})
    assert failed.status_code == 503
    assert 'credentials' not in failed.get_data(as_text=True)
    assert reader.get('/api/feed/posts').get_json()['posts'] == [first]


@pytest.mark.parametrize('text,status', [('not json', 'completed'), ('{}', 'completed'), (json.dumps(REPORT), 'incomplete')])
def test_bad_provider_output_can_be_retried(reader, monkeypatch, text, status):
    provider(monkeypatch, text=text, status=status)
    assert reader.post('/api/feed/posts', json={'end': END}).status_code == 503
    assert reader.get('/api/feed/posts').get_json()['posts'] == []
    provider(monkeypatch)
    assert reader.post('/api/feed/posts', json={'end': END}).status_code == 201


def test_posts_and_journal_entries_are_private(reader, app_module, monkeypatch):
    provider(monkeypatch)
    reader.put('/api/lifestyle/2026-09-18', json={'journal': 'Private entry'})
    reader.post('/api/feed/posts', json={'end': END})
    stranger = app_module.app.test_client()
    register(stranger, username='stranger')
    assert stranger.get('/api/feed/posts').get_json()['posts'] == []
    assert stranger.get('/api/journal/entries').get_json()['entries'] == []
    assert stranger.post('/api/feed/posts', json={'end': END}).status_code == 422
    assert reader.get('/api/journal/entries').get_json()['entries'] == [{'date': '2026-09-18', 'journal': 'Private entry'}]


@pytest.mark.parametrize('data', [{}, [], {'end': 'no'}, {'end': '9999-12-26'}, {'end': '2026-09-18'}])
def test_invalid_week_is_rejected_before_provider(reader, monkeypatch, data):
    fake = provider(monkeypatch)
    assert reader.post('/api/feed/posts', json=data).status_code == 400
    assert not fake.requests


def test_budget_rate_and_configuration_guards(reader, monkeypatch):
    fake = provider(monkeypatch)
    monkeypatch.setattr(config, 'is_configured', lambda: False)
    assert reader.post('/api/feed/posts', json={'end': END}).status_code == 503
    monkeypatch.setattr(config, 'is_configured', lambda: True)
    monkeypatch.setattr(usage, 'check_budget', lambda *args: (False, 'Budget reached'))
    assert reader.post('/api/feed/posts', json={'end': END}).status_code == 429
    monkeypatch.setattr(usage, 'check_budget', lambda *args: (True, None))
    monkeypatch.setattr(usage, 'rate_limited', lambda *args: True)
    assert reader.post('/api/feed/posts', json={'end': END}).status_code == 429
    assert not fake.requests


def test_pending_generation_is_not_duplicated_and_expired_lease_recovers(reader, app_module, monkeypatch):
    fake = provider(monkeypatch)
    conn = app_module.get_db_connection()
    try:
        conn.execute('INSERT INTO weekly_posts (user_id, week_end) VALUES (1, ?)', (END,))
        conn.commit()
        assert reader.post('/api/feed/posts', json={'end': END}).status_code == 409
        assert not fake.requests
        conn.execute("UPDATE weekly_posts SET requested_at = datetime('now', '-5 minutes')")
        conn.commit()
    finally:
        conn.close()
    assert reader.post('/api/feed/posts', json={'end': END}).status_code == 201


def test_new_endpoints_require_login_and_csrf(client, raw_client):
    assert client.get('/api/feed/posts').status_code == 302
    assert client.get('/api/journal/entries').status_code == 302
    assert client.post('/api/feed/posts', json={'end': END}).status_code == 302
    assert raw_client.post('/api/feed/posts', json={'end': END}).status_code == 403
