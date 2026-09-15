"""Learning workspace endpoints.

Its own blueprint for the same reasons training_api.py and nutrition_api.py are:
app.py is long enough, and the auth helper, database helper and recompute
function are injected at registration so this module never imports app back.
"""
from datetime import date as _date, timedelta as _timedelta

from flask import Blueprint, jsonify, request, session

from scoring import producers
from scoring.config import DEFAULT_CONFIG

learning_bp = Blueprint('learning', __name__)

_get_db = None
_login_required = None
_recompute = None


def init_learning(app, get_db_connection, login_required, recompute):
    global _get_db, _login_required, _recompute
    _get_db = get_db_connection
    _login_required = login_required
    _recompute = recompute
    app.register_blueprint(learning_bp)


def _auth(view):
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _duration_from_clock(started_at, ended_at):
    """Minutes between two HH:MM times, assuming at most one midnight crossing."""
    start = producers._minutes_since_midnight(started_at)
    end = producers._minutes_since_midnight(ended_at)
    if start is None or end is None:
        return None
    return (end - start) % 1440 or None


def _owns(conn, table, row_id, user_id):
    if not row_id:
        return True  # nothing referenced is fine; unfiled topics are allowed
    row = conn.execute(
        f'SELECT 1 FROM {table} WHERE id = ? AND user_id = ?', (row_id, user_id)
    ).fetchone()
    return row is not None


# --- areas and topics -------------------------------------------------------

@learning_bp.route('/api/learning/areas', methods=['GET', 'POST'])
@_auth
def areas():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'POST':
        data = request.json or {}
        name = (data.get('name') or '').strip()
        if not name:
            conn.close()
            return jsonify({'error': 'name is required'}), 400

        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO learning_areas (user_id, name, accent, notes, '
            'weekly_target_minutes) VALUES (?, ?, ?, ?, ?)',
            (user_id, name, data.get('accent', 'learning'), data.get('notes'),
             data.get('weekly_target_minutes')),
        )
        conn.commit()
        row = conn.execute('SELECT * FROM learning_areas WHERE id = ?',
                           (cursor.lastrowid,)).fetchone()
        payload = dict(row)
        conn.close()
        return jsonify(payload), 201

    rows = conn.execute(
        '''
        SELECT a.*,
               COUNT(DISTINCT t.id) AS topic_count,
               COALESCE(SUM(s.duration_minutes), 0) AS total_minutes
        FROM learning_areas a
        LEFT JOIN learning_topics t ON t.area_id = a.id AND t.archived = 0
        LEFT JOIN learning_sessions s ON s.topic_id = t.id
        WHERE a.user_id = ? AND a.archived = 0
        GROUP BY a.id ORDER BY a.name
        ''',
        (user_id,),
    ).fetchall()
    conn.close()
    return jsonify({'areas': [dict(row) for row in rows]})


@learning_bp.route('/api/learning/areas/<int:area_id>', methods=['PUT', 'DELETE'])
@_auth
def area_detail(area_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM learning_areas WHERE id = ? AND user_id = ?',
                       (area_id, user_id)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if request.method == 'DELETE':
        # Archived, not deleted: topics point at it and their sessions are
        # history. Unfiling the topics would lose which area the work belonged to.
        conn.execute('UPDATE learning_areas SET archived = 1 WHERE id = ?', (area_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    data = request.json or {}
    conn.execute(
        'UPDATE learning_areas SET name = ?, accent = ?, notes = ?, '
        'weekly_target_minutes = ? WHERE id = ?',
        (data.get('name', row['name']), data.get('accent', row['accent']),
         data.get('notes', row['notes']),
         data.get('weekly_target_minutes', row['weekly_target_minutes']), area_id),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM learning_areas WHERE id = ?', (area_id,)).fetchone()
    payload = dict(row)
    conn.close()
    return jsonify(payload)


@learning_bp.route('/api/learning/topics', methods=['GET', 'POST'])
@_auth
def topics():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'POST':
        data = request.json or {}
        name = (data.get('name') or '').strip()
        if not name:
            conn.close()
            return jsonify({'error': 'name is required'}), 400

        area_id = data.get('area_id')
        if not _owns(conn, 'learning_areas', area_id, user_id):
            conn.close()
            return jsonify({'error': 'unknown area'}), 404

        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO learning_topics (user_id, area_id, name, notes, status) '
            'VALUES (?, ?, ?, ?, ?)',
            (user_id, area_id, name, data.get('notes'), data.get('status', 'active')),
        )
        conn.commit()
        row = conn.execute('SELECT * FROM learning_topics WHERE id = ?',
                           (cursor.lastrowid,)).fetchone()
        payload = dict(row)
        conn.close()
        return jsonify(payload), 201

    rows = conn.execute(
        '''
        SELECT t.*, a.name AS area_name, a.accent AS area_accent,
               COUNT(s.id) AS session_count,
               COALESCE(SUM(s.duration_minutes), 0) AS total_minutes,
               MAX(s.date) AS last_studied
        FROM learning_topics t
        LEFT JOIN learning_areas a ON a.id = t.area_id
        LEFT JOIN learning_sessions s ON s.topic_id = t.id
        WHERE t.user_id = ? AND t.archived = 0
        GROUP BY t.id ORDER BY t.status, t.name
        ''',
        (user_id,),
    ).fetchall()
    conn.close()
    return jsonify({'topics': [dict(row) for row in rows]})


@learning_bp.route('/api/learning/topics/<int:topic_id>', methods=['PUT', 'DELETE'])
@_auth
def topic_detail(topic_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM learning_topics WHERE id = ? AND user_id = ?',
                       (topic_id, user_id)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if request.method == 'DELETE':
        conn.execute('UPDATE learning_topics SET archived = 1 WHERE id = ?', (topic_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    data = request.json or {}
    area_id = data.get('area_id', row['area_id'])
    if not _owns(conn, 'learning_areas', area_id, user_id):
        conn.close()
        return jsonify({'error': 'unknown area'}), 404

    conn.execute(
        'UPDATE learning_topics SET name = ?, area_id = ?, notes = ?, status = ? '
        'WHERE id = ?',
        (data.get('name', row['name']), area_id, data.get('notes', row['notes']),
         data.get('status', row['status']), topic_id),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM learning_topics WHERE id = ?', (topic_id,)).fetchone()
    payload = dict(row)
    conn.close()
    return jsonify(payload)


# --- sessions ---------------------------------------------------------------

@learning_bp.route('/api/learning/sessions', methods=['GET', 'POST'])
@_auth
def sessions():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'POST':
        data = request.json or {}
        day = (data.get('date') or '').strip()
        if not day:
            conn.close()
            return jsonify({'error': 'date is required'}), 400

        topic_id = data.get('topic_id')
        if not _owns(conn, 'learning_topics', topic_id, user_id):
            conn.close()
            return jsonify({'error': 'unknown topic'}), 404

        duration = data.get('duration_minutes')
        if duration is None:
            duration = _duration_from_clock(data.get('started_at'), data.get('ended_at'))
        if not duration or int(duration) <= 0:
            conn.close()
            return jsonify({
                'error': 'duration_minutes, or a start and end time, are required',
            }), 400

        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO learning_sessions (user_id, date, topic_id, started_at, '
            'ended_at, duration_minutes, focus_rating, difficulty, notes) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (user_id, day, topic_id, data.get('started_at'), data.get('ended_at'),
             int(duration), data.get('focus_rating'), data.get('difficulty'),
             data.get('notes')),
        )
        conn.commit()
        _recompute(conn, user_id, day)
        conn.commit()
        row = conn.execute('SELECT * FROM learning_sessions WHERE id = ?',
                           (cursor.lastrowid,)).fetchone()
        payload = dict(row)
        conn.close()
        return jsonify(payload), 201

    limit = min(int(request.args.get('limit', 50)), 200)
    rows = conn.execute(
        '''
        SELECT s.*, t.name AS topic_name, a.name AS area_name, a.accent AS area_accent
        FROM learning_sessions s
        LEFT JOIN learning_topics t ON t.id = s.topic_id
        LEFT JOIN learning_areas a ON a.id = t.area_id
        WHERE s.user_id = ?
        ORDER BY s.date DESC, s.started_at DESC, s.id DESC
        LIMIT ?
        ''',
        (user_id, limit),
    ).fetchall()
    conn.close()
    return jsonify({'sessions': [dict(row) for row in rows]})


@learning_bp.route('/api/learning/sessions/<int:session_id>', methods=['PUT', 'DELETE'])
@_auth
def session_detail(session_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM learning_sessions WHERE id = ? AND user_id = ?',
                       (session_id, user_id)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if request.method == 'DELETE':
        conn.execute('DELETE FROM learning_sessions WHERE id = ?', (session_id,))
    else:
        data = request.json or {}
        duration = data.get('duration_minutes', row['duration_minutes'])
        conn.execute(
            'UPDATE learning_sessions SET topic_id = ?, started_at = ?, ended_at = ?, '
            'duration_minutes = ?, focus_rating = ?, difficulty = ?, notes = ? '
            'WHERE id = ?',
            (data.get('topic_id', row['topic_id']),
             data.get('started_at', row['started_at']),
             data.get('ended_at', row['ended_at']), int(duration),
             data.get('focus_rating', row['focus_rating']),
             data.get('difficulty', row['difficulty']),
             data.get('notes', row['notes']), session_id),
        )

    conn.commit()
    _recompute(conn, user_id, row['date'])
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# --- the dashboard ----------------------------------------------------------

def _streak(dates, today):
    """Consecutive days studied, ending today or yesterday.

    Allowing yesterday matters: at 09:00 you have not studied today yet, and a
    counter that reset overnight would tell you you had lost a three-week streak
    every single morning.
    """
    studied = set(dates)
    if not studied:
        return 0

    cursor = today if today.isoformat() in studied else today - _timedelta(days=1)
    if cursor.isoformat() not in studied:
        return 0

    count = 0
    while cursor.isoformat() in studied:
        count += 1
        cursor -= _timedelta(days=1)
    return count


@learning_bp.route('/api/learning')
@_auth
def learning_summary():
    """Everything the Learning dashboard needs, in one response."""
    user_id = session.get('user_id')
    conn = _get_db()
    days = min(int(request.args.get('days', 30)), 365)

    today = _date.today()
    since = (today - _timedelta(days=days - 1)).isoformat()

    all_sessions = conn.execute(
        'SELECT date, duration_minutes, started_at FROM learning_sessions '
        'WHERE user_id = ? ORDER BY date',
        (user_id,),
    ).fetchall()
    session_rows = [dict(row) for row in all_sessions]

    recent = conn.execute(
        '''
        SELECT s.*, t.name AS topic_name, a.name AS area_name, a.accent AS area_accent
        FROM learning_sessions s
        LEFT JOIN learning_topics t ON t.id = s.topic_id
        LEFT JOIN learning_areas a ON a.id = t.area_id
        WHERE s.user_id = ?
        ORDER BY s.date DESC, s.id DESC LIMIT 10
        ''',
        (user_id,),
    ).fetchall()

    by_day = conn.execute(
        'SELECT date, SUM(duration_minutes) AS minutes, COUNT(*) AS sessions '
        'FROM learning_sessions WHERE user_id = ? AND date >= ? '
        'GROUP BY date ORDER BY date',
        (user_id, since),
    ).fetchall()

    # Topic distribution: where the hours actually went. Unfiled work is reported
    # as its own bucket rather than dropped, or the percentages would not add up.
    by_topic = conn.execute(
        '''
        SELECT COALESCE(t.name, 'Unfiled') AS topic,
               COALESCE(a.name, '') AS area,
               COALESCE(a.accent, 'learning') AS accent,
               SUM(s.duration_minutes) AS minutes,
               COUNT(*) AS sessions
        FROM learning_sessions s
        LEFT JOIN learning_topics t ON t.id = s.topic_id
        LEFT JOIN learning_areas a ON a.id = t.area_id
        WHERE s.user_id = ? AND s.date >= ?
        GROUP BY t.id ORDER BY minutes DESC
        ''',
        (user_id, since),
    ).fetchall()

    profile = conn.execute('SELECT weekly_study_minutes FROM user_profile '
                           'WHERE user_id = ?', (user_id,)).fetchone()
    weekly_target = (profile['weekly_study_minutes'] if profile
                     and profile['weekly_study_minutes']
                     else DEFAULT_CONFIG.weekly_study_minutes)

    week_start = (today - _timedelta(days=6)).isoformat()
    this_week = sum(row['duration_minutes'] for row in session_rows
                    if row['date'] >= week_start)

    # Depth is reported as the same number the scorer uses rather than a second
    # definition of it - two ways to compute "how deep was your work" would
    # eventually disagree.
    depth_ratio = None
    if session_rows:
        computed = producers.learning_ratios(
            session_rows, [today.isoformat()], {today.isoformat(): weekly_target},
        )
        entry = computed.get(today.isoformat(), {}).get('Focus')
        depth_ratio = round(entry[0] * 100) if entry else None

    conn.close()
    return jsonify({
        'recent': [dict(row) for row in recent],
        'by_day': [dict(row) for row in by_day],
        'by_topic': [dict(row) for row in by_topic],
        'totals': {
            'sessions': len(session_rows),
            'minutes': sum(row['duration_minutes'] for row in session_rows),
            'this_week_minutes': this_week,
            'weekly_target_minutes': weekly_target,
            'streak_days': _streak([row['date'] for row in session_rows], today),
            'depth_pct': depth_ratio,
            'target_block_minutes': DEFAULT_CONFIG.focus_target_block_minutes,
        },
    })
