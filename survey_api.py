"""The daily survey: the shared questions, and each person's own additions.

Four hero Paths became one shared survey. Picking a Path at signup quietly
decided your *scores* - the opportunity denominator comes from the items in it,
so an Ironman never had a Stamina denominator from the checklist and a Thor never
had a Knowledge one, while the leaderboard ranked those people against each other
as though the numbers meant the same thing.

One survey makes completion percentages comparable and gives every attribute the
same denominator for everybody.

## The one rule the model implies

A core question belongs to everyone (`habits.user_id IS NULL`), so one person
cannot rename, reweight or reschedule it. That is an admin action and it changes
the question for all five accounts at once. Personal extras are the escape hatch:
they belong to one account, sort after the core set, and behave exactly as a Path
item used to.

Refusals here are 403 with the reason spelled out, not 404. "Not found" would be
a lie about a question the person can plainly see on their own Today page.
"""
import json
from uuid import uuid4

from flask import Blueprint, jsonify, request, session

import habits as habits_store
import xp_config

survey_bp = Blueprint('survey', __name__)

_get_db = None
_login_required = None
_recompute = None


def init_survey(app, get_db_connection, login_required, recompute):
    global _get_db, _login_required, _recompute
    _get_db = get_db_connection
    _login_required = login_required
    _recompute = recompute
    app.register_blueprint(survey_bp)


def _auth(view):
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


SURVEY_TYPES = ('yes-no', 'time', 'rating', 'text')

CORE_REFUSAL = ('That question is part of the shared survey. Only an admin can '
                'change it, and the change applies to everyone.')


def _is_admin(conn, user_id):
    row = conn.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,)).fetchone()
    return bool(row and row['is_admin'])


def _stored_options(row):
    if row is None:
        return None
    try:
        return json.loads(row['options']) if row['options'] else None
    except (TypeError, ValueError):
        return None


def _clean(data, current=None):
    """(fields, error). Validates rather than coerces, like onboarding_api."""
    name = str(data.get('name', (current['name'] if current else '') or '')).strip()
    if not name:
        return None, 'A question needs some text'
    if len(name) > 200:
        return None, 'That question is too long'

    kind = data.get('type', (current['type'] if current else None) or 'yes-no')
    if kind not in SURVEY_TYPES:
        return None, 'type must be one of: ' + ', '.join(SURVEY_TYPES)

    try:
        weight = int(data.get('weight', current['weight'] if current else 1))
    except (TypeError, ValueError):
        return None, 'weight must be a whole number'
    if not 0 <= weight <= 5:
        return None, 'weight must be between 0 and 5'

    options = data.get('options', _stored_options(current))
    if kind == 'time':
        options = [str(option).strip() for option in (options or []) if str(option).strip()]
        if len(options) < 2:
            return None, 'A time question needs at least two options'
    else:
        options = None

    return {
        'name': name,
        'type': kind,
        'icon': str(data.get('icon', (current['icon'] if current else None) or 'default')).strip()
                or 'default',
        # A rating is never scored - extract_signals skips rating items outright -
        # so any non-zero weight would be denominator nobody can ever earn
        # against, quietly capping everyone's completion below 100%.
        'weight': 0 if kind == 'rating' else weight,
        'options': json.dumps(options) if options else None,
    }, None


def _xp_headroom(questions):
    """What a perfect day is worth, against what the daily cap will actually pay.

    The checklist cap has always been 150, tuned to the stock Paths' 15 weight
    points. Nothing enforced the relationship, so a survey worth more than that
    silently threw the excess away - an early draft of the shared survey totalled
    17 points and lost 20 XP off every perfect day without a word.

    Now that an admin can add questions, that drift is a matter of time. Reporting
    both numbers lets the editor say so out loud rather than leaving someone to
    wonder why a harder day stopped being worth more.
    """
    weight = sum(int(q.get('weight') or 0) for q in questions
                 if q.get('type') != 'rating')
    perfect = weight * xp_config.XP_PER_WEIGHT_POINT
    cap = xp_config.DAILY_SOURCE_CAPS.get('checklist')
    return {
        'weight_total': weight,
        'perfect_day_xp': perfect,
        'daily_cap': cap,
        'over_cap': bool(cap is not None and perfect > cap),
    }


@survey_bp.route('/api/survey')
@_auth
def get_survey():
    """The questions this account is asked: the shared core, then its own."""
    user_id = session.get('user_id')
    conn = _get_db()
    try:
        questions = habits_store.load_survey(conn, user_id)
        return jsonify({
            'questions': questions,
            'can_edit_core': _is_admin(conn, user_id),
            'xp': _xp_headroom(questions),
        })
    finally:
        conn.close()


@survey_bp.route('/api/survey/questions', methods=['POST'])
@_auth
def create_question():
    """Add a question. Personal by default; `is_core` requires admin."""
    user_id = session.get('user_id')
    data = request.json or {}
    conn = _get_db()
    try:
        core = bool(data.get('is_core'))
        if core and not _is_admin(conn, user_id):
            return jsonify({'error': CORE_REFUSAL}), 403

        fields, error = _clean(data)
        if error:
            return jsonify({'error': error}), 400

        # Appended, never inserted. Reordering is its own operation; slotting a
        # new question into the middle of a survey people answer every evening
        # would move the rest of it under their fingers.
        last = conn.execute(
            'SELECT MAX(position) AS p FROM habits WHERE archived = 0 AND is_core = ? '
            'AND user_id IS ?',
            (1 if core else 0, None if core else user_id),
        ).fetchone()

        cursor = conn.execute(
            'INSERT INTO habits (user_id, group_id, is_core, slug, name, type, icon, '
            'weight, options, position, archived) '
            'VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 0)',
            (None if core else user_id, 1 if core else 0, str(uuid4()),
             fields['name'], fields['type'], fields['icon'], fields['weight'],
             fields['options'], ((last['p'] if last else None) or 0) + 1),
        )
        conn.commit()
        row = conn.execute('SELECT * FROM habits WHERE id = ?', (cursor.lastrowid,)).fetchone()
        return jsonify(habits_store.habit_payload(row)), 201
    finally:
        conn.close()


@survey_bp.route('/api/survey/questions/<int:question_id>', methods=['PUT', 'DELETE'])
@_auth
def edit_question(question_id):
    user_id = session.get('user_id')
    conn = _get_db()
    try:
        row = conn.execute('SELECT * FROM habits WHERE id = ? AND archived = 0',
                           (question_id,)).fetchone()
        if row is None:
            return jsonify({'error': 'not found'}), 404

        if row['is_core']:
            if not _is_admin(conn, user_id):
                return jsonify({'error': CORE_REFUSAL}), 403
        elif row['user_id'] != user_id:
            # Somebody else's personal question. 404 rather than 403 here, because
            # unlike a core question this one is genuinely none of their business.
            return jsonify({'error': 'not found'}), 404

        if request.method == 'DELETE':
            # Archived, never deleted. habit_completions references it, and the
            # answers people already gave are history rather than clutter -
            # daily_log snapshots keep scoring past days correctly either way.
            conn.execute('UPDATE habits SET archived = 1 WHERE id = ?', (question_id,))
            conn.commit()
            return jsonify({'success': True})

        fields, error = _clean(request.json or {}, row)
        if error:
            return jsonify({'error': error}), 400

        conn.execute(
            'UPDATE habits SET name = ?, type = ?, icon = ?, weight = ?, options = ? '
            'WHERE id = ?',
            (fields['name'], fields['type'], fields['icon'], fields['weight'],
             fields['options'], question_id),
        )
        conn.commit()
        updated = conn.execute('SELECT * FROM habits WHERE id = ?', (question_id,)).fetchone()
        return jsonify(habits_store.habit_payload(updated))
    finally:
        conn.close()
