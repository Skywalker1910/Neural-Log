"""Tests for the demo data seeder.

The behaviour that actually matters is the safety rail: this script fabricates
history, and the obvious mistake is pointing it at a real account.
"""
import random

import pytest

from conftest import register
import scoring


@pytest.fixture()
def seeded(app_module, client):
    """A registered user plus the seeder module, sharing one temp database."""
    import importlib
    import sys

    register(client, username='demo')
    sys.modules.pop('seed_demo', None)
    sys.path.insert(0, str(app_module.PROJECT_ROOT / 'scripts'))
    seed_demo = importlib.import_module('seed_demo')
    # The script imports the app itself; point it at this test's module so both
    # sides share the temp database rather than opening the real one.
    seed_demo.neural_log = app_module

    conn = app_module.get_db_connection()
    user_row = conn.execute("SELECT * FROM users WHERE username = 'demo'").fetchone()
    yield seed_demo, conn, user_row
    conn.close()


def test_seeds_history_marked_as_seed(seeded):
    seed_demo, conn, user_row = seeded
    written = seed_demo.seed(conn, user_row, days=30, miss_rate=0.15, rng=random.Random(1))

    assert written > 0
    rows = conn.execute('SELECT source FROM daily_log WHERE user_id = ?',
                        (user_row['id'],)).fetchall()
    assert len(rows) == written
    assert all(row['source'] == 'seed' for row in rows), 'seeded days must be identifiable'


def test_seeded_days_are_not_all_perfect(seeded):
    """A seed where every day is 100% makes a dashboard look great and proves
    nothing - the variation is the point."""
    seed_demo, conn, user_row = seeded
    seed_demo.seed(conn, user_row, days=40, miss_rate=0.15, rng=random.Random(2))

    values = [row['completion_pct'] for row in conn.execute(
        'SELECT completion_pct FROM daily_log WHERE user_id = ?', (user_row['id'],))]
    assert len(set(values)) > 5, 'completion should vary day to day'
    assert min(values) < 80
    assert max(values) > min(values) + 20


def test_missed_days_leave_gaps(seeded):
    """Consistency and streaks have nothing to measure without gaps."""
    seed_demo, conn, user_row = seeded
    written = seed_demo.seed(conn, user_row, days=40, miss_rate=0.25, rng=random.Random(3))
    assert written < 40


def test_seeding_produces_scored_attributes(seeded):
    seed_demo, conn, user_row = seeded
    seed_demo.seed(conn, user_row, days=30, miss_rate=0.1, rng=random.Random(4))

    attributes = scoring.get_attributes(conn, user_row['id'])
    active = [a for a in attributes if a['status'] == 'active']
    assert len(active) >= 5
    # Self-reported checkbox data should not produce a wall of 100s.
    assert not all(a['score'] == 100 for a in active)


def test_clear_removes_only_seeded_days(seeded):
    """Real logged days must survive a --clear."""
    seed_demo, conn, user_row = seeded
    user_id = user_row['id']
    paths = seed_demo.neural_log.load_user_paths(user_row)
    items = seed_demo.neural_log.get_selected_path(paths)['checklist_items']

    scoring.record_day(conn, user_id, '2020-01-01', items, {}, source='checklist')
    conn.commit()
    seed_demo.seed(conn, user_row, days=20, miss_rate=0.1, rng=random.Random(5))

    removed = seed_demo.clear(conn, user_id)
    assert removed > 0

    remaining = conn.execute(
        'SELECT source FROM daily_log WHERE user_id = ?', (user_id,)).fetchall()
    assert [row['source'] for row in remaining] == ['checklist']
    # And nothing orphaned behind it.
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM activities WHERE user_id = ? "
        "AND activity_name = 'Daily Checklist'", (user_id,)).fetchone()['n'] == 0


def test_seed_is_reproducible_for_a_given_rng_seed(seeded):
    seed_demo, conn, user_row = seeded
    first = seed_demo.seed(conn, user_row, days=25, miss_rate=0.2, rng=random.Random(9))
    values_a = [r['completion_pct'] for r in conn.execute(
        'SELECT completion_pct FROM daily_log WHERE user_id = ? ORDER BY date',
        (user_row['id'],))]

    seed_demo.clear(conn, user_row['id'])
    second = seed_demo.seed(conn, user_row, days=25, miss_rate=0.2, rng=random.Random(9))
    values_b = [r['completion_pct'] for r in conn.execute(
        'SELECT completion_pct FROM daily_log WHERE user_id = ? ORDER BY date',
        (user_row['id'],))]

    assert first == second
    assert values_a == values_b
