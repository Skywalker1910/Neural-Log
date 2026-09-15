"""Tests for the Learning workspace endpoints."""
from datetime import date, timedelta

import pytest

from conftest import register

TODAY = date.today()


@pytest.fixture()
def student(client):
    register(client, username='student')
    return client


def _iso(offset=0):
    return (TODAY - timedelta(days=offset)).isoformat()


def _area(client, name='Computer Science'):
    return client.post('/api/learning/areas', json={'name': name}).get_json()


def _topic(client, name='Distributed Systems', area_id=None):
    return client.post('/api/learning/topics',
                       json={'name': name, 'area_id': area_id}).get_json()


def _log(client, offset=0, minutes=60, topic_id=None, start=None, end=None):
    return client.post('/api/learning/sessions', json={
        'date': _iso(offset), 'duration_minutes': minutes, 'topic_id': topic_id,
        'started_at': start, 'ended_at': end,
    })


# --- areas and topics -------------------------------------------------------

def test_an_area_holds_topics(student):
    area = _area(student)
    _topic(student, 'Consensus', area['id'])
    _topic(student, 'Replication', area['id'])

    areas = student.get('/api/learning/areas').get_json()['areas']
    assert areas[0]['topic_count'] == 2


def test_a_topic_can_be_unfiled(student):
    """Studying something you have not organised yet still has to count."""
    topic = _topic(student, 'Something new', None)
    assert topic['area_id'] is None
    _log(student, topic_id=topic['id'])

    summary = student.get('/api/learning').get_json()
    assert summary['totals']['minutes'] == 60


def test_a_session_can_have_no_topic_at_all(student):
    assert _log(student).status_code == 201
    summary = student.get('/api/learning').get_json()
    assert summary['totals']['minutes'] == 60
    assert summary['by_topic'][0]['topic'] == 'Unfiled'


def test_archiving_an_area_keeps_the_sessions_studied_under_it(student):
    area = _area(student)
    topic = _topic(student, 'Consensus', area['id'])
    _log(student, topic_id=topic['id'], minutes=90)

    assert student.delete(f"/api/learning/areas/{area['id']}").status_code == 200
    assert student.get('/api/learning/areas').get_json()['areas'] == []

    summary = student.get('/api/learning').get_json()
    assert summary['totals']['minutes'] == 90, 'the hours studied are history'


def test_areas_and_topics_are_scoped_to_their_owner(student, client):
    area = _area(student)
    topic = _topic(student, 'Consensus', area['id'])
    student.get('/logout')

    register(client, username='someone-else')
    assert client.get('/api/learning/areas').get_json()['areas'] == []
    assert client.put(f"/api/learning/areas/{area['id']}",
                      json={'name': 'mine'}).status_code == 404
    assert client.put(f"/api/learning/topics/{topic['id']}",
                      json={'name': 'mine'}).status_code == 404


def test_you_cannot_file_a_topic_under_someone_elses_area(student, client):
    area = _area(student)
    student.get('/logout')

    register(client, username='intruder')
    response = client.post('/api/learning/topics',
                           json={'name': 'Mine', 'area_id': area['id']})
    assert response.status_code == 404


def test_you_cannot_log_against_someone_elses_topic(student, client):
    topic = _topic(student)
    student.get('/logout')

    register(client, username='intruder')
    response = client.post('/api/learning/sessions', json={
        'date': _iso(), 'duration_minutes': 60, 'topic_id': topic['id'],
    })
    assert response.status_code == 404


def test_naming_is_required(student):
    assert student.post('/api/learning/areas', json={}).status_code == 400
    assert student.post('/api/learning/topics', json={'name': '  '}).status_code == 400


# --- sessions ---------------------------------------------------------------

def test_duration_is_derived_from_the_clock_when_not_given(student):
    student.post('/api/learning/sessions', json={
        'date': _iso(), 'started_at': '09:00', 'ended_at': '10:45',
    })
    sessions = student.get('/api/learning/sessions').get_json()['sessions']
    assert sessions[0]['duration_minutes'] == 105


def test_a_session_crossing_midnight_is_not_negative(student):
    student.post('/api/learning/sessions', json={
        'date': _iso(), 'started_at': '23:30', 'ended_at': '01:00',
    })
    sessions = student.get('/api/learning/sessions').get_json()['sessions']
    assert sessions[0]['duration_minutes'] == 90


def test_a_session_needs_a_duration_or_a_clock(student):
    assert student.post('/api/learning/sessions',
                        json={'date': _iso()}).status_code == 400
    assert student.post('/api/learning/sessions', json={}).status_code == 400


def test_several_sessions_a_day_are_all_kept(student):
    """Unlike sleep, a second session today is a second session, not a
    correction - and the shape of those sessions is the point."""
    _log(student, minutes=45, start='09:00', end='09:45')
    _log(student, minutes=45, start='14:00', end='14:45')

    sessions = student.get('/api/learning/sessions').get_json()['sessions']
    assert len(sessions) == 2


def test_deleting_a_session_removes_its_minutes(student):
    _log(student, minutes=60)
    session_id = student.get('/api/learning/sessions').get_json()['sessions'][0]['id']

    student.delete(f'/api/learning/sessions/{session_id}')
    assert student.get('/api/learning').get_json()['totals']['minutes'] == 0


# --- the dashboard ----------------------------------------------------------

def test_summary_reports_topic_distribution(student):
    area = _area(student)
    consensus = _topic(student, 'Consensus', area['id'])
    replication = _topic(student, 'Replication', area['id'])

    _log(student, topic_id=consensus['id'], minutes=120)
    _log(student, topic_id=replication['id'], minutes=30)

    by_topic = student.get('/api/learning').get_json()['by_topic']
    assert by_topic[0]['topic'] == 'Consensus'
    assert by_topic[0]['minutes'] == 120
    assert by_topic[1]['minutes'] == 30


def test_summary_for_a_new_user_is_empty_not_broken(student):
    summary = student.get('/api/learning').get_json()
    assert summary['totals']['minutes'] == 0
    assert summary['totals']['streak_days'] == 0
    assert summary['totals']['depth_pct'] is None
    assert summary['by_topic'] == []


def test_a_streak_counts_consecutive_days(student):
    for offset in range(4):
        _log(student, offset=offset, minutes=30)
    assert student.get('/api/learning').get_json()['totals']['streak_days'] == 4


def test_a_streak_survives_not_having_studied_yet_today(student):
    """At 09:00 you have not studied today. A counter that reset overnight would
    report a lost streak every single morning."""
    for offset in range(1, 4):
        _log(student, offset=offset, minutes=30)
    assert student.get('/api/learning').get_json()['totals']['streak_days'] == 3


def test_a_streak_breaks_on_a_real_gap(student):
    _log(student, offset=0, minutes=30)
    _log(student, offset=3, minutes=30)
    assert student.get('/api/learning').get_json()['totals']['streak_days'] == 1


def test_studying_moves_knowledge_and_focus_off_unobserved(student):
    """Both ran on checklist data alone before R5."""
    before = student.get('/api/attributes').get_json()['attributes']
    assert all(a['status'] in ('unobserved', 'locked') for a in before)

    for offset in range(5):
        _log(student, offset=offset, minutes=75, start='09:00', end='10:15')

    after = student.get('/api/attributes').get_json()['attributes']
    knowledge = next(a for a in after if a['attribute'] == 'Knowledge')
    focus = next(a for a in after if a['attribute'] == 'Focus')

    assert knowledge['status'] == 'active'
    assert focus['status'] == 'active'
    assert focus['score'] is not None


def test_the_dashboard_depth_matches_the_scorer(student):
    """Two definitions of "how deep was your work" would eventually disagree."""
    for offset in range(3):
        _log(student, offset=offset, minutes=90, start='09:00', end='10:30')

    depth = student.get('/api/learning').get_json()['totals']['depth_pct']
    assert depth == 100

    attributes = student.get('/api/attributes').get_json()['attributes']
    focus = next(a for a in attributes if a['attribute'] == 'Focus')
    assert focus['score'] is not None


def test_fragmented_study_scores_lower_depth_than_one_long_block(student, client):
    for offset in range(3):
        _log(student, offset=offset, minutes=120, start='09:00', end='11:00')
    deep = student.get('/api/learning').get_json()['totals']['depth_pct']
    student.get('/logout')

    register(client, username='fragmented')
    for offset in range(3):
        for hour in (9, 12, 15, 18):
            client.post('/api/learning/sessions', json={
                'date': _iso(offset), 'duration_minutes': 30,
                'started_at': f'{hour:02d}:00', 'ended_at': f'{hour:02d}:30',
            })
    shallow = client.get('/api/learning').get_json()['totals']['depth_pct']

    assert deep > shallow, 'the same total shaped differently must not score the same'


def test_learning_endpoints_require_login(client):
    for url in ('/api/learning', '/api/learning/areas', '/api/learning/topics',
                '/api/learning/sessions'):
        assert client.get(url).status_code == 302
