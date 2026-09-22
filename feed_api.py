"""The weekly feed and review-before-save AI journal summaries."""
import json
from datetime import date as _date, datetime, timedelta

from flask import Blueprint, jsonify, request, session

from assistant import agent, config, usage

feed_bp = Blueprint('feed', __name__)
_get_db = None
_login_required = None


def init_feed(app, get_db_connection, login_required):
    global _get_db, _login_required
    _get_db = get_db_connection
    _login_required = login_required
    app.register_blueprint(feed_bp)


def _auth(view):
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _day(raw=None):
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date() if raw else _date.today()
    except (TypeError, ValueError):
        return _date.today()


def _weekly_data(conn, user_id, end):
    start = end - timedelta(days=6)
    dates = [(start + timedelta(days=offset)).isoformat() for offset in range(7)]
    nutrition = {
        row['date']: dict(row) for row in conn.execute(
            'SELECT e.date, SUM(f.kcal_per_100g * e.grams / 100.0) AS calories, '
            'SUM(f.protein_per_100g * e.grams / 100.0) AS protein '
            'FROM food_entries e JOIN foods f ON f.id = e.food_id '
            'WHERE e.user_id = ? AND e.date BETWEEN ? AND ? GROUP BY e.date',
            (user_id, dates[0], dates[-1]),
        )
    }
    training = {
        row['date']: dict(row) for row in conn.execute(
            'SELECT date, COUNT(*) AS sessions, SUM(total_sets) AS sets, '
            'SUM(total_volume) AS volume FROM workout_sessions '
            'WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date',
            (user_id, dates[0], dates[-1]),
        )
    }
    sleep = {row['date']: dict(row) for row in conn.execute(
        'SELECT date, duration_minutes FROM sleep_entries WHERE user_id = ? AND date BETWEEN ? AND ?',
        (user_id, dates[0], dates[-1]),
    )}
    lifestyle = {row['date']: dict(row) for row in conn.execute(
        'SELECT date, water_ml, steps, mood, journal FROM lifestyle_days '
        'WHERE user_id = ? AND date BETWEEN ? AND ?', (user_id, dates[0], dates[-1]),
    )}
    learning = {row['date']: dict(row) for row in conn.execute(
        'SELECT date, SUM(duration_minutes) AS minutes FROM learning_sessions '
        'WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date',
        (user_id, dates[0], dates[-1]),
    )}
    days = []
    for day in dates:
        food, workout, night, life, study = (
            nutrition.get(day), training.get(day), sleep.get(day), lifestyle.get(day), learning.get(day),
        )
        days.append({
            'date': day,
            'calories': round(float(food['calories']), 0) if food and food['calories'] is not None else None,
            'protein_g': round(float(food['protein']), 1) if food and food['protein'] is not None else None,
            'sessions': int(workout['sessions']) if workout else 0,
            'sets': int(workout['sets'] or 0) if workout else 0,
            'volume': round(float(workout['volume'] or 0)) if workout else 0,
            'sleep_minutes': int(night['duration_minutes']) if night else None,
            'water_ml': int(life['water_ml']) if life and life['water_ml'] is not None else None,
            'steps': int(life['steps']) if life and life['steps'] is not None else None,
            'mood': int(life['mood']) if life and life['mood'] is not None else None,
            'study_minutes': int(study['minutes']) if study and study['minutes'] is not None else 0,
        })
    return start, end, days


def _mean(days, key):
    values = [day[key] for day in days if day[key] is not None]
    return round(sum(values) / len(values), 1) if values else None


def _insights(days):
    logged_food = sum(day['calories'] is not None for day in days)
    logged_sleep = sum(day['sleep_minutes'] is not None for day in days)
    sessions = sum(day['sessions'] for day in days)
    session_label = 'session' if sessions == 1 else 'sessions'
    insights = [
        {
            'tone': 'info', 'title': 'Coverage first',
            'body': f'Food was logged on {logged_food}/7 days and sleep on {logged_sleep}/7. Gaps stay unknown rather than counting as zero.',
        },
        {
            'tone': 'success' if sessions >= 2 else 'warning',
            'title': 'Training',
            'body': f'{sessions} {session_label} and {sum(day['sets'] for day in days)} working sets recorded this week.',
        },
    ]
    if _mean(days, 'sleep_minutes') is not None:
        average = _mean(days, 'sleep_minutes')
        insights.append({
            'tone': 'info', 'title': 'Recovery',
            'body': f'Average recorded sleep was {int(average // 60)}h {int(average % 60):02d}m.',
        })
    return insights


@feed_bp.route('/api/feed/weekly')
@_auth
def weekly_feed():
    end = _day(request.args.get('end'))
    conn = _get_db()
    try:
        start, end, days = _weekly_data(conn, session.get('user_id'), end)
        totals = {
            'training_sessions': sum(day['sessions'] for day in days),
            'working_sets': sum(day['sets'] for day in days),
            'training_volume': sum(day['volume'] for day in days),
            'study_minutes': sum(day['study_minutes'] for day in days),
            'avg_calories': _mean(days, 'calories'),
            'avg_protein_g': _mean(days, 'protein_g'),
            'avg_sleep_minutes': _mean(days, 'sleep_minutes'),
            'avg_steps': _mean(days, 'steps'),
            'avg_water_ml': _mean(days, 'water_ml'),
        }
        return jsonify({
            'range': {'start': start.isoformat(), 'end': end.isoformat()},
            'days': days, 'totals': totals, 'insights': _insights(days),
        })
    finally:
        conn.close()


@feed_bp.route('/api/journal/summary', methods=['POST'])
@_auth
def journal_summary():
    data = request.json or {}
    day = _day(data.get('date'))
    conn = _get_db()
    try:
        if not config.is_configured():
            return jsonify({'error': 'The assistant is not configured on this instance.'}), 503
        allowed, message = usage.check_budget(conn, session.get('user_id'))
        if not allowed:
            return jsonify({'error': message}), 429
        if usage.rate_limited(conn, session.get('user_id')):
            return jsonify({'error': 'That is a lot of requests at once - give it a few seconds.'}), 429
        _, _, days = _weekly_data(conn, session.get('user_id'), day)
        facts = next(item for item in days if item['date'] == day.isoformat())
        prompt = (
            'Write a private journal entry of at most 110 words from these logged facts. '
            'Do not invent events, feelings, motivations, food names, or health advice. '
            'Use a calm first-person voice and say less when data is sparse. Facts: '
            + json.dumps(facts)
        )
        try:
            response = agent.build_client().responses.create(
                model=config.CHAT_MODEL, input=prompt, max_output_tokens=220,
                reasoning={'effort': 'low'}, store=False,
            )
            usage.record(conn, session.get('user_id'), 'journal', config.CHAT_MODEL,
                         agent._usage_from(response))
            summary = agent._text_of(response)
        except Exception as error:
            usage.record(conn, session.get('user_id'), 'journal', config.CHAT_MODEL, ok=False, error=error)
            return jsonify({'error': 'The assistant could not summarise this day right now.'}), 503
        return jsonify({'date': day.isoformat(), 'summary': summary})
    finally:
        conn.close()
