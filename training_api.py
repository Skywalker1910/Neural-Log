"""Training workspace endpoints.

Split into its own module rather than piled onto app.py, which is already ~1950
lines. Registered as a blueprint from app.py; the auth decorator and database
helper are injected at registration time so this module never imports app - the
test suite swaps modules per test, and importing app here would bind to whichever
copy happened to be loaded first.
"""
import json

from flask import Blueprint, jsonify, request, session

import scoring

training = Blueprint('training', __name__)

# Injected by init_training(); see the note above about not importing app.
_get_db = None
_login_required = None
_recompute = None


def init_training(app, get_db_connection, login_required, recompute):
    global _get_db, _login_required, _recompute
    _get_db = get_db_connection
    _login_required = login_required
    # R7: saving a workout now moves XP as well as the attribute scores.
    _recompute = recompute
    app.register_blueprint(training)


def _auth(view):
    """Defers to the app's login_required, which is injected after import."""
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _json_list(value):
    try:
        parsed = json.loads(value or '[]')
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _exercise_row(row):
    return {
        'id': row['id'],
        'slug': row['slug'],
        'name': row['name'],
        'primary_muscle': row['primary_muscle'],
        'secondary_muscles': _json_list(row['secondary_muscles']),
        'equipment': row['equipment'],
        'category': row['category'],
        'difficulty': row['difficulty'],
        'is_compound': bool(row['is_compound']),
        'instructions': _json_list(row['instructions']),
        # Which of the seventeen movement shapes this is, so the UI can animate
        # it. Keyed to the movement rather than the exercise: a barbell, dumbbell
        # and machine chest press are one movement done three ways.
        'movement_pattern': row['movement_pattern'] if 'movement_pattern' in row.keys() else None,
        'is_custom': row['user_id'] is not None,
    }


@training.route('/api/exercises')
@_auth
def list_exercises():
    """The library plus the user's own exercises.

    Archived rows are excluded: they are exercises dropped from a later version
    of the library, kept only so historical sets still resolve.
    """
    user_id = session.get('user_id')
    conn = _get_db()

    clauses = ['(user_id IS NULL OR user_id = ?)', 'archived = 0']
    params = [user_id]

    for field, column in (('muscle', 'primary_muscle'), ('category', 'category'),
                          ('equipment', 'equipment')):
        value = request.args.get(field)
        if value:
            clauses.append(f'{column} = ?')
            params.append(value)

    search = (request.args.get('q') or '').strip()
    if search:
        clauses.append('LOWER(name) LIKE ?')
        params.append(f'%{search.lower()}%')

    rows = conn.execute(
        f'SELECT * FROM exercises WHERE {" AND ".join(clauses)} '
        f'ORDER BY primary_muscle, name',
        params,
    ).fetchall()
    conn.close()

    return jsonify({'exercises': [_exercise_row(row) for row in rows]})


@training.route('/api/exercises/<int:exercise_id>/history')
@_auth
def exercise_history(exercise_id):
    """Previous performance and the best set, for the logging screen.

    "Last time: 80kg x 8" is the single most useful thing a training app can put
    in front of someone mid-session, so it gets its own endpoint rather than
    being derived client-side from the full history.
    """
    user_id = session.get('user_id')
    conn = _get_db()

    # The session you are editing must not quote itself back at you as "last
    # time" - the useful comparison is always what you did *before* today. The
    # logging screen passes its own id here; a fresh session has nothing to skip.
    exclude = request.args.get('exclude_session', type=int)
    skip = ' AND s.id != ?' if exclude else ''
    scope = (user_id, exercise_id) + ((exclude,) if exclude else ())

    recent = conn.execute(
        f'''
        SELECT s.date AS date, x.weight, x.weight_unit, x.reps, x.duration_seconds,
               x.rpe, x.is_warmup
        FROM exercise_sets x
        JOIN workout_sessions s ON s.id = x.session_id
        WHERE s.user_id = ? AND x.exercise_id = ? AND x.is_warmup = 0{skip}
        ORDER BY s.date DESC, x.position
        LIMIT 60
        ''',
        scope,
    ).fetchall()

    # Two different records, because "best" means two things in a gym and
    # conflating them is misleading: 82.5kg x 6 is the heavier lift, 80kg x 8 is
    # the bigger set. Both are worth seeing before you pick today's weight.
    heaviest = conn.execute(
        f'''
        SELECT x.weight, x.weight_unit, x.reps, s.date AS date
        FROM exercise_sets x
        JOIN workout_sessions s ON s.id = x.session_id
        WHERE s.user_id = ? AND x.exercise_id = ? AND x.is_warmup = 0
          AND x.weight IS NOT NULL AND x.reps IS NOT NULL{skip}
        ORDER BY x.weight DESC, x.reps DESC
        LIMIT 1
        ''',
        scope,
    ).fetchone()

    best_volume = conn.execute(
        f'''
        SELECT x.weight, x.weight_unit, x.reps, s.date AS date,
               (x.weight * x.reps) AS volume
        FROM exercise_sets x
        JOIN workout_sessions s ON s.id = x.session_id
        WHERE s.user_id = ? AND x.exercise_id = ? AND x.is_warmup = 0
          AND x.weight IS NOT NULL AND x.reps IS NOT NULL{skip}
        ORDER BY volume DESC
        LIMIT 1
        ''',
        scope,
    ).fetchone()
    conn.close()

    sets = [dict(row) for row in recent]
    last_date = sets[0]['date'] if sets else None
    return jsonify({
        'exercise_id': exercise_id,
        'last_session_date': last_date,
        'last_session_sets': [s for s in sets if s['date'] == last_date],
        'heaviest_set': dict(heaviest) if heaviest else None,
        'best_volume_set': dict(best_volume) if best_volume else None,
        'recent_sets': sets,
    })


def _session_payload(conn, row):
    sets = conn.execute(
        '''
        SELECT x.*, e.name AS exercise_name, e.primary_muscle, e.category
        FROM exercise_sets x JOIN exercises e ON e.id = x.exercise_id
        WHERE x.session_id = ? ORDER BY x.position
        ''',
        (row['id'],),
    ).fetchall()

    return {
        'id': row['id'],
        'date': row['date'],
        'name': row['name'],
        'notes': row['notes'],
        'routine_id': row['routine_id'],
        'duration_seconds': row['duration_seconds'],
        'total_volume': row['total_volume'],
        'total_sets': row['total_sets'],
        'finished_at': row['finished_at'],
        'sets': [
            {
                'id': s['id'],
                'exercise_id': s['exercise_id'],
                'exercise_name': s['exercise_name'],
                'primary_muscle': s['primary_muscle'],
                'category': s['category'],
                'position': s['position'],
                'weight': s['weight'],
                'weight_unit': s['weight_unit'],
                'reps': s['reps'],
                'duration_seconds': s['duration_seconds'],
                'rpe': s['rpe'],
                'is_warmup': bool(s['is_warmup']),
                'completed': bool(s['completed']),
            }
            for s in sets
        ],
    }


@training.route('/api/workouts', methods=['GET', 'POST'])
@_auth
def workouts():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'POST':
        data = request.json or {}
        date = (data.get('date') or '').strip()
        if not date:
            conn.close()
            return jsonify({'error': 'date is required'}), 400

        # A session started from a routine inherits its name unless told otherwise,
        # so "Push" beats "Workout" in the history without the client restating it.
        routine_id = data.get('routine_id')
        name = (data.get('name') or '').strip()
        if not name and routine_id:
            routine = conn.execute(
                'SELECT name FROM routines WHERE id = ? AND user_id = ?',
                (routine_id, user_id),
            ).fetchone()
            name = routine['name'] if routine else ''

        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO workout_sessions (user_id, date, name, routine_id, notes) '
            'VALUES (?, ?, ?, ?, ?)',
            (user_id, date, name or 'Workout', routine_id, data.get('notes', '')),
        )
        conn.commit()
        row = conn.execute('SELECT * FROM workout_sessions WHERE id = ?',
                           (cursor.lastrowid,)).fetchone()
        payload = _session_payload(conn, row)
        conn.close()
        return jsonify(payload), 201

    limit = min(int(request.args.get('limit', 20)), 100)
    rows = conn.execute(
        'SELECT * FROM workout_sessions WHERE user_id = ? ORDER BY date DESC, id DESC '
        'LIMIT ?', (user_id, limit),
    ).fetchall()
    payload = [_session_payload(conn, row) for row in rows]
    conn.close()
    return jsonify({'workouts': payload})


@training.route('/api/workouts/<int:workout_id>', methods=['GET', 'PUT', 'DELETE'])
@_auth
def workout_detail(workout_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute(
        'SELECT * FROM workout_sessions WHERE id = ? AND user_id = ?',
        (workout_id, user_id),
    ).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'Workout not found'}), 404

    if request.method == 'GET':
        payload = _session_payload(conn, row)
        conn.close()
        return jsonify(payload)

    if request.method == 'DELETE':
        conn.execute('DELETE FROM exercise_sets WHERE session_id = ?', (workout_id,))
        conn.execute('DELETE FROM workout_sessions WHERE id = ?', (workout_id,))
        conn.commit()
        # The deleted session was feeding Strength/Stamina/Agility, so the
        # derived scores have to be rebuilt from its date onward.
        _recompute(conn, user_id, row['date'])
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    data = request.json or {}
    sets = data.get('sets')
    if sets is not None and not isinstance(sets, list):
        conn.close()
        return jsonify({'error': 'sets must be a list'}), 400

    conn.execute(
        'UPDATE workout_sessions SET name = ?, notes = ?, duration_seconds = ?, '
        'finished_at = ? WHERE id = ?',
        (data.get('name', row['name']), data.get('notes', row['notes']),
         data.get('duration_seconds', row['duration_seconds']),
         data.get('finished_at', row['finished_at']), workout_id),
    )

    if sets is not None:
        # Replace wholesale rather than diffing. The client holds the whole
        # session in local state while you train and saves the lot, so a diff
        # would be more code for the same result - and a partial save that left
        # deleted sets behind would quietly inflate volume.
        conn.execute('DELETE FROM exercise_sets WHERE session_id = ?', (workout_id,))
        for position, entry in enumerate(sets):
            if not entry.get('exercise_id'):
                continue
            conn.execute(
                'INSERT INTO exercise_sets (session_id, exercise_id, position, weight, '
                'weight_unit, reps, duration_seconds, distance, distance_unit, rpe, '
                'is_warmup, completed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (workout_id, entry['exercise_id'], position, entry.get('weight'),
                 entry.get('weight_unit', 'kg'), entry.get('reps'),
                 entry.get('duration_seconds'), entry.get('distance'),
                 entry.get('distance_unit'), entry.get('rpe'),
                 1 if entry.get('is_warmup') else 0,
                 0 if entry.get('completed') is False else 1),
            )

        totals = conn.execute(
            'SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(weight, 0) * COALESCE(reps, 0)), 0) '
            'AS volume FROM exercise_sets WHERE session_id = ? AND is_warmup = 0',
            (workout_id,),
        ).fetchone()
        conn.execute(
            'UPDATE workout_sessions SET total_sets = ?, total_volume = ? WHERE id = ?',
            (totals['n'], totals['volume'], workout_id),
        )

    conn.commit()
    _recompute(conn, user_id, row['date'])
    conn.commit()

    updated = conn.execute('SELECT * FROM workout_sessions WHERE id = ?',
                           (workout_id,)).fetchone()
    payload = _session_payload(conn, updated)
    conn.close()
    return jsonify(payload)


@training.route('/api/training')
@_auth
def training_summary():
    """Everything the Training dashboard needs, in one response - same reasoning
    as /api/home: five queries would mean five independent loading states."""
    user_id = session.get('user_id')
    conn = _get_db()

    recent = conn.execute(
        'SELECT * FROM workout_sessions WHERE user_id = ? ORDER BY date DESC, id DESC '
        'LIMIT 8', (user_id,),
    ).fetchall()

    volume_by_day = conn.execute(
        'SELECT date, SUM(total_volume) AS volume, COUNT(*) AS sessions '
        'FROM workout_sessions WHERE user_id = ? GROUP BY date ORDER BY date DESC LIMIT 30',
        (user_id,),
    ).fetchall()

    # Where the work actually went. The brief asks for muscle-group balance, and
    # this is the honest version of it - sets per group, not a guess from the
    # routine's name.
    by_muscle = conn.execute(
        '''
        SELECT e.primary_muscle AS muscle, COUNT(*) AS sets,
               COALESCE(SUM(COALESCE(x.weight, 0) * COALESCE(x.reps, 0)), 0) AS volume
        FROM exercise_sets x
        JOIN workout_sessions s ON s.id = x.session_id
        JOIN exercises e ON e.id = x.exercise_id
        WHERE s.user_id = ? AND x.is_warmup = 0 AND s.date >= date('now', '-30 days')
        GROUP BY e.primary_muscle ORDER BY volume DESC
        ''',
        (user_id,),
    ).fetchall()

    records = conn.execute(
        '''
        SELECT e.name AS exercise, e.id AS exercise_id, MAX(x.weight) AS weight,
               x.weight_unit, x.reps, s.date AS date
        FROM exercise_sets x
        JOIN workout_sessions s ON s.id = x.session_id
        JOIN exercises e ON e.id = x.exercise_id
        WHERE s.user_id = ? AND x.is_warmup = 0 AND x.weight IS NOT NULL
        GROUP BY e.id ORDER BY x.weight DESC LIMIT 8
        ''',
        (user_id,),
    ).fetchall()

    totals = conn.execute(
        'SELECT COUNT(*) AS sessions, COALESCE(SUM(total_volume), 0) AS volume '
        'FROM workout_sessions WHERE user_id = ?', (user_id,),
    ).fetchone()

    measurements = conn.execute(
        'SELECT metric, value, unit, date FROM body_measurements WHERE user_id = ? '
        'ORDER BY date DESC LIMIT 20', (user_id,),
    ).fetchall()

    payload = {
        'total_sessions': totals['sessions'],
        'total_volume': totals['volume'],
        'recent': [_session_payload(conn, row) for row in recent],
        'volume_trend': [dict(row) for row in reversed(volume_by_day)],
        'by_muscle': [dict(row) for row in by_muscle],
        'records': [dict(row) for row in records],
        'measurements': [dict(row) for row in measurements],
    }
    conn.close()
    return jsonify(payload)


def _routine_payload(conn, row):
    exercises = conn.execute(
        '''
        SELECT r.id, r.exercise_id, r.position, r.target_sets, r.target_reps, r.notes,
               e.name, e.category, e.primary_muscle
        FROM routine_exercises r
        JOIN exercises e ON e.id = r.exercise_id
        WHERE r.routine_id = ? ORDER BY r.position
        ''',
        (row['id'],),
    ).fetchall()
    return {
        'id': row['id'],
        'name': row['name'],
        'split_type': row['split_type'],
        'notes': row['notes'],
        'archived': bool(row['archived']),
        'exercises': [dict(e) for e in exercises],
    }


def _write_routine_exercises(conn, routine_id, exercises):
    """Replace the exercise list wholesale.

    Diffing positions against what is already stored buys nothing here - a
    routine is a handful of rows that the client always sends in full - and a
    replace cannot leave the order half-applied.
    """
    conn.execute('DELETE FROM routine_exercises WHERE routine_id = ?', (routine_id,))
    for position, entry in enumerate(exercises or []):
        if not entry.get('exercise_id'):
            continue
        conn.execute(
            'INSERT INTO routine_exercises '
            '(routine_id, exercise_id, position, target_sets, target_reps, notes) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (routine_id, entry['exercise_id'], position, entry.get('target_sets'),
             entry.get('target_reps'), entry.get('notes')),
        )


@training.route('/api/routines', methods=['GET', 'POST'])
@_auth
def routines():
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
            'INSERT INTO routines (user_id, name, split_type, notes) VALUES (?, ?, ?, ?)',
            (user_id, name, data.get('split_type'), data.get('notes')),
        )
        _write_routine_exercises(conn, cursor.lastrowid, data.get('exercises'))
        conn.commit()
        row = conn.execute('SELECT * FROM routines WHERE id = ?',
                           (cursor.lastrowid,)).fetchone()
        payload = _routine_payload(conn, row)
        conn.close()
        return jsonify(payload), 201

    rows = conn.execute(
        'SELECT * FROM routines WHERE user_id = ? AND archived = 0 ORDER BY name',
        (user_id,),
    ).fetchall()
    payload = [_routine_payload(conn, row) for row in rows]
    conn.close()
    return jsonify({'routines': payload})


@training.route('/api/routines/<int:routine_id>', methods=['GET', 'PUT', 'DELETE'])
@_auth
def routine_detail(routine_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM routines WHERE id = ? AND user_id = ?',
                       (routine_id, user_id)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if request.method == 'DELETE':
        # Archived, not deleted: workout_sessions.routine_id points here, and a
        # deleted routine must not erase the history of having trained it.
        conn.execute('UPDATE routines SET archived = 1 WHERE id = ?', (routine_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    if request.method == 'PUT':
        data = request.json or {}
        conn.execute(
            'UPDATE routines SET name = ?, split_type = ?, notes = ? WHERE id = ?',
            (data.get('name', row['name']), data.get('split_type', row['split_type']),
             data.get('notes', row['notes']), routine_id),
        )
        if 'exercises' in data:
            _write_routine_exercises(conn, routine_id, data['exercises'])
        conn.commit()
        row = conn.execute('SELECT * FROM routines WHERE id = ?', (routine_id,)).fetchone()

    payload = _routine_payload(conn, row)
    conn.close()
    return jsonify(payload)


@training.route('/api/measurements', methods=['GET', 'POST'])
@_auth
def measurements():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'POST':
        data = request.json or {}
        metric = (data.get('metric') or '').strip()
        date = (data.get('date') or '').strip()
        if not metric or not date or data.get('value') is None:
            conn.close()
            return jsonify({'error': 'metric, date and value are required'}), 400

        conn.execute(
            'INSERT INTO body_measurements (user_id, date, metric, value, unit, notes) '
            'VALUES (?, ?, ?, ?, ?, ?) '
            'ON CONFLICT(user_id, date, metric) DO UPDATE SET '
            'value = excluded.value, unit = excluded.unit, notes = excluded.notes',
            (user_id, date, metric, float(data['value']), data.get('unit'),
             data.get('notes')),
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True}), 201

    metric = request.args.get('metric')
    if metric:
        rows = conn.execute(
            'SELECT * FROM body_measurements WHERE user_id = ? AND metric = ? '
            'ORDER BY date', (user_id, metric)).fetchall()
    else:
        rows = conn.execute(
            'SELECT * FROM body_measurements WHERE user_id = ? ORDER BY date DESC',
            (user_id,)).fetchall()
    conn.close()
    return jsonify({'measurements': [dict(row) for row in rows]})
