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
from datetime import date as _date

from . import nutrition, producers
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


def _load_training_sets(conn, user_id):
    """Every completed set the user has logged, with the exercise metadata the
    producer needs to decide which attribute it feeds."""
    rows = conn.execute(
        """
        SELECT s.date AS date, e.category AS category, e.primary_muscle AS primary_muscle,
               x.weight AS weight, x.weight_unit AS weight_unit, x.reps AS reps,
               x.duration_seconds AS duration_seconds, x.is_warmup AS is_warmup,
               x.completed AS completed
        FROM exercise_sets x
        JOIN workout_sessions s ON s.id = x.session_id
        JOIN exercises e ON e.id = x.exercise_id
        WHERE s.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_sleep(conn, user_id):
    rows = conn.execute(
        'SELECT date, duration_minutes, bedtime, wake_time FROM sleep_entries '
        'WHERE user_id = ? ORDER BY date',
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_lifestyle(conn, user_id):
    rows = conn.execute(
        'SELECT date, water_ml, steps, sunlight_minutes FROM lifestyle_days '
        'WHERE user_id = ? ORDER BY date',
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_learning_sessions(conn, user_id):
    rows = conn.execute(
        'SELECT date, duration_minutes, started_at FROM learning_sessions '
        'WHERE user_id = ? ORDER BY date, started_at',
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_nutrition_totals(conn, user_id):
    """Per-day macro totals, summed in SQL rather than in Python.

    Macros are derived from the food's per-100g values on every read rather than
    denormalised onto the entry, so correcting a food's data corrects history
    instead of leaving a trail of rows frozen at the wrong numbers.
    """
    rows = conn.execute(
        '''
        SELECT e.date AS date,
               SUM(f.kcal_per_100g    * e.grams / 100.0) AS calories,
               SUM(f.protein_per_100g * e.grams / 100.0) AS protein_g,
               SUM(f.carbs_per_100g   * e.grams / 100.0) AS carbs_g,
               SUM(f.fat_per_100g     * e.grams / 100.0) AS fat_g,
               SUM(f.fibre_per_100g   * e.grams / 100.0) AS fibre_g
        FROM food_entries e
        JOIN foods f ON f.id = e.food_id
        WHERE e.user_id = ?
        GROUP BY e.date
        ''',
        (user_id,),
    ).fetchall()
    return {row['date']: dict(row) for row in rows}


def _load_profile(conn, user_id):
    row = conn.execute(
        'SELECT * FROM user_profile WHERE user_id = ?', (user_id,)
    ).fetchone()
    return dict(row) if row else {}


def _weight_timeline(conn, user_id):
    """Body weights, oldest first, as (date, kg). Empty when nothing is recorded."""
    rows = conn.execute(
        "SELECT date, value FROM body_measurements "
        "WHERE user_id = ? AND metric = 'weight' ORDER BY date",
        (user_id,),
    ).fetchall()
    return [(row['date'], row['value']) for row in rows]


def _weight_on(timeline, iso):
    """The weight known as of a date.

    Uses the most recent measurement on or before that day, falling back to the
    earliest one for dates before any weigh-in. The fallback matters: without it
    every day before the first weigh-in would have no calorie target and so no
    adherence signal, which would read as "you were not adhering" rather than
    "nobody knew what you weighed yet".
    """
    if not timeline:
        return None
    current = None
    for date, value in timeline:
        if date <= iso:
            current = value
        else:
            break
    return current if current is not None else timeline[0][1]


def _targets_by_date(conn, user_id, dates):
    """Each day's nutrition and lifestyle targets, as they would have applied then.

    Body weight is read per-date rather than once, so a calorie target follows
    the weight it was derived from instead of retroactively rewriting every past
    day against today's.
    """
    profile = _load_profile(conn, user_id)
    timeline = _weight_timeline(conn, user_id)

    out = {}
    for iso in dates:
        out[iso] = nutrition.resolve_targets(
            profile, _weight_on(timeline, iso), _date.fromisoformat(iso)
        )
    return out


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


def _prune_orphaned_scores(conn, user_id, live_dates, from_date=None):
    """Remove derived rows whose source day no longer exists."""
    existing = conn.execute(
        'SELECT DISTINCT date FROM daily_scores WHERE user_id = ?', (user_id,)
    ).fetchall()
    live = set(live_dates)

    for row in existing:
        date = row['date']
        if date in live:
            continue
        if from_date and date < from_date:
            continue
        conn.execute('DELETE FROM daily_scores WHERE user_id = ? AND date = ?',
                     (user_id, date))
        conn.execute('DELETE FROM attribute_scores WHERE user_id = ? AND date = ?',
                     (user_id, date))


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

    # Training is measured over a trailing window rather than per day, so it is
    # computed for every date up front - including days where the only thing
    # logged was a workout.
    checklist_dates = [day for day, _, _ in history]
    training_sets = _load_training_sets(conn, user_id)
    sleep_rows = _load_sleep(conn, user_id)
    lifestyle_rows = _load_lifestyle(conn, user_id)
    nutrition_totals = _load_nutrition_totals(conn, user_id)
    learning_rows = _load_learning_sessions(conn, user_id)

    # Every workspace can be the only thing logged on a day - a night's sleep
    # with no checklist, a meal with no workout - so the date set is the union of
    # all of them. Anything missing here would silently drop those days from the
    # series.
    all_dates = sorted(
        set(checklist_dates)
        | {row['date'] for row in training_sets}
        | {row['date'] for row in sleep_rows}
        | {row['date'] for row in lifestyle_rows}
        | {row['date'] for row in learning_rows}
        | set(nutrition_totals)
    )

    # Derived rows for dates that no longer have ANY source data must go, or
    # deleting a workout leaves its scores behind - still crediting training that
    # does not exist. The early-return-on-empty version of this function had
    # exactly that bug: wiping every session left Strength sitting at 100.
    _prune_orphaned_scores(conn, user_id, all_dates, from_date)
    if not all_dates:
        return 0

    targets = _targets_by_date(conn, user_id, all_dates)
    sleep_targets = {iso: t.get('sleep_minutes') for iso, t in targets.items()}
    step_targets = {iso: t.get('steps') for iso, t in targets.items()}
    study_targets = {iso: t.get('weekly_study_minutes') for iso, t in targets.items()}
    training_days = {iso: t.get('training_days_per_week') for iso, t in targets.items()}

    # Five measured producers now, and several of them speak to the same
    # attribute: sleep consistency and adherence both feed Discipline, steps and
    # cardio both feed Stamina. merge_measured averages by weight where they
    # overlap - a plain dict update would have let whichever ran last silently
    # win.
    measured = producers.merge_measured(
        producers.training_ratios(training_sets, all_dates, training_days, config),
        producers.sleep_ratios(sleep_rows, all_dates, sleep_targets, config),
        producers.steps_ratios(lifestyle_rows, all_dates, step_targets, config),
        producers.adherence_ratios(lifestyle_rows, nutrition_totals, targets, config),
        producers.learning_ratios(learning_rows, all_dates, study_targets, config),
    )

    # One blended ratio per attribute per day. Where a day has both a ticked box
    # and logged sets for the same attribute, the measured signal dominates but
    # the self-report is not discarded - see producers.blend.
    checklist_by_date = {day: ratios for day, ratios, _ in history}
    completion_by_date = {day: pct for day, _, pct in history}
    blended = {}
    for day in all_dates:
        reported = checklist_by_date.get(day, {})
        observed = measured.get(day, {})
        blended[day] = {
            attribute: producers.blend(attribute, reported.get(attribute), observed.get(attribute), config)
            for attribute in set(reported) | set(observed)
        }

    recomputed = 0
    for index, date in enumerate(all_dates):
        if from_date and date < from_date:
            continue

        completion_pct = completion_by_date.get(date, 0)
        window_dates = all_dates[: index + 1]
        # Consistency measures showing up for the daily log specifically, so it
        # counts checklist days only - a workout is not a substitute for logging.
        log_dates = [day for day in window_dates if day in checklist_by_date]

        results = {}
        for attribute in ATTRIBUTES:
            if attribute == 'Consistency':
                # Showing up is not a checklist item, so it has its own producer.
                ratios = consistency_from_log_dates(
                    log_dates, config.full_confidence_days, date, config
                )
            else:
                ratios = [
                    blended[day][attribute]
                    for day in window_dates
                    if blended[day].get(attribute) is not None
                ]
            results[attribute] = aggregate_attribute(attribute, ratios, config)

        for attribute, result in results.items():
            # That day's own observed ratio, distinct from the rolling score.
            raw_value = blended[date].get(attribute)
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
    """Recent daily/discipline scores, oldest first.

    `daily_score` is None on any day the checklist was not submitted, and
    `logged` says which days those were.

    The table itself stores 0 for them, and a stored 0 cannot be told apart from
    a day where every answer was No - the column holds 0 either way. `daily_log`
    can tell them apart, because a row exists there only for a day that was
    actually submitted, so the score is read through that join.

    Without this, Home's trend drew a flat line along the bottom for every day
    someone had not logged, which reads as "you scored nothing" rather than "you
    did not log" - and those are opposite claims. Same reasoning, and the same
    join, as the analytics endpoint's daily_score metric; see docs/ANALYTICS.md.

    `discipline_score` needs no such treatment: it comes from workspace activity
    rather than the checklist, and is already NULL when unobserved.
    """
    rows = conn.execute(
        'SELECT daily_scores.date              AS date, '
        '       daily_scores.daily_score       AS daily_score, '
        '       daily_scores.discipline_score  AS discipline_score, '
        '       daily_scores.completion_pct    AS completion_pct, '
        '       daily_log.id                   AS log_id '
        'FROM daily_scores '
        'LEFT JOIN daily_log ON daily_log.user_id = daily_scores.user_id '
        '                   AND daily_log.date = daily_scores.date '
        'WHERE daily_scores.user_id = ? '
        'ORDER BY daily_scores.date DESC LIMIT ?',
        (user_id, limit),
    ).fetchall()
    return [
        {
            'date': row['date'],
            'daily_score': row['daily_score'] if row['log_id'] is not None else None,
            'discipline_score': row['discipline_score'],
            'completion_pct': row['completion_pct'],
            'logged': row['log_id'] is not None,
        }
        for row in reversed(rows)
    ]
