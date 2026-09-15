"""Analytics endpoints - long-range trends across every workspace.

Its own blueprint for the same reasons training_api.py and the rest are: app.py
is long enough, and the auth and database helpers are injected at registration so
this module never imports app back.

## What makes this honest

Every other workspace answers "what did I do today". This one answers "am I
getting better", and that question is much easier to answer dishonestly.

Three rules keep it straight, and they are why the payload looks the way it does:

**A day with no record is unobserved, not zero.** If you did not log food on
Tuesday, your intake on Tuesday is unknown - it is not 0 kcal. Those days carry
`null` in the series, so a chart gaps rather than drawing a floor that never
happened, and they are excluded from averages. Every metric reports
`observed_days` next to `days`, so "averaging 7h 20m" can always be read as
"across the 9 nights out of 30 that were logged".

**A comparison needs something to compare against.** The previous window is the
equal-length window immediately before this one. When it holds no observations
the delta is `null` rather than a percentage - "up 100%" from nothing is not
information, and an arrow pointing up is worse than no arrow.

**Sums and averages are not interchangeable.** Training volume sums: two sessions
in a week is more work than one. Sleep averages: nine hours across two nights is
not "better" than eight across seven. Each metric declares which it is, and the
UI renders the aggregate it is told rather than guessing from the unit.
"""
from datetime import date as _date, datetime, timedelta

from flask import Blueprint, jsonify, request, session

analytics_bp = Blueprint('analytics', __name__)

_get_db = None
_login_required = None


def init_analytics(app, get_db_connection, login_required):
    global _get_db, _login_required
    _get_db = get_db_connection
    _login_required = login_required
    app.register_blueprint(analytics_bp)


def _auth(view):
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


# --- periods ----------------------------------------------------------------

# 'all' is capped rather than unbounded. A chart with four years of daily points
# is unreadable, and the query cost grows without buying an answer.
MAX_ALL_DAYS = 730

PERIODS = {
    '7': 7,
    '30': 30,
    '90': 90,
    '365': 365,
    'all': None,
}

PERIOD_LABELS = {
    '7': 'Last 7 days',
    '30': 'Last 30 days',
    '90': 'Last 90 days',
    '365': 'Last year',
    'all': 'All time',
}


def _iso(value):
    return value.strftime('%Y-%m-%d')


def _parse_date(raw, fallback):
    if not raw:
        return fallback
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return fallback


def _first_logged_day(conn, user_id):
    """The earliest date this user has any record on, across every workspace.

    'All time' has to mean *their* all time. Anchoring it to account creation
    would pad the chart with empty months before they started logging, and
    anchoring it to a fixed number of days would silently truncate someone with
    two years of history.
    """
    tables = (
        ('daily_scores', 'date'), ('daily_log', 'date'), ('daily_xp', 'date'),
        ('workout_sessions', 'date'), ('learning_sessions', 'date'),
        ('food_entries', 'date'), ('sleep_entries', 'date'),
        ('lifestyle_days', 'date'),
    )
    earliest = None
    for table, column in tables:
        row = conn.execute(
            f'SELECT MIN({column}) AS d FROM {table} WHERE user_id = ?', (user_id,)
        ).fetchone()
        if row and row['d'] and (earliest is None or row['d'] < earliest):
            earliest = row['d']
    return earliest


def _resolve_range(conn, user_id, period, end):
    """(start, end, days) for the requested period, as dates."""
    span = PERIODS.get(period, 30)

    if span is None:
        first = _first_logged_day(conn, user_id)
        start = _parse_date(first, end) if first else end
        days = (end - start).days + 1
        if days > MAX_ALL_DAYS:
            days = MAX_ALL_DAYS
            start = end - timedelta(days=days - 1)
        return start, end, max(days, 1)

    return end - timedelta(days=span - 1), end, span


# --- metrics ----------------------------------------------------------------

# Each metric is one row per day for one user between two dates. Grouping happens
# in SQL rather than Python because several of these tables hold many rows per
# day - 41 sets across 9 sessions, 90 food entries across 10 days - and pulling
# them all back to sum them in the API would scale with logging, not with the
# length of the window being charted.
SUM, AVG = 'sum', 'avg'

METRICS = [
    {
        'key': 'daily_score', 'label': 'Daily score', 'unit': '', 'accent': 'brand',
        'aggregate': AVG, 'precision': 1, 'domain': [0, 100],
        # Joined to daily_log rather than read straight off daily_scores. The
        # engine writes daily_score = 0 for every day the checklist was not
        # submitted, so on that table a zero means "no answer" and a zero also
        # means "answered No to everything" - the column cannot tell them apart.
        # A daily_log row can: it exists only for a day that was actually
        # submitted. Without this join, thirteen unlogged days averaged a real
        # 100 and 95 down to 13.0.
        'sql': 'SELECT daily_scores.date AS date, daily_scores.daily_score AS value '
               'FROM daily_scores '
               'JOIN daily_log ON daily_log.user_id = daily_scores.user_id '
               '                AND daily_log.date = daily_scores.date '
               'WHERE daily_scores.user_id = ? '
               '  AND daily_scores.date BETWEEN ? AND ? '
               '  AND daily_scores.daily_score IS NOT NULL',
    },
    {
        'key': 'discipline', 'label': 'Discipline', 'unit': '', 'accent': 'discipline',
        'aggregate': AVG, 'precision': 1, 'domain': [0, 100],
        'sql': 'SELECT date, discipline_score AS value FROM daily_scores '
               'WHERE user_id = ? AND date BETWEEN ? AND ? AND discipline_score IS NOT NULL',
    },
    {
        'key': 'xp', 'label': 'XP earned', 'unit': ' XP', 'accent': 'discipline',
        'aggregate': SUM, 'precision': 0,
        'sql': 'SELECT date, SUM(total_xp) AS value FROM daily_xp '
               'WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date',
    },
    {
        'key': 'training_volume', 'label': 'Training volume', 'unit': ' kg', 'accent': 'fitness',
        'aggregate': SUM, 'precision': 0,
        'sql': 'SELECT date, SUM(total_volume) AS value FROM workout_sessions '
               'WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date',
    },
    {
        'key': 'training_sets', 'label': 'Working sets', 'unit': '', 'accent': 'fitness',
        'aggregate': SUM, 'precision': 0,
        'sql': 'SELECT date, SUM(total_sets) AS value FROM workout_sessions '
               'WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date',
    },
    {
        'key': 'study_minutes', 'label': 'Study time', 'unit': ' min', 'accent': 'learning',
        'aggregate': SUM, 'precision': 0,
        'sql': 'SELECT date, SUM(duration_minutes) AS value FROM learning_sessions '
               'WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date',
    },
    {
        'key': 'sleep_minutes', 'label': 'Sleep', 'unit': ' min', 'accent': 'recovery',
        'aggregate': AVG, 'precision': 0,
        'sql': 'SELECT date, SUM(duration_minutes) AS value FROM sleep_entries '
               'WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date',
    },
    {
        'key': 'calories', 'label': 'Calories', 'unit': ' kcal', 'accent': 'lifestyle',
        'aggregate': AVG, 'precision': 0,
        'sql': 'SELECT food_entries.date AS date, '
               '       SUM(foods.kcal_per_100g * food_entries.grams / 100.0) AS value '
               'FROM food_entries JOIN foods ON foods.id = food_entries.food_id '
               'WHERE food_entries.user_id = ? AND food_entries.date BETWEEN ? AND ? '
               'GROUP BY food_entries.date',
    },
    {
        'key': 'protein_g', 'label': 'Protein', 'unit': ' g', 'accent': 'lifestyle',
        'aggregate': AVG, 'precision': 0,
        'sql': 'SELECT food_entries.date AS date, '
               '       SUM(foods.protein_per_100g * food_entries.grams / 100.0) AS value '
               'FROM food_entries JOIN foods ON foods.id = food_entries.food_id '
               'WHERE food_entries.user_id = ? AND food_entries.date BETWEEN ? AND ? '
               'GROUP BY food_entries.date',
    },
    {
        'key': 'steps', 'label': 'Steps', 'unit': '', 'accent': 'fitness',
        'aggregate': AVG, 'precision': 0,
        'sql': 'SELECT date, steps AS value FROM lifestyle_days '
               'WHERE user_id = ? AND date BETWEEN ? AND ? AND steps IS NOT NULL AND steps > 0',
    },
    {
        'key': 'water_ml', 'label': 'Hydration', 'unit': ' ml', 'accent': 'recovery',
        'aggregate': AVG, 'precision': 0,
        'sql': 'SELECT date, water_ml AS value FROM lifestyle_days '
               'WHERE user_id = ? AND date BETWEEN ? AND ? AND water_ml IS NOT NULL AND water_ml > 0',
    },
]

METRICS_BY_KEY = {metric['key']: metric for metric in METRICS}


def _observed(conn, metric, user_id, start, end):
    """{date: value} for the days this metric actually has data on.

    Days absent from this map are unobserved, and stay absent all the way to the
    client. Filling them with 0 here would be irreversible - nothing downstream
    could tell a rest day from a day you forgot to log.
    """
    rows = conn.execute(metric['sql'], (user_id, _iso(start), _iso(end))).fetchall()
    return {
        row['date']: float(row['value'])
        for row in rows
        if row['value'] is not None
    }


def _aggregate(metric, values):
    if not values:
        return None
    total = sum(values)
    if metric['aggregate'] == AVG:
        total /= len(values)
    return round(total, metric['precision']) if metric['precision'] else round(total)


def _series(observed, start, days):
    """One point per calendar day, null where nothing was observed."""
    out = []
    for offset in range(days):
        day = _iso(start + timedelta(days=offset))
        out.append({'date': day, 'value': observed.get(day)})
    return out


def _metric_payload(conn, metric, user_id, start, end, days, prev_start, prev_end):
    observed = _observed(conn, metric, user_id, start, end)
    previous = _observed(conn, metric, user_id, prev_start, prev_end)

    value = _aggregate(metric, list(observed.values()))
    prior = _aggregate(metric, list(previous.values()))

    # No previous observations means no comparison. Reporting "+100%" against an
    # empty window would turn "I started logging sleep this month" into a
    # improvement claim about sleeping more.
    delta = delta_pct = None
    if value is not None and prior is not None:
        delta = round(value - prior, metric['precision']) if metric['precision'] else round(value - prior)
        delta_pct = round((value - prior) / prior * 100, 1) if prior else None

    return {
        'key': metric['key'],
        'label': metric['label'],
        'unit': metric['unit'],
        'accent': metric['accent'],
        'aggregate': metric['aggregate'],
        'domain': metric.get('domain'),
        'value': value,
        'previous': prior,
        'delta': delta,
        'delta_pct': delta_pct,
        'observed_days': len(observed),
        'previous_observed_days': len(previous),
        'days': days,
        'series': _series(observed, start, days),
    }


# --- calendar ---------------------------------------------------------------

def _calendar(conn, user_id, start, end, days):
    """One cell per day: how much of that day's Path was completed.

    Adherence rather than XP, because XP is capped and multiplied and a perfect
    day late in a streak outscores a perfect day on day one. The heatmap is meant
    to answer "did I show up", and completion is the only number that means the
    same thing on every square.
    """
    rows = conn.execute(
        'SELECT date, completion_pct, items_completed, items_total '
        'FROM daily_log WHERE user_id = ? AND date BETWEEN ? AND ?',
        (user_id, _iso(start), _iso(end)),
    ).fetchall()
    logged = {row['date']: row for row in rows}

    scores = {
        row['date']: row['daily_score']
        for row in conn.execute(
            'SELECT date, daily_score FROM daily_scores '
            'WHERE user_id = ? AND date BETWEEN ? AND ?',
            (user_id, _iso(start), _iso(end)),
        ).fetchall()
    }

    out = []
    for offset in range(days):
        day = _iso(start + timedelta(days=offset))
        row = logged.get(day)
        out.append({
            'date': day,
            'logged': row is not None,
            'completion_pct': row['completion_pct'] if row else None,
            'items_completed': row['items_completed'] if row else None,
            'items_total': row['items_total'] if row else None,
            'daily_score': scores.get(day),
        })
    return out


# --- attributes -------------------------------------------------------------

def _attribute_comparison(conn, user_id, start, end):
    """Each attribute now, next to where it stood at the start of the window.

    The radar already renders a `previous` overlay; this is what fills it. The
    comparison point is the most recent score *on or before* the window opened,
    not the score on that exact date - attributes are only written on days that
    produced a signal, and demanding an exact match would blank the overlay for
    anyone who took a day off.
    """
    current = {
        row['attribute']: row
        for row in conn.execute(
            'SELECT attribute, score, status, sample_days FROM attribute_scores '
            'WHERE user_id = ? AND date = (SELECT MAX(date) FROM attribute_scores '
            '                              WHERE user_id = ? AND date <= ?)',
            (user_id, user_id, _iso(end)),
        ).fetchall()
    }

    before = {
        row['attribute']: row
        for row in conn.execute(
            'SELECT attribute, score FROM attribute_scores '
            'WHERE user_id = ? AND date = (SELECT MAX(date) FROM attribute_scores '
            '                              WHERE user_id = ? AND date <= ?)',
            (user_id, user_id, _iso(start)),
        ).fetchall()
    }

    from scoring.config import ATTRIBUTES

    out = []
    for attribute in ATTRIBUTES:
        now = current.get(attribute)
        then = before.get(attribute)
        score = now['score'] if now else None
        prior = then['score'] if then else None
        out.append({
            'attribute': attribute,
            'score': score,
            'previous': prior,
            'delta': round(score - prior, 1) if score is not None and prior is not None else None,
            'status': now['status'] if now else 'unobserved',
            'sample_days': now['sample_days'] if now else 0,
        })
    return out


# --- endpoint ---------------------------------------------------------------

@analytics_bp.route('/api/analytics')
@_auth
def analytics():
    """Everything the Analytics page needs, in one response.

    Composed server-side for the same reason /api/home is: QueryBoundary wraps a
    single query, so eleven separate metric calls would mean eleven skeletons and
    eleven independent error states on one screen.
    """
    user_id = session.get('user_id')
    period = request.args.get('period', '30')
    if period not in PERIODS:
        return jsonify({'error': 'Unknown period'}), 400

    conn = _get_db()
    try:
        end = _parse_date(request.args.get('end'), _date.today())
        start, end, days = _resolve_range(conn, user_id, period, end)

        # The comparison window sits immediately before this one and is the same
        # length, so "last 30 days" is always measured against the 30 before it.
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days - 1)

        metrics = [
            _metric_payload(conn, metric, user_id, start, end, days, prev_start, prev_end)
            for metric in METRICS
        ]

        calendar = _calendar(conn, user_id, start, end, days)

        return jsonify({
            'period': period,
            'range': {
                'start': _iso(start), 'end': _iso(end), 'days': days,
                'label': PERIOD_LABELS[period],
            },
            'previous': {
                'start': _iso(prev_start), 'end': _iso(prev_end), 'days': days,
            },
            'metrics': metrics,
            'calendar': calendar,
            'attributes': _attribute_comparison(conn, user_id, start, end),
            'days_logged': sum(1 for cell in calendar if cell['logged']),
        })
    finally:
        conn.close()
