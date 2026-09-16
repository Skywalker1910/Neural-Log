"""Goals, milestones and tasks.

Its own blueprint for the same reasons the other workspaces are, with the auth
helper and database helper injected at registration so it never imports app.

No recompute function is injected here, and that absence is the point: nothing in
this module moves an attribute score. See the header of migrations/007_goals.sql -
a goal is an intention plus a number you type in, and scoring typed-in numbers
would pay you to declare progress rather than make it. The habits underneath a
goal are already scored; the goal itself is a lens on them.
"""
from datetime import date as _date, timedelta as _timedelta

from flask import Blueprint, jsonify, request, session

goals_bp = Blueprint('goals', __name__)

_get_db = None
_login_required = None

CATEGORIES = ('fitness', 'learning', 'lifestyle', 'career', 'finance', 'other')
STATUSES = ('active', 'paused', 'achieved', 'abandoned')


def init_goals(app, get_db_connection, login_required):
    global _get_db, _login_required
    _get_db = get_db_connection
    _login_required = login_required
    app.register_blueprint(goals_bp)


def _auth(view):
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _owned(conn, table, row_id, user_id):
    if not row_id:
        return True
    return conn.execute(
        f'SELECT 1 FROM {table} WHERE id = ? AND user_id = ?', (row_id, user_id)
    ).fetchone() is not None


def _linkable_habit(conn, habit_id, user_id):
    """A goal may be linked to your own question or to a shared core one.

    _owned() is not enough here: a core question has no owner, so it fails an
    ownership test and the link was silently dropped - which read as a goal that
    refused to track anything.
    """
    if not habit_id:
        return True
    return conn.execute(
        'SELECT 1 FROM habits WHERE id = ? AND (is_core = 1 OR user_id = ?)',
        (habit_id, user_id),
    ).fetchone() is not None


# --- progress ---------------------------------------------------------------

def _habit_progress(conn, goal_id, user_id, since_iso):
    """How the linked habits have actually gone, since the goal started.

    Adherence is completions-with-credit over days-elapsed, per habit, averaged.
    Days elapsed rather than days-the-habit-was-due, because a goal that has run
    for sixty days and been kept twice is 3% of the way there however the habit
    was scheduled - scaling by the schedule would let a once-a-fortnight habit
    read as perfect adherence while the goal went nowhere.
    """
    rows = conn.execute(
        '''
        SELECT h.id, h.name,
               COUNT(CASE WHEN c.credit > 0 THEN 1 END) AS done
        FROM goal_habits gh
        JOIN habits h ON h.id = gh.habit_id
        -- c.user_id matters since the survey became shared: a core question is
        -- one row answered by every account, so an unfiltered join would count
        -- everyone's completions towards one person's goal.
        LEFT JOIN habit_completions c
               ON c.habit_id = h.id AND c.user_id = ? AND c.date >= ?
        WHERE gh.goal_id = ? AND h.archived = 0
        GROUP BY h.id
        ''',
        (user_id, since_iso, goal_id),
    ).fetchall()
    if not rows:
        return None, []

    elapsed = max(1, (_date.today() - _date.fromisoformat(since_iso)).days + 1)
    linked = []
    for row in rows:
        linked.append({
            'habit_id': row['id'],
            'name': row['name'],
            'done': row['done'],
            'elapsed_days': elapsed,
            'adherence': round(min(1.0, row['done'] / elapsed), 3),
        })

    average = sum(entry['adherence'] for entry in linked) / len(linked)
    return round(average * 100), linked


def _goal_progress(conn, goal, milestones):
    """A goal's progress, and an honest label for where the number came from.

    Three sources, most evidenced first:

      habits     - derived from linked habits' real completions
      milestones - how many you have ticked off; self-reported but discrete
      metric     - a number you maintain by hand
      none       - nothing to measure, and saying so beats inventing a percentage
    """
    since = goal['started_on'] or goal['created_at'][:10]
    habit_pct, linked = _habit_progress(conn, goal['id'], goal['user_id'], since)

    if habit_pct is not None:
        return {'percent': habit_pct, 'source': 'habits', 'linked_habits': linked}

    if milestones:
        done = sum(1 for m in milestones if m['completed_on'])
        return {
            'percent': round(done / len(milestones) * 100),
            'source': 'milestones',
            'linked_habits': [],
        }

    if goal['target_value']:
        return {
            'percent': round(min(1.0, (goal['current_value'] or 0) / goal['target_value']) * 100),
            'source': 'metric',
            'linked_habits': [],
        }

    return {'percent': None, 'source': 'none', 'linked_habits': []}


def _goal_payload(conn, row):
    milestones = [dict(m) for m in conn.execute(
        'SELECT * FROM goal_milestones WHERE goal_id = ? ORDER BY position, id',
        (row['id'],),
    )]
    tasks = [dict(t) for t in conn.execute(
        'SELECT * FROM tasks WHERE goal_id = ? AND archived = 0 '
        'ORDER BY completed_on IS NOT NULL, priority, position, id',
        (row['id'],),
    )]

    goal = dict(row)
    goal['milestones'] = milestones
    goal['tasks'] = tasks
    goal['progress'] = _goal_progress(conn, row, milestones)
    goal['habit_ids'] = [
        r['habit_id'] for r in conn.execute(
            'SELECT habit_id FROM goal_habits WHERE goal_id = ?', (row['id'],))
    ]

    if row['target_date']:
        days = (_date.fromisoformat(row['target_date']) - _date.today()).days
        goal['days_remaining'] = days
    else:
        goal['days_remaining'] = None

    return goal


def _set_links(conn, goal_id, user_id, habit_ids):
    conn.execute('DELETE FROM goal_habits WHERE goal_id = ?', (goal_id,))
    for habit_id in habit_ids or []:
        if _linkable_habit(conn, habit_id, user_id):
            conn.execute(
                'INSERT OR IGNORE INTO goal_habits (goal_id, habit_id) VALUES (?, ?)',
                (goal_id, habit_id),
            )


# --- goals ------------------------------------------------------------------

@goals_bp.route('/api/goals', methods=['GET', 'POST'])
@_auth
def goals():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'POST':
        data = request.json or {}
        title = (data.get('title') or '').strip()
        if not title:
            conn.close()
            return jsonify({'error': 'title is required'}), 400

        category = data.get('category')
        if category not in CATEGORIES:
            category = 'other'

        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO goals (user_id, title, description, category, accent, '
            'status, target_date, metric_name, target_value, current_value, started_on) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (user_id, title, data.get('description'), category,
             data.get('accent', 'goals'), 'active', data.get('target_date'),
             data.get('metric_name'), data.get('target_value'),
             data.get('current_value') or 0,
             data.get('started_on') or _date.today().isoformat()),
        )
        goal_id = cursor.lastrowid

        for position, title_text in enumerate(data.get('milestones') or []):
            text = str(title_text).strip() if not isinstance(title_text, dict) \
                else str(title_text.get('title') or '').strip()
            if text:
                conn.execute(
                    'INSERT INTO goal_milestones (goal_id, user_id, title, position) '
                    'VALUES (?, ?, ?, ?)', (goal_id, user_id, text, position),
                )

        _set_links(conn, goal_id, user_id, data.get('habit_ids'))
        conn.commit()

        row = conn.execute('SELECT * FROM goals WHERE id = ?', (goal_id,)).fetchone()
        payload = _goal_payload(conn, row)
        conn.close()
        return jsonify(payload), 201

    status = request.args.get('status')
    query = 'SELECT * FROM goals WHERE user_id = ? AND archived = 0'
    params = [user_id]
    if status in STATUSES:
        query += ' AND status = ?'
        params.append(status)
    query += " ORDER BY status = 'achieved', status = 'abandoned', target_date IS NULL, target_date, id"

    rows = conn.execute(query, params).fetchall()
    payload = [_goal_payload(conn, row) for row in rows]
    conn.close()
    return jsonify({'goals': payload})


@goals_bp.route('/api/goals/<int:goal_id>', methods=['GET', 'PUT', 'DELETE'])
@_auth
def goal_detail(goal_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM goals WHERE id = ? AND user_id = ?',
                       (goal_id, user_id)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if request.method == 'DELETE':
        # Archived, not deleted. Milestones and tasks point here, and a goal you
        # gave up on is worth more in hindsight than a gap in the record.
        conn.execute('UPDATE goals SET archived = 1 WHERE id = ?', (goal_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    if request.method == 'PUT':
        data = request.json or {}
        status = data.get('status', row['status'])
        if status not in STATUSES:
            status = row['status']

        category = data.get('category', row['category'])
        if category not in CATEGORIES:
            category = row['category']

        # Reaching 'achieved' stamps the date once and keeps it: re-opening and
        # re-achieving a goal should not quietly rewrite when you first did it.
        achieved_on = row['achieved_on']
        if status == 'achieved' and not achieved_on:
            achieved_on = _date.today().isoformat()

        conn.execute(
            'UPDATE goals SET title = ?, description = ?, category = ?, accent = ?, '
            'status = ?, target_date = ?, metric_name = ?, target_value = ?, '
            'current_value = ?, achieved_on = ? WHERE id = ?',
            (str(data.get('title', row['title'])).strip() or row['title'],
             data.get('description', row['description']), category,
             data.get('accent', row['accent']), status,
             data.get('target_date', row['target_date']),
             data.get('metric_name', row['metric_name']),
             data.get('target_value', row['target_value']),
             data.get('current_value', row['current_value']),
             achieved_on, goal_id),
        )

        if 'habit_ids' in data:
            _set_links(conn, goal_id, user_id, data['habit_ids'])

        conn.commit()
        row = conn.execute('SELECT * FROM goals WHERE id = ?', (goal_id,)).fetchone()

    payload = _goal_payload(conn, row)
    conn.close()
    return jsonify(payload)


# --- milestones -------------------------------------------------------------

@goals_bp.route('/api/goals/<int:goal_id>/milestones', methods=['POST'])
@_auth
def add_milestone(goal_id):
    user_id = session.get('user_id')
    conn = _get_db()

    if not _owned(conn, 'goals', goal_id, user_id):
        conn.close()
        return jsonify({'error': 'not found'}), 404

    data = request.json or {}
    title = (data.get('title') or '').strip()
    if not title:
        conn.close()
        return jsonify({'error': 'title is required'}), 400

    position = conn.execute(
        'SELECT COALESCE(MAX(position), -1) + 1 AS p FROM goal_milestones WHERE goal_id = ?',
        (goal_id,)).fetchone()['p']

    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO goal_milestones (goal_id, user_id, title, target_date, position) '
        'VALUES (?, ?, ?, ?, ?)',
        (goal_id, user_id, title, data.get('target_date'), position),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM goal_milestones WHERE id = ?',
                       (cursor.lastrowid,)).fetchone()
    payload = dict(row)
    conn.close()
    return jsonify(payload), 201


@goals_bp.route('/api/milestones/<int:milestone_id>', methods=['PUT', 'DELETE'])
@_auth
def milestone_detail(milestone_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM goal_milestones WHERE id = ? AND user_id = ?',
                       (milestone_id, user_id)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if request.method == 'DELETE':
        conn.execute('DELETE FROM goal_milestones WHERE id = ?', (milestone_id,))
    else:
        data = request.json or {}
        completed_on = row['completed_on']
        if 'completed' in data:
            completed_on = _date.today().isoformat() if data['completed'] else None

        conn.execute(
            'UPDATE goal_milestones SET title = ?, target_date = ?, completed_on = ? '
            'WHERE id = ?',
            (str(data.get('title', row['title'])).strip() or row['title'],
             data.get('target_date', row['target_date']), completed_on, milestone_id),
        )

    conn.commit()
    conn.close()
    return jsonify({'success': True})


# --- tasks ------------------------------------------------------------------

@goals_bp.route('/api/tasks', methods=['GET', 'POST'])
@_auth
def tasks():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'POST':
        data = request.json or {}
        title = (data.get('title') or '').strip()
        if not title:
            conn.close()
            return jsonify({'error': 'title is required'}), 400

        goal_id = data.get('goal_id')
        if goal_id and not _owned(conn, 'goals', goal_id, user_id):
            conn.close()
            return jsonify({'error': 'unknown goal'}), 404

        position = conn.execute(
            'SELECT COALESCE(MAX(position), -1) + 1 AS p FROM tasks WHERE user_id = ?',
            (user_id,)).fetchone()['p']

        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO tasks (user_id, goal_id, title, notes, due_date, priority, position) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (user_id, goal_id, title, data.get('notes'), data.get('due_date'),
             int(data.get('priority') or 2), position),
        )
        conn.commit()
        row = conn.execute('SELECT * FROM tasks WHERE id = ?', (cursor.lastrowid,)).fetchone()
        payload = dict(row)
        conn.close()
        return jsonify(payload), 201

    rows = conn.execute(
        'SELECT t.*, g.title AS goal_title, g.accent AS goal_accent '
        'FROM tasks t LEFT JOIN goals g ON g.id = t.goal_id '
        'WHERE t.user_id = ? AND t.archived = 0 '
        'ORDER BY t.completed_on IS NOT NULL, t.due_date IS NULL, t.due_date, '
        't.priority, t.position, t.id',
        (user_id,),
    ).fetchall()
    conn.close()
    return jsonify({'tasks': [dict(row) for row in rows]})


@goals_bp.route('/api/tasks/<int:task_id>', methods=['PUT', 'DELETE'])
@_auth
def task_detail(task_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM tasks WHERE id = ? AND user_id = ?',
                       (task_id, user_id)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if request.method == 'DELETE':
        conn.execute('UPDATE tasks SET archived = 1 WHERE id = ?', (task_id,))
    else:
        data = request.json or {}
        completed_on = row['completed_on']
        if 'completed' in data:
            completed_on = _date.today().isoformat() if data['completed'] else None

        goal_id = data.get('goal_id', row['goal_id'])
        if goal_id and not _owned(conn, 'goals', goal_id, user_id):
            conn.close()
            return jsonify({'error': 'unknown goal'}), 404

        conn.execute(
            'UPDATE tasks SET title = ?, notes = ?, due_date = ?, priority = ?, '
            'goal_id = ?, completed_on = ? WHERE id = ?',
            (str(data.get('title', row['title'])).strip() or row['title'],
             data.get('notes', row['notes']), data.get('due_date', row['due_date']),
             int(data.get('priority') or row['priority']), goal_id,
             completed_on, task_id),
        )

    conn.commit()
    conn.close()
    return jsonify({'success': True})


# --- the dashboard ----------------------------------------------------------

@goals_bp.route('/api/goals/summary')
@_auth
def goals_summary():
    """Everything the Goals page needs, plus the habit list for linking."""
    user_id = session.get('user_id')
    conn = _get_db()
    today = _date.today()

    goal_rows = conn.execute(
        'SELECT * FROM goals WHERE user_id = ? AND archived = 0 '
        "ORDER BY status = 'achieved', status = 'abandoned', "
        'target_date IS NULL, target_date, id',
        (user_id,),
    ).fetchall()
    goals_payload = [_goal_payload(conn, row) for row in goal_rows]

    task_rows = conn.execute(
        'SELECT t.*, g.title AS goal_title, g.accent AS goal_accent '
        'FROM tasks t LEFT JOIN goals g ON g.id = t.goal_id '
        'WHERE t.user_id = ? AND t.archived = 0 '
        'ORDER BY t.completed_on IS NOT NULL, t.due_date IS NULL, t.due_date, '
        't.priority, t.position, t.id LIMIT 50',
        (user_id,),
    ).fetchall()

    # The shared survey plus this person's own questions. This used to be scoped
    # to the selected Path, because the four stock paths shared most of their
    # items and the unscoped list offered "What time did you wake up?" four times
    # with no way to tell the copies apart. One survey has nothing to scope to.
    habit_rows = conn.execute(
        'SELECT h.id, h.name, h.icon, h.is_core '
        'FROM habits h '
        'WHERE h.archived = 0 AND (h.is_core = 1 OR h.user_id = ?) '
        'ORDER BY h.is_core DESC, h.position',
        (user_id,),
    ).fetchall()

    active = [g for g in goals_payload if g['status'] == 'active']
    overdue = [
        g for g in active
        if g['target_date'] and g['target_date'] < today.isoformat()
    ]
    soon_iso = (today + _timedelta(days=7)).isoformat()

    conn.close()
    return jsonify({
        'goals': goals_payload,
        'tasks': [dict(row) for row in task_rows],
        'habits': [dict(row) for row in habit_rows],
        'totals': {
            'active': len(active),
            'achieved': len([g for g in goals_payload if g['status'] == 'achieved']),
            'overdue': len(overdue),
            'due_soon': len([
                g for g in active
                if g['target_date'] and today.isoformat() <= g['target_date'] <= soon_iso
            ]),
            'open_tasks': len([t for t in task_rows if not t['completed_on']]),
        },
    })
