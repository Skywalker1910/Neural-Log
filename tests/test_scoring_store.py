"""Tests for persisting scored days and the derived attribute time series.

The behaviour that matters most here is that history is *materialised* rather
than recomputed from live Path templates - see docs/SCORING.md.
"""
from datetime import date, timedelta

import pytest

import scoring

START = date(2026, 9, 1)


@pytest.fixture()
def db(app_module):
    """A connection with one user, on an isolated per-test database."""
    conn = app_module.get_db_connection()
    conn.execute("INSERT INTO users (username, password_hash) VALUES ('demo', 'x')")
    conn.commit()
    user_id = conn.execute(
        "SELECT id FROM users WHERE username = 'demo'"
    ).fetchone()['id']
    yield conn, user_id, app_module
    conn.close()


def _items(app_module):
    return [p for p in app_module.build_default_paths()
            if p['id'] == 'batman-path'][0]['checklist_items']


def _answers(items, yes=True, wake=0):
    out = {}
    for item in items:
        if item['type'] == 'time':
            out[item['name']] = item['options'][wake]
        elif item['type'] == 'yes-no':
            out[item['name']] = 'Yes' if yes else 'No'
    return out


def _log_days(conn, user_id, items, count, yes=True, start=START):
    for offset in range(count):
        day = (start + timedelta(days=offset)).isoformat()
        scoring.record_day(conn, user_id, day, items, _answers(items, yes=yes),
                           path_id='batman-path', path_name='Batman Path')
    conn.commit()
    scoring.recompute_scores(conn, user_id)
    conn.commit()


# --- recording ---------------------------------------------------------------

def test_record_day_writes_one_row_and_snapshots_items(db):
    conn, user_id, app_module = db
    items = _items(app_module)
    scoring.record_day(conn, user_id, '2026-09-01', items, _answers(items))
    conn.commit()

    row = conn.execute('SELECT * FROM daily_log WHERE user_id = ?', (user_id,)).fetchone()
    assert row['date'] == '2026-09-01'
    assert row['completion_pct'] == 100
    assert row['items_total'] > 0

    import json
    payload = json.loads(row['payload_json'])
    assert len(payload['items']) == row['items_total']
    # The snapshot carries the weights/icons as they were, so later scoring never
    # depends on the mutable live Path file.
    assert all('weight' in i and 'credit' in i for i in payload['items'])


def test_resubmitting_a_day_replaces_rather_than_duplicates(db):
    conn, user_id, app_module = db
    items = _items(app_module)

    scoring.record_day(conn, user_id, '2026-09-01', items, _answers(items, yes=True))
    scoring.record_day(conn, user_id, '2026-09-01', items, _answers(items, yes=False))
    conn.commit()

    rows = conn.execute('SELECT * FROM daily_log WHERE user_id = ?', (user_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]['completion_pct'] < 50  # the corrected, worse day won


def test_snapshot_survives_the_path_changing_afterwards(db):
    """The whole point of snapshotting: editing a Path must not rewrite history."""
    conn, user_id, app_module = db
    items = _items(app_module)
    scoring.record_day(conn, user_id, '2026-09-01', items, _answers(items))
    conn.commit()

    before = conn.execute(
        'SELECT weight_total FROM daily_log WHERE user_id = ?', (user_id,)
    ).fetchone()['weight_total']

    # Mutate the "live" template the way the Path editor would.
    for item in items:
        item['weight'] = 5

    scoring.recompute_scores(conn, user_id)
    conn.commit()

    after = conn.execute(
        'SELECT weight_total FROM daily_log WHERE user_id = ?', (user_id,)
    ).fetchone()['weight_total']
    assert after == before


# --- derived scores ----------------------------------------------------------

def test_scores_are_materialised_per_day(db):
    conn, user_id, app_module = db
    _log_days(conn, user_id, _items(app_module), 6)

    dates = [r['date'] for r in conn.execute(
        'SELECT DISTINCT date FROM attribute_scores WHERE user_id = ? ORDER BY date',
        (user_id,))]
    assert len(dates) == 6  # a row set per day, not just a current snapshot


def test_early_days_are_calibrating_not_zero(db):
    """Cold start must not look like failure - an unscored attribute has no
    number rather than a zero."""
    conn, user_id, app_module = db
    _log_days(conn, user_id, _items(app_module), 2)

    rows = conn.execute(
        "SELECT * FROM attribute_scores WHERE user_id = ? AND attribute = 'Discipline' "
        "ORDER BY date", (user_id,)).fetchall()
    assert [r['status'] for r in rows] == ['calibrating', 'calibrating']
    assert all(r['score'] is None for r in rows)


def test_attribute_with_no_signal_is_unobserved_not_zero(db):
    """Agility stopped being locked when R3 added mobility work. With a Path
    containing no mobility and no logged training it is now 'unobserved' -
    still no number, but for a different and more accurate reason.
    """
    conn, user_id, app_module = db
    _log_days(conn, user_id, _items(app_module), 5)

    row = conn.execute(
        "SELECT * FROM attribute_scores WHERE user_id = ? AND attribute = 'Agility' "
        "ORDER BY date DESC LIMIT 1", (user_id,)).fetchone()
    assert row['status'] == 'unobserved'
    assert row['score'] is None


def test_history_is_preserved_for_past_dates(db):
    """The requirement: answer 'what was my Discipline back then'."""
    conn, user_id, app_module = db
    items = _items(app_module)

    # Five weak days, then five strong ones.
    for offset in range(5):
        day = (START + timedelta(days=offset)).isoformat()
        scoring.record_day(conn, user_id, day, items, _answers(items, yes=False))
    for offset in range(5, 10):
        day = (START + timedelta(days=offset)).isoformat()
        scoring.record_day(conn, user_id, day, items, _answers(items, yes=True))
    conn.commit()
    scoring.recompute_scores(conn, user_id)
    conn.commit()

    series = scoring.get_attribute_history(conn, user_id, 'Knowledge', limit=30)
    early = next(s for s in series if s['status'] == 'active')
    latest = series[-1]
    assert latest['score'] > early['score']  # improvement is visible in the series


def test_get_attributes_returns_stable_axis_order(db):
    """A radar whose axes reorder between renders is unreadable."""
    conn, user_id, app_module = db
    _log_days(conn, user_id, _items(app_module), 5)

    names = [a['attribute'] for a in scoring.get_attributes(conn, user_id)]
    assert names == [a for a in scoring.ATTRIBUTES if a in names]


def test_daily_score_ignores_components_without_a_number(db):
    """Consistency is calibrating on day one; the composite must renormalise
    rather than treat the missing component as zero."""
    conn, user_id, app_module = db
    _log_days(conn, user_id, _items(app_module), 1)

    row = conn.execute(
        'SELECT * FROM daily_scores WHERE user_id = ?', (user_id,)).fetchone()
    assert row['daily_score'] == row['completion_pct'] == 100


def test_recompute_is_idempotent(db):
    conn, user_id, app_module = db
    _log_days(conn, user_id, _items(app_module), 5)

    before = [dict(r) for r in conn.execute(
        'SELECT date, attribute, score FROM attribute_scores WHERE user_id = ? '
        'ORDER BY date, attribute', (user_id,))]
    scoring.recompute_scores(conn, user_id)
    conn.commit()
    after = [dict(r) for r in conn.execute(
        'SELECT date, attribute, score FROM attribute_scores WHERE user_id = ? '
        'ORDER BY date, attribute', (user_id,))]
    assert before == after


def test_recompute_with_no_history_is_a_noop(db):
    conn, user_id, _ = db
    assert scoring.recompute_scores(conn, user_id) == 0


def test_engine_version_is_stamped(db):
    """Without it, a weight change silently rewrites history with no record."""
    conn, user_id, app_module = db
    _log_days(conn, user_id, _items(app_module), 4)

    for table in ('daily_log', 'attribute_scores', 'daily_scores'):
        row = conn.execute(
            f'SELECT engine_version FROM {table} WHERE user_id = ? LIMIT 1',
            (user_id,)).fetchone()
        assert row['engine_version'] == scoring.ENGINE_VERSION
