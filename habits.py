"""Habit storage - the SQL home of what used to be the Paths JSON files.

WHY THIS LOOKS LIKE A COMPATIBILITY LAYER
-----------------------------------------
Because it is one, deliberately. `load_paths()` returns byte-for-byte the same
payload `load_user_paths()` used to build from JSON:

    {'paths': [{'id', 'name', 'is_default', 'checklist_items': [...]}],
     'selected_path_id': ...}

Twelve call sites across app.py, the Jinja templates, static/js/app.js and the
SPA's Today page consume that shape. Changing the storage underneath without
changing the shape is what lets the daily checklist - the one feature that is
actually used every day - keep working while it moves into SQL.

The string ids are load-bearing. A path id ('batman-path') and an item id (a
uuid) are already referenced by daily_log.path_id, users.selected_path and every
client. They are carried across as `slug` rather than replaced by integers.

Every function takes an open connection rather than opening its own. Some callers
already hold one with uncommitted writes - score_checklist_day() in particular -
and a second connection writing to the same SQLite file would block on it.
"""
import json
from datetime import date as _date, timedelta as _timedelta

# Ordinal 'time' answers are graded, matching scoring/engine.py's ladder. A habit
# completion stores the same credit the scorer computed so adherence queries do
# not have to re-derive it.
TIME_BUCKET_CREDIT = (1.0, 0.8, 0.55, 0.3)

SCHEDULE_TYPES = ('daily', 'weekdays', 'days', 'times-per-week')


def _loads(value, fallback):
    try:
        parsed = json.loads(value) if value else fallback
    except (TypeError, ValueError):
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def habit_payload(row):
    """One habit as a checklist item, in the shape clients already expect."""
    item = {
        'id': row['slug'],
        'name': row['name'],
        'type': row['type'],
        'icon': row['icon'],
        'weight': row['weight'],
        # Whether this question is everyone's or just yours. The UI groups on it;
        # nothing in scoring cares.
        'is_core': bool(row['is_core']),
    }

    # The scoring resolver's tier 1. Only carried when the question states it -
    # an absent key leaves the icon and keyword tiers to do their job, which is
    # what every migrated Path item still relies on.
    attributes = _loads(row['attributes'], {})
    if attributes:
        item['attributes'] = attributes

    options = _loads(row['options'], [])
    if options:
        item['options'] = options

    sub_response = _loads(row['sub_response'], {})
    if sub_response:
        item['subResponse'] = sub_response

    # Schedule fields ride alongside rather than replacing anything, so an older
    # client that ignores them still behaves exactly as before.
    item['schedule'] = {
        'type': row['schedule_type'],
        'days': _loads(row['schedule_days'], []),
        'target_per_week': row['target_per_week'],
    }
    return item


def has_imported(conn, user_id):
    row = conn.execute('SELECT 1 FROM habit_imports WHERE user_id = ?',
                       (user_id,)).fetchone()
    return row is not None


# The single survey replaced four Paths, but three clients still speak the
# paths payload, so it survives as a compatibility view with exactly one entry.
SURVEY_ID = 'daily-survey'
SURVEY_NAME = 'Daily survey'


def load_survey(conn, user_id):
    """The questions this person is asked today: the shared core, then their own.

    Core questions have no owner (`user_id IS NULL`), so they come back for
    everyone. Personal extras belong to one account and sort after the core set,
    which is also how the UI groups them.

    Pass user_id=None for the core set alone - `user_id = NULL` is never true in
    SQL, so the personal half of the predicate simply matches nothing. That is
    what the admin editor and the tests want.
    """
    rows = conn.execute(
        'SELECT * FROM habits '
        'WHERE archived = 0 AND (is_core = 1 OR user_id = ?) '
        'ORDER BY is_core DESC, position, id',
        (user_id,),
    ).fetchall()
    return [habit_payload(row) for row in rows]


def load_paths(conn, user_id):
    """Compatibility view: the survey, wrapped in the shape Paths used to have.

    The Jinja app, static/js/app.js and the SPA's Today page all read
    `{paths: [...], selected_path_id}`. Rewriting three clients to drop a concept
    they only ever used to find "the list of questions" would be a lot of churn
    for no behaviour change, so they keep getting a list - of one.

    Returns None when there are no questions at all, which now only happens if
    the core set were deleted outright. Callers treat that as "seed something".
    """
    items = load_survey(conn, user_id)
    if not items:
        return None

    return {
        'paths': [{
            'id': SURVEY_ID,
            'name': SURVEY_NAME,
            'is_default': True,
            'checklist_items': items,
        }],
        'selected_path_id': SURVEY_ID,
    }


def save_paths(conn, user_id, payload):
    """Persist a full paths payload, reconciling against what is stored.

    Takes the whole payload rather than a diff because that is what every caller
    already has - they load, mutate the structure, and hand it back. Rows that
    disappear are ARCHIVED, never deleted: habit_completions point at them, and
    deleting a habit would silently rewrite the history of having done it.
    """
    paths = payload.get('paths') or []
    selected_slug = payload.get('selected_path_id')

    existing_groups = {
        row['slug']: row for row in conn.execute(
            'SELECT * FROM habit_groups WHERE user_id = ?', (user_id,))
    }

    live_group_ids = []
    for position, path in enumerate(paths):
        slug = str(path.get('id') or '').strip()
        if not slug:
            continue

        name = str(path.get('name') or 'Untitled Path').strip() or 'Untitled Path'
        is_default = 1 if path.get('is_default') else 0
        is_selected = 1 if slug == selected_slug else 0

        current = existing_groups.get(slug)
        if current is None:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO habit_groups (user_id, slug, name, is_default, '
                'is_selected, position) VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, slug, name, is_default, is_selected, position),
            )
            group_id = cursor.lastrowid
        else:
            group_id = current['id']
            conn.execute(
                'UPDATE habit_groups SET name = ?, is_default = ?, is_selected = ?, '
                'position = ?, archived = 0 WHERE id = ?',
                (name, is_default, is_selected, position, group_id),
            )

        live_group_ids.append(group_id)
        _save_habits(conn, user_id, group_id, path.get('checklist_items') or [])

    for slug, row in existing_groups.items():
        if row['id'] not in live_group_ids and not row['archived']:
            conn.execute('UPDATE habit_groups SET archived = 1, is_selected = 0 '
                         'WHERE id = ?', (row['id'],))
            conn.execute('UPDATE habits SET archived = 1 WHERE group_id = ?',
                         (row['id'],))

    return payload


def _save_habits(conn, user_id, group_id, items):
    existing = {
        row['slug']: row for row in conn.execute(
            'SELECT * FROM habits WHERE group_id = ?', (group_id,))
    }

    live_slugs = set()
    for position, item in enumerate(items):
        slug = str(item.get('id') or '').strip()
        if not slug:
            continue
        live_slugs.add(slug)

        schedule = item.get('schedule') or {}
        schedule_type = schedule.get('type') or 'daily'
        if schedule_type not in SCHEDULE_TYPES:
            schedule_type = 'daily'

        values = (
            str(item.get('name') or '').strip(),
            item.get('type') or 'yes-no',
            item.get('icon') or 'default',
            int(item.get('weight') or 1),
            json.dumps(item.get('options') or []),
            json.dumps(item.get('subResponse') or {}),
            schedule_type,
            json.dumps(schedule.get('days') or []),
            schedule.get('target_per_week'),
            position,
        )

        if slug in existing:
            conn.execute(
                'UPDATE habits SET name = ?, type = ?, icon = ?, weight = ?, '
                'options = ?, sub_response = ?, schedule_type = ?, '
                'schedule_days = ?, target_per_week = ?, position = ?, archived = 0 '
                'WHERE id = ?',
                (*values, existing[slug]['id']),
            )
        else:
            conn.execute(
                'INSERT INTO habits (user_id, group_id, slug, name, type, icon, '
                'weight, options, sub_response, schedule_type, schedule_days, '
                'target_per_week, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (user_id, group_id, slug, *values),
            )

    for slug, row in existing.items():
        if slug not in live_slugs and not row['archived']:
            conn.execute('UPDATE habits SET archived = 1 WHERE id = ?', (row['id'],))


def import_paths(conn, user_id, payload, source='artifacts/paths'):
    """One-time import of a user's JSON paths into SQL.

    Recorded in habit_imports so it runs exactly once per user. Without that
    marker a later edit that removed a path would be undone on the next load by
    re-importing the original file.
    """
    if has_imported(conn, user_id):
        return {'groups': 0, 'habits': 0, 'completions': 0}

    save_paths(conn, user_id, payload)

    groups = conn.execute('SELECT COUNT(*) AS n FROM habit_groups WHERE user_id = ?',
                          (user_id,)).fetchone()['n']
    habits = conn.execute('SELECT COUNT(*) AS n FROM habits WHERE user_id = ?',
                          (user_id,)).fetchone()['n']

    conn.execute(
        'INSERT INTO habit_imports (user_id, source, groups_imported, habits_imported) '
        'VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO NOTHING',
        (user_id, source, groups, habits),
    )

    completions = backfill_completions(conn, user_id)
    conn.execute('UPDATE habit_imports SET completions_backfilled = ? WHERE user_id = ?',
                 (completions, user_id))

    return {'groups': groups, 'habits': habits, 'completions': completions}


def backfill_completions(conn, user_id):
    """Rebuild habit_completions from the daily_log snapshots.

    Matched by NAME, because that is the only key the snapshots carry - they
    record items as they were rendered, not the ids behind them. A habit renamed
    before this runs will not match its own history, which is why the import
    happens on first load rather than being deferred.

    daily_log is left untouched. It remains the authority for scoring; this is a
    queryable index built from it.
    """
    rows = conn.execute(
        'SELECT date, payload_json FROM daily_log WHERE user_id = ? ORDER BY date',
        (user_id,),
    ).fetchall()
    if not rows:
        return 0

    # Core questions and this person's own, plus the archived Path items - past
    # snapshots name questions that are no longer asked, and their history is
    # exactly what this rebuilds.
    habits_by_name = {}
    for habit in conn.execute(
        'SELECT id, name FROM habits WHERE is_core = 1 OR user_id = ? '
        'ORDER BY archived, is_core DESC, position, id',
        (user_id,),
    ):
        habits_by_name.setdefault(habit['name'], habit['id'])

    written = 0
    for row in rows:
        payload = _loads(row['payload_json'], {})
        for item in payload.get('items') or []:
            habit_id = habits_by_name.get(item.get('name'))
            if habit_id is None:
                continue
            conn.execute(
                'INSERT INTO habit_completions (user_id, habit_id, date, response, credit) '
                'VALUES (?, ?, ?, ?, ?) '
                'ON CONFLICT(user_id, habit_id, date) DO UPDATE SET '
                'response = excluded.response, credit = excluded.credit',
                (user_id, habit_id, row['date'], item.get('response'),
                 float(item.get('credit') or 0)),
            )
            written += 1

    return written


def record_completions(conn, user_id, date, scored_items):
    """Write one day's answers as per-habit rows.

    Called from the same save that writes daily_log, so the two cannot drift.
    `scored_items` is scoring.engine.score_day()'s item list: name, response and
    the graded credit it already computed.
    """
    # Core questions have no owner, so the old `user_id = ?` filter found none of
    # them and the shared survey recorded nothing at all.
    habits_by_name = {}
    for habit in conn.execute(
        'SELECT id, name FROM habits '
        'WHERE archived = 0 AND (is_core = 1 OR user_id = ?) '
        'ORDER BY is_core DESC, position, id',
        (user_id,),
    ):
        habits_by_name.setdefault(habit['name'], habit['id'])

    written = 0
    for item in scored_items or []:
        habit_id = habits_by_name.get(item.get('name'))
        if habit_id is None:
            continue
        conn.execute(
            'INSERT INTO habit_completions (user_id, habit_id, date, response, credit) '
            'VALUES (?, ?, ?, ?, ?) '
            # (user_id, habit_id, date) since 012. A shared question answered by
            # five people on one day is five rows, not one contested slot.
            'ON CONFLICT(user_id, habit_id, date) DO UPDATE SET '
            'response = excluded.response, credit = excluded.credit',
            (user_id, habit_id, date, item.get('response'),
             float(item.get('credit') or 0)),
        )
        written += 1
    return written


# --- schedules --------------------------------------------------------------

def is_due(habit, on_date):
    """Is this habit expected today?

    `times-per-week` always returns True: it has no particular day, so the
    question "is it due today" has no honest answer beyond "you could do it
    today". Whether you are behind on it is a weekly question - see
    weekly_progress() - and answering it here would make Today's list flicker
    depending on the order you happened to complete things in.
    """
    schedule_type = habit.get('schedule_type') or habit.get('type') or 'daily'
    if schedule_type == 'daily':
        return True
    if schedule_type == 'weekdays':
        return on_date.weekday() < 5
    if schedule_type == 'days':
        days = habit.get('schedule_days')
        if isinstance(days, str):
            days = _loads(days, [])
        return on_date.weekday() in (days or [])
    return True


def due_habits(conn, user_id, on_date, group_slug=None):
    """The habits expected on a date, with this user's answer if there is one.

    `group_slug` is vestigial and ignored - it selected a Path, and there is one
    survey now. Kept so existing callers do not need changing.
    """
    query = (
        'SELECT h.*, c.response AS response, c.credit AS credit '
        'FROM habits h '
        # c.user_id is load-bearing: a core question is one row shared by
        # everyone, so an unfiltered join would show you someone else's answer.
        'LEFT JOIN habit_completions c '
        '       ON c.habit_id = h.id AND c.user_id = ? AND c.date = ? '
        'WHERE h.archived = 0 AND (h.is_core = 1 OR h.user_id = ?) '
        'ORDER BY h.is_core DESC, h.position, h.id'
    )
    params = [user_id, on_date.isoformat(), user_id]

    out = []
    for row in conn.execute(query, params):
        habit = dict(row)
        if not is_due(habit, on_date):
            continue
        habit['options'] = _loads(row['options'], [])
        habit['schedule_days'] = _loads(row['schedule_days'], [])
        out.append(habit)
    return out


def weekly_progress(conn, user_id, on_date):
    """For `times-per-week` habits: how many days this week they were done.

    The week runs Monday to the given date, not a rolling seven days, because a
    weekly target is a thing you either hit by Sunday or did not.
    """
    week_start = (on_date - _timedelta(days=on_date.weekday())).isoformat()
    rows = conn.execute(
        '''
        SELECT h.id, h.name, h.target_per_week,
               COUNT(c.id) AS done
        FROM habits h
        LEFT JOIN habit_completions c
               ON c.habit_id = h.id AND c.user_id = ?
              AND c.date >= ? AND c.date <= ? AND c.credit > 0
        WHERE h.archived = 0 AND (h.is_core = 1 OR h.user_id = ?)
          AND h.schedule_type = 'times-per-week'
        GROUP BY h.id
        ''',
        (user_id, week_start, on_date.isoformat(), user_id),
    ).fetchall()
    return [dict(row) for row in rows]


# --- stats ------------------------------------------------------------------

def habit_stats(conn, user_id, days=30, on_date=None, only_selected=True):
    """Per-habit adherence and current streak.

    This is the thing the JSON files could not answer at all, and the reason the
    conversion was worth doing.

    `only_selected` is vestigial and ignored. It existed because the four stock
    Paths shared most of their items, so the unscoped list repeated "What time
    did you wake up?" once per path. One shared survey has nothing to scope to,
    and the parameter is kept only so existing callers do not need changing.
    """
    today = on_date or _date.today()
    since = (today - _timedelta(days=days - 1)).isoformat()

    query = '''
        SELECT h.id, h.slug, h.name, h.icon, h.weight, h.is_core,
               h.schedule_type, h.schedule_days, h.target_per_week,
               COUNT(c.id) AS logged,
               SUM(CASE WHEN c.credit > 0 THEN 1 ELSE 0 END) AS done,
               AVG(c.credit) AS avg_credit
        FROM habits h
        -- The user filter on the JOIN is load-bearing now. A core question is
        -- one row shared by everyone, so without it this would count all five
        -- accounts' answers as one person's adherence.
        LEFT JOIN habit_completions c
               ON c.habit_id = h.id AND c.user_id = ? AND c.date >= ?
        WHERE h.archived = 0 AND (h.is_core = 1 OR h.user_id = ?)
        GROUP BY h.id ORDER BY h.is_core DESC, h.position, h.id
    '''

    rows = conn.execute(query, (user_id, since, user_id)).fetchall()

    out = []
    for row in rows:
        entry = dict(row)
        entry['schedule_days'] = _loads(row['schedule_days'], [])
        entry['avg_credit'] = round(row['avg_credit'], 3) if row['avg_credit'] else 0.0
        entry['streak'] = _habit_streak(conn, user_id, row['id'], today)
        out.append(entry)
    return out


def _habit_streak(conn, user_id, habit_id, today):
    """Consecutive days completed by this user, ending today or yesterday.

    Takes user_id because a core question is a single row answered by everyone -
    without it, one person logging would extend everybody's streak.

    Two different states have to be told apart, and conflating them is the easy
    mistake:

      nothing logged today  - you have not got to it yet. At 09:00 that is the
                              normal state, and a counter that reset overnight
                              would report a lost streak every single morning,
                              so yesterday is allowed to carry the streak.
      logged today as 'No'  - you answered, and the answer was that you did not
                              do it. That is a miss, and it breaks the streak
                              today rather than being treated as "not yet".
    """
    rows = {
        row['date']: row['credit'] for row in conn.execute(
            'SELECT date, credit FROM habit_completions '
            'WHERE habit_id = ? AND user_id = ?',
            (habit_id, user_id),
        )
    }
    done = {day for day, credit in rows.items() if credit > 0}
    if not done:
        return 0

    iso_today = today.isoformat()
    if iso_today in rows and rows[iso_today] <= 0:
        return 0  # answered today, and the answer was no

    cursor = today if iso_today in done else today - _timedelta(days=1)
    if cursor.isoformat() not in done:
        return 0

    count = 0
    while cursor.isoformat() in done:
        count += 1
        cursor -= _timedelta(days=1)
    return count
