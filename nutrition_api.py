"""Nutrition and Lifestyle workspace endpoints.

Its own blueprint for the same reasons training_api.py is one: app.py is already
~1,960 lines, and the auth decorator and database helper are injected at
registration rather than imported, so this module never imports app. The test
suite swaps modules per test, and importing app here would bind to whichever copy
happened to load first.
"""
from datetime import date as _date

from flask import Blueprint, jsonify, request, session

import scoring
from scoring import nutrition as nut

nutrition_bp = Blueprint('nutrition', __name__)

_get_db = None
_login_required = None
_recompute = None


def init_nutrition(app, get_db_connection, login_required, recompute):
    global _get_db, _login_required, _recompute
    _get_db = get_db_connection
    _login_required = login_required
    _recompute = recompute
    app.register_blueprint(nutrition_bp)


def _auth(view):
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _slugify(name, prefix=''):
    cleaned = ''.join(c.lower() if c.isalnum() else '-' for c in (name or '').strip())
    while '--' in cleaned:
        cleaned = cleaned.replace('--', '-')
    return f'{prefix}{cleaned.strip("-") or "item"}'


def _food_row(row):
    return {
        'id': row['id'],
        'slug': row['slug'],
        'name': row['name'],
        'category': row['category'],
        'source': row['source'],
        'kcal_per_100g': row['kcal_per_100g'],
        'protein_per_100g': row['protein_per_100g'],
        'carbs_per_100g': row['carbs_per_100g'],
        'fat_per_100g': row['fat_per_100g'],
        'fibre_per_100g': row['fibre_per_100g'],
        'serving_name': row['serving_name'],
        'serving_grams': row['serving_grams'],
        'is_custom': row['user_id'] is not None,
    }


def _profile_and_targets(conn, user_id, on_date):
    """The profile plus the targets that apply on a date.

    Body weight comes from `body_measurements`, which R3 already fills - a second
    copy on the profile would drift from the first.
    """
    row = conn.execute('SELECT * FROM user_profile WHERE user_id = ?',
                       (user_id,)).fetchone()
    profile = dict(row) if row else {}

    weight_row = conn.execute(
        "SELECT value FROM body_measurements WHERE user_id = ? AND metric = 'weight' "
        'AND date <= ? ORDER BY date DESC LIMIT 1',
        (user_id, on_date),
    ).fetchone()
    if weight_row is None:
        weight_row = conn.execute(
            "SELECT value FROM body_measurements WHERE user_id = ? AND metric = 'weight' "
            'ORDER BY date LIMIT 1', (user_id,),
        ).fetchone()

    weight = weight_row['value'] if weight_row else None
    targets = nut.resolve_targets(profile, weight, _date.fromisoformat(on_date))
    return profile, targets, weight


# --- foods ------------------------------------------------------------------

@nutrition_bp.route('/api/foods')
@_auth
def list_foods():
    """The library plus this user's own foods and recipes.

    Filtering happens here rather than in the client so a search is one indexed
    query instead of shipping 233 rows and refiltering them on every keystroke.
    """
    user_id = session.get('user_id')
    conn = _get_db()

    clauses = ['(user_id IS NULL OR user_id = ?)', 'archived = 0']
    params = [user_id]

    category = request.args.get('category')
    if category:
        clauses.append('category = ?')
        params.append(category)

    source = request.args.get('source')
    if source:
        clauses.append('source = ?')
        params.append(source)

    search = (request.args.get('q') or '').strip()
    if search:
        clauses.append('name LIKE ?')
        params.append(f'%{search}%')

    params.append(min(int(request.args.get('limit', 300)), 500))
    rows = conn.execute(
        f"SELECT * FROM foods WHERE {' AND '.join(clauses)} "
        'ORDER BY (user_id IS NULL), name LIMIT ?',
        params,
    ).fetchall()
    conn.close()
    return jsonify({'foods': [_food_row(row) for row in rows]})


@nutrition_bp.route('/api/foods', methods=['POST'])
@_auth
def create_food():
    """A custom food - something the shipped library does not carry."""
    user_id = session.get('user_id')
    data = request.json or {}
    name = (data.get('name') or '').strip()
    if not name or data.get('kcal_per_100g') is None:
        return jsonify({'error': 'name and kcal_per_100g are required'}), 400

    conn = _get_db()
    slug = _slugify(name, 'custom-')
    # A user may legitimately want two foods with similar names; disambiguate
    # rather than refuse.
    existing = {r['slug'] for r in conn.execute(
        'SELECT slug FROM foods WHERE user_id = ?', (user_id,))}
    candidate, suffix = slug, 2
    while candidate in existing:
        candidate, suffix = f'{slug}-{suffix}', suffix + 1

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO foods (user_id, slug, source, name, category, kcal_per_100g, "
        'protein_per_100g, carbs_per_100g, fat_per_100g, fibre_per_100g, '
        "serving_name, serving_grams) VALUES (?, ?, 'custom', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, candidate, name, data.get('category', 'prepared'),
         float(data['kcal_per_100g']), float(data.get('protein_per_100g') or 0),
         float(data.get('carbs_per_100g') or 0), float(data.get('fat_per_100g') or 0),
         float(data.get('fibre_per_100g') or 0), data.get('serving_name'),
         data.get('serving_grams')),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM foods WHERE id = ?', (cursor.lastrowid,)).fetchone()
    payload = _food_row(row)
    conn.close()
    return jsonify(payload), 201


# --- recipes ----------------------------------------------------------------

def _recipe_payload(conn, row):
    ingredients = conn.execute(
        '''
        SELECT ri.id, ri.food_id, ri.grams, ri.position, f.name, f.category,
               f.kcal_per_100g, f.protein_per_100g, f.carbs_per_100g,
               f.fat_per_100g, f.fibre_per_100g
        FROM recipe_ingredients ri
        JOIN foods f ON f.id = ri.food_id
        WHERE ri.recipe_id = ? ORDER BY ri.position
        ''',
        (row['id'],),
    ).fetchall()
    food = conn.execute('SELECT * FROM foods WHERE id = ?', (row['food_id'],)).fetchone()

    return {
        'id': row['id'],
        'food_id': row['food_id'],
        'name': row['name'],
        'servings': row['servings'],
        'total_grams': row['total_grams'],
        'notes': row['notes'],
        'ingredients': [dict(i) for i in ingredients],
        'food': _food_row(food) if food else None,
    }


def _write_recipe_food(conn, food_id, name, ingredients, total_grams):
    """Recompute the `foods` row a recipe produces.

    The recipe's macros are always derived, never typed - so correcting an
    ingredient corrects every dish that uses it.
    """
    per_100g = nut.recipe_per_100g(ingredients, total_grams)
    if per_100g is None:
        return None

    conn.execute(
        'UPDATE foods SET name = ?, kcal_per_100g = ?, protein_per_100g = ?, '
        'carbs_per_100g = ?, fat_per_100g = ?, fibre_per_100g = ?, '
        'serving_name = ?, serving_grams = ? WHERE id = ?',
        (name, per_100g['kcal_per_100g'], per_100g['protein_per_100g'],
         per_100g['carbs_per_100g'], per_100g['fat_per_100g'],
         per_100g['fibre_per_100g'], '1 serving', per_100g['total_grams'], food_id),
    )
    return per_100g


def _load_ingredients(conn, entries):
    """Attach per-100g values to the {food_id, grams} pairs a client sends."""
    resolved = []
    for entry in entries or []:
        food_id = entry.get('food_id')
        grams = entry.get('grams')
        if not food_id or not grams:
            continue
        food = conn.execute('SELECT * FROM foods WHERE id = ?', (food_id,)).fetchone()
        if food is None:
            continue
        resolved.append({
            'food_id': food_id,
            'grams': float(grams),
            'kcal_per_100g': food['kcal_per_100g'],
            'protein_per_100g': food['protein_per_100g'],
            'carbs_per_100g': food['carbs_per_100g'],
            'fat_per_100g': food['fat_per_100g'],
            'fibre_per_100g': food['fibre_per_100g'],
        })
    return resolved


@nutrition_bp.route('/api/recipes', methods=['GET', 'POST'])
@_auth
def recipes():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'POST':
        data = request.json or {}
        name = (data.get('name') or '').strip()
        if not name:
            conn.close()
            return jsonify({'error': 'name is required'}), 400

        ingredients = _load_ingredients(conn, data.get('ingredients'))
        if not ingredients:
            conn.close()
            return jsonify({'error': 'a recipe needs at least one ingredient'}), 400

        slug = _slugify(name, 'recipe-')
        existing = {r['slug'] for r in conn.execute(
            'SELECT slug FROM foods WHERE user_id = ?', (user_id,))}
        candidate, suffix = slug, 2
        while candidate in existing:
            candidate, suffix = f'{slug}-{suffix}', suffix + 1

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO foods (user_id, slug, source, name, category, kcal_per_100g) "
            "VALUES (?, ?, 'recipe', ?, 'prepared', 0)",
            (user_id, candidate, name),
        )
        food_id = cursor.lastrowid

        total_grams = data.get('total_grams')
        _write_recipe_food(conn, food_id, name, ingredients, total_grams)

        cursor.execute(
            'INSERT INTO recipes (user_id, food_id, name, servings, total_grams, notes) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, food_id, name, float(data.get('servings') or 1),
             total_grams, data.get('notes')),
        )
        recipe_id = cursor.lastrowid
        for position, ingredient in enumerate(ingredients):
            conn.execute(
                'INSERT INTO recipe_ingredients (recipe_id, food_id, grams, position) '
                'VALUES (?, ?, ?, ?)',
                (recipe_id, ingredient['food_id'], ingredient['grams'], position),
            )
        conn.commit()

        row = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
        payload = _recipe_payload(conn, row)
        conn.close()
        return jsonify(payload), 201

    rows = conn.execute(
        'SELECT * FROM recipes WHERE user_id = ? AND archived = 0 ORDER BY name',
        (user_id,),
    ).fetchall()
    payload = [_recipe_payload(conn, row) for row in rows]
    conn.close()
    return jsonify({'recipes': payload})


@nutrition_bp.route('/api/recipes/<int:recipe_id>', methods=['GET', 'PUT', 'DELETE'])
@_auth
def recipe_detail(recipe_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM recipes WHERE id = ? AND user_id = ?',
                       (recipe_id, user_id)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if request.method == 'DELETE':
        # Archived, not deleted: food_entries point at the food this recipe
        # produced, and removing it would rewrite past calorie totals.
        conn.execute('UPDATE recipes SET archived = 1 WHERE id = ?', (recipe_id,))
        conn.execute('UPDATE foods SET archived = 1 WHERE id = ?', (row['food_id'],))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    if request.method == 'PUT':
        data = request.json or {}
        name = (data.get('name') or row['name']).strip()
        total_grams = data.get('total_grams', row['total_grams'])

        if 'ingredients' in data:
            ingredients = _load_ingredients(conn, data['ingredients'])
            if not ingredients:
                conn.close()
                return jsonify({'error': 'a recipe needs at least one ingredient'}), 400
            conn.execute('DELETE FROM recipe_ingredients WHERE recipe_id = ?', (recipe_id,))
            for position, ingredient in enumerate(ingredients):
                conn.execute(
                    'INSERT INTO recipe_ingredients (recipe_id, food_id, grams, position) '
                    'VALUES (?, ?, ?, ?)',
                    (recipe_id, ingredient['food_id'], ingredient['grams'], position),
                )
        else:
            ingredients = _load_ingredients(conn, [
                {'food_id': r['food_id'], 'grams': r['grams']}
                for r in conn.execute(
                    'SELECT food_id, grams FROM recipe_ingredients WHERE recipe_id = ? '
                    'ORDER BY position', (recipe_id,))
            ])

        _write_recipe_food(conn, row['food_id'], name, ingredients, total_grams)
        conn.execute(
            'UPDATE recipes SET name = ?, servings = ?, total_grams = ?, notes = ? '
            'WHERE id = ?',
            (name, float(data.get('servings') or row['servings']), total_grams,
             data.get('notes', row['notes']), recipe_id),
        )
        conn.commit()

        # Editing a recipe changes the macros of every meal already logged with
        # it, so the scores derived from those meals have to move too.
        # No date: editing a recipe changes the macros of every meal ever
        # logged with it, so every day has to be rebuilt.
        _recompute(conn, user_id)
        conn.commit()

        row = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()

    payload = _recipe_payload(conn, row)
    conn.close()
    return jsonify(payload)


# --- the daily food log -----------------------------------------------------

def _entries_for(conn, user_id, day):
    rows = conn.execute(
        '''
        SELECT e.id, e.meal, e.grams, e.position, e.food_id,
               f.name, f.category, f.source, f.serving_name, f.serving_grams,
               f.kcal_per_100g, f.protein_per_100g, f.carbs_per_100g,
               f.fat_per_100g, f.fibre_per_100g
        FROM food_entries e
        JOIN foods f ON f.id = e.food_id
        WHERE e.user_id = ? AND e.date = ?
        ORDER BY e.position, e.id
        ''',
        (user_id, day),
    ).fetchall()

    entries = []
    for row in rows:
        entry = dict(row)
        entry['macros'] = {
            key: round(value, 1)
            for key, value in nut.entry_macros(entry, entry['grams']).items()
        }
        entries.append(entry)
    return entries


@nutrition_bp.route('/api/nutrition/<date>')
@_auth
def nutrition_day(date):
    """One day's meals, totals and targets - everything the page needs at once."""
    user_id = session.get('user_id')
    conn = _get_db()

    entries = _entries_for(conn, user_id, date)
    totals = nut.total_macros([
        {**entry, 'grams': entry['grams']} for entry in entries
    ])
    _, targets, weight = _profile_and_targets(conn, user_id, date)

    by_meal = {}
    for entry in entries:
        by_meal.setdefault(entry['meal'], []).append(entry)

    conn.close()
    return jsonify({
        'date': date,
        'entries': entries,
        'by_meal': by_meal,
        'totals': {key: round(value, 1) for key, value in totals.items()},
        'targets': targets,
        'body_weight_kg': weight,
    })


@nutrition_bp.route('/api/nutrition/<date>/entries', methods=['POST'])
@_auth
def add_entry(date):
    user_id = session.get('user_id')
    data = request.json or {}
    food_id = data.get('food_id')
    grams = data.get('grams')
    if not food_id or not grams:
        return jsonify({'error': 'food_id and grams are required'}), 400

    conn = _get_db()
    food = conn.execute(
        'SELECT id FROM foods WHERE id = ? AND (user_id IS NULL OR user_id = ?)',
        (food_id, user_id),
    ).fetchone()
    if food is None:
        conn.close()
        return jsonify({'error': 'unknown food'}), 404

    position = conn.execute(
        'SELECT COALESCE(MAX(position), -1) + 1 AS p FROM food_entries '
        'WHERE user_id = ? AND date = ?', (user_id, date),
    ).fetchone()['p']

    conn.execute(
        'INSERT INTO food_entries (user_id, date, meal, food_id, grams, position) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (user_id, date, data.get('meal', 'snack'), food_id, float(grams), position),
    )
    conn.commit()
    _recompute(conn, user_id, date)
    conn.commit()
    conn.close()
    return jsonify({'success': True}), 201


@nutrition_bp.route('/api/nutrition/entries/<int:entry_id>', methods=['PUT', 'DELETE'])
@_auth
def entry_detail(entry_id):
    user_id = session.get('user_id')
    conn = _get_db()

    row = conn.execute('SELECT * FROM food_entries WHERE id = ? AND user_id = ?',
                       (entry_id, user_id)).fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    if request.method == 'DELETE':
        conn.execute('DELETE FROM food_entries WHERE id = ?', (entry_id,))
    else:
        data = request.json or {}
        conn.execute(
            'UPDATE food_entries SET grams = ?, meal = ? WHERE id = ?',
            (float(data.get('grams') or row['grams']), data.get('meal', row['meal']),
             entry_id),
        )

    conn.commit()
    _recompute(conn, user_id, row['date'])
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# --- sleep and lifestyle ----------------------------------------------------

def _duration_from_clock(bedtime, wake_time):
    """Minutes between two HH:MM times, assuming the night crosses midnight once.

    Returning None rather than a negative number when the input is unparseable
    keeps a malformed entry out of the score entirely.
    """
    from scoring.producers import _minutes_since_midnight

    start = _minutes_since_midnight(bedtime)
    end = _minutes_since_midnight(wake_time)
    if start is None or end is None:
        return None
    return (end - start) % 1440 or None


@nutrition_bp.route('/api/sleep', methods=['GET', 'POST'])
@_auth
def sleep():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'POST':
        data = request.json or {}
        day = (data.get('date') or '').strip()
        if not day:
            conn.close()
            return jsonify({'error': 'date is required'}), 400

        duration = data.get('duration_minutes')
        if duration is None:
            duration = _duration_from_clock(data.get('bedtime'), data.get('wake_time'))
        if not duration:
            conn.close()
            return jsonify({
                'error': 'duration_minutes, or a bedtime and wake_time, are required',
            }), 400

        conn.execute(
            'INSERT INTO sleep_entries (user_id, date, bedtime, wake_time, '
            'duration_minutes, quality, notes) VALUES (?, ?, ?, ?, ?, ?, ?) '
            'ON CONFLICT(user_id, date) DO UPDATE SET '
            'bedtime = excluded.bedtime, wake_time = excluded.wake_time, '
            'duration_minutes = excluded.duration_minutes, '
            'quality = excluded.quality, notes = excluded.notes',
            (user_id, day, data.get('bedtime'), data.get('wake_time'),
             int(duration), data.get('quality'), data.get('notes')),
        )
        conn.commit()
        _recompute(conn, user_id, day)
        conn.commit()
        conn.close()
        return jsonify({'success': True}), 201

    limit = min(int(request.args.get('limit', 30)), 180)
    rows = conn.execute(
        'SELECT * FROM sleep_entries WHERE user_id = ? ORDER BY date DESC LIMIT ?',
        (user_id, limit),
    ).fetchall()
    conn.close()
    return jsonify({'sleep': [dict(row) for row in reversed(rows)]})


@nutrition_bp.route('/api/lifestyle/<date>', methods=['GET', 'PUT'])
@_auth
def lifestyle_day(date):
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'PUT':
        data = request.json or {}
        fields = ('water_ml', 'steps', 'sunlight_minutes', 'mood', 'stress',
                  'energy', 'journal')
        current = conn.execute(
            'SELECT * FROM lifestyle_days WHERE user_id = ? AND date = ?',
            (user_id, date),
        ).fetchone()
        merged = {f: (data[f] if f in data else (current[f] if current else None))
                  for f in fields}

        conn.execute(
            'INSERT INTO lifestyle_days (user_id, date, water_ml, steps, '
            'sunlight_minutes, mood, stress, energy, journal) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) '
            'ON CONFLICT(user_id, date) DO UPDATE SET '
            'water_ml = excluded.water_ml, steps = excluded.steps, '
            'sunlight_minutes = excluded.sunlight_minutes, mood = excluded.mood, '
            'stress = excluded.stress, energy = excluded.energy, '
            'journal = excluded.journal',
            (user_id, date, merged['water_ml'], merged['steps'],
             merged['sunlight_minutes'], merged['mood'], merged['stress'],
             merged['energy'], merged['journal']),
        )
        conn.commit()
        _recompute(conn, user_id, date)
        conn.commit()

    row = conn.execute(
        'SELECT * FROM lifestyle_days WHERE user_id = ? AND date = ?',
        (user_id, date),
    ).fetchone()
    sleep_row = conn.execute(
        'SELECT * FROM sleep_entries WHERE user_id = ? AND date = ?',
        (user_id, date),
    ).fetchone()
    _, targets, _ = _profile_and_targets(conn, user_id, date)
    conn.close()

    return jsonify({
        'date': date,
        'lifestyle': dict(row) if row else None,
        'sleep': dict(sleep_row) if sleep_row else None,
        'targets': targets,
    })


@nutrition_bp.route('/api/lifestyle')
@_auth
def lifestyle_summary():
    """The Lifestyle dashboard: recent sleep, water, steps and mood, plus targets."""
    user_id = session.get('user_id')
    conn = _get_db()
    limit = min(int(request.args.get('days', 30)), 180)

    lifestyle = conn.execute(
        'SELECT * FROM lifestyle_days WHERE user_id = ? ORDER BY date DESC LIMIT ?',
        (user_id, limit),
    ).fetchall()
    sleep_rows = conn.execute(
        'SELECT * FROM sleep_entries WHERE user_id = ? ORDER BY date DESC LIMIT ?',
        (user_id, limit),
    ).fetchall()

    today = _date.today().isoformat()
    _, targets, _ = _profile_and_targets(conn, user_id, today)

    nights = [dict(row) for row in reversed(sleep_rows)]
    durations = [n['duration_minutes'] for n in nights if n['duration_minutes']]

    # Consistency is reported as the same number the scorer uses, not a second
    # definition of it - two ways to compute "how regular is your sleep" would
    # eventually disagree.
    consistency = None
    if nights:
        computed = scoring.producers.sleep_ratios(
            nights, [nights[-1]['date']],
            {nights[-1]['date']: targets.get('sleep_minutes')},
        )
        entry = computed.get(nights[-1]['date'], {}).get('Discipline')
        consistency = round(entry[0] * 100) if entry else None

    conn.close()
    return jsonify({
        'sleep': nights,
        'lifestyle': [dict(row) for row in reversed(lifestyle)],
        'targets': targets,
        'averages': {
            'sleep_minutes': round(sum(durations) / len(durations)) if durations else None,
            'schedule_consistency': consistency,
            'water_ml': _mean([r['water_ml'] for r in lifestyle]),
            'steps': _mean([r['steps'] for r in lifestyle]),
        },
    })


def _mean(values):
    present = [v for v in values if v]
    return round(sum(present) / len(present)) if present else None


# --- profile ----------------------------------------------------------------

@nutrition_bp.route('/api/profile', methods=['GET', 'PUT'])
@_auth
def profile():
    user_id = session.get('user_id')
    conn = _get_db()

    if request.method == 'PUT':
        data = request.json or {}
        fields = ('birth_year', 'sex', 'height_cm', 'activity_level', 'goal',
                  'calorie_target', 'protein_target_g', 'carb_target_g',
                  'fat_target_g', 'fibre_target_g', 'water_target_ml',
                  'step_target', 'sleep_target_minutes')
        current = conn.execute('SELECT * FROM user_profile WHERE user_id = ?',
                               (user_id,)).fetchone()
        merged = {f: (data[f] if f in data else (current[f] if current else None))
                  for f in fields}

        # activity_level and goal are NOT NULL with schema defaults, so a partial
        # PUT that omits them - "just set my calorie target" - would otherwise
        # fail against a profile row that does not exist yet.
        merged['activity_level'] = merged['activity_level'] or 'moderate'
        merged['goal'] = merged['goal'] or 'maintain'

        assignments = ', '.join(f'{f} = excluded.{f}' for f in fields)
        conn.execute(
            f"INSERT INTO user_profile (user_id, {', '.join(fields)}) "
            f"VALUES (?{', ?' * len(fields)}) "
            f'ON CONFLICT(user_id) DO UPDATE SET {assignments}, '
            'updated_at = CURRENT_TIMESTAMP',
            (user_id, *(merged[f] for f in fields)),
        )
        conn.commit()

        # Targets feed the adherence signal, so changing them rescores history.
        # No date: targets feed the "hit your calorie target" rules, so
        # changing them re-judges every day.
        _recompute(conn, user_id)
        conn.commit()

    today = _date.today().isoformat()
    stored, targets, weight = _profile_and_targets(conn, user_id, today)
    conn.close()

    return jsonify({
        'profile': stored,
        'targets': targets,
        'body_weight_kg': weight,
    })
