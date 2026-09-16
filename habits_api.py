"""Habit endpoints - schedules, stats and what is due today.

Separate from the legacy /api/paths surface on purpose. Those endpoints are a
compatibility view kept in the shape three different clients already expect, and
bolting schedule editing onto them would drag that shape somewhere it was never
designed to go. These are the new ones, free to be shaped around habits.
"""
import json
from datetime import date as _date

from flask import Blueprint, jsonify, request, session

import habits as habits_store

habits_bp = Blueprint('habits', __name__)

_get_db = None
_login_required = None


def init_habits(app, get_db_connection, login_required):
    global _get_db, _login_required
    _get_db = get_db_connection
    _login_required = login_required
    app.register_blueprint(habits_bp)


def _auth(view):
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


@habits_bp.route('/api/habits')
@_auth
def list_habits():
    """Habits with their adherence and streak over a window.

    Scoped to the path you are actually following unless `all=1`. The four stock
    paths share most of their items, so the unscoped list repeats "What time did
    you wake up?" once per path.
    """
    user_id = session.get('user_id')
    days = min(int(request.args.get('days', 30)), 365)
    only_selected = request.args.get('all') not in ('1', 'true')

    conn = _get_db()
    stats = habits_store.habit_stats(conn, user_id, days=days,
                                     only_selected=only_selected)
    conn.close()
    return jsonify({
        'habits': stats,
        'window_days': days,
        'scope': 'selected' if only_selected else 'all',
    })


@habits_bp.route('/api/habits/due')
@_auth
def habits_due():
    """What is expected today, with today's answer where there is one.

    `times-per-week` habits always appear - they have no particular day - so the
    weekly counts ride alongside, which is what actually answers "am I behind on
    this one".
    """
    user_id = session.get('user_id')
    on_date = request.args.get('date') or _date.today().isoformat()
    try:
        parsed = _date.fromisoformat(on_date)
    except ValueError:
        return jsonify({'error': 'invalid date'}), 400

    conn = _get_db()
    due = habits_store.due_habits(conn, user_id, parsed)
    weekly = habits_store.weekly_progress(conn, user_id, parsed)
    conn.close()

    return jsonify({
        'date': on_date,
        'habits': [
            {
                'id': row['id'],
                'slug': row['slug'],
                'name': row['name'],
                'type': row['type'],
                'icon': row['icon'],
                'weight': row['weight'],
                'options': row['options'],
                'schedule_type': row['schedule_type'],
                'schedule_days': row['schedule_days'],
                'target_per_week': row['target_per_week'],
                'response': row['response'],
                'credit': row['credit'],
            }
            for row in due
        ],
        'weekly': weekly,
    })


@habits_bp.route('/api/habits/<int:habit_id>', methods=['PUT'])
@_auth
def update_habit(habit_id):
    """Edit a habit's schedule, name or weight.

    Deliberately narrow: this does not create or delete habits. Those still go
    through the paths endpoints, because a habit's existence is tied to the group
    it lives in and splitting that across two APIs is how they drift apart.
    """
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM habits WHERE id = ?', (habit_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    # A core question belongs to everyone. Letting one person reschedule it would
    # silently reschedule it for all five accounts, so it is refused here; the
    # survey endpoints are where changing it for everyone is the stated intent.
    if row['is_core']:
        conn.close()
        return jsonify({
            'error': 'That question is part of the shared survey. Only an admin '
                     'can change it, and the change applies to everyone.'
        }), 403

    if row['user_id'] != user_id:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    data = request.json or {}
    schedule_type = data.get('schedule_type', row['schedule_type'])
    if schedule_type not in habits_store.SCHEDULE_TYPES:
        schedule_type = row['schedule_type']

    days = data.get('schedule_days')
    if days is None:
        schedule_days = row['schedule_days']
    else:
        # Keep only real weekday indices, so a malformed list cannot make a habit
        # permanently undue.
        cleaned = sorted({int(d) for d in days if isinstance(d, int) and 0 <= d <= 6})
        schedule_days = json.dumps(cleaned)

    target = data.get('target_per_week', row['target_per_week'])
    if schedule_type != 'times-per-week':
        target = None

    conn.execute(
        'UPDATE habits SET name = ?, weight = ?, icon = ?, schedule_type = ?, '
        'schedule_days = ?, target_per_week = ? WHERE id = ?',
        (str(data.get('name', row['name'])).strip() or row['name'],
         int(data.get('weight', row['weight'])), data.get('icon', row['icon']),
         schedule_type, schedule_days, target, habit_id),
    )
    conn.commit()

    updated = conn.execute('SELECT * FROM habits WHERE id = ?', (habit_id,)).fetchone()
    payload = dict(updated)
    conn.close()
    return jsonify(payload)
