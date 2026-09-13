"""Persisting scored days and the derived attribute time series.

Split from engine.py because the engine is pure and this is not. Every function
here takes an open sqlite3 connection explicitly rather than reaching for one -
the test suite swaps databases per test, and a module that grabbed its own
connection (or imported app) would quietly bind to a previous test's database.

The write path is:

    record_day()        raw facts + a snapshot of the items as they were  -> daily_log
    recompute_scores()  derived, rewritable, engine-stamped               -> attribute_scores
                                                                             daily_scores

Recomputing never touches daily_log, which is what makes "retune the weights and
rescore everything" safe.
"""
import json

from .config import ATTRIBUTES, DEFAULT_CONFIG
from .engine import (
    ENGINE_VERSION,
    aggregate_attribute,
    consistency_from_log_dates,
    score_day,
)


def record_day(conn, user_id, date, checklist_items, custom_responses,
               path_id=None, path_name=None, activity_id=None,
               source='checklist', self_rating=None, notes=None,
               config=DEFAULT_CONFIG):
    """Write one day's raw facts to daily_log, replacing any existing row.

    Stores a snapshot of every item as it was on this date, so later scoring
    never depends on the user's live Path file - which app.py rewrites on every
    read, and which has drifted before.

    Returns the scored day (see engine.score_day).
    """
    scored = score_day(checklist_items, custom_responses, config)

    payload = {
        'items': scored['items'],
        'attributes': scored['attributes'],
    }
    items_completed = sum(1 for i in scored['items'] if i['credit'] > 0)
    completion_pct = round(scored['completion'] * 100)

    conn.execute(
        '''
        INSERT INTO daily_log (
            user_id, date, source, path_id, path_name,
            weight_total, weight_earned, completion_pct,
            items_total, items_completed,
            self_rating, notes, activity_id, payload_json, engine_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET
            source = excluded.source,
            path_id = excluded.path_id,
            path_name = excluded.path_name,
            weight_total = excluded.weight_total,
            weight_earned = excluded.weight_earned,
            completion_pct = excluded.completion_pct,
            items_total = excluded.items_total,
            items_completed = excluded.items_completed,
            self_rating = excluded.self_rating,
            notes = excluded.notes,
            activity_id = excluded.activity_id,
            payload_json = excluded.payload_json,
            engine_version = excluded.engine_version,
            submitted_at = CURRENT_TIMESTAMP
        ''',
        (
            user_id, date, source, path_id, path_name,
            scored['weight_total'], scored['weight_earned'], completion_pct,
            len(scored['items']), items_completed,
            self_rating, notes, activity_id, json.dumps(payload), ENGINE_VERSION,
        ),
    )
    return scored


def _load_history(conn, user_id):
    """Every logged day for a user, oldest first, as (date, {attr: ratio}, completion)."""
    rows = conn.execute(
        'SELECT date, payload_json, completion_pct FROM daily_log '
        'WHERE user_id = ? ORDER BY date',
        (user_id,),
    ).fetchall()

    history = []
    for row in rows:
        try:
            payload = json.loads(row['payload_json'] or '{}')
        except (TypeError, ValueError):
            payload = {}

        ratios = {}
        for attribute, bucket in (payload.get('attributes') or {}).items():
            available = bucket.get('available') or 0
            if available > 0:
                ratios[attribute] = bucket.get('earned', 0) / available

        history.append((row['date'], ratios, row['completion_pct'] or 0))
    return history


def recompute_scores(conn, user_id, from_date=None, config=DEFAULT_CONFIG):
    """Rebuild the derived attribute and daily score rows.

    Scores are materialised per day using only the history available up to that
    day, so the series answers "what was my Discipline in March" honestly rather
    than projecting today's numbers backwards.

    `from_date` limits the rebuild to that date onward; a day edited in the past
    still forces everything after it to be recomputed, since later days depend on
    it. Cheap at this scale - a year of history is 365 iterations.

    Returns the number of days recomputed.
    """
    history = _load_history(conn, user_id)
    if not history:
        return 0

    recomputed = 0
    for index, (date, _, completion_pct) in enumerate(history):
        if from_date and date < from_date:
            continue

        window = history[: index + 1]
        log_dates = [day for day, _, _ in window]

        results = {}
        for attribute in ATTRIBUTES:
            if attribute == 'Consistency':
                # Showing up is not a checklist item, so it has its own producer.
                ratios = consistency_from_log_dates(
                    log_dates, config.full_confidence_days, date, config
                )
            else:
                ratios = [
                    day_ratios[attribute]
                    for _, day_ratios, _ in window
                    if attribute in day_ratios
                ]
            results[attribute] = aggregate_attribute(attribute, ratios, config)

        for attribute, result in results.items():
            # That day's own observed ratio, distinct from the rolling score.
            raw_value = window[-1][1].get(attribute)
            conn.execute(
                '''
                INSERT INTO attribute_scores (
                    user_id, date, attribute, raw_value, score, status,
                    confidence, sample_days, engine_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date, attribute) DO UPDATE SET
                    raw_value = excluded.raw_value,
                    score = excluded.score,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    sample_days = excluded.sample_days,
                    engine_version = excluded.engine_version,
                    computed_at = CURRENT_TIMESTAMP
                ''',
                (
                    user_id, date, attribute, raw_value, result['score'],
                    result['status'], result['confidence'], result['sample_days'],
                    ENGINE_VERSION,
                ),
            )

        discipline = results['Discipline']['score']
        consistency = results['Consistency']['score']
        weights = config.daily_score_weights

        # The composite only counts components that actually have a number, and
        # renormalises - otherwise a user whose Consistency is still calibrating
        # would be silently scored as if it were zero.
        parts = [(completion_pct, weights['completion'])]
        if consistency is not None:
            parts.append((consistency, weights['consistency']))
        weight_sum = sum(w for _, w in parts)
        daily_score = round(sum(v * w for v, w in parts) / weight_sum) if weight_sum else None

        conn.execute(
            '''
            INSERT INTO daily_scores (
                user_id, date, daily_score, discipline_score, completion_pct,
                engine_version
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                daily_score = excluded.daily_score,
                discipline_score = excluded.discipline_score,
                completion_pct = excluded.completion_pct,
                engine_version = excluded.engine_version,
                computed_at = CURRENT_TIMESTAMP
            ''',
            (user_id, date, daily_score, discipline, completion_pct, ENGINE_VERSION),
        )
        recomputed += 1

    return recomputed


def get_attributes(conn, user_id, date=None):
    """The attribute set as of a date (default: the most recent scored day).

    Returns a list in ATTRIBUTES order so the radar's axes stay stable between
    renders - a radar whose axes reorder is unreadable.
    """
    if date is None:
        row = conn.execute(
            'SELECT MAX(date) AS d FROM attribute_scores WHERE user_id = ?',
            (user_id,),
        ).fetchone()
        date = row['d'] if row else None

    if not date:
        return []

    rows = conn.execute(
        'SELECT attribute, raw_value, score, status, confidence, sample_days '
        'FROM attribute_scores WHERE user_id = ? AND date = ?',
        (user_id, date),
    ).fetchall()

    by_name = {row['attribute']: dict(row) for row in rows}
    return [by_name[a] for a in ATTRIBUTES if a in by_name]


def get_attribute_history(conn, user_id, attribute, limit=30):
    """One attribute's recent series, oldest first, for a trend chart."""
    rows = conn.execute(
        'SELECT date, score, status FROM attribute_scores '
        'WHERE user_id = ? AND attribute = ? ORDER BY date DESC LIMIT ?',
        (user_id, attribute, limit),
    ).fetchall()
    return [dict(row) for row in reversed(rows)]


def get_daily_scores(conn, user_id, limit=30):
    """Recent daily/discipline scores, oldest first."""
    rows = conn.execute(
        'SELECT date, daily_score, discipline_score, completion_pct '
        'FROM daily_scores WHERE user_id = ? ORDER BY date DESC LIMIT ?',
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in reversed(rows)]
